# %% [markdown]
# # 05 · Net revenue forecast (next 6 months, by site)
#
# Uses monthly **net revenue** (accrual) per site. Model: Holt-Winters exponential smoothing with additive
# trend and 12-month seasonality when there are at least 24 months of history; otherwise a simple linear trend.
# The 80% range comes from the spread of the model's past errors.
#
# This is a planning aid, not a promise. It is shown next to the budget so finance can see where the
# year is heading. All figures are synthetic.

# %% [markdown]
# Sets `lh_hospital` as this notebook's default lakehouse, so relative paths like `Files/...` and table
# names work without attaching the lakehouse by hand. It must stay the first code cell.

# %%
%%configure -f
{"defaultLakehouse": {"name": "lh_hospital"}}

# %% tags=["parameters"]
horizon_months = 6
trained_through = "auto"   # "auto" = last complete month in the data

# %%
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from pyspark.sql import functions as F

fe = spark.table("gold_fact_encounter")
if trained_through == "auto":
    trained_through = str(spark.table("gold_fact_transaction").agg(F.last_day(F.max("posting_date"))).first()[0])
cutoff = pd.Timestamp(trained_through)

monthly = (fe.where(F.col("discharge_date") <= F.lit(trained_through))
             .groupBy("site_code", F.trunc("discharge_date", "month").alias("month_start"))
             .agg(F.sum("expected_net_revenue").cast("double").alias("net_revenue"))
             .toPandas())
monthly["month_start"] = pd.to_datetime(monthly["month_start"])

try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    has_sm = True
except ImportError:
    has_sm = False

rows = []
for site, g in monthly.groupby("site_code"):
    s = g.set_index("month_start")["net_revenue"].asfreq("MS").fillna(0.0)
    future = pd.date_range(s.index[-1] + pd.offsets.MonthBegin(1), periods=horizon_months, freq="MS")
    if has_sm and len(s) >= 24:
        fit = ExponentialSmoothing(s, trend="add", seasonal="add", seasonal_periods=12).fit(optimized=True)
        pred, resid, model = fit.forecast(horizon_months).to_numpy(), (s - fit.fittedvalues).to_numpy(), "Holt-Winters additive"
    else:
        x = np.arange(len(s))
        b, a = np.polyfit(x, s.to_numpy(), 1)
        pred = a + b * np.arange(len(s), len(s) + horizon_months)
        resid, model = s.to_numpy() - (a + b * x), "Linear trend"
    sd = float(np.std(resid))
    for m, p in zip(future, pred):
        rows.append((m.date(), site, float(p), float(p - 1.2816 * sd), float(p + 1.2816 * sd), model))

out = spark.createDataFrame(pd.DataFrame(rows, columns=["month_start", "site_code", "forecast_net_revenue",
                                                        "lower_80", "upper_80", "model"]))
out = (out.withColumn("trained_through", F.to_date(F.lit(trained_through)))
          .withColumn("run_ts", F.lit(datetime.now(timezone.utc)))
          .withColumn("is_synthetic", F.lit("Y")))
for c in ["forecast_net_revenue", "lower_80", "upper_80"]:
    out = out.withColumn(c, F.round(F.col(c), 2).cast("decimal(18,2)"))
out.write.format("delta").mode("overwrite").option("overwriteSchema", True).saveAsTable("gold_fact_forecast")
display(out)
