"""The Fabric notebooks (.ipynb) must be regenerated from the .py sources, and the Warehouse SQL must parse."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_notebooks_in_sync(tmp_path):
    before = {p.name: p.read_text() for p in (ROOT / "notebooks/fabric").glob("*.ipynb")}
    subprocess.run([sys.executable, str(ROOT / "tools/build_notebooks.py")], check=True, capture_output=True)
    after = {p.name: p.read_text() for p in (ROOT / "notebooks/fabric").glob("*.ipynb")}
    assert before == after, "notebooks/fabric is out of date: run python tools/build_notebooks.py and commit"
    for text in after.values():
        nb = json.loads(text)
        assert nb["nbformat"] == 4 and nb["cells"]


def test_warehouse_sql_parses():
    result = subprocess.run(["sqlfluff", "parse", "--dialect", "tsql", *map(str, (ROOT / "warehouse").glob("*.sql"))],
                            capture_output=True, text=True)
    assert "unparsable" not in result.stdout.lower(), result.stdout[-2000:]
