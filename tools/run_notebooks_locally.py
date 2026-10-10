"""Run the Fabric notebooks on a laptop with plain local Spark, to test the logic before using Fabric capacity.

It imitates the few Fabric-only pieces the notebooks use (notebookutils.fs.ls/head, notebook.exit, display).
Delta Lake jars are not needed: tables are stored as Parquet and a small stand-in implements the Delta
operations the notebooks use (MERGE, DELETE, UPDATE). Results match; performance and Delta features do not.
Usage (Python 3.11 with pyspark 3.5):
    python tools/run_notebooks_locally.py --landing data/landing --work /tmp/lakehouse nb_01 nb_02 nb_03 nb_04 nb_05
Optional parameter overrides:  --param nb_04.period_end=2026-08-31
"""
import argparse
import os
import re
import types
from pathlib import Path

import sys
from pyspark.sql import SparkSession, DataFrameWriter, functions as F

ROOT = Path(__file__).resolve().parent.parent


class NotebookExit(Exception):
    pass


# ---------------------------------------------------------------- Delta stand-in (Parquet underneath)
_orig_format = DataFrameWriter.format
DataFrameWriter.format = lambda self, src: _orig_format(self, "parquet" if src == "delta" else src)


def _overwrite(spark, name, df):
    df = df.localCheckpoint(eager=True)
    df.write.format("parquet").mode("overwrite").saveAsTable(name)


class _MergeBuilder:
    def __init__(self, spark, name, target, source, cond):
        self.spark, self.name, self.t, self.s, self.cond = spark, name, target, source, cond
        self.update_cond, self.do_update, self.do_insert = None, False, False

    def whenMatchedUpdateAll(self, condition=None):
        self.do_update, self.update_cond = True, condition
        return self

    def whenNotMatchedInsertAll(self):
        self.do_insert = True
        return self

    def execute(self):
        t, s, on = self.t, self.s, F.expr(self.cond)
        cols = [c for c in t.columns]
        parts = []
        if self.do_update:
            upd = t.join(s, on, "inner")
            if self.update_cond:
                upd = upd.where(F.expr(self.update_cond))
            upd = upd.select("s.*").select(*cols)
            keep = t.join(upd.alias("u"), F.expr(self.cond.replace("s.", "u.")), "left_anti")
            parts += [keep.select(*cols), upd]
        else:
            parts.append(t.select(*cols))
        if self.do_insert:
            parts.append(s.join(t, on, "left_anti").select("s.*").select(*cols))
        out = parts[0]
        for p in parts[1:]:
            out = out.unionByName(p)
        _overwrite(self.spark, self.name, out)


class _DeltaTable:
    def __init__(self, spark, name):
        self.spark, self.name, self._alias = spark, name, "t"

    @classmethod
    def forName(cls, spark, name):
        return cls(getattr(spark, "_real", spark), name)

    def alias(self, a):
        self._alias = a
        return self

    def merge(self, source, cond):
        return _MergeBuilder(self.spark, self.name, self.spark.table(self.name).alias(self._alias), source, cond)


sys.modules["delta"] = types.ModuleType("delta")
sys.modules["delta.tables"] = types.SimpleNamespace(DeltaTable=_DeltaTable)


class SparkShim:
    """Delegates to the real SparkSession but runs DELETE / UPDATE against Parquet tables."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, item):
        return getattr(self._real, item)

    def sql(self, q):
        q1 = " ".join(q.split())
        m = re.match(r"DELETE FROM (\w+) WHERE (.+)$", q1, re.I)
        if m:
            name, cond = m.groups()
            _overwrite(self._real, name, self._real.table(name).where(f"NOT coalesce(({cond}), false)"))
            return None
        m = re.match(r"UPDATE (\w+) SET (.+) WHERE (.+)$", q1, re.I)
        if m:
            name, sets, cond = m.groups()
            df = self._real.table(name)
            for a in re.split(r",\s*(?=\w+\s*=)", sets):
                col, val = a.split("=", 1)
                df = df.withColumn(col.strip(), F.when(F.expr(cond), F.expr(val.strip())).otherwise(F.col(col.strip())))
            _overwrite(self._real, name, df)
            return None
        return self._real.sql(q)


class _Info:
    def __init__(self, p: Path):
        self.name, self.path, self.isDir = p.name + ("/" if p.is_dir() else ""), str(p), p.is_dir()


def make_notebookutils():
    def ls(path):
        return [_Info(p) for p in sorted(Path(path).iterdir())]

    def head(path, n=100000):
        return Path(path).read_text()[:n]

    def exit_(value):
        raise NotebookExit(value)

    return types.SimpleNamespace(fs=types.SimpleNamespace(ls=ls, head=head),
                                 notebook=types.SimpleNamespace(exit=exit_))


def run(nb: str, spark, overrides: dict):
    path = next((ROOT / "notebooks").glob(f"{nb}*.py"))
    text = path.read_text()
    parts = re.split(r"^# %%(.*)$", text, flags=re.M)
    g = {"spark": SparkShim(spark), "notebookutils": make_notebookutils(), "display": lambda df: df.show(30, truncate=False),
         "__name__": "__main__"}
    print(f"\n========== {path.name}")
    for header, body in zip(parts[1::2], parts[2::2]):
        if "[markdown]" in header:
            continue
        if body.strip().startswith("%%configure"):
            continue
        if "refreshMetadata" in body:      # Fabric REST call (SQL endpoint sync) - nothing to sync locally
            print("skipped: SQL endpoint sync (Fabric only)")
            continue
        body = "\n".join(l for l in body.splitlines() if not l.strip().startswith("%pip"))
        try:
            exec(compile(body, str(path), "exec"), g)
        except NotebookExit as e:
            print("EXIT:", e)
            return str(e)
        if "parameters" in header:
            for k, v in overrides.items():
                g[k] = type(g[k])(v) if not isinstance(g[k], bool) else v.lower() == "true"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--landing", required=True, type=Path)
    ap.add_argument("--work", required=True, type=Path)
    ap.add_argument("--param", action="append", default=[])
    ap.add_argument("notebooks", nargs="+")
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    files = a.work / "Files"
    files.mkdir(exist_ok=True)
    link = files / "landing"
    if not link.exists():
        link.symlink_to(a.landing.resolve())
    os.chdir(a.work)
    builder = (SparkSession.builder.master("local[2]").appName("local-fabric")
               .config("spark.sql.shuffle.partitions", "4")
               .config("spark.sql.session.timeZone", "UTC")
               .config("spark.driver.memory", "3g")
               .enableHiveSupport())
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    params = {}
    for p in a.param:
        key, val = p.split("=", 1)
        nb, name = key.split(".", 1)
        params.setdefault(nb, {})[name] = val
    for nb in a.notebooks:
        run(nb, spark, params.get(nb, {}))


if __name__ == "__main__":
    main()
