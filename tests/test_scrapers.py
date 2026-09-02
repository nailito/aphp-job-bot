from datetime import datetime

import pytest
import requests

import scraper_aphp
import scraper_hcl


def test_aphp_helpers_normalize_html_reference_and_tags() -> None:
    html = "<p>Mission data</p><p>Référence de l'offre 2026-1234</p>"

    assert "Mission data" in scraper_aphp.strip_html(html)
    assert scraper_aphp.extract_reference(html) == "2026-1234"
    assert scraper_aphp.parse_tags([{"id": 434, "value": "CDI"}]) == {"contrat": "CDI"}


def test_aphp_ids_do_not_depend_on_human_reference(monkeypatch) -> None:
    payload = {
        "jobs": {
            "totalCount": 2,
            "offers": [
                {"id": 123, "title": "Data analyst", "description": "Référence de l'offre 1-2"},
                {"id": 124, "title": "Chef de projet", "description": "Sans référence"},
            ],
        }
    }
    monkeypatch.setattr(scraper_aphp, "init_session", lambda: None)
    monkeypatch.setattr(scraper_aphp, "fetch_page", lambda _page: payload)
    monkeypatch.setattr(scraper_aphp, "send_or_edit", lambda _message: None)
    monkeypatch.setattr(scraper_aphp.time, "sleep", lambda _seconds: None)

    jobs = scraper_aphp.scrape_jobs(max_pages=1)

    assert [job["id"] for job in jobs] == ["123", "124"]


def test_hcl_html_to_text_keeps_readable_sections() -> None:
    text = scraper_hcl.html_to_text("<h2>Mission</h2><p>Analyser les données</p>")

    assert "Mission" in text
    assert "Analyser les données" in text


class FakeResponse:
    status_code = 200
    headers = {"X-WP-Total": "2", "X-WP-TotalPages": "2"}

    def __init__(self, payload) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class InterruptedSession:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, *_args, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return FakeResponse([{"id": 1}])
        raise requests.ConnectionError("connection lost")


def test_hcl_partial_snapshot_raises_instead_of_returning_data(monkeypatch) -> None:
    monkeypatch.setattr(scraper_hcl.time, "sleep", lambda _seconds: None)

    with pytest.raises(scraper_hcl.ScrapingError, match="Erreur réseau page 2"):
        scraper_hcl.fetch_all_offers_raw(InterruptedSession())


def test_hcl_parse_offer_uses_synthetic_data(monkeypatch) -> None:
    monkeypatch.setattr(
        scraper_hcl,
        "resolve_term_labels",
        lambda _session, taxonomy, _ids: [taxonomy.rsplit("_", 1)[-1]],
    )
    raw = {
        "id": 7,
        "title": {"rendered": "Ingénieur data"},
        "link": "https://example.test/jobs/7",
        "content": {"rendered": "<p>Mission synthétique</p>"},
        "date": "2026-01-02T08:00:00",
        "modified": "2026-01-03T08:00:00",
        "meta": {"job_starting_date": int(datetime(2026, 2, 1).timestamp())},
        "job_custom_hcl_hopital": [1],
        "job_custom_chulyon_typedecontrat": [2],
        "job_custom_hcl_filiere": [3],
    }

    offer = scraper_hcl.parse_offer(object(), raw, known_ids=set())

    assert offer["id"] == 7
    assert offer["titre"] == "Ingénieur data"
    assert offer["date_publication"] == "2026-01-02"
    assert "Mission synthétique" in offer["description"]
