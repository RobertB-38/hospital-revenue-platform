# Fabric build guide (step by step)

Follow the steps in order. Each step says what to click, what you should see, and what to do if
something different appears. Work in the **Fabric Demo** Chrome profile, signed in as
`fabricdemo@robertborkar38gmail.onmicrosoft.com`.

Names used everywhere (the code looks them up by name, so type them exactly):

| Thing | Name |
|---|---|
| Fabric workspace | `ardmore-health-dev` |
| Lakehouse | `lh_hospital` |
| Warehouse | `wh_hospital` |
| Pipeline | `pl_daily_load` |
| Semantic model | `Ardmore Hospital Performance` |
| Azure DevOps organisation / project | `fabricdemo0181` / `ardmore-health-demo` |

Time needed: about 90 minutes, most of it waiting for notebooks to run.

---

## Step 1 · Upload the data (10 min)

1. Open the workspace `ardmore-health-dev` → click `lh_hospital`.
2. In the **Explorer** on the left, hover over **Files** → click the **…** → **Upload** → **Upload folder**.
3. On your Mac, choose `PROJECTs/hospital-revenue-platform/data/landing` → **Upload**.
4. Chrome asks "Upload N files to this site?" → **Upload**. Wait until the progress bar finishes (about 2–3 minutes).
5. Click **Files** → you should see `landing`, and inside it `his_export` (30 month folders, 202401–202606) and `reference`.

> The last three months (202607–202609) are kept in `data/landing_next/` on purpose. You upload them in
> Step 6 to prove the pipeline only loads **new** data.

If the folder lands as `Files/his_export` instead of `Files/landing/his_export`: in Explorer, create a new
subfolder `landing` and move both folders into it (… → Move).

## Step 2 · Import the notebooks (5 min)

1. Go back to the workspace (click `ardmore-health-dev` in the left bar).
2. Top bar → **Import** → **Notebook** → **From this computer** → **Upload**.
3. Select all six files in `notebooks/fabric/` (`nb_01_…` to `nb_06_…`) → **Open**.
4. You should see six notebooks in the workspace.

You do **not** need to attach the lakehouse: the first code cell of each notebook (`%%configure`) sets
`lh_hospital` as its default lakehouse.

## Step 3 · Run the notebooks once, by hand (25 min)

Open each notebook and click **Run all**, in this order. Wait for each to finish before opening the next.

| Notebook | What you should see at the end |
|---|---|
| `nb_01_bronze_ingest` | `Batch 202401 loaded…` … `Batch 202606 loaded…`, then an exit value listing 30 batches |
| `nb_02_silver_conform` | row counts for `silver_patient`, `silver_visit`, `silver_txn` and a small data-quality table |
| `nb_03_gold_model` | a row count for every `gold_` table |
| `nb_04_monthend_checks` | a table of 10 checks, all `PASS`, and `Overall: PASS` |
| `nb_05_forecast` | 18 forecast rows (3 sites × 6 months) |

Things that can happen and are normal:
- The first run says **"Starting Spark session"** for 1–3 minutes. That is the trial capacity warming up.
- After `%%configure` the session restarts once. That is expected.
- If a notebook stops with `table or view not found: bronze_visit`, an earlier notebook did not finish. Run the earlier one again.

## Step 4 · Set up the Warehouse (10 min)

1. Workspace → open `wh_hospital` → **New SQL query**.
2. Open `warehouse/01_create_fin_schema.sql` on your Mac, copy everything, paste, **Run**. You should see "Commands completed successfully".
3. New SQL query again → paste `02_usp_close_month.sql` → **Run**.
4. New SQL query again → paste `03_finance_views.sql` → **Run**.
5. Close the month for the first time. New SQL query →
   ```sql
   EXEC fin.usp_close_month @period_end = '2026-06-30';
   SELECT * FROM fin.vw_close_status;
   ```
   You should see one row for 2026-06-30 with `is_locked = 1`.

If you get **"Invalid object name 'lh_hospital.dbo.gold_monthend_check'"**: the Lakehouse SQL endpoint
has not caught up with the new tables yet. Open `lh_hospital` → switch the top-right view to
**SQL analytics endpoint** → click **Refresh**. Wait one minute and run the `EXEC` again.

## Step 5 · Build the pipeline (20 min)

Workspace → **+ New item** → **Data pipeline** (it may be listed as **Pipeline**) → name `pl_daily_load` → **Create** → **Pipeline activity**.

