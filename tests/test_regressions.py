"""Offline regressions for snapshot integrity and private notification credentials."""

import pytest
import requests

import notifier
import scraper_aphp
import scraper_hcl


@pytest.fixture(autouse=True)
def prevent_network(monkeypatch) -> None:
    def fail_request(*_args, **_kwargs):
        raise AssertionError("Regression tests must not make real HTTP requests")

    monkeypatch.setattr(requests.sessions.Session, "request", fail_request)


def mock_aphp_pages(monkeypatch, pages: dict) -> None:
    monkeypatch.setattr(scraper_aphp, "init_session", lambda: None)
    monkeypatch.setattr(scraper_aphp, "fetch_page", lambda page: pages[page])
    monkeypatch.setattr(scraper_aphp, "send_or_edit", lambda _message: None)
    monkeypatch.setattr(scraper_aphp, "notify", lambda _message: None)
    monkeypatch.setattr(scraper_aphp.time, "sleep", lambda _seconds: None)


@pytest.mark.parametrize("description", ["Sans référence", "Référence de l'offre 2026-123"])
def test_aphp_preserves_existing_legacy_id(monkeypatch, description) -> None:
    mock_aphp_pages(
        monkeypatch,
        {
            1: {
                "jobs": {
                    "totalCount": 1,
                    "offers": [{"id": 123, "title": "Data analyst", "description": description}],
                }
            }
        },
    )

    jobs = scraper_aphp.scrape_jobs(max_pages=1, known_ids={"ID_123"})

    assert [job["id"] for job in jobs] == ["ID_123"]
    assert jobs[0]["url"] == "https://recrutement.aphp.fr/jobs/123"


def test_aphp_rejects_snapshot_exceeding_page_limit(monkeypatch) -> None:
    mock_aphp_pages(
        monkeypatch,
        {1: {"jobs": {"totalCount": 2, "offers": [{"id": 1, "title": "Data analyst"}]}}},
    )

    with pytest.raises(scraper_aphp.ScrapingError):
        scraper_aphp.scrape_jobs(max_pages=1)


@pytest.mark.parametrize(
    "invalid_offer",
    [
        {"title": "Offre sans identifiant"},
        {"id": 2, "title": "Offre mal formée", "customTags": None},
    ],
    ids=["missing-id", "parsing-error"],
)
def test_aphp_rejects_snapshot_with_unparseable_offer(monkeypatch, invalid_offer) -> None:
    mock_aphp_pages(
        monkeypatch,
        {
            1: {
                "jobs": {
                    "totalCount": 2,
                    "offers": [{"id": 1, "title": "Data analyst"}, invalid_offer],
                }
            }
        },
    )

    with pytest.raises(scraper_aphp.ScrapingError):
        scraper_aphp.scrape_jobs(max_pages=1)


def test_aphp_rejects_snapshot_with_missing_page_content(monkeypatch) -> None:
    mock_aphp_pages(
        monkeypatch,
        {
            1: {"jobs": {"totalCount": 2, "offers": [{"id": 1, "title": "Data analyst"}]}},
            2: {"jobs": {"totalCount": 2, "offers": []}},
        },
    )

    with pytest.raises(scraper_aphp.ScrapingError):
        scraper_aphp.scrape_jobs(max_pages=2)


@pytest.mark.parametrize("meta", [{}, {"job_starting_date": 0}, None])
def test_hcl_missing_start_date_is_sql_null(meta) -> None:
    raw = {"id": 7, "title": {"rendered": "Ingénieur data"}, "meta": meta}

    offer = scraper_hcl.parse_offer(object(), raw, known_ids=set())

    assert offer["date_debut"] is None


def test_hcl_rejects_snapshot_when_individual_offer_parsing_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        scraper_hcl,
        "fetch_all_offers_raw",
        lambda _session: [{"id": 1}, {"id": 2}],
    )

    def parse_offer(_session, raw, _known_ids):
        if raw["id"] == 2:
            raise ValueError("Synthetic malformed offer")
        return {"id": raw["id"], "titre": "Data analyst"}

    monkeypatch.setattr(scraper_hcl, "parse_offer", parse_offer)

    with pytest.raises(scraper_hcl.ScrapingError):
        scraper_hcl.run_scraper(known_ids={1, 2})


@pytest.mark.parametrize("target", ["message", "alert", "progress-new", "progress-edit"])
def test_telegram_exception_does_not_print_token(monkeypatch, capsys, caplog, target) -> None:
    token = "123456789:synthetic-secret-for-regression-test"
    monkeypatch.setattr(notifier, "TELEGRAM_TOKEN", token)
    monkeypatch.setattr(notifier, "TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr(scraper_aphp, "TELEGRAM_TOKEN", token)
    monkeypatch.setattr(scraper_aphp, "TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr(scraper_aphp, "last_message_id", 42 if target == "progress-edit" else None)
    monkeypatch.setenv("TELEGRAM_TOKEN_ALERT", token)
    monkeypatch.setenv("TELEGRAM_CHAT_ID_ALERT", "123")
    attempted_urls = []

    def fail_post(url, **_kwargs):
        attempted_urls.append(url)
        raise requests.ConnectionError(f"Unable to connect to {url}")

    monkeypatch.setattr(requests, "post", fail_post)

    if target == "message":
        notifier.send_telegram("Synthetic status update")
    elif target == "alert":
        notifier.send_telegram_alert("Synthetic status update")
    else:
        scraper_aphp.send_or_edit("Synthetic status update")

    captured = capsys.readouterr()
    output = captured.out + captured.err + caplog.text
    assert len(attempted_urls) == 1
    assert token in attempted_urls[0]
    endpoint = "editMessageText" if target == "progress-edit" else "sendMessage"
    assert attempted_urls[0].endswith(endpoint)
    assert token not in output
    assert "ConnectionError" in output
