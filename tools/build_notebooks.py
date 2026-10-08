"""Convert notebooks/*.py (cells split by '# %%') into Fabric-importable .ipynb files in notebooks/fabric/.

The first code cell tagged 'parameters' becomes the notebook's parameter cell, so the Fabric
pipeline can pass values into it. Run:  python tools/build_notebooks.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "notebooks"
OUT = SRC / "fabric"
SPEC = (ROOT / "semantic_model" / "model_spec.py").read_text()


def cells_from(text: str):
    parts = re.split(r"^# %%(.*)$", text, flags=re.M)
    # parts = [preamble, header1, body1, header2, body2, ...]
    for header, body in zip(parts[1::2], parts[2::2]):
        body = body.strip("\n")
        if "[markdown]" in header:
            md = "\n".join(l[2:] if l.startswith("# ") else l.lstrip("#") for l in body.splitlines())
            yield {"cell_type": "markdown", "metadata": {}, "source": md.splitlines(keepends=True)}
        else:
            tags = ["parameters"] if "parameters" in header else []
            body = body.replace("# <<MODEL_SPEC>>", SPEC)
            yield {"cell_type": "code", "metadata": {"tags": tags} if tags else {}, "execution_count": None,
                   "outputs": [], "source": body.splitlines(keepends=True)}


def main():
    OUT.mkdir(exist_ok=True)
    for py in sorted(SRC.glob("nb_*.py")):
        nb = {"cells": list(cells_from(py.read_text())),
              "metadata": {"kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark",
                                          "language": "Python"},
                           "language_info": {"name": "python"}},
              "nbformat": 4, "nbformat_minor": 5}
        (OUT / f"{py.stem}.ipynb").write_text(json.dumps(nb, indent=1))
        print("wrote", (OUT / f"{py.stem}.ipynb").relative_to(ROOT))


if __name__ == "__main__":
    main()