**5a. Parameters.** Click the empty canvas → bottom panel → **Parameters** → **+ New** twice:

| Name | Type | Default value |
|---|---|---|
| `p_batch_id` | String | `auto` |
| `p_period_end` | String | `auto` |

**5b. Four notebook activities in a chain.** Ribbon → **Activities** → **Notebook**, four times. For each one,
set **General → Name** and **Settings → Workspace / Notebook**:

| Activity name | Notebook | Base parameters (Settings → Base parameters → + New) |
|---|---|---|
| `Bronze ingest` | `nb_01_bronze_ingest` | `batch_id` String `@pipeline().parameters.p_batch_id` |
| `Silver conform` | `nb_02_silver_conform` | none |
| `Gold model` | `nb_03_gold_model` | none |
| `Month-end checks` | `nb_04_monthend_checks` | `period_end` String `@pipeline().parameters.p_period_end` |

To type an expression, click the value box → **Add dynamic content** → paste → **OK**.

Connect them: drag the **green tick** (On success) on the right edge of `Bronze ingest` onto `Silver conform`;
the same from `Silver conform` to `Gold model`, and from `Gold model` to `Month-end checks`.

**5c. Forecast.** Add a fifth Notebook activity `Forecast` → `nb_05_forecast`. Connect `Gold model` → (green tick) → `Forecast`.

**5d. Close the month only if the checks pass.** Activities → **If Condition** → name `Checks passed` (no `?`: it is not allowed in activity names).
Connect `Month-end checks` → (green tick) → `Checks passed`. In its **Activities** tab, Expression:
```
@equals(json(activity('Month-end checks').output.result.exitValue).status, 'PASS')
```
Click the pencil on **True** → add **Wait** (name `Wait for SQL endpoint`, 60 seconds), then **Stored procedure**
(name `Close month`) connected after it with the green tick:
- Settings → Connection: `wh_hospital` → Stored procedure name: `fin.usp_close_month`
- **Import** parameters → set `period_end` (String) to
  `@json(activity('Month-end checks').output.result.exitValue).period_end` and `force` (Boolean) to `true`.
Go back to the main canvas (breadcrumb at the top).

`force = true` because the daily run re-closes the latest month as new payments arrive. A month is only
truly frozen once the next month has been closed.

**5e. Failure alert.** Fabric's Outlook activity sends mail **from** the signed-in account, and `fabricdemo` has
no mailbox, so the demo uses a free push notification instead (ntfy.sh, no account needed). In a real
hospital tenant you would swap this one activity for the Office 365 Outlook or Teams activity.

1. On your phone, install the **ntfy** app → **+** → subscribe to a topic with a long random name, e.g. `ardmore-bi-7f3k9q2x`.
2. In the pipeline: Activities → **Web** → name `Alert on failure`. Settings:
   - Connection: **+ New** → URL `https://ntfy.sh` → Authentication **Anonymous** → **Create**.
   - Relative URL: `ardmore-bi-7f3k9q2x` (your topic) · Method: **POST**
   - Body: `@concat('pl_daily_load FAILED. Run ', pipeline().RunId, '. Open Monitor in Fabric.')`
3. Connect `Month-end checks` → `Alert on failure` **twice**: once with the red cross (**On fail**) and once with the grey arrow (**On skip**).
   Two conditions from the same activity mean *fail OR skip*. Because a failure anywhere earlier skips
   `Month-end checks`, this one alert covers every notebook.
4. Inside `Checks passed` → **False** → add another Web activity named `Alert checks failed` (names must be unique) with the
   same connection and body `Month-end checks FAILED - month not closed.`

**5f. Save and test.** Ribbon → **Save** → **Run**. Watch the **Output** tab: every activity should go green
and `Close month` should run. Test the alert: run again with `p_batch_id` = `209901` (a folder that does not exist).
`Bronze ingest` fails, and your phone should buzz.

**5g. Schedule.** Ribbon → **Schedule** → On → Repeat **Daily** → time **06:00** → time zone **Dublin** → **Apply**.

## Step 6 · Prove the incremental load (5 min)

1. In `lh_hospital` → Files → `landing` → `his_export` → **…** → **Upload** → **Upload folder** → choose
   `data/landing_next/his_export/202607` on your Mac. Repeat for `202608` and `202609`.
