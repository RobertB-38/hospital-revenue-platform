# %% [markdown]
# # 04 · Month-end reconciliation checks
#
# Runs before the month-end pack is released. Each check compares two numbers that **must** agree.
# A `FAIL` stops the pipeline, so the month is not closed in the Warehouse and the alert e-mail goes out.
# A `WARN` is reported but does not block the close.
#
# | Check | Rule |
# |---|---|
# | Manifest vs bronze | every loaded file matched its manifest row count and control total |
# | Bronze vs gold charges | charges received (after removing duplicate rows and quarantined rows) = charges in gold |
# | Ledger identity | charges − payments − adjustments − write-offs = debtors balance at month-end |
# | Every encounter has a payer and a service line | no blanks in the dimensions finance reports on |
# | No duplicate transactions in gold | `txn_id` is unique |
# | Expected vs actual contractual discount (WARN) | settled insurer accounts: expected discount ≈ posted discount |
# | Budget coverage (WARN) | every site × service line with activity in the month has a budget |
# | Quarantine rate (WARN) | quarantined rows below 0.5% of rows received |

# %% [markdown]
# Sets `lh_hospital` as this notebook's default lakehouse, so relative paths like `Files/...` and table
# names work without attaching the lakehouse by hand. It must stay the first code cell.

# %%
%%configure -f
{"defaultLakehouse": {"name": "lh_hospital"}}

# %% tags=["parameters"]
period_end = "auto"   # "auto" = last complete month in the data, or e.g. "2026-08-31"

# %%
import json
from datetime import datetime, timezone
from pyspark.sql import functions as F

run_ts = datetime.now(timezone.utc)
ft = spark.table("gold_fact_transaction")
if period_end == "auto":
    period_end = str(ft.agg(F.last_day(F.max("posting_date"))).first()[0])
pe = F.to_date(F.lit(period_end))
print("Checking period ending", period_end)
results = []

def check(name, expected, actual, severity="FAIL", tolerance=0.01):
    expected, actual = float(expected or 0), float(actual or 0)
    diff = round(actual - expected, 2)
    status = "PASS" if abs(diff) <= tolerance else severity
    level = "Blocking" if severity == "FAIL" else "Warning"
    results.append((period_end, name, level, expected, actual, diff, status, run_ts))

# 1. manifest vs bronze
bad = spark.sql("SELECT COUNT(*) FROM etl_batch_log WHERE status = 'REJECTED' "
                "AND batch_id NOT IN (SELECT batch_id FROM etl_batch_log WHERE status = 'LOADED')").first()[0]
check("Manifest vs bronze: rejected batches", 0, bad)

# 2. bronze vs gold charges, up to the period end
bronze_chg = (spark.table("bronze_txn").dropDuplicates(["TXN_ID"])
              .where((F.col("TXN_TYPE") == "CHG") & (F.to_date(F.to_timestamp("POSTING_DTTM", "yyyy-MM-dd HH:mm:ss")) <= pe))
              .agg(F.sum(F.col("AMOUNT").cast("decimal(18,2)"))).first()[0])
quarantined_chg = 0.0
if spark.catalog.tableExists("silver_quarantine"):
    q = spark.table("silver_quarantine").where("entity = 'txn'")
    quarantined_chg = (q.select(F.from_json("record_json", "TXN_TYPE string, AMOUNT string, POSTING_DTTM string").alias("r"))
                        .where((F.col("r.TXN_TYPE") == "CHG") & (F.to_date(F.substring("r.POSTING_DTTM", 1, 10)) <= pe))
                        .agg(F.sum(F.col("r.AMOUNT").cast("decimal(18,2)"))).first()[0] or 0.0)
gold_chg = ft.where(F.col("posting_date") <= pe).agg(F.sum("charge_amount")).first()[0]
check("Bronze vs gold: charges to period end", float(bronze_chg or 0) - float(quarantined_chg), gold_chg)

# 3. ledger identity at period end
ledger = ft.where(F.col("posting_date") <= pe).agg(
    F.sum("charge_amount").alias("c"), F.sum("payment_amount").alias("p"),
    F.sum("adjustment_amount").alias("a"), F.sum("writeoff_amount").alias("w")).first()
ar = spark.table("gold_fact_ar_snapshot").where(F.col("snapshot_date") == pe).agg(F.sum("balance")).first()[0]
check("Ledger identity: charges - payments - adjustments - write-offs = debtors",
      float(ledger.c) - float(ledger.p) - float(ledger.a) - float(ledger.w), ar)

# 4-5. completeness of the dimensions finance reports on
fe = spark.table("gold_fact_encounter")
check("Encounters without payer", 0, fe.where("payer_code IS NULL").count())
check("Encounters without service line", 0, fe.where("service_line_code IS NULL").count())
check("Encounters with unknown payer code", 0,
      fe.join(spark.table("gold_dim_payer"), "payer_code", "left_anti").count())

# 6. uniqueness
check("Duplicate transaction IDs in gold", 0, ft.count() - ft.select("txn_id").distinct().count())

# 7. expected vs actual contractual discount on settled insurer accounts (WARN)
settled = (spark.table("gold_fact_ar_snapshot").where(F.col("snapshot_date") == pe).select("encounter_id"))
posted_adj = ft.where(F.col("posting_date") <= pe).groupBy("encounter_id").agg(
    F.sum("adjustment_amount").alias("posted"), F.sum("writeoff_amount").alias("wo"))
cmp = (fe.where(F.col("discharge_date") <= pe).join(settled, "encounter_id", "left_anti")
         .join(posted_adj, "encounter_id").where("wo = 0")
         .agg(F.sum("expected_contractual_adj").alias("exp"), F.sum("posted").alias("act"), F.count("*").alias("n")).first())
check("Expected vs posted contractual discount (settled accounts)", cmp.exp, cmp.act,
      severity="WARN", tolerance=0.01 * max(int(cmp.n or 0), 1))

# 8. budget coverage for the month (WARN)
month_start = F.trunc(pe, "month")
active = fe.where(F.trunc("discharge_date", "month") == month_start).select("site_code", "service_line_code").distinct()
budgeted = spark.table("gold_fact_budget").where(F.col("month_start") == month_start).select("site_code", "service_line_code")
check("Site x service line with activity but no budget", 0, active.join(budgeted, ["site_code", "service_line_code"], "left_anti").count(),
      severity="WARN")

# 9. quarantine rate (WARN)
received = spark.table("bronze_txn").count() + spark.table("bronze_visit").count()
quarantined = spark.table("silver_quarantine").count() if spark.catalog.tableExists("silver_quarantine") else 0
check("Quarantined rows above 0.5% of received", 0, max(0, quarantined - 0.005 * received), severity="WARN", tolerance=0)

# %%
schema = ("period_end string, check_name string, severity string, expected double, actual double, "
          "difference double, status string, run_ts timestamp")
df = spark.createDataFrame(results, schema).withColumn("period_end", F.to_date("period_end"))
if spark.catalog.tableExists("gold_monthend_check"):
    spark.sql(f"DELETE FROM gold_monthend_check WHERE period_end = DATE'{period_end}'")
df.write.format("delta").mode("append").saveAsTable("gold_monthend_check")
display(df)

overall = "FAIL" if any(r[6] == "FAIL" for r in results) else "PASS"
print("Overall:", overall)
notebookutils.notebook.exit(json.dumps({"period_end": period_end, "status": overall}))
