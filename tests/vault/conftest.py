import sqlite3
import pytest
from sable.platform.db import ensure_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    ensure_schema(c)
    c.execute("INSERT INTO orgs (org_id, display_name) VALUES ('testorg', 'Test Org')")
    c.commit()
    yield c
    c.close()


@pytest.fixture
def vault_root(tmp_path):
    d = tmp_path / "vault" / "testorg"
    d.mkdir(parents=True)
    return d
