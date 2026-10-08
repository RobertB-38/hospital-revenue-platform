# %% [markdown]
# # 02 · Silver (clean, de-duplicate, pseudonymise, conform)
#
# **What it does**
# - Takes only bronze rows from batches newer than the last silver run (incremental), unless `full_refresh` is on.
# - Converts text to proper types, removes duplicate rows, and keeps the latest version of each record.
# - **Pseudonymises patients:** the hospital MRN is replaced by a salted SHA-256 key. Names, address,
#   date of birth and membership number are dropped here and never reach silver or gold (GDPR data minimisation).
# - Fills a missing visit payer from the patient's primary payer and flags it.
# - Maps every visit to a service line using the rules in `ref_service_line_map`.
# - Sends rows that fail a rule to `silver_quarantine` instead of silently dropping them, and writes counts to `silver_dq_log`.

# %% [markdown]
# Sets `lh_hospital` as this notebook's default lakehouse, so relative paths like `Files/...` and table
# names work without attaching the lakehouse by hand. It must stay the first code cell.

# %%
%%configure -f
{"defaultLakehouse": {"name": "lh_hospital"}}

# %% tags=["parameters"]
full_refresh = False
# In production the salt comes from Azure Key Vault, e.g.
# notebookutils.credentials.getSecret("https://<vault>.vault.azure.net/", "pseudo-salt")
pseudo_salt = "demo-salt-change-me"

# %%
from datetime import datetime, timezone
from delta.tables import DeltaTable
from pyspark.sql import functions as F, Window

run_ts = datetime.now(timezone.utc)
TS = "yyyy-MM-dd HH:mm:ss"

def tbl_exists(name): return spark.catalog.tableExists(name)

def blank_to_null(col):
    return F.when(F.trim(F.col(col)) == "", F.lit(None)).otherwise(F.trim(F.col(col)))

if full_refresh:
    for t in ["silver_patient", "silver_visit", "silver_txn", "silver_quarantine", "silver_dq_log", "etl_watermark"]:
        spark.sql(f"DROP TABLE IF EXISTS {t}")

if not tbl_exists("etl_watermark"):
    spark.createDataFrame([("silver", "000000", run_ts)], "layer string, last_batch_id string, updated_at timestamp") \
         .write.format("delta").saveAsTable("etl_watermark")
last_batch = spark.sql("SELECT last_batch_id FROM etl_watermark WHERE layer = 'silver'").first()[0]
new_max = spark.sql("SELECT MAX(_batch_id) FROM bronze_visit").first()[0]
print(f"Silver watermark: {last_batch}  newest bronze batch: {new_max}")

def new_rows(table):
    return spark.table(table).where(F.col("_batch_id") > last_batch)

dq_rows = []
def dq(entity, check, failed, action):
    dq_rows.append((run_ts, entity, check, int(failed), action))

def quarantine(df, entity, key_col, reason):
    out = df.select(F.lit(entity).alias("entity"), F.col(key_col).cast("string").alias("record_key"),
                    F.lit(reason).alias("reason"), F.col("_batch_id").alias("batch_id"),
                    F.to_json(F.struct(*[c for c in df.columns if not c.startswith("_")])).alias("record_json"),
                    F.lit(run_ts).alias("quarantined_at"))
    out.write.format("delta").mode("append").saveAsTable("silver_quarantine")

def latest(df, key, order_col):
    w = Window.partitionBy(key).orderBy(F.col(order_col).desc(), F.col("_batch_id").desc())
    return df.withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn")

# %% [markdown]
# ## Patients — pseudonymise

# %%
pk = lambda c: F.sha2(F.concat(F.lit(pseudo_salt), F.col(c)), 256)

p = new_rows("bronze_patient")
p = latest(p.withColumn("last_updated", F.to_timestamp("LAST_UPDATED", TS)), "MRN", "last_updated")
patients = p.select(
    pk("MRN").alias("patient_key"),
    F.year(F.to_date("DOB")).alias("birth_year"),
    F.col("SEX").alias("sex"),
    F.col("COUNTY").alias("county"),
    F.col("PRIMARY_PAYER_CODE").alias("primary_payer_code"),
    F.to_date(F.to_timestamp("REG_DTTM", TS)).alias("registered_date"),
    "last_updated", F.col("_batch_id").alias("batch_id"))
# SURNAME, FORENAME, DOB, ADDRESS_LINE1, EIRCODE_ROUTING and MEMBERSHIP_NO are deliberately not selected.

if tbl_exists("silver_patient"):
    (DeltaTable.forName(spark, "silver_patient").alias("t")
     .merge(patients.alias("s"), "t.patient_key = s.patient_key")
     .whenMatchedUpdateAll(condition="s.last_updated > t.last_updated")
     .whenNotMatchedInsertAll().execute())
else:
    patients.write.format("delta").saveAsTable("silver_patient")
print("silver_patient rows:", spark.table("silver_patient").count())

# %% [markdown]
# ## Visits — type, de-duplicate, validate, map service line

# %%
sites = [r.site_code for r in spark.table("ref_site").collect()]
v = new_rows("bronze_visit")
v = v.select(
    F.col("ACCOUNT_NO").alias("account_no"), pk("MRN").alias("patient_key"),
    F.col("SITE_CODE").alias("site_code"), F.col("VISIT_TYPE").alias("encounter_type_code"),
    F.to_timestamp("ADMIT_DTTM", TS).alias("admit_ts"), F.to_timestamp("DISCH_DTTM", TS).alias("discharge_ts"),
    F.col("REASON_CODE").alias("reason_code"), F.col("REASON_DESC").alias("reason_desc"),
    F.col("VISIT_DESC").alias("visit_desc"), F.col("CONSULTANT_ID").alias("consultant_id"),
    blank_to_null("PAYER_CODE").alias("payer_code"),
    F.to_timestamp("LAST_UPDATED", TS).alias("last_updated"), "_batch_id")

