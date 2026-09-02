"""Offline coverage for private logs and offers pending an available LLM."""

import json
import logging
import traceback
from types import SimpleNamespace

import httpx
import pytest
import requests

import filter_aphp
import filter_hcl
import notifier
import scorer_hcl

PRIVATE_TEXT = "SYNTHETIC_PRIVATE_CONTENT_DO_NOT_LOG"


@pytest.fixture(autouse=True)
def prevent_network(monkeypatch):
    def fail_request(*_args, **_kwargs):
        raise AssertionError("Safety tests must not make network requests")

    monkeypatch.setattr(requests.sessions.Session, "request", fail_request)
    monkeypatch.setattr(httpx.Client, "request", fail_request)


@pytest.fixture(params=[filter_aphp, filter_hcl], ids=["aphp", "hcl"])
def filter_module(request):
    return request.param


class FakeConnection:
    def __init__(self):
        self.rollbacks = 0
        self.failed = False

    def rollback(self):
        self.rollbacks += 1
        self.failed = False


def make_client(raw=None, error=None):
    def create(**_kwargs):
        if error is not None:
            raise error
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=raw))])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def configure_filter(monkeypatch, module, key="synthetic-key", count=4):
    jobs = [{"id": index + 1} for index in range(count)]
    monkeypatch.setattr(module, "GROQ_API_KEY", key)
    monkeypatch.setattr(module, "Groq", lambda **_kwargs: object())
    monkeypatch.setattr(module, "get_offers_to_filter", lambda _conn: jobs)
    monkeypatch.setattr(module, "tqdm", lambda values, **_kwargs: values)
    monkeypatch.setattr(module, "is_too_old", lambda _job: False)
    for name in (
        "_reject_contrat",
        "_reject_title",
        "_reject_paramedical",
        "_reject_diploma_level",
        "_reject_filiere",
        "_auto_pass",
        "_auto_pass_metier",
    ):
        if hasattr(module, name):
            monkeypatch.setattr(module, name, lambda _job: None)
    if hasattr(module, "notify"):
        monkeypatch.setattr(module, "notify", lambda _message: None)
    saved = []
    monkeypatch.setattr(
        module,
        "update_ai_filter",
        lambda *args, **kwargs: saved.append((args, kwargs)),
    )
    return saved


@pytest.mark.parametrize(
    "raw",
    [
        PRIVATE_TEXT,
        json.dumps({"resultat": PRIVATE_TEXT, "raison": "Synthetic"}),
        json.dumps({"resultat": "pass", "categorie": PRIVATE_TEXT, "raison": "Synthetic"}),
        json.dumps({"raison": PRIVATE_TEXT}),
        json.dumps({"resultat": "pass", "raison": [PRIVATE_TEXT]}),
    ],
    ids=["not-json", "invalid-decision", "invalid-category", "missing-decision", "invalid-reason"],
)
def test_invalid_llm_response_stays_pending_without_private_logs(filter_module, caplog, raw):
    caplog.set_level(logging.DEBUG)

    decision, category, reason = filter_module._ai_filter({"id": 1}, make_client(raw=raw))

    assert decision == "error"
    assert category is None
    assert "attente" in reason
    assert PRIVATE_TEXT not in caplog.text


def test_provider_error_does_not_expose_body(filter_module, caplog):
    result = filter_module._ai_filter({"id": 1}, make_client(error=ValueError(PRIVATE_TEXT)))

    assert result[0] == "error"
    assert "ValueError" in caplog.text
    assert PRIVATE_TEXT not in caplog.text


def test_daily_quota_exception_is_safe_to_report(filter_module, caplog):
    client = make_client(error=ValueError(f"429 rate_limit TPD {PRIVATE_TEXT}"))

    with pytest.raises(filter_module.DailyQuotaExceeded) as error:
        filter_module._ai_filter({"id": 1}, client)

    assert PRIVATE_TEXT not in "".join(traceback.format_exception(error.value))
    assert PRIVATE_TEXT not in caplog.text


def test_absent_key_counts_pending_and_keeps_deterministic_rules(
    monkeypatch,
    filter_module,
    caplog,
):
    saved = configure_filter(monkeypatch, filter_module, key="")
    monkeypatch.setattr(
        filter_module,
        "_auto_pass",
        lambda job: "Synthetic rule" if job["id"] == 2 else None,
    )

    stats = filter_module.run_filter(FakeConnection())

    assert stats["skipped"] == 3
    assert stats["auto_passed"] == 1
    assert stats["fallback_passed"] == 0
    assert len(saved) == 1
    assert "fallback pass" not in caplog.text


def test_daily_quota_counts_all_pending_but_continues_deterministic_rules(
    monkeypatch,
    filter_module,
    caplog,
):
    saved = configure_filter(monkeypatch, filter_module)
    monkeypatch.setattr(
        filter_module,
        "_auto_pass",
        lambda job: "Synthetic rule" if job["id"] == 2 else None,
    )
    attempted = []

    def quota_exhausted(job, _client):
        attempted.append(job["id"])
        raise filter_module.DailyQuotaExceeded(PRIVATE_TEXT)

    monkeypatch.setattr(filter_module, "_ai_filter", quota_exhausted)

    stats = filter_module.run_filter(FakeConnection())

    assert attempted == [1]
    assert stats["skipped"] == 3
    assert stats["auto_passed"] == 1
    assert len(saved) == 1
    assert PRIVATE_TEXT not in caplog.text


