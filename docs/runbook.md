# Runbook

Who this is for: whoever looks after `pl_daily_load` when it fails, or runs month-end.

## Normal day

- `pl_daily_load` runs at 06:00 (Dublin). It loads any new export folders, rebuilds gold, runs the month-end checks
  for the latest month and re-closes that month in the Warehouse.
- Check: **Monitor** (left bar in Fabric) → latest `pl_daily_load` run is **Succeeded**.
- Nothing new in landing? Bronze loads nothing and everything else still runs. That is fine.

## When the alert arrives

1. Fabric → **Monitor** → open the failed run → find the first red activity → **Output / Error**.
2. Match the error:

| Where it failed | Message contains | Cause | Fix |
|---|---|---|---|
| Bronze ingest | `rejected - files do not match manifest` | Extract incomplete or changed after the manifest was written | Ask the source team to resend the batch. Delete the bad folder from landing, upload the new one, rerun with `p_batch_id` = that batch. |
| Bronze ingest | `not found in Files/landing/his_export` | Wrong `p_batch_id` | Rerun with `p_batch_id` = `auto`. |
| Any notebook, after about 20 seconds | `430` / `TooManyRequestsForCapacity` / `Spark session` | Capacity busy (the last session has not let go of its cores) | Each notebook activity retries 3 times, 3 minutes apart, so this usually fixes itself. If all retries fail, stop open notebook sessions and rerun. On a paid capacity, check it is not paused. |
| Silver conform | `table or view not found: bronze_…` | Bronze never ran successfully | Run `nb_01` first. |
| Month-end checks | `Overall: FAIL` (If condition goes to False) | A reconciliation check failed | Open `gold_monthend_check` for the period; see the section below. |
| Close month | `already closed and locked` | Someone ran it without `force` | Expected for a past month. Only rerun with `@force = 1` if finance agreed to reopen it. |
| Close month | `No month-end checks found for this period` or `Invalid object name 'lh_hospital.dbo…'` | Lakehouse SQL endpoint not yet in sync with the new gold tables | `nb_04` forces this sync now, so it should not happen. If it does: lakehouse → SQL analytics endpoint → **Refresh**, then rerun. |
| Checks passed (If) | `The function 'bool' was invoked with a parameter that is not valid` | The If expression was saved as plain text | Re-enter it through **Add dynamic content**. The box must turn green. |
| Alert on failure | `Invalid datasourceObjectId` | The Web activity connection box holds typed text, not a saved connection | Clear the box and pick the `ntfy-alerts` connection from the dropdown. |

## When a month-end check fails

| Check | What it usually means | What to do |
|---|---|---|
| Bronze vs gold charges | Rows dropped between layers | Look at `silver_quarantine` for the period. If rows are there, fix the source or the rule and rerun silver with `full_refresh = True`. |
| Ledger identity | A posting type is missing from gold or a debtors snapshot is stale | Rerun `nb_03_gold_model`, then the checks. |
| Encounters without payer / service line | New payer code or a new kind of visit | Add the payer to `reference/payer.csv` or a keyword to `reference/service_line_map.csv`, re-upload, rerun. |
| Duplicate transaction IDs | Silver de-duplication bypassed | Rerun silver with `full_refresh = True`. |
| Expected vs posted discount (warning) | Insurer paid at a different rate | Tell finance; update `contractual_discount_rate` if the contract changed. |
| Budget coverage (warning) | Activity in a service line with no budget | Ask finance for a budget line. |

## Month-end (finance calendar)

1. Working day 1: confirm the last export of the month has landed (folder `yyyymm` exists).
2. Run `pl_daily_load` by hand. `Month-end checks` must be `PASS` and `Close month` must succeed.
3. In `wh_hospital`: `SELECT * FROM fin.vw_close_status ORDER BY period_end DESC;` → the month is locked.
4. Share the report's **Month-end control** page with finance. Pack is released only when it says **RELEASED**.
5. Reopening a closed month: only with finance sign-off, `EXEC fin.usp_close_month @period_end = 'yyyy-mm-dd', @force = 1;`
   The `note` column records that it was re-closed.

## Rebuild from scratch

1. Run `nb_02_silver_conform` with `full_refresh = True` (drops silver and the watermark).
2. Run `nb_03`, `nb_04`, `nb_05`. Bronze is the audit copy and is never dropped.

## Lessons from the first runs

- On a trial capacity, notebooks that run one after another fail at random unless they retry. Keep the retries.
- Before reading gold through the SQL endpoint, ask Fabric to sync it and wait for the answer. A fixed Wait of 60 seconds was not enough.
- Text boxes in pipeline activities look the same whether they hold text or an expression. Green means expression.
- Test a failure path on purpose (`p_batch_id = 209901`) before trusting the alert. Mine failed silently the first time.

## Contacts (fill in)

| Role | Name |
|---|---|
| Pipeline owner | |
| Finance sign-off | |
| Source-system team | |
