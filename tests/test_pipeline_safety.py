"""Exercise pipeline orchestration without databases, APIs or notifications."""

import importlib
import traceback
from types import SimpleNamespace
from unittest.mock import Mock

import psycopg
import pytest
import requests

import notifier


SENSITIVE_DETAIL = "synthetic-private-token-and-candidate-details"
FAILED_STEP_STATS = [
    ("filter", "errors"),
    ("filter", "ai_errors"),
    ("filter", "skipped"),
    ("scorer", "errors"),
    ("scorer", "skipped"),
]


def filter_stats() -> dict:
    return {
        "total": 1,
        "auto_passed": 1,
        "fallback_passed": 0,
        "ai_passed": 0,
        "ai_rejected": 0,
        "rejected": 0,
        "errors": 0,
        "ai_errors": 0,
        "skipped": 0,
    }


def scorer_stats() -> dict:
    return {"total": 1, "scored": 1, "errors": 0, "skipped": 0}


@pytest.fixture(autouse=True)
def isolated_services(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://synthetic.invalid/job_bot")
    monkeypatch.setenv("PROFILE_FACTUEL_FILE", "")
    monkeypatch.setenv("PROFILE_MOTIVATIONNEL_FILE", "")
    monkeypatch.setenv("PROFILE_FACTUEL", "Synthetic candidate")
    monkeypatch.setenv("PROFILE_MOTIVATIONNEL", "Synthetic preferences")

    def forbidden_connection(*_args, **_kwargs):
        raise AssertionError("Pipeline tests must not access external services")

    monkeypatch.setattr(psycopg, "connect", forbidden_connection)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden_connection)
    telegram = Mock()
    alert = Mock()
    monkeypatch.setattr(notifier, "send_telegram", telegram)
    monkeypatch.setattr(notifier, "send_telegram_alert", alert)
    return SimpleNamespace(telegram=telegram, alert=alert)


@pytest.fixture
def aphp_pipeline(monkeypatch, isolated_services):
    pipeline = importlib.import_module("pipeline_aphp")
    database = importlib.import_module("database_aphp")
    scraper = importlib.import_module("scraper_aphp")
    filter_module = importlib.import_module("filter_aphp")
    scorer_module = importlib.import_module("scorer_aphp")
    main = importlib.import_module("main")
    connection = Mock()
    job = {"id": "ID_123", "title": "Synthetic data analyst", "metier": "", "contrat": ""}
    known_ids = Mock(return_value={"ID_123"})
    scrape = Mock(return_value=[job])
    upsert = Mock(return_value={"new": [job], "removed": []})
    run_filter = Mock(return_value=filter_stats())
    run_scorer = Mock(return_value=scorer_stats())
    fetch_new_jobs = Mock(return_value=[job])
    save_run = Mock()

    monkeypatch.setattr(database, "init_db", Mock())
    monkeypatch.setattr(database, "get_connection", Mock(return_value=connection))
    monkeypatch.setattr(database, "get_all_known_ids", known_ids)
    monkeypatch.setattr(database, "upsert_jobs", upsert)
    monkeypatch.setattr(scraper, "scrape_jobs", scrape)
    monkeypatch.setattr(filter_module, "run_filter", run_filter)
    monkeypatch.setattr(scorer_module, "run_scorer", run_scorer)
    monkeypatch.setattr(main, "mark_rejected", Mock())
    monkeypatch.setattr(pipeline, "execute_with_retry", lambda function: function(connection))
    monkeypatch.setattr(pipeline, "fetch_new_jobs", fetch_new_jobs)
    monkeypatch.setattr(pipeline, "get_counts", Mock(return_value=(1, 0, 1)))
    monkeypatch.setattr(pipeline, "save_run", save_run)
    monkeypatch.setattr(pipeline, "send_telegram", isolated_services.telegram)

    return SimpleNamespace(
        pipeline=pipeline,
        known_ids=known_ids,
        scrape=scrape,
        upsert=upsert,
        filter=run_filter,
        scorer=run_scorer,
        fetch_new_jobs=fetch_new_jobs,
        save_run=save_run,
        telegram=isolated_services.telegram,
    )


@pytest.fixture
def hcl_pipeline(monkeypatch, isolated_services):
    pipeline = importlib.import_module("pipeline_hcl")
    database = importlib.import_module("database_hcl")
    database_schema = importlib.import_module("database_schema")
    scraper = importlib.import_module("scraper_hcl")
    filter_module = importlib.import_module("filter_hcl")
    scorer_module = importlib.import_module("scorer_hcl")
    connection = Mock()
    scrape = Mock(return_value=[{"id": 123, "titre": "Synthetic data analyst"}])
    run_filter = Mock(return_value=filter_stats())
    run_scorer = Mock(return_value=scorer_stats())
    log_run = Mock()

    monkeypatch.setattr(database_schema, "initialize_schema", Mock())
    monkeypatch.setattr(database, "get_connection", Mock(return_value=connection))
    monkeypatch.setattr(database, "get_all_known_ids", Mock(return_value={123}))
    monkeypatch.setattr(
        database,
        "upsert_jobs",
        Mock(return_value={"new": 0, "removed": 0, "reactivated": 0, "updated": 1}),
    )
    monkeypatch.setattr(database, "log_pipeline_run", log_run)
    monkeypatch.setattr(scraper, "run_scraper", scrape)
    monkeypatch.setattr(filter_module, "run_filter", run_filter)
    monkeypatch.setattr(scorer_module, "run_scorer", run_scorer)

    return SimpleNamespace(
        pipeline=pipeline,
        connection=connection,
        scrape=scrape,
        filter=run_filter,
        scorer=run_scorer,
        log_run=log_run,
        telegram=isolated_services.telegram,
    )


