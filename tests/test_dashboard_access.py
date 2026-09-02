"""The dashboard must authenticate before making any database connection."""

from pathlib import Path

import psycopg
import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize("password", [None, "synthetic-test-password"])
def test_dashboard_blocks_database_access_before_login(monkeypatch, password):
    if password is None:
        monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("DASHBOARD_PASSWORD", password)
    connections = []

    def forbidden_connection(*args, **kwargs):
        connections.append((args, kwargs))
        raise AssertionError("Database must not be accessed before authentication")

    monkeypatch.setattr(psycopg, "connect", forbidden_connection)
    app = AppTest.from_file(
        str(Path(__file__).parents[1] / "dashboard.py"), default_timeout=20
    ).run()

    assert not app.exception
    assert not connections
    if password is None:
        assert "DASHBOARD_PASSWORD" in app.error[0].value
    else:
        assert app.text_input[0].label == "Mot de passe"
        app.text_input[0].set_value("wrong-password")
        app.button[0].click().run()
        assert not app.exception
        assert not connections
        assert app.error[0].value == "Mot de passe incorrect."
