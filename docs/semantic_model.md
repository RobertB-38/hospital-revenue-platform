# Semantic model: Ardmore Hospital Performance

Direct Lake model on the gold tables of `lh_hospital`. Generated from `semantic_model/model_spec.py`.

## Relationships (many → one, single direction)

| From (many) | To (one) |
|---|---|
| `gold_fact_encounter[discharge_date]` | `gold_dim_date[date]` |
| `gold_fact_encounter[site_code]` | `gold_dim_site[site_code]` |
| `gold_fact_encounter[payer_code]` | `gold_dim_payer[payer_code]` |
| `gold_fact_encounter[service_line_code]` | `gold_dim_service_line[service_line_code]` |
| `gold_fact_encounter[encounter_type_code]` | `gold_dim_encounter_type[encounter_type_code]` |
| `gold_fact_encounter[patient_key]` | `gold_dim_patient[patient_key]` |
| `gold_fact_transaction[posting_date]` | `gold_dim_date[date]` |
| `gold_fact_transaction[site_code]` | `gold_dim_site[site_code]` |
| `gold_fact_transaction[payer_code]` | `gold_dim_payer[payer_code]` |
| `gold_fact_transaction[service_line_code]` | `gold_dim_service_line[service_line_code]` |
| `gold_fact_transaction[encounter_type_code]` | `gold_dim_encounter_type[encounter_type_code]` |
| `gold_fact_ar_snapshot[snapshot_date]` | `gold_dim_date[date]` |
| `gold_fact_ar_snapshot[site_code]` | `gold_dim_site[site_code]` |
| `gold_fact_ar_snapshot[payer_code]` | `gold_dim_payer[payer_code]` |
| `gold_fact_ar_snapshot[service_line_code]` | `gold_dim_service_line[service_line_code]` |
| `gold_fact_ar_snapshot[encounter_type_code]` | `gold_dim_encounter_type[encounter_type_code]` |
| `gold_fact_ar_snapshot[ageing_band]` | `gold_dim_ageing_band[ageing_band]` |
| `gold_fact_budget[month_start]` | `gold_dim_date[date]` |
| `gold_fact_budget[site_code]` | `gold_dim_site[site_code]` |
| `gold_fact_budget[service_line_code]` | `gold_dim_service_line[service_line_code]` |
| `gold_fact_forecast[month_start]` | `gold_dim_date[date]` |
| `gold_fact_forecast[site_code]` | `gold_dim_site[site_code]` |
| `gold_monthend_check[period_end]` | `gold_dim_date[date]` |

## Measures

### Activity

**Encounters** (home table `gold_fact_encounter`, format `#,0`): Number of visits (all types).

```dax
Encounters =
SUM ( gold_fact_encounter[encounter_count] )
```

**Inpatient Discharges** (home table `gold_fact_encounter`, format `#,0`): Inpatient stays discharged in the period.

```dax
Inpatient Discharges =
CALCULATE ( [Encounters], gold_fact_encounter[encounter_type_code] = "IP" )
```

**Day Cases** (home table `gold_fact_encounter`, format `#,0`): Day-case procedures in the period.

```dax
Day Cases =
CALCULATE ( [Encounters], gold_fact_encounter[encounter_type_code] = "DC" )
```

**Average Length of Stay** (home table `gold_fact_encounter`, format `#,0.0`): Average nights per inpatient stay (minimum 1).

```dax
Average Length of Stay =
CALCULATE ( AVERAGE ( gold_fact_encounter[los_nights] ), gold_fact_encounter[encounter_type_code] = "IP" )
```

**Readmission Rate 30d** (home table `gold_fact_encounter`, format `0.0%`): Share of inpatient discharges followed by another inpatient admission within 30 days.

```dax
Readmission Rate 30d =
DIVIDE ( CALCULATE ( SUM ( gold_fact_encounter[readmitted_within_30d] ), gold_fact_encounter[encounter_type_code] = "IP" ), [Inpatient Discharges] )
```

### Revenue

**Gross Charges** (home table `gold_fact_encounter`, format `€#,0;-€#,0;€0`): Total billed at list price for visits discharged in the period.

```dax
Gross Charges =
SUM ( gold_fact_encounter[gross_charges] )
```

**Net Revenue** (home table `gold_fact_encounter`, format `€#,0;-€#,0;€0`): Gross charges less the expected insurer contractual discount. Recognised at discharge.

```dax
Net Revenue =
SUM ( gold_fact_encounter[expected_net_revenue] )
```

**Direct Cost** (home table `gold_fact_encounter`, format `€#,0;-€#,0;€0`): Synthetic direct cost (gross charges x service-line cost ratio).

