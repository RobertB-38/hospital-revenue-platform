"""Checks the semantic-model definition is internally consistent before it is deployed."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "semantic_model"))
import model_spec as m  # noqa: E402


def test_relationship_tables_exist():
    for f_tbl, _, t_tbl, _ in m.RELATIONSHIPS:
        assert f_tbl in m.TABLES and t_tbl in m.TABLES


def test_measures_reference_known_tables_and_measures():
    names = {x[1] for x in m.MEASURES}
    assert len(names) == len(m.MEASURES), "duplicate measure names"
    assert len(names) >= 10
    for table, name, dax, *_ in m.MEASURES:
        assert table in m.TABLES
        for ref_table in re.findall(r"\b(gold_[a-z_]+)\[", dax):
            assert ref_table in m.TABLES, f"{name} uses unknown table {ref_table}"
        for ref in re.findall(r"(?<![\w\]])\[([^\]]+)\]", dax):
            if ref not in names:
                # a bare [x] that is not a measure must be a column reference written as table[col]
                assert re.search(rf"\w\[{re.escape(ref)}\]", dax), f"{name}: unknown measure [{ref}]"


def test_rls_roles_defined():
    roles = {r[0] for r in m.ROLES}
    assert {"Group Finance", "Site Manager (dynamic)"} <= roles