2. Open `pl_daily_load` → **Run** (keep both parameters `auto`).
3. In the run output, open the `Bronze ingest` activity → **Output** → the exit value lists **only**
   `202607`, `202608`, `202609`. That is your evidence of incremental loading. Screenshot it.
4. `Month-end checks` now checks `2026-09-30` and `Close month` closes September.

## Step 7 · Semantic model, Direct Lake (15 min)

**7A. From code (recommended).** Open `nb_06_semantic_model` → **Run all**. It installs `semantic-link-labs`,
creates the Direct Lake model `Ardmore Hospital Performance`, adds 23 relationships, marks the date table,
adds the measures and the five security roles, then refreshes the model.

Then in the workspace open the model → **Open data model**. Check:
- Top right says **Direct Lake** (storage mode).
- Model view shows the star: facts in the middle, dimensions around them.
- Measures appear under display folders (Activity, Revenue, Budget, Revenue cycle, Control).

**7B. If 7A fails** (the library changes often): `lh_hospital` → **New semantic model** → name
`Ardmore Hospital Performance` → tick the 14 `gold_` tables listed in `semantic_model/model_spec.py` →
**Confirm**. Then **Open data model** and:
- Drag each relationship in `RELATIONSHIPS` (many-side column onto one-side column).
- Select `gold_dim_date` → **Mark as date table** → column `date`.
- For each measure in `docs/semantic_model.md`: select the home table → **New measure** → paste the DAX → set the format.
- **Manage roles** → create the roles from the same document.

## Step 8 · Row-level security test (5 min)

Workspace → semantic model **…** → **Security** → pick role `Site - Galway` → **Test as role**. A report
opens showing Galway only. Screenshot it, then repeat with `Group Finance` (all three sites).
For the dynamic role, edit `data/landing/reference/security_user_site.csv` with a real user's e-mail,
re-upload it, and rerun the pipeline.

## Step 9 · Report pages (30 min)

Open the semantic model → **Create report** → **Create from scratch**. Build the pages in
`docs/report_pages.md`. Put the text **"All financial figures are synthetic"** in the header of every page.
**Save** as `Ardmore Hospital Performance`.

## Step 10 · Azure DevOps (20 min)

**10a. Push the repo.** In DevOps → project `ardmore-health-demo` → **Repos** → **Generate Git credentials** → copy
the password. On your Mac, open **Terminal**:
```bash
cd ~/Desktop/PROJECTs/hospital-revenue-platform
git add -A
git commit -m "Add screenshots and checklist"
git remote add origin https://fabricdemo0181@dev.azure.com/fabricdemo0181/ardmore-health-demo/_git/ardmore-health-demo
git push -u origin main
```
Paste the generated password when asked. (If macOS says *"xcode-select: no developer tools were found"*,
click **Install**, wait about 5 minutes, then run `git push` again.)

**10b. Billing (gives the free build minutes).** Organization settings → **Billing** → **Set up billing** →
your Pay-As-You-Go subscription → **Save**. Leave all paid quantities at 0.

**10c. CI pipeline.** **Pipelines** → **Create pipeline** → **Azure Repos Git** → `ardmore-health-demo` →
**Existing Azure Pipelines YAML file** → branch `main`, path `/azure-pipelines.yml` → **Continue** → **Run**.
It should finish green with 46 tests passed (open the **Tests** tab and screenshot it).
If it says **"No hosted parallelism has been purchased or granted"**, billing from 10b has not applied yet:
wait 30 minutes and click **Rerun**.

**10d. Branch rules.** **Repos** → **Branches** → `main` → **…** → **Branch policies**:
- **Require a minimum number of reviewers** → On → 1 → tick **Allow requestors to approve their own changes** (you are the only user).
- **Build validation** → **+** → pipeline `ardmore-health-demo` → **Save**.
Now `main` only changes through a pull request that passes the tests.

**10e. Connect Fabric to Git (optional, good to show).** Fabric workspace → **Workspace settings** →
**Git integration** → **Azure DevOps** → organisation `fabricdemo0181` → project `ardmore-health-demo` → repo
`ardmore-health-demo` → branch **create new** `fabric-workspace` → folder `fabric` → **Connect and sync**.
Fabric commits the definitions of your notebooks, pipeline and semantic model into that branch.

## Step 11 · Screenshots (the trial ends after 60 days)

Save every screenshot in `docs/screenshots/` with exactly these names. The full checklist, with when to take
each one, is in `docs/screenshots/README.md`.