```dax
Direct Cost =
SUM ( gold_fact_encounter[synthetic_direct_cost] )
```

**Contribution Margin** (home table `gold_fact_encounter`, format `€#,0;-€#,0;€0`): Net revenue less direct cost.

```dax
Contribution Margin =
[Net Revenue] - [Direct Cost]
```

**Contribution Margin %** (home table `gold_fact_encounter`, format `0.0%`): Contribution margin as a share of net revenue.

```dax
Contribution Margin % =
DIVIDE ( [Contribution Margin], [Net Revenue] )
```

**Net Revenue per Case** (home table `gold_fact_encounter`, format `€#,0;-€#,0;€0`): Average net revenue per visit.

```dax
Net Revenue per Case =
DIVIDE ( [Net Revenue], [Encounters] )
```

**Cost per Case** (home table `gold_fact_encounter`, format `€#,0;-€#,0;€0`): Average direct cost per visit.

```dax
Cost per Case =
DIVIDE ( [Direct Cost], [Encounters] )
```

**Payer Mix %** (home table `gold_fact_encounter`, format `0.0%`): Each payer's share of net revenue.

```dax
Payer Mix % =
DIVIDE ( [Net Revenue], CALCULATE ( [Net Revenue], REMOVEFILTERS ( gold_dim_payer ) ) )
```

**Net Revenue YTD** (home table `gold_fact_encounter`, format `€#,0;-€#,0;€0`): Net revenue from 1 January to the end of the selected period.

```dax
Net Revenue YTD =
TOTALYTD ( [Net Revenue], gold_dim_date[date] )
```

**Net Revenue PY** (home table `gold_fact_encounter`, format `€#,0;-€#,0;€0`): Net revenue in the same period last year.

```dax
Net Revenue PY =
CALCULATE ( [Net Revenue], SAMEPERIODLASTYEAR ( gold_dim_date[date] ) )
```

**Net Revenue YoY %** (home table `gold_fact_encounter`, format `0.0%`): Change versus the same period last year.

```dax
Net Revenue YoY % =
DIVIDE ( [Net Revenue] - [Net Revenue PY], [Net Revenue PY] )
```

### Budget

**Budget Net Revenue** (home table `gold_fact_budget`, format `€#,0;-€#,0;€0`): Synthetic budgeted net revenue.

```dax
Budget Net Revenue =
SUM ( gold_fact_budget[budget_net_revenue] )
```

**Budget Direct Cost** (home table `gold_fact_budget`, format `€#,0;-€#,0;€0`): Synthetic budgeted direct cost.

```dax
Budget Direct Cost =
SUM ( gold_fact_budget[budget_direct_cost] )
```

**Budget Variance** (home table `gold_fact_budget`, format `€#,0;-€#,0;€0`): Actual net revenue minus budget. Positive = ahead of budget.

```dax
Budget Variance =
[Net Revenue] - [Budget Net Revenue]
```

**Budget Variance %** (home table `gold_fact_budget`, format `0.0%`): Variance as a share of budget.

```dax
Budget Variance % =
DIVIDE ( [Budget Variance], [Budget Net Revenue] )
```

**Cost Variance** (home table `gold_fact_budget`, format `€#,0;-€#,0;€0`): Budgeted cost minus actual cost. Positive = spent less than budget.

```dax
Cost Variance =
[Budget Direct Cost] - [Direct Cost]
```

**Forecast Net Revenue** (home table `gold_fact_forecast`, format `€#,0;-€#,0;€0`): Model forecast of net revenue for future months.

```dax
Forecast Net Revenue =
SUM ( gold_fact_forecast[forecast_net_revenue] )
```

**Forecast Low 80** (home table `gold_fact_forecast`, format `€#,0;-€#,0;€0`): Lower edge of the 80% forecast range.

```dax
Forecast Low 80 =
SUM ( gold_fact_forecast[lower_80] )
```

**Forecast High 80** (home table `gold_fact_forecast`, format `€#,0;-€#,0;€0`): Upper edge of the 80% forecast range.

```dax
Forecast High 80 =
SUM ( gold_fact_forecast[upper_80] )
```

### Revenue cycle

**Charges Posted** (home table `gold_fact_transaction`, format `€#,0;-€#,0;€0`): Charges posted to the ledger in the period.

```dax
Charges Posted =
SUM ( gold_fact_transaction[charge_amount] )
```

**Cash Collected** (home table `gold_fact_transaction`, format `€#,0;-€#,0;€0`): Payments received from insurers and patients in the period.

```dax
Cash Collected =
SUM ( gold_fact_transaction[payment_amount] )
```

