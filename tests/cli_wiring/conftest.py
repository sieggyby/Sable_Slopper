"""Fixtures for CLI wiring tests."""
import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()
