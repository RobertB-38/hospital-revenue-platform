"""Single source of truth for the Power BI semantic model: tables, relationships, measures and security roles.

Used by notebooks/nb_06_semantic_model (which builds the model in Fabric) and by
generator/build_docs.py (which writes docs/semantic_model.md). Edit here, not in two places.
"""

MODEL_NAME = "Ardmore Hospital Performance"
LAKEHOUSE = "lh_hospital"

TABLES = [
    "gold_dim_date", "gold_dim_site", "gold_dim_payer", "gold_dim_service_line", "gold_dim_encounter_type",
    "gold_dim_ageing_band", "gold_dim_patient", "gold_fact_encounter", "gold_fact_transaction",
    "gold_fact_ar_snapshot", "gold_fact_budget", "gold_fact_forecast", "gold_monthend_check", "gold_sec_user_site",
]

# (from_table [many side], from_column, to_table [one side], to_column)
RELATIONSHIPS = [
    ("gold_fact_encounter", "discharge_date", "gold_dim_date", "date"),
    ("gold_fact_encounter", "site_code", "gold_dim_site", "site_code"),
    ("gold_fact_encounter", "payer_code", "gold_dim_payer", "payer_code"),
    ("gold_fact_encounter", "service_line_code", "gold_dim_service_line", "service_line_code"),
    ("gold_fact_encounter", "encounter_type_code", "gold_dim_encounter_type", "encounter_type_code"),
    ("gold_fact_encounter", "patient_key", "gold_dim_patient", "patient_key"),
    ("gold_fact_transaction", "posting_date", "gold_dim_date", "date"),
    ("gold_fact_transaction", "site_code", "gold_dim_site", "site_code"),
    ("gold_fact_transaction", "payer_code", "gold_dim_payer", "payer_code"),
    ("gold_fact_transaction", "service_line_code", "gold_dim_service_line", "service_line_code"),
    ("gold_fact_transaction", "encounter_type_code", "gold_dim_encounter_type", "encounter_type_code"),
    ("gold_fact_ar_snapshot", "snapshot_date", "gold_dim_date", "date"),
    ("gold_fact_ar_snapshot", "site_code", "gold_dim_site", "site_code"),
    ("gold_fact_ar_snapshot", "payer_code", "gold_dim_payer", "payer_code"),
    ("gold_fact_ar_snapshot", "service_line_code", "gold_dim_service_line", "service_line_code"),
    ("gold_fact_ar_snapshot", "encounter_type_code", "gold_dim_encounter_type", "encounter_type_code"),
    ("gold_fact_ar_snapshot", "ageing_band", "gold_dim_ageing_band", "ageing_band"),
    ("gold_fact_budget", "month_start", "gold_dim_date", "date"),
    ("gold_fact_budget", "site_code", "gold_dim_site", "site_code"),
    ("gold_fact_budget", "service_line_code", "gold_dim_service_line", "service_line_code"),
    ("gold_fact_forecast", "month_start", "gold_dim_date", "date"),
    ("gold_fact_forecast", "site_code", "gold_dim_site", "site_code"),
    ("gold_monthend_check", "period_end", "gold_dim_date", "date"),
]

EUR = "€#,0;-€#,0;€0"
PCT = "0.0%"
NUM = "#,0"
DEC = "#,0.0"

