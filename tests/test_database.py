from database_aphp import update_ai_filter


class RecordingCursor:
    def __init__(self) -> None:
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _query, params) -> None:
        self.params = params


class RecordingConnection:
    def __init__(self) -> None:
        self.cursor_instance = RecordingCursor()
        self.committed = False

    def cursor(self) -> RecordingCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True


def test_update_ai_filter_preserves_rejection_category() -> None:
    connection = RecordingConnection()

    update_ai_filter(
        connection,
        "job-1",
        "reject",
        "Diplôme incompatible",
        category="diplome_paramedical",
    )

    assert connection.cursor_instance.params == (
        "diplome_paramedical",
        "Diplôme incompatible",
        "job-1",
    )
    assert connection.committed


def test_update_ai_filter_uses_pass_category() -> None:
    connection = RecordingConnection()

    update_ai_filter(connection, "job-2", "pass", "Profil compatible")

    assert connection.cursor_instance.params[0] == "passed_filter_1"
