from pathlib import Path

from config import _load_private_text


def test_private_text_prefers_inline_environment(monkeypatch, tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.md"
    profile_path.write_text("from file", encoding="utf-8")
    monkeypatch.setenv("TEST_PROFILE", "from environment")
    monkeypatch.setenv("TEST_PROFILE_FILE", str(profile_path))

    assert _load_private_text("TEST_PROFILE", "TEST_PROFILE_FILE") == "from environment"


def test_private_text_loads_local_file(monkeypatch, tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.md"
    profile_path.write_text("private profile\n", encoding="utf-8")
    monkeypatch.delenv("TEST_PROFILE", raising=False)
    monkeypatch.setenv("TEST_PROFILE_FILE", str(profile_path))

    assert _load_private_text("TEST_PROFILE", "TEST_PROFILE_FILE") == "private profile"