before = v.count()
v = latest(v, "account_no", "last_updated")
dq("visit", "duplicate_or_superseded_rows", before - v.count(), "kept latest LAST_UPDATED")

bad = v.where((F.col("discharge_ts") < F.col("admit_ts")) | (~F.col("site_code").isin(sites)) |
              (~F.col("encounter_type_code").isin("IP", "DC", "OP", "ED")) | F.col("discharge_ts").isNull())
n_bad = bad.count()
if n_bad:
    quarantine(bad, "visit", "account_no", "invalid dates, site or visit type")
dq("visit", "invalid_dates_site_or_type", n_bad, "quarantined")
v = v.join(bad.select("account_no"), "account_no", "left_anti")

# fill a missing payer from the patient's primary payer, and flag it
pp = spark.table("silver_patient").select("patient_key", F.col("primary_payer_code").alias("_pp"))
v = v.join(pp, "patient_key", "left")
dq("visit", "missing_payer_imputed", v.where(F.col("payer_code").isNull()).count(), "filled from patient primary payer")
v = (v.withColumn("dq_payer_imputed", F.col("payer_code").isNull())
       .withColumn("payer_code", F.coalesce("payer_code", "_pp", F.lit("SELF"))).drop("_pp"))

# service line: lowest priority number whose keyword appears in the reason or visit description
rules = spark.table("ref_service_line_map").select("priority", F.lower("keyword").alias("keyword"), "service_line_code")
txt = v.select("account_no", F.lower(F.concat_ws(" ", "reason_desc", "visit_desc")).alias("_txt"))
hit = (txt.crossJoin(F.broadcast(rules)).where(F.col("_txt").contains(F.col("keyword")))
          .withColumn("_rn", F.row_number().over(Window.partitionBy("account_no").orderBy("priority", "keyword")))
          .where("_rn = 1").select("account_no", "service_line_code"))
v = (v.join(hit, "account_no", "left")
      .withColumn("service_line_code", F.coalesce("service_line_code",
                  F.when(F.col("encounter_type_code") == "ED", "EMR").otherwise("GEN")))
      .withColumn("los_days", F.round((F.unix_timestamp("discharge_ts") - F.unix_timestamp("admit_ts")) / 86400, 2))
      .withColumnRenamed("_batch_id", "batch_id"))

if tbl_exists("silver_visit"):
    (DeltaTable.forName(spark, "silver_visit").alias("t")
     .merge(v.alias("s"), "t.account_no = s.account_no")
     .whenMatchedUpdateAll(condition="s.last_updated > t.last_updated")
     .whenNotMatchedInsertAll().execute())
else:
    v.write.format("delta").saveAsTable("silver_visit")
print("silver_visit rows:", spark.table("silver_visit").count())

# %% [markdown]
# ## Transactions — type, de-duplicate, check every row belongs to a known visit

# %%
t = new_rows("bronze_txn")
t = t.select(
    F.col("TXN_ID").alias("txn_id"), F.col("ACCOUNT_NO").alias("account_no"),
    F.col("TXN_TYPE").alias("txn_type"), F.col("TXN_SUBTYPE").alias("txn_subtype"),
    blank_to_null("PAYER_CODE").alias("txn_payer_code"),
    F.col("SERVICE_CODE").alias("service_code"), F.col("SERVICE_DESC").alias("service_desc"),
    F.col("QTY").cast("int").alias("qty"), F.col("AMOUNT").cast("decimal(18,2)").alias("amount"),
    F.to_timestamp("POSTING_DTTM", TS).alias("posting_ts"), F.col("_batch_id").alias("batch_id"))

before = t.count()
t = t.dropDuplicates(["txn_id"])
dq("txn", "exact_duplicate_txn_id", before - t.count(), "removed")

known = spark.table("silver_visit").select("account_no")
orphans = t.join(known, "account_no", "left_anti")
n_orph = orphans.count()
if n_orph:
    quarantine(orphans.withColumnRenamed("batch_id", "_batch_id"), "txn", "txn_id", "account not found in silver_visit")
dq("txn", "orphan_transactions", n_orph, "quarantined")
bad_type = t.where(~F.col("txn_type").isin("CHG", "PAY", "ADJ", "WO") | F.col("amount").isNull())
dq("txn", "invalid_type_or_amount", bad_type.count(), "quarantined")
if bad_type.count():
    quarantine(bad_type.withColumnRenamed("batch_id", "_batch_id"), "txn", "txn_id", "invalid type or amount")
t = t.join(known, "account_no", "left_semi").join(bad_type.select("txn_id"), "txn_id", "left_anti")

if tbl_exists("silver_txn"):
    (DeltaTable.forName(spark, "silver_txn").alias("t")
     .merge(t.alias("s"), "t.txn_id = s.txn_id").whenNotMatchedInsertAll().execute())
else:
    t.write.format("delta").saveAsTable("silver_txn")
print("silver_txn rows:", spark.table("silver_txn").count())

# %% [markdown]
# ## Data-quality log and watermark

# %%
spark.createDataFrame(dq_rows, "run_ts timestamp, entity string, check_name string, failed_rows long, action string") \
     .withColumn("batch_range", F.lit(f"{last_batch}<b<={new_max}")) \
     .write.format("delta").mode("append").saveAsTable("silver_dq_log")
if new_max:
    spark.sql(f"UPDATE etl_watermark SET last_batch_id = '{new_max}', updated_at = current_timestamp() WHERE layer = 'silver'")
display(spark.createDataFrame(dq_rows, "run_ts timestamp, entity string, check_name string, failed_rows long, action string"))
