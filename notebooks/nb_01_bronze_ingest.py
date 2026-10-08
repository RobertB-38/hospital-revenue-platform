# %% [markdown]
# # 01 · Bronze ingest (landing files → bronze Delta tables)
#
# **What it does:** finds export batches in `Files/landing/his_export/` that have not been loaded yet,
# checks every file against the batch manifest (row counts and control totals), and appends the rows
# to bronze tables *exactly as received* (all columns kept as text). Also reloads the reference files.
#
# **Why:** bronze is the audit copy. If a number is ever questioned we can trace it back to the file
# and batch it came from. A batch whose files do not match its manifest is rejected and the run fails,
# so bad extracts never reach finance reports.
#
# All data is synthetic. The export imitates a hospital-system flat file; it is not MEDITECH.

# %% [markdown]
# Sets `lh_hospital` as this notebook's default lakehouse, so relative paths like `Files/...` and table
# names work without attaching the lakehouse by hand. It must stay the first code cell.

# %%
%%configure -f
{"defaultLakehouse": {"name": "lh_hospital"}}

# %% tags=["parameters"]
batch_id = "auto"        # "auto" = every batch folder not yet loaded; or e.g. "202509" to (re)load one batch
landing_root = "Files/landing/his_export"
reference_root = "Files/landing/reference"

# %%
import json
import uuid
from datetime import datetime, timezone
from pyspark.sql import functions as F
from pyspark.sql import types as T

run_id = str(uuid.uuid4())
run_ts = datetime.now(timezone.utc)
ENTITIES = {"PATIENT": "bronze_patient", "VISIT": "bronze_visit", "TXN": "bronze_txn"}

log_schema = T.StructType([
    T.StructField("batch_id", T.StringType()), T.StructField("file_name", T.StringType()),
    T.StructField("manifest_rows", T.LongType()), T.StructField("loaded_rows", T.LongType()),
    T.StructField("manifest_amount", T.DoubleType()), T.StructField("loaded_amount", T.DoubleType()),
    T.StructField("status", T.StringType()), T.StructField("message", T.StringType()),
    T.StructField("run_id", T.StringType()), T.StructField("loaded_at", T.TimestampType()),
])
if not spark.catalog.tableExists("etl_batch_log"):
    spark.createDataFrame([], log_schema).write.format("delta").saveAsTable("etl_batch_log")

# %% [markdown]
# ## Reference files (small, reloaded every run)

# %%
ref_files = {
    "ref_payer": "payer.csv", "ref_site": "site.csv", "ref_service_line": "service_line.csv",
    "ref_service_line_map": "service_line_map.csv", "ref_budget": "budget.csv",
    "ref_security_user_site": "security_user_site.csv",
}
for table, fname in ref_files.items():
    df = spark.read.option("header", True).option("inferSchema", True).csv(f"{reference_root}/{fname}")
    df.write.format("delta").mode("overwrite").option("overwriteSchema", True).saveAsTable(table)
    print(f"{table}: {df.count()} rows")

# %% [markdown]
# ## Work out which batches to load

# %%
available = sorted(f.name.strip("/") for f in notebookutils.fs.ls(landing_root) if f.isDir)
loaded = {r.batch_id for r in spark.sql(
    "SELECT DISTINCT batch_id FROM etl_batch_log WHERE status = 'LOADED'").collect()}

if batch_id == "auto":
    to_load = [b for b in available if b not in loaded]
else:
    if batch_id not in available:
        raise ValueError(f"Batch {batch_id} not found in {landing_root}")
    to_load = [batch_id]
print(f"Available: {len(available)}  already loaded: {len(loaded)}  to load now: {to_load}")

# %% [markdown]
# ## Load each batch, checking it against its manifest

# %%
def load_batch(b: str) -> None:
    folder = f"{landing_root}/{b}"
    manifest = json.loads(notebookutils.fs.head(f"{folder}/MANIFEST_{b}.json", 1_000_000))
    log_rows, frames = [], {}
    for entry in manifest["files"]:
        fname = entry["file"]
        entity = fname.split("_")[0]
        df = (spark.read.option("header", True).option("inferSchema", False).csv(f"{folder}/{fname}")
              .withColumn("_batch_id", F.lit(b))
              .withColumn("_source_file", F.lit(fname))
              .withColumn("_load_ts", F.lit(run_ts))
              .withColumn("_run_id", F.lit(run_id)))
        rows = df.count()
        amt = None
        if "control_total_amount" in entry:
            amt = float(df.agg(F.sum(F.col("AMOUNT").cast("decimal(18,2)"))).first()[0] or 0)
        ok = rows == entry["row_count"] and (amt is None or abs(amt - entry["control_total_amount"]) < 0.01)
        msg = "" if ok else f"rows {rows} vs manifest {entry['row_count']}; amount {amt} vs {entry.get('control_total_amount')}"
        log_rows.append((b, fname, entry["row_count"], rows, entry.get("control_total_amount"), amt,
                         "LOADED" if ok else "REJECTED", msg, run_id, run_ts))
        frames[entity] = df

    if any(r[6] == "REJECTED" for r in log_rows):
        spark.createDataFrame(log_rows, log_schema).write.format("delta").mode("append").saveAsTable("etl_batch_log")
        raise Exception(f"Batch {b} rejected - files do not match manifest: {[r[7] for r in log_rows if r[7]]}")

    for entity, df in frames.items():
        table = ENTITIES[entity]
        if spark.catalog.tableExists(table):          # re-running a batch replaces it, never doubles it
            spark.sql(f"DELETE FROM {table} WHERE _batch_id = '{b}'")
        df.write.format("delta").mode("append").option("mergeSchema", True).saveAsTable(table)
    spark.createDataFrame(log_rows, log_schema).write.format("delta").mode("append").saveAsTable("etl_batch_log")
    print(f"Batch {b} loaded: " + ", ".join(f"{r[1]}={r[3]}" for r in log_rows))

for b in to_load:
    load_batch(b)

# %%
notebookutils.notebook.exit(json.dumps({"run_id": run_id, "batches_loaded": to_load}))
