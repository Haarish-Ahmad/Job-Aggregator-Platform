"""The migrations must match the models (this is the check that failed on the original schema)."""
from alembic import command
from sqlalchemy import inspect, text

from conftest import alembic_config
from db import engine


def test_alembic_check_finds_no_drift():
    command.check(alembic_config())  # raises if models and migrations disagree


def test_original_year_grad_columns_are_gone():
    cols = {c["name"] for c in inspect(engine).get_columns("students")}
    assert "year_grad" not in cols and "alerts_enabled" in cols
    assert "year_grad" not in {c["name"] for c in inspect(engine).get_columns("job_postings")}


def test_source_external_id_is_unique():
    uniques = {u["name"] for u in inspect(engine).get_unique_constraints("job_postings")}
    assert "uq_job_source_external_id" in uniques


def test_downgrade_and_upgrade_round_trip():
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    assert "students" not in inspect(engine).get_table_names()
    command.upgrade(cfg, "head")
    command.check(cfg)


def test_drift_migration_keeps_existing_students():
    """Rows created under the original schema (year_grad NOT NULL) survive the upgrade with grad_year filled."""
    cfg = alembic_config()
    command.downgrade(cfg, "ab7b8208ab2d")  # the originally shipped schema
    with engine.begin() as c:
        c.execute(text("INSERT INTO students (name, branch, email, password_hash, year_grad, role, skills) "
                       "VALUES ('Old', 'CSE', 'old@x.edu', 'h', 2027, 'student', '{}')"))
    command.upgrade(cfg, "head")
    with engine.connect() as c:
        assert c.execute(text("SELECT grad_year FROM students WHERE email = 'old@x.edu'")).scalar() == 2027
        c.execute(text("TRUNCATE students CASCADE"))
        c.commit()
