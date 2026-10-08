# %% [markdown]
# # 03 · Gold (star schema for reporting)
#
# Builds the dimension and fact tables the Power BI model reads in **Direct Lake** mode.
# Gold is rebuilt from silver on every run (the data is small, so a full rebuild is simpler and always consistent).
#
# | Table | Grain | Main use |
# |---|---|---|
# | `gold_fact_encounter` | one row per visit | activity, LOS, readmissions, **accrual revenue** (net revenue, synthetic cost) |
# | `gold_fact_transaction` | one row per ledger posting | **cash view**: charges, payments, contractual adjustments, write-offs |
# | `gold_fact_ar_snapshot` | open visit × month-end | debtors balance and ageing at each month-end |
# | `gold_fact_budget` | site × service line × month | budget vs actual (synthetic budget) |
# | `gold_dim_*` | | date, site, payer, service line, encounter type, patient (pseudonymised), ageing band |
#
# Revenue is recognised at discharge (accrual): gross charges less the expected contractual discount.
# Cash is what was actually received, on the date it was posted. Finance needs both, and they differ by timing.

# %% [markdown]
# Sets `lh_hospital` as this notebook's default lakehouse, so relative paths like `Files/...` and table
# names work without attaching the lakehouse by hand. It must stay the first code cell.

# %%
%%configure -f
{"defaultLakehouse": {"name": "lh_hospital"}}

# %%
from pyspark.sql import functions as F, Window

def save(df, name):
    df.write.format("delta").mode("overwrite").option("overwriteSchema", True).saveAsTable(name)
    print(f"{name}: {spark.table(name).count():,} rows")

visit = spark.table("silver_visit")
txn = spark.table("silver_txn")
payer = spark.table("ref_payer")
sl = spark.table("ref_service_line")

# %% [markdown]
# ## Dimensions

# %%
dates = spark.sql("SELECT explode(sequence(to_date('2023-01-01'), to_date('2027-12-31'), interval 1 day)) AS date")
dim_date = dates.select(
    "date",
    (F.year("date") * 10000 + F.month("date") * 100 + F.dayofmonth("date")).alias("date_key"),
    F.year("date").alias("year"), F.quarter("date").alias("quarter"), F.month("date").alias("month_number"),
    F.date_format("date", "MMMM").alias("month_name"), F.date_format("date", "MMM yyyy").alias("month_label"),
    F.date_format("date", "yyyy-MM").alias("year_month"),
    F.trunc("date", "month").alias("month_start"), F.last_day("date").alias("month_end"),
    (F.col("date") == F.last_day("date")).alias("is_month_end"),
    F.date_format("date", "EEE").alias("weekday"))
save(dim_date, "gold_dim_date")

save(spark.table("ref_site").select("site_code", "site_name", "region", "beds", "is_fictional"), "gold_dim_site")
save(payer.select("payer_code", "payer_name", "payer_type", "contractual_discount_rate", "is_synthetic_assumption"),
     "gold_dim_payer")
save(sl.select("service_line_code", "service_line_name", "direct_cost_ratio", "is_synthetic_assumption"),
     "gold_dim_service_line")
save(spark.createDataFrame([("IP", "Inpatient", 1), ("DC", "Day Case", 2), ("OP", "Outpatient", 3), ("ED", "Emergency", 4)],
                           "encounter_type_code string, encounter_type_name string, sort_order int"),
     "gold_dim_encounter_type")
save(spark.createDataFrame([("0-30", 1), ("31-60", 2), ("61-90", 3), ("91-120", 4), ("120+", 5)],
                           "ageing_band string, ageing_band_sort int"), "gold_dim_ageing_band")
save(spark.table("silver_patient").select("patient_key", "sex", "birth_year", "county"), "gold_dim_patient")
save(spark.table("ref_security_user_site").select(F.lower("user_upn").alias("user_upn"), "site_code"),
     "gold_sec_user_site")

# %% [markdown]
# ## Encounter fact (activity + accrual revenue)

# %%
gross = (txn.where("txn_type = 'CHG'").groupBy("account_no")
            .agg(F.sum("amount").cast("decimal(18,2)").alias("gross_charges")))

e = (visit.join(gross, "account_no", "left").fillna({"gross_charges": 0})
     .join(payer.select("payer_code", "payer_type", "contractual_discount_rate", "ip_excess_eur", "op_excess_eur"),
           "payer_code", "left")
     .join(sl.select("service_line_code", "direct_cost_ratio"), "service_line_code", "left")
     .join(spark.table("silver_patient").select("patient_key", "birth_year"), "patient_key", "left"))

excess = F.when(F.col("payer_type") == "Patient", F.col("gross_charges")).otherwise(
    F.least(F.col("gross_charges"),
            F.when(F.col("encounter_type_code").isin("IP", "DC"), F.col("ip_excess_eur")).otherwise(F.col("op_excess_eur"))))
insurer_part = F.col("gross_charges") - excess
e = (e.withColumn("expected_contractual_adj", F.round(insurer_part * F.col("contractual_discount_rate"), 2))
      .withColumn("expected_net_revenue", F.round(F.col("gross_charges") - F.col("expected_contractual_adj"), 2))
      .withColumn("synthetic_direct_cost", F.round(F.col("gross_charges") * F.col("direct_cost_ratio"), 2)))

# 30-day readmission: an inpatient discharge followed by another inpatient admission within 30 days
ip = e.where("encounter_type_code = 'IP'").select("account_no", "patient_key", "admit_ts", "discharge_ts")
w = Window.partitionBy("patient_key").orderBy("admit_ts")
ip = (ip.withColumn("next_admit", F.lead("admit_ts").over(w))
        .withColumn("prev_discharge", F.lag("discharge_ts").over(w))
        .select("account_no",
                (F.datediff("next_admit", "discharge_ts").between(0, 30)).cast("int").alias("readmitted_within_30d"),
                (F.datediff("admit_ts", "prev_discharge").between(0, 30)).cast("int").alias("is_readmission")))
