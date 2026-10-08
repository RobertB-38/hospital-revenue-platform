# Report pages

Report name: **Ardmore Hospital Performance**. Built in the Power BI web editor on the Direct Lake semantic model.
Every page header shows: *"Synthetic data – Ardmore Health is fictional. All financial figures are synthetic."*

Common slicers (top of each page, synced): **Month** (`gold_dim_date[month_label]`, single select), **Site** (`gold_dim_site[site_name]`).

| # | Page | Question it answers | Visuals |
|---|---|---|---|
| 1 | **Executive summary** | How did the month go? | Cards: Net Revenue, Budget Variance %, Contribution Margin %, Debtor Days, Inpatient Discharges, Readmission Rate 30d · Line chart: Net Revenue and Budget Net Revenue by `month_start` (last 12 months) · Card: Month-end Status |
| 2 | **Revenue cycle & debtors** | How much are we owed, by whom, and for how long? | Stacked bar: Debtors Balance by `payer_name`, legend `ageing_band` (sorted by `ageing_band_sort`) · Cards: Debtors Balance, Debtors over 90 Days %, Avg Days to Insurer Payment, Write-off Rate · Line: Cash Collected vs Charges Posted by month |
| 3 | **Payer mix** | Who pays us, and is it shifting? | Donut: Payer Mix % by payer · 100% stacked column: Net Revenue by month, legend payer · Table: payer, Net Revenue, Payer Mix %, Avg Days to Insurer Payment, Write-off Rate |
| 4 | **Service line profitability** | Which services make or lose money? | Bar: Contribution Margin by `service_line_name` · Table: service line, Encounters, Net Revenue per Case, Cost per Case, Contribution Margin % (conditional formatting: red below 10%) · Scatter: Net Revenue (x) vs Contribution Margin % (y), size Encounters |
| 5 | **Budget, actual & forecast** | Are we on budget, and where is the year heading? | Line: Net Revenue, Budget Net Revenue, Forecast Net Revenue with Forecast Low 80/High 80 (error band) by month · Matrix: rows site → service line, values Net Revenue, Budget Net Revenue, Budget Variance, Budget Variance % · Card: Net Revenue YTD, Net Revenue YoY % |
| 6 | **Clinical throughput** | How busy are we, and how well do patients flow? | Column: Encounters by month, legend `encounter_type_name` · Cards: Average Length of Stay, Readmission Rate 30d, Day Cases · Bar: Average Length of Stay by service line · Bar: Encounters by `age_band` |
| 7 | **Month-end control** | Can the month-end pack be released? | Card: Month-end Status · Table from `gold_monthend_check`: check_name, severity, expected, actual, difference, status (status coloured: PASS green, WARN amber, FAIL red) · Card: Month-end Checks Failed |

Notes for building
- Do **not** put a payer slicer on page 5: the budget is set by site and service line, not by payer.
- Page 2 uses month-end balances. **Debtors Balance** already picks the last month-end in the selection, so a year filter shows the year-end balance, not a sum of twelve months.
- Use **Format → Conditional formatting** on Budget Variance (green above 0, red below 0).
