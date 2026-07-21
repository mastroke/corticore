import pytest

from corticore import Memory
from corticore.cli import main


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "cli.db")
    mem = Memory(path)
    mem.remember("the user's name is Priya", namespace="alice")
    mem.remember("the deadline is March 15", namespace="alice")
    mem.close()
    return path


def test_list_shows_memories(db, capsys):
    assert main(["--db", db, "list"]) == 0
    out = capsys.readouterr().out
    assert "Priya" in out
    assert "March 15" in out


def test_list_filters_by_namespace(db, capsys):
    assert main(["--db", db, "list", "--namespace", "nobody"]) == 0
    assert "(no memories)" in capsys.readouterr().out


def test_recall_prints_ranked_results(db, capsys):
    assert main(["--db", db, "recall", "when is the deadline", "--namespace", "alice"]) == 0
    out = capsys.readouterr().out
    assert "March 15" in out


def test_reflect_reports_counts(db, capsys):
    assert main(["--db", db, "reflect"]) == 0
    out = capsys.readouterr().out
    assert "inspected=" in out


def test_why_prints_trace(db, capsys):
    # recall once so there is a "recalled" event, then find an id to explain.
    mem = Memory(db)
    mid = mem.store.all()[0].id
    mem.close()

    assert main(["--db", db, "why", mid]) == 0
    out = capsys.readouterr().out
    assert "stored" in out


def test_why_missing_memory_exits_nonzero(db, capsys):
    assert main(["--db", db, "why", "does-not-exist"]) == 1
    err = capsys.readouterr().err
    assert "memory not found" in err
