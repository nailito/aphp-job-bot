from datetime import datetime, timedelta, timezone

import filter_aphp
import filter_hcl


def test_aphp_rejects_excluded_contract() -> None:
    category, reason = filter_aphp._reject_contrat({"contrat": "Stage de six mois"})

    assert category == "contrat_exclu"
    assert "stage" in reason.lower()


def test_hcl_rejects_paramedical_diploma() -> None:
    job = {
        "titre": "Cadre de proximité",
        "description": "Diplôme d'État d'infirmier obligatoire",
    }

    category, _reason = filter_hcl._reject_paramedical(job)

    assert category == "diplome_paramedical"


def test_recent_offer_is_not_too_old() -> None:
    today = datetime.now(timezone.utc).date().isoformat()

    assert filter_aphp.is_too_old({"date_publication": today}) is False


def test_old_offer_is_rejected_by_age() -> None:
    old_date = (datetime.now(timezone.utc) - timedelta(days=120)).date().isoformat()

    assert filter_aphp.is_too_old({"date_publication": old_date}) is True