**Contractual Adjustments** (home table `gold_fact_transaction`, format `€#,0;-€#,0;€0`): Insurer discounts posted in the period.

```dax
Contractual Adjustments =
SUM ( gold_fact_transaction[adjustment_amount] )
```

**Write-offs** (home table `gold_fact_transaction`, format `€#,0;-€#,0;€0`): Denied claims and bad debt written off in the period.

```dax
Write-offs =
SUM ( gold_fact_transaction[writeoff_amount] )
```

**Write-off Rate** (home table `gold_fact_transaction`, format `0.0%`): Write-offs as a share of charges posted.

```dax
Write-off Rate =
DIVIDE ( [Write-offs], [Charges Posted] )
```

**Avg Days to Insurer Payment** (home table `gold_fact_transaction`, format `#,0.0`): Average days from discharge to insurer payment.

```dax
Avg Days to Insurer Payment =
CALCULATE ( AVERAGE ( gold_fact_transaction[days_since_discharge] ), gold_fact_transaction[txn_type] = "PAY", gold_fact_transaction[txn_subtype] = "INSURER" )
```

**Debtors Balance** (home table `gold_fact_ar_snapshot`, format `€#,0;-€#,0;€0`): Money still owed at the last month-end in the selected period (not summed across months).

```dax
Debtors Balance =
VAR LastSnap = CALCULATE ( MAX ( gold_fact_ar_snapshot[snapshot_date] ) )
RETURN CALCULATE ( SUM ( gold_fact_ar_snapshot[balance] ), gold_fact_ar_snapshot[snapshot_date] = LastSnap )
```

**Debtors over 90 Days** (home table `gold_fact_ar_snapshot`, format `€#,0;-€#,0;€0`): Debtors balance older than 90 days from discharge.

```dax
Debtors over 90 Days =
CALCULATE ( [Debtors Balance], gold_dim_ageing_band[ageing_band_sort] >= 4 )
```

**Debtors over 90 Days %** (home table `gold_fact_ar_snapshot`, format `0.0%`): Share of the debtors balance older than 90 days.

```dax
Debtors over 90 Days % =
DIVIDE ( [Debtors over 90 Days], [Debtors Balance] )
```

**Debtor Days** (home table `gold_fact_ar_snapshot`, format `#,0.0`): How many days of revenue are sitting unpaid (debtors / average daily net revenue over 3 months).

```dax
Debtor Days =
VAR LastSnap = CALCULATE ( MAX ( gold_fact_ar_snapshot[snapshot_date] ) )
VAR Rev3M = CALCULATE ( [Net Revenue], DATESINPERIOD ( gold_dim_date[date], LastSnap, -3, MONTH ) )
RETURN DIVIDE ( [Debtors Balance], DIVIDE ( Rev3M, 91 ) )
```

### Control

**Month-end Checks Failed** (home table `gold_monthend_check`, format `#,0`): Number of failed reconciliation checks.

```dax
Month-end Checks Failed =
CALCULATE ( COUNTROWS ( gold_monthend_check ), gold_monthend_check[status] = "FAIL" ) + 0
```

**Month-end Checks Warned** (home table `gold_monthend_check`, format `#,0`): Number of checks with a warning.

```dax
Month-end Checks Warned =
CALCULATE ( COUNTROWS ( gold_monthend_check ), gold_monthend_check[status] = "WARN" ) + 0
```

**Month-end Status** (home table `gold_monthend_check`, format `text`): Whether the month-end pack can be released.

```dax
Month-end Status =
IF ( COUNTROWS ( gold_monthend_check ) = 0, "NOT RUN", IF ( [Month-end Checks Failed] > 0, "NOT RELEASED", "RELEASED" ) )
```

## Row-level security roles

| Role | Table | DAX filter | Who |
|---|---|---|---|
| Group Finance | (none) | (none) | Sees every site. |
| Site - Dublin South | `gold_dim_site` | `[site_code] = "DS"` | Sees Dublin South only. |
| Site - Dublin West | `gold_dim_site` | `[site_code] = "DW"` | Sees Dublin West only. |
| Site - Galway | `gold_dim_site` | `[site_code] = "GW"` | Sees Galway only. |
| Site Manager (dynamic) | `gold_dim_site` | `[site_code] IN CALCULATETABLE ( VALUES ( gold_sec_user_site[site_code] ), gold_sec_user_site[user_upn] = LOWER ( USERPRINCIPALNAME () ) )` | Sees only the sites listed for the signed-in user in gold_sec_user_site. |
| Site Manager (dynamic) | `gold_sec_user_site` | `[user_upn] = LOWER ( USERPRINCIPALNAME () )` | Sees only the sites listed for the signed-in user in gold_sec_user_site. |