def test_llm_failure_counts_pending_without_database_write(monkeypatch, filter_module):
    saved = configure_filter(monkeypatch, filter_module)
    monkeypatch.setattr(filter_module, "_ai_filter", lambda *_args: ("error", None, "Synthetic"))

    stats = filter_module.run_filter(FakeConnection(), limit=2)

    assert stats["total"] == 2
    assert stats["ai_errors"] == 2
    assert stats["skipped"] == 2
    assert saved == []


@pytest.mark.parametrize("decision", ["pass", "reject"])
def test_successful_llm_reason_is_saved_but_not_logged(
    monkeypatch,
    filter_module,
    caplog,
    decision,
):
    caplog.set_level(logging.DEBUG)
    saved = configure_filter(monkeypatch, filter_module, count=1)
    monkeypatch.setattr(
        filter_module,
        "_ai_filter",
        lambda *_args: (decision, "surqualification", PRIVATE_TEXT),
    )

    stats = filter_module.run_filter(FakeConnection())

    assert stats["skipped"] == 0
    assert saved[0][0][3] == PRIVATE_TEXT
    assert PRIVATE_TEXT not in caplog.text


def test_database_failure_rolls_back_before_next_offer(monkeypatch, filter_module, caplog):
    configure_filter(monkeypatch, filter_module, count=2)
    monkeypatch.setattr(filter_module, "_auto_pass", lambda _job: "Synthetic rule")
    connection = FakeConnection()
    saved = []

    def update(conn, job_id, *_args, **_kwargs):
        if job_id == 1:
            conn.failed = True
            raise filter_module.DatabaseError(PRIVATE_TEXT)
        assert not conn.failed
        saved.append(job_id)

    monkeypatch.setattr(filter_module, "update_ai_filter", update)

    stats = filter_module.run_filter(connection)

    assert connection.rollbacks == 1
    assert saved == [2]
    assert stats["errors"] == 1
    assert stats["auto_passed"] == 1
    assert PRIVATE_TEXT not in caplog.text


def configure_scorer(monkeypatch, count=4):
    monkeypatch.setattr(scorer_hcl, "GROQ_API_KEY", "synthetic-key")
    monkeypatch.setattr(scorer_hcl, "PROFILE_FACTUEL", "Synthetic candidate")
    monkeypatch.setattr(scorer_hcl, "PROFILE_MOTIVATIONNEL", "Synthetic preferences")
    monkeypatch.setattr(scorer_hcl, "Groq", lambda **_kwargs: object())
    monkeypatch.setattr(
        scorer_hcl,
        "get_offers_to_score",
        lambda _conn: [{"id": i + 1} for i in range(count)],
    )
    monkeypatch.setattr(scorer_hcl, "_notify_top_score", lambda *_args: None)
    monkeypatch.setattr(scorer_hcl, "_persist", lambda *_args: 85)


def test_scorer_counts_all_remaining_offers_after_daily_quota(monkeypatch, caplog):
    configure_scorer(monkeypatch)
    attempted = []

    def score(job, _client):
        attempted.append(job["id"])
        if job["id"] == 2:
            raise scorer_hcl.DailyQuotaExceeded(PRIVATE_TEXT)
        return {"score": 85, "priorite": "P1"}

    monkeypatch.setattr(scorer_hcl, "_score_job", score)

    stats = scorer_hcl.run_scorer(FakeConnection())

    assert attempted == [1, 2]
    assert stats == {"total": 4, "scored": 1, "errors": 0, "skipped": 3}
    assert PRIVATE_TEXT not in caplog.text


def test_scorer_database_failure_rolls_back_before_next_offer(monkeypatch, caplog):
    configure_scorer(monkeypatch, count=2)
    monkeypatch.setattr(
        scorer_hcl,
        "_score_job",
        lambda *_args: {"score": 85, "priorite": "P1"},
    )
    connection = FakeConnection()

    def persist(conn, job, _result):
        if job["id"] == 1:
            conn.failed = True
            raise scorer_hcl.DatabaseError(PRIVATE_TEXT)
        assert not conn.failed
        return 85

    monkeypatch.setattr(scorer_hcl, "_persist", persist)

    stats = scorer_hcl.run_scorer(connection)

    assert connection.rollbacks == 1
    assert stats == {"total": 2, "scored": 1, "errors": 1, "skipped": 0}
    assert PRIVATE_TEXT not in caplog.text


def test_scorer_telegram_error_does_not_log_secret(monkeypatch, caplog):
    def failed_notification(_message):
        raise requests.ConnectionError(PRIVATE_TEXT)

    monkeypatch.setattr(notifier, "send_telegram", failed_notification)

    scorer_hcl._notify_top_score({"id": 1}, 85, "P1", "Synthetic reason")

    assert "ConnectionError" in caplog.text
    assert PRIVATE_TEXT not in caplog.text
