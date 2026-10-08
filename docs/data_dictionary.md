# Data dictionary

Tables the Power BI model reads (Lakehouse `lh_hospital`, gold layer). Bronze and silver tables are described in `architecture.md`. **All money columns are synthetic euro amounts.**


## `gold_dim_date`

One row per calendar day, 2023–2027. Marked as the date table.

| Column | Type | Meaning |
|---|---|---|
| `date` | date32[day] | Calendar date (key) |
| `date_key` | int32 | yyyymmdd as integer |
| `year` | int32 |  |
| `quarter` | int32 |  |
| `month_number` | int32 |  |
| `month_name` | string |  |
| `month_label` | string | Text e.g. Sep 2026 |
| `year_month` | string | Text yyyy-MM |
| `month_start` | date32[day] | First day of the month |
| `month_end` | date32[day] | Last day of the month |
| `is_month_end` | bool | True on the last day of a month |
| `weekday` | string |  |

## `gold_dim_site`

Fictional hospital sites.

| Column | Type | Meaning |
|---|---|---|
| `site_code` | string | DS, DW or GW (key) |
| `site_name` | string |  |
| `region` | string |  |
| `beds` | int32 | Synthetic bed count |
| `is_fictional` | string | Always Y |

## `gold_dim_payer`

Who pays: four Irish insurers, restricted-membership schemes and self-pay.

| Column | Type | Meaning |
|---|---|---|
| `payer_code` | string | Key |
| `payer_name` | string |  |
| `payer_type` | string | Insurer or Patient |
| `contractual_discount_rate` | double | Synthetic discount the insurer takes off the bill |
| `is_synthetic_assumption` | string | Y: rates are invented |

## `gold_dim_service_line`

Clinical service lines used for profitability.

| Column | Type | Meaning |
|---|---|---|
| `service_line_code` | string | Key |
| `service_line_name` | string |  |
| `direct_cost_ratio` | double | Synthetic share of charges that is direct cost |
| `is_synthetic_assumption` | string |  |

## `gold_dim_encounter_type`

Inpatient, Day Case, Outpatient, Emergency.

| Column | Type | Meaning |
|---|---|---|
| `encounter_type_code` | string |  |
| `encounter_type_name` | string |  |
| `sort_order` | int32 |  |

## `gold_dim_ageing_band`

Debtor ageing buckets with a sort order.

| Column | Type | Meaning |
|---|---|---|
| `ageing_band` | string |  |
| `ageing_band_sort` | int32 | 1 = 0-30 days … 5 = 120+ days |

## `gold_dim_patient`

Pseudonymised patient. No name, address, full date of birth or membership number.

| Column | Type | Meaning |
|---|---|---|
| `patient_key` | string | Salted SHA-256 of the hospital MRN |
| `sex` | string |  |
| `birth_year` | int32 | Year only (data minimisation) |
| `county` | string | County of residence |

## `gold_fact_encounter`

One row per visit. Activity, length of stay, readmissions and accrual revenue.

| Column | Type | Meaning |
|---|---|---|
| `encounter_id` | string | Hospital account number (key) |
| `patient_key` | string |  |
| `site_code` | string |  |
| `payer_code` | string |  |
| `service_line_code` | string |  |
| `encounter_type_code` | string |  |
| `consultant_id` | string |  |
| `admit_date` | date32[day] |  |
| `discharge_date` | date32[day] | Date revenue is recognised; joins to gold_dim_date |
| `los_nights` | int32 | Nights in hospital, inpatients only (minimum 1) |
| `age_at_admission` | int32 |  |
| `age_band` | string | 0-17, 18-39, 40-64, 65-79, 80+ |
| `encounter_count` | int32 |  |
| `readmitted_within_30d` | int32 | 1 if this inpatient stay was followed by another inpatient admission within 30 days |
| `is_readmission` | int32 | 1 if this stay started within 30 days of a previous discharge |
| `gross_charges` | decimal(18, 2) | Sum of charge lines (list price) |
| `expected_contractual_adj` | decimal(18, 2) | Expected insurer discount |
| `expected_net_revenue` | decimal(18, 2) | Gross charges less expected discount (accrual revenue) |
| `synthetic_direct_cost` | decimal(18, 2) | Gross charges × service-line cost ratio (synthetic) |
| `dq_payer_imputed` | bool | True if the payer was missing in the source and filled from the patient record |

