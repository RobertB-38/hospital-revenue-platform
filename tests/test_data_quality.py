"""Data-quality tests run on every commit by the Azure DevOps pipeline.

Each file in tests/sql returns the rows that break a rule. Zero rows = pass.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SQL_TESTS = sorted((Path(__file__).parent / "sql").glob("*.sql"))


@pytest.mark.parametrize("sql_file", SQL_TESTS, ids=[p.stem for p in SQL_TESTS])
def test_sql_rule(db, sql_file):
    rows = db.execute(sql_file.read_text()).fetchall()
    assert not rows, f"{sql_file.name}: {len(rows)} failing rows, first: {rows[:3]}"


@pytest.mark.parametrize("batch", sorted((ROOT / "data/landing/his_export").iterdir()), ids=lambda p: p.name)
def test_manifest_matches_files(db, batch):
    manifest = json.loads((batch / f"MANIFEST_{batch.name}.json").read_text())
    for entry in manifest["files"]:
        path = (batch / entry["file"]).as_posix()
        n = db.execute(f"SELECT COUNT(*) FROM read_csv('{path}', header=true, all_varchar=true)").fetchone()[0]
        assert n == entry["row_count"], f"{entry['file']}: {n} rows vs manifest {entry['row_count']}"
        if "control_total_amount" in entry:
            total = db.execute(f"SELECT SUM(CAST(AMOUNT AS DECIMAL(18,2))) FROM read_csv('{path}', header=true, "
                               f"all_varchar=true)").fetchone()[0]
            assert abs(float(total) - entry["control_total_amount"]) < 0.01


def test_patient_identifiers_only_in_landing():
    """Names and addresses exist only in the landing export; the silver notebook must not select them."""
    silver = (ROOT / "notebooks/nb_02_silver_conform.py").read_text()
    select_block = silver.split("patients = p.select(")[1].split(")\n#")[0]
    for col in ["SURNAME", "FORENAME", "ADDRESS_LINE1", "MEMBERSHIP_NO", "EIRCODE_ROUTING"]:
        assert col not in select_block, f"{col} would reach silver"