e = e.join(ip, "account_no", "left").fillna({"readmitted_within_30d": 0, "is_readmission": 0})

age = F.year("admit_ts") - F.col("birth_year")
fact_encounter = e.select(
    F.col("account_no").alias("encounter_id"), "patient_key", "site_code", "payer_code", "service_line_code",
    "encounter_type_code", "consultant_id",
    F.to_date("admit_ts").alias("admit_date"), F.to_date("discharge_ts").alias("discharge_date"),
    F.when(F.col("encounter_type_code") == "IP", F.greatest(F.lit(1), F.datediff(F.to_date("discharge_ts"), F.to_date("admit_ts"))))
     .alias("los_nights"),
    age.alias("age_at_admission"),
    F.when(age < 18, "0-17").when(age < 40, "18-39").when(age < 65, "40-64").when(age < 80, "65-79").otherwise("80+").alias("age_band"),
    F.lit(1).alias("encounter_count"),
    F.col("readmitted_within_30d").cast("int"), F.col("is_readmission").cast("int"),
    F.col("gross_charges").cast("decimal(18,2)"), F.col("expected_contractual_adj").cast("decimal(18,2)"),
    F.col("expected_net_revenue").cast("decimal(18,2)"), F.col("synthetic_direct_cost").cast("decimal(18,2)"),
    "dq_payer_imputed")
save(fact_encounter, "gold_fact_encounter")

# %% [markdown]
# ## Transaction fact (cash and ledger view)

# %%
fe = spark.table("gold_fact_encounter").select("encounter_id", "site_code", "payer_code", "service_line_code",
                                               "encounter_type_code", "discharge_date")
amt = F.col("amount")
fact_txn = (txn.join(fe, txn.account_no == fe.encounter_id)
    .select("txn_id", "encounter_id", "site_code", "service_line_code", "encounter_type_code",
            F.col("payer_code").alias("encounter_payer_code"),
            F.coalesce("txn_payer_code", "payer_code").alias("payer_code"),
            "txn_type", "txn_subtype", "service_code", "service_desc",
            F.to_date("posting_ts").alias("posting_date"),
            F.datediff(F.to_date("posting_ts"), "discharge_date").alias("days_since_discharge"),
            amt.alias("amount"),
            F.when(F.col("txn_type") == "CHG", amt).otherwise(0).cast("decimal(18,2)").alias("charge_amount"),
            F.when(F.col("txn_type") == "PAY", -amt).otherwise(0).cast("decimal(18,2)").alias("payment_amount"),
            F.when(F.col("txn_type") == "ADJ", -amt).otherwise(0).cast("decimal(18,2)").alias("adjustment_amount"),
            F.when(F.col("txn_type") == "WO", -amt).otherwise(0).cast("decimal(18,2)").alias("writeoff_amount")))
save(fact_txn, "gold_fact_transaction")

# %% [markdown]
# ## Debtors (accounts receivable) snapshot at every month-end
# For each visit and each month-end after its discharge: balance = sum of all postings up to that date.
# Only non-zero balances are kept. Ageing is measured from the discharge date.

# %%
ft = spark.table("gold_fact_transaction")
last_month_end = ft.agg(F.last_day(F.max("posting_date"))).first()[0]
month_ends = (spark.sql(f"SELECT explode(sequence(to_date('2024-01-31'), to_date('{last_month_end}'), interval 1 month)) AS m")
              .select(F.last_day("m").alias("snapshot_date")))

moves = (ft.groupBy("encounter_id", F.last_day("posting_date").alias("snapshot_date"))
           .agg(F.sum("amount").alias("movement")))
enc_months = (fe.crossJoin(F.broadcast(month_ends)).where(F.col("snapshot_date") >= F.col("discharge_date")))
w = Window.partitionBy("encounter_id").orderBy("snapshot_date").rowsBetween(Window.unboundedPreceding, 0)
snap = (enc_months.join(moves, ["encounter_id", "snapshot_date"], "left").fillna({"movement": 0})
        .withColumn("balance", F.sum("movement").over(w))
        .where(F.abs("balance") >= 0.01)
        .withColumn("days_outstanding", F.datediff("snapshot_date", "discharge_date"))
        .withColumn("ageing_band", F.when(F.col("days_outstanding") <= 30, "0-30")
                    .when(F.col("days_outstanding") <= 60, "31-60").when(F.col("days_outstanding") <= 90, "61-90")
                    .when(F.col("days_outstanding") <= 120, "91-120").otherwise("120+")))
fact_ar = snap.select("snapshot_date", "encounter_id", "site_code", "payer_code", "service_line_code",
                      "encounter_type_code", "discharge_date", "days_outstanding", "ageing_band",
                      F.col("balance").cast("decimal(18,2)").alias("balance"))
save(fact_ar, "gold_fact_ar_snapshot")

# %% [markdown]
# ## Budget (synthetic)

# %%
save(spark.table("ref_budget").select(
        F.to_date("month_start").alias("month_start"), "site_code", "service_line_code",
        F.col("budget_net_revenue_eur").cast("decimal(18,2)").alias("budget_net_revenue"),
        F.col("budget_direct_cost_eur").cast("decimal(18,2)").alias("budget_direct_cost"),
        F.col("budget_activity").cast("double").alias("budget_activity"), "is_synthetic"),
     "gold_fact_budget")
