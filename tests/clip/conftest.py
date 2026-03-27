import pytest


@pytest.fixture(autouse=True)
def tmp_sable_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SABLE_HOME", str(tmp_path / ".sable"))
    monkeypatch.setenv("SABLE_WORKSPACE", str(tmp_path / "workspace"))


def make_words(*triples):
    return [{"start": s, "end": e, "text": t} for s, e, t in triples]


def make_segments(*triples):
    return [{"start": s, "end": e, "text": t} for s, e, t in triples]
