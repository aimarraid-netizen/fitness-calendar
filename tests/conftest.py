"""Ühised fixtures: temp SQLite DB + näidis-CSV laadimine."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "v2"))

from db import ensure_columns, get_db, init_schema  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def conn(tmp_path):
    c = get_db(tmp_path / "test.db")
    init_schema(c)
    ensure_columns(c)
    yield c
    c.close()


@pytest.fixture
def loaded_conn(conn):
    """DB, kuhu on imporditud sample_single_workout.csv."""
    import parse_gymaholic_csv as pg
    parsed = pg.parse_csv(FIXTURES / "sample_single_workout.csv")
    pg.save_to_db(parsed, conn)
    return conn
