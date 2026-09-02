import scorer_hcl


class NoWriteConnection:
    def cursor(self):  # pragma: no cover - must not be used for a passing score
        raise AssertionError("unexpected rejection query")


def test_persist_returns_the_saved_score(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        scorer_hcl,
        "update_score",
        lambda connection, job_id, score, analysis: calls.append(
            (connection, job_id, score, analysis)
        ),
    )
    connection = NoWriteConnection()
    result = {
        "score": 82,
        "priorite": "P1",
        "raison": "Correspondance synthétique.",
        "points_forts": ["Python"],
        "points_faibles": [],
    }

    score = scorer_hcl._persist(connection, {"id": 42}, result)

    assert score == 82
    assert calls[0][1:3] == (42, 82)