def aphp_saved_status(save_run: Mock) -> str:
    assert save_run.called
    call = save_run.call_args
    return call.kwargs["status"] if "status" in call.kwargs else call.args[6]


def assert_aphp_failure_recorded(save_run: Mock) -> None:
    status = aphp_saved_status(save_run).lower()
    assert "error" in status or "fail" in status


def test_aphp_supplies_known_ids_to_scraper(aphp_pipeline) -> None:
    aphp_pipeline.pipeline.run_pipeline()

    aphp_pipeline.known_ids.assert_called_once()
    assert aphp_pipeline.scrape.call_args.kwargs["known_ids"] == {"ID_123"}


def test_aphp_processes_pending_offers_without_new_offers(aphp_pipeline) -> None:
    aphp_pipeline.upsert.return_value = {"new": [], "removed": []}
    aphp_pipeline.fetch_new_jobs.return_value = []

    aphp_pipeline.pipeline.run_pipeline()

    aphp_pipeline.filter.assert_called_once()
    aphp_pipeline.scorer.assert_called_once()
    assert aphp_saved_status(aphp_pipeline.save_run) in {"success", "no_new_offers"}


@pytest.mark.parametrize("step,counter", FAILED_STEP_STATS)
def test_aphp_rejects_internal_step_failures(aphp_pipeline, step, counter) -> None:
    failed_step = getattr(aphp_pipeline, step)
    failed_step.return_value[counter] = 1

    with pytest.raises(RuntimeError):
        aphp_pipeline.pipeline.run_pipeline()

    failed_step.assert_called_once()
    aphp_pipeline.filter.assert_called_once()
    aphp_pipeline.scorer.assert_called_once()
    assert_aphp_failure_recorded(aphp_pipeline.save_run)


@pytest.mark.parametrize("step,counter", FAILED_STEP_STATS)
def test_hcl_rejects_internal_step_failures(hcl_pipeline, step, counter) -> None:
    failed_step = getattr(hcl_pipeline, step)
    failed_step.return_value[counter] = 1

    with pytest.raises(RuntimeError):
        hcl_pipeline.pipeline.run_pipeline()

    failed_step.assert_called_once()
    hcl_pipeline.filter.assert_called_once()
    hcl_pipeline.scorer.assert_called_once()
    assert hcl_pipeline.log_run.called
    assert hcl_pipeline.log_run.call_args.args[1]["errors"]
    assert hcl_pipeline.log_run.call_args.args[1]["status"].startswith("error")
    hcl_pipeline.connection.close.assert_called_once()


def test_aphp_upstream_exception_is_redacted(aphp_pipeline, capsys, caplog) -> None:
    aphp_pipeline.scrape.side_effect = RuntimeError(SENSITIVE_DETAIL)

    with pytest.raises(RuntimeError) as error:
        aphp_pipeline.pipeline.run_pipeline()

    captured = capsys.readouterr()
    observable = (
        captured.out
        + captured.err
        + caplog.text
        + repr(aphp_pipeline.telegram.call_args_list)
        + repr(aphp_pipeline.save_run.call_args_list)
        + "".join(traceback.format_exception(error.value))
    )
    assert SENSITIVE_DETAIL not in observable
    assert_aphp_failure_recorded(aphp_pipeline.save_run)


def test_hcl_upstream_exception_is_redacted(hcl_pipeline, capsys, caplog) -> None:
    hcl_pipeline.scrape.side_effect = RuntimeError(SENSITIVE_DETAIL)

    with pytest.raises(RuntimeError) as error:
        hcl_pipeline.pipeline.run_pipeline()

    captured = capsys.readouterr()
    observable = (
        captured.out
        + captured.err
        + caplog.text
        + repr(hcl_pipeline.telegram.call_args_list)
        + repr(hcl_pipeline.log_run.call_args_list)
        + "".join(traceback.format_exception(error.value))
    )
    assert SENSITIVE_DETAIL not in observable
    assert hcl_pipeline.log_run.call_args.args[1]["errors"]


def test_hcl_safe_step_redacts_exception_details(hcl_pipeline, capsys, caplog) -> None:
    failing_step = Mock(side_effect=ValueError(SENSITIVE_DETAIL))

    result, error = hcl_pipeline.pipeline.safe_step("SYNTHETIC STEP", failing_step)

    captured = capsys.readouterr()
    observable = (
        captured.out
        + captured.err
        + caplog.text
        + repr(hcl_pipeline.telegram.call_args_list)
        + str(error)
    )
    assert result is None
    assert error
    assert SENSITIVE_DETAIL not in observable