# (home table, name, DAX, format, display folder, plain-English meaning)
MEASURES = [
    # Activity and clinical
    ("gold_fact_encounter", "Encounters", "SUM ( gold_fact_encounter[encounter_count] )", NUM, "Activity",
     "Number of visits (all types)."),
    ("gold_fact_encounter", "Inpatient Discharges",
     'CALCULATE ( [Encounters], gold_fact_encounter[encounter_type_code] = "IP" )', NUM, "Activity",
     "Inpatient stays discharged in the period."),
    ("gold_fact_encounter", "Day Cases",
     'CALCULATE ( [Encounters], gold_fact_encounter[encounter_type_code] = "DC" )', NUM, "Activity",
     "Day-case procedures in the period."),
    ("gold_fact_encounter", "Average Length of Stay",
     'CALCULATE ( AVERAGE ( gold_fact_encounter[los_nights] ), gold_fact_encounter[encounter_type_code] = "IP" )',
     DEC, "Activity", "Average nights per inpatient stay (minimum 1)."),
    ("gold_fact_encounter", "Readmission Rate 30d",
     'DIVIDE ( CALCULATE ( SUM ( gold_fact_encounter[readmitted_within_30d] ), '
     'gold_fact_encounter[encounter_type_code] = "IP" ), [Inpatient Discharges] )', PCT, "Activity",
     "Share of inpatient discharges followed by another inpatient admission within 30 days."),
    # Accrual revenue and margin
    ("gold_fact_encounter", "Gross Charges", "SUM ( gold_fact_encounter[gross_charges] )", EUR, "Revenue",
     "Total billed at list price for visits discharged in the period."),
    ("gold_fact_encounter", "Net Revenue", "SUM ( gold_fact_encounter[expected_net_revenue] )", EUR, "Revenue",
     "Gross charges less the expected insurer contractual discount. Recognised at discharge."),
    ("gold_fact_encounter", "Direct Cost", "SUM ( gold_fact_encounter[synthetic_direct_cost] )", EUR, "Revenue",
     "Synthetic direct cost (gross charges x service-line cost ratio)."),
    ("gold_fact_encounter", "Contribution Margin", "[Net Revenue] - [Direct Cost]", EUR, "Revenue",
     "Net revenue less direct cost."),
    ("gold_fact_encounter", "Contribution Margin %", "DIVIDE ( [Contribution Margin], [Net Revenue] )", PCT, "Revenue",
     "Contribution margin as a share of net revenue."),
    ("gold_fact_encounter", "Net Revenue per Case", "DIVIDE ( [Net Revenue], [Encounters] )", EUR, "Revenue",
     "Average net revenue per visit."),
    ("gold_fact_encounter", "Cost per Case", "DIVIDE ( [Direct Cost], [Encounters] )", EUR, "Revenue",
     "Average direct cost per visit."),
    ("gold_fact_encounter", "Payer Mix %",
     "DIVIDE ( [Net Revenue], CALCULATE ( [Net Revenue], REMOVEFILTERS ( gold_dim_payer ) ) )", PCT, "Revenue",
     "Each payer's share of net revenue."),
    ("gold_fact_encounter", "Net Revenue YTD", "TOTALYTD ( [Net Revenue], gold_dim_date[date] )", EUR, "Revenue",
     "Net revenue from 1 January to the end of the selected period."),
    ("gold_fact_encounter", "Net Revenue PY", "CALCULATE ( [Net Revenue], SAMEPERIODLASTYEAR ( gold_dim_date[date] ) )",
     EUR, "Revenue", "Net revenue in the same period last year."),
    ("gold_fact_encounter", "Net Revenue YoY %", "DIVIDE ( [Net Revenue] - [Net Revenue PY], [Net Revenue PY] )", PCT,
     "Revenue", "Change versus the same period last year."),
    # Budget and forecast
    ("gold_fact_budget", "Budget Net Revenue", "SUM ( gold_fact_budget[budget_net_revenue] )", EUR, "Budget",
     "Synthetic budgeted net revenue."),
    ("gold_fact_budget", "Budget Direct Cost", "SUM ( gold_fact_budget[budget_direct_cost] )", EUR, "Budget",
     "Synthetic budgeted direct cost."),
    ("gold_fact_budget", "Budget Variance", "[Net Revenue] - [Budget Net Revenue]", EUR, "Budget",
     "Actual net revenue minus budget. Positive = ahead of budget."),
    ("gold_fact_budget", "Budget Variance %", "DIVIDE ( [Budget Variance], [Budget Net Revenue] )", PCT, "Budget",
     "Variance as a share of budget."),
    ("gold_fact_budget", "Cost Variance", "[Budget Direct Cost] - [Direct Cost]", EUR, "Budget",
     "Budgeted cost minus actual cost. Positive = spent less than budget."),
    ("gold_fact_forecast", "Forecast Net Revenue", "SUM ( gold_fact_forecast[forecast_net_revenue] )", EUR, "Budget",
     "Model forecast of net revenue for future months."),
    ("gold_fact_forecast", "Forecast Low 80", "SUM ( gold_fact_forecast[lower_80] )", EUR, "Budget",
     "Lower edge of the 80% forecast range."),
    ("gold_fact_forecast", "Forecast High 80", "SUM ( gold_fact_forecast[upper_80] )", EUR, "Budget",
     "Upper edge of the 80% forecast range."),
    # Cash and revenue cycle
    ("gold_fact_transaction", "Charges Posted", "SUM ( gold_fact_transaction[charge_amount] )", EUR, "Revenue cycle",
     "Charges posted to the ledger in the period."),
    ("gold_fact_transaction", "Cash Collected", "SUM ( gold_fact_transaction[payment_amount] )", EUR, "Revenue cycle",
     "Payments received from insurers and patients in the period."),
    ("gold_fact_transaction", "Contractual Adjustments", "SUM ( gold_fact_transaction[adjustment_amount] )", EUR,
     "Revenue cycle", "Insurer discounts posted in the period."),
    ("gold_fact_transaction", "Write-offs", "SUM ( gold_fact_transaction[writeoff_amount] )", EUR, "Revenue cycle",
     "Denied claims and bad debt written off in the period."),
    ("gold_fact_transaction", "Write-off Rate", "DIVIDE ( [Write-offs], [Charges Posted] )", PCT, "Revenue cycle",
     "Write-offs as a share of charges posted."),
    ("gold_fact_transaction", "Avg Days to Insurer Payment",
     'CALCULATE ( AVERAGE ( gold_fact_transaction[days_since_discharge] ), '
     'gold_fact_transaction[txn_type] = "PAY", gold_fact_transaction[txn_subtype] = "INSURER" )', DEC,
     "Revenue cycle", "Average days from discharge to insurer payment."),
    ("gold_fact_ar_snapshot", "Debtors Balance",
     "VAR LastSnap = CALCULATE ( MAX ( gold_fact_ar_snapshot[snapshot_date] ) )\n"
     "RETURN CALCULATE ( SUM ( gold_fact_ar_snapshot[balance] ), gold_fact_ar_snapshot[snapshot_date] = LastSnap )",
     EUR, "Revenue cycle", "Money still owed at the last month-end in the selected period (not summed across months)."),
    ("gold_fact_ar_snapshot", "Debtors over 90 Days",
     "CALCULATE ( [Debtors Balance], gold_dim_ageing_band[ageing_band_sort] >= 4 )", EUR, "Revenue cycle",
     "Debtors balance older than 90 days from discharge."),
    ("gold_fact_ar_snapshot", "Debtors over 90 Days %", "DIVIDE ( [Debtors over 90 Days], [Debtors Balance] )", PCT,
     "Revenue cycle", "Share of the debtors balance older than 90 days."),
    ("gold_fact_ar_snapshot", "Debtor Days",
     "VAR LastSnap = CALCULATE ( MAX ( gold_fact_ar_snapshot[snapshot_date] ) )\n"
     "VAR Rev3M = CALCULATE ( [Net Revenue], DATESINPERIOD ( gold_dim_date[date], LastSnap, -3, MONTH ) )\n"
     "RETURN DIVIDE ( [Debtors Balance], DIVIDE ( Rev3M, 91 ) )", DEC, "Revenue cycle",
     "How many days of revenue are sitting unpaid (debtors / average daily net revenue over 3 months)."),
    # Month-end control
    ("gold_monthend_check", "Month-end Checks Failed",
     'CALCULATE ( COUNTROWS ( gold_monthend_check ), gold_monthend_check[status] = "FAIL" ) + 0', NUM, "Control",
     "Number of failed reconciliation checks."),
    ("gold_monthend_check", "Month-end Checks Warned",
     'CALCULATE ( COUNTROWS ( gold_monthend_check ), gold_monthend_check[status] = "WARN" ) + 0', NUM, "Control",
     "Number of checks with a warning."),
    ("gold_monthend_check", "Month-end Status",
     'IF ( COUNTROWS ( gold_monthend_check ) = 0, "NOT RUN", '
     'IF ( [Month-end Checks Failed] > 0, "NOT RELEASED", "RELEASED" ) )', None, "Control",
     "Whether the month-end pack can be released."),
]

# Row-level security: (role, [(table, DAX filter)], description)
ROLES = [
    ("Group Finance", [], "Sees every site."),
    ("Site - Dublin South", [("gold_dim_site", '[site_code] = "DS"')], "Sees Dublin South only."),
    ("Site - Dublin West", [("gold_dim_site", '[site_code] = "DW"')], "Sees Dublin West only."),
    ("Site - Galway", [("gold_dim_site", '[site_code] = "GW"')], "Sees Galway only."),
    ("Site Manager (dynamic)", [
        ("gold_dim_site", "[site_code] IN CALCULATETABLE ( VALUES ( gold_sec_user_site[site_code] ), "
                          "gold_sec_user_site[user_upn] = LOWER ( USERPRINCIPALNAME () ) )"),
        ("gold_sec_user_site", "[user_upn] = LOWER ( USERPRINCIPALNAME () )"),
     ], "Sees only the sites listed for the signed-in user in gold_sec_user_site."),
]
