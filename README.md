# Hospital Revenue & Performance Platform (Microsoft Fabric)

A working demonstrator of the BI platform a private hospital group needs: hospital-system exports go into a
Fabric Lakehouse (bronze, silver, gold); a parameterised pipeline loads only new data, reconciles it and closes the
month in a Fabric Warehouse; a Direct Lake Power BI model reports activity, revenue cycle, payer mix, service-line
profitability, budget vs actual and forecast, with row-level security; Azure DevOps tests every change.

> **All data is synthetic.** "Ardmore Health" and its three sites are fictional. Patients come from Synthea;
> every money figure is synthetic. The export only imitates a hospital-system flat file. **It is not MEDITECH.**

## The problem it solves

At month end, a hospital's finance figures and activity figures usually come from different extracts, are joined by
hand in Excel, and rarely agree. This project produces finance and activity from **one** pipeline and **proves**
they agree (ten reconciliation checks) before the month is released and locked.

## What is in it

| Area | What was built | Where |
|---|---|---|
| Source simulation | Monthly flat-file export (patients, visits, ledger) with manifest control totals; revenue cycle with insurer discounts, denials, patient excess and bad debt | `generator/` |
| Lakehouse | Bronze (as received, batch log), silver (typed, de-duplicated, pseudonymised, quarantine), gold (star schema) | `notebooks/nb_01`–`nb_03` |
| Incremental ETL | Batch log + watermark: only new months are processed; reruns replace, never double | `nb_01`, `nb_02` |
| Month-end | 10 reconciliation checks; Warehouse procedure freezes and locks the month | `nb_04`, `warehouse/` |
| Forecast | Holt-Winters, 6 months ahead, by site, with an 80% range | `nb_05` |
| Semantic model | Direct Lake, 23 relationships, 37 DAX measures, 5 security roles, built from code | `semantic_model/`, `nb_06` |
| Report | 7 pages: executive, debtors, payer mix, service lines, budget/forecast, throughput, month-end control | `docs/report_pages.md` |
| Pipeline | `pl_daily_load`: parameters, chain, conditional close, failure alert, daily schedule | `docs/fabric_build_guide.md` Step 5 |
| CI/CD | Azure DevOps YAML: 46 tests (T-SQL parse, notebook sync, model checks, 10 SQL data-quality rules, manifest checks); branch policy | `azure-pipelines.yml`, `tests/` |
| Governance | Data dictionary, GDPR/HIQA/HSE note, runbook, architecture | `docs/` |

## Results on the synthetic data (33 months, Jan 2024 – Sep 2026)

| Measure | Value |
|---|---|
| Patients / visits / ledger postings | 5,179 / ~68,000 / ~436,000 |
| Inpatient stays · average length of stay · 30-day readmission rate | 1,281 · 5.1 nights · 22.6% |
| Net revenue per year (synthetic) | about €48m |
| Debtors at 30 Sep 2026 · debtor days · write-off rate | €6.0m · 47 days · 1.7% |
| Month-end checks (Jun and Sep 2026 tested) | 10 of 10 pass; bronze-to-gold charges reconcile to the cent |

## Repository layout

```
generator/          build_staging.py: Synthea output -> monthly hospital-style export (+ budget)
data/landing/       export batches 2024-01 .. 2026-06 + reference files (upload to Fabric)
data/landing_next/  batches 2026-07 .. 2026-09 (upload later to show incremental loading)
notebooks/          nb_01..nb_06 as .py (source) and fabric/*.ipynb (import into Fabric)
warehouse/          T-SQL: fin schema, close procedure, finance views
semantic_model/     model_spec.py: tables, relationships, measures, roles (single source of truth)
tests/              pytest + DuckDB data-quality rules (run in CI)
tools/              build_notebooks.py, run_notebooks_locally.py (test notebooks without Fabric)
docs/               build guide, architecture, data dictionary, semantic model, report pages, runbook,
                    governance note, Copilot answer
azure-pipelines.yml CI pipeline
```

## How to run

1. **Fabric:** follow `docs/fabric_build_guide.md` (about 90 minutes).
2. **Tests locally:** `pip install -r requirements-ci.txt && pytest tests`
3. **Notebooks without Fabric** (Python 3.11, `pip install pyspark==3.5.5 pandas statsmodels pyarrow`):
   `python tools/run_notebooks_locally.py --landing data/landing --work /tmp/lh nb_01 nb_02 nb_03 nb_04 nb_05`
4. **Regenerate the data** (needs Synthea CSV output):
   `python generator/build_staging.py --synthea <synthea>/output/csv --out data/landing`

## Data sources and licences

- Synthea synthetic patient generator, MITRE, Apache-2.0; generated data is public domain.
- Insurer weighting: Health Insurance Authority, *Market Report 2025* (Vhi 48%, Laya 28%, Irish Life Health 20%, Level 1%).
- No MIMIC data is used.