## `gold_fact_transaction`

One row per ledger posting. The cash view of the revenue cycle.

| Column | Type | Meaning |
|---|---|---|
| `txn_id` | string |  |
| `encounter_id` | string |  |
| `site_code` | string |  |
| `service_line_code` | string |  |
| `encounter_type_code` | string |  |
| `encounter_payer_code` | string | Primary payer of the visit |
| `payer_code` | string | Who the posting is from (insurer or SELF) |
| `txn_type` | string | CHG charge · PAY payment · ADJ contractual adjustment · WO write-off |
| `txn_subtype` | string | SERVICE, INSURER, PATIENT, CONTRACTUAL, DENIAL, BAD_DEBT |
| `service_code` | string |  |
| `service_desc` | string |  |
| `posting_date` | date32[day] | Date posted to the ledger; joins to gold_dim_date |
| `days_since_discharge` | int32 | Posting date minus discharge date |
| `amount` | decimal(18, 2) | Signed: charges positive, everything else negative. Sum per encounter = balance |
| `charge_amount` | decimal(18, 2) |  |
| `payment_amount` | decimal(18, 2) |  |
| `adjustment_amount` | decimal(18, 2) |  |
| `writeoff_amount` | decimal(18, 2) |  |

## `gold_fact_ar_snapshot`

Debtors ledger: one row per open visit per month-end. Semi-additive: never sum across months.

| Column | Type | Meaning |
|---|---|---|
| `snapshot_date` | date32[day] | Month-end date |
| `encounter_id` | string |  |
| `site_code` | string |  |
| `payer_code` | string |  |
| `service_line_code` | string |  |
| `encounter_type_code` | string |  |
| `discharge_date` | date32[day] |  |
| `days_outstanding` | int32 | Snapshot date minus discharge date |
| `ageing_band` | string | 0-30, 31-60, 61-90, 91-120, 120+ |
| `balance` | decimal(18, 2) | Amount still owed at that month-end |

## `gold_fact_budget`

Synthetic budget by site × service line × month.

| Column | Type | Meaning |
|---|---|---|
| `month_start` | date32[day] |  |
| `site_code` | string |  |
| `service_line_code` | string |  |
| `budget_net_revenue` | decimal(18, 2) | Prior-year same month × 1.05 (2024: 2024 average × 1.03), with noise |
| `budget_direct_cost` | decimal(18, 2) |  |
| `budget_activity` | double | Budgeted visit count |
| `is_synthetic` | string |  |

## `gold_fact_forecast`

Six-month net revenue forecast by site.

| Column | Type | Meaning |
|---|---|---|
| `month_start` | date32[day] |  |
| `site_code` | string |  |
| `forecast_net_revenue` | decimal(18, 2) |  |
| `lower_80` | decimal(18, 2) | Lower edge of 80% range |
| `upper_80` | decimal(18, 2) | Upper edge of 80% range |
| `model` | string | Holt-Winters additive or linear trend |
| `trained_through` | date32[day] |  |
| `run_ts` | timestamp[ns] |  |
| `is_synthetic` | string |  |

## `gold_monthend_check`

Result of every month-end reconciliation check.

| Column | Type | Meaning |
|---|---|---|
| `period_end` | date32[day] |  |
| `check_name` | string |  |
| `severity` | string | Blocking (stops the close) or Warning |
| `expected` | double |  |
| `actual` | double |  |
| `difference` | double |  |
| `status` | string | PASS, FAIL or WARN |
| `run_ts` | timestamp[ns] |  |

## `gold_sec_user_site`

Which user may see which site (dynamic row-level security).

| Column | Type | Meaning |
|---|---|---|
| `user_upn` | string | Lower-case sign-in name |
| `site_code` | string |  |
