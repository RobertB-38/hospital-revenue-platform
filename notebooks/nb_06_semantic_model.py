# %% [markdown]
# # 06 · Build the Power BI semantic model (Direct Lake) from code
#
# Creates a **Direct Lake** semantic model on the gold tables of `lh_hospital`, then adds relationships,
# marks the date table, adds every DAX measure and the row-level-security roles.
# Run it once by hand after the first pipeline run (it is not part of the daily pipeline).
#
# Uses the open-source **semantic-link-labs** library from Microsoft. If a call fails because the library
# changed, open `docs/fabric_build_guide.md` step 7B and build the same model by hand in the browser —
# the measures and roles are listed there.

# %% [markdown]
# Sets `lh_hospital` as this notebook's default lakehouse, so relative paths like `Files/...` and table
# names work without attaching the lakehouse by hand. It must stay the first code cell.

# %%
%%configure -f
{"defaultLakehouse": {"name": "lh_hospital"}}

# %%
%pip install -q semantic-link-labs

# %%
# <<MODEL_SPEC>>

# %%
import sempy_labs as labs
from sempy_labs import directlake
from sempy_labs.tom import connect_semantic_model

import inspect

# semantic-link-labs renames arguments between versions, so match the installed version's names
fn = directlake.generate_direct_lake_semantic_model
params = inspect.signature(fn).parameters
print("Installed signature:", inspect.signature(fn))
kw = {}
for name in ("dataset", "name"):
    if name in params:
        kw[name] = MODEL_NAME
        break
for name in ("tables", "lakehouse_tables"):
    if name in params:
        kw[name] = TABLES
        break
for name in ("lakehouse", "source"):
    if name in params:
        kw[name] = LAKEHOUSE
        break
for name, value in (("overwrite", True), ("refresh", False)):
    if name in params:
        kw[name] = value
fn(**kw)
print("Model created:", MODEL_NAME)

# %%
with connect_semantic_model(dataset=MODEL_NAME, readonly=False) as tom:
    for f_tbl, f_col, t_tbl, t_col in RELATIONSHIPS:
        tom.add_relationship(from_table=f_tbl, from_column=f_col, to_table=t_tbl, to_column=t_col,
                             from_cardinality="Many", to_cardinality="One")
    tom.mark_as_date_table(table_name="gold_dim_date", column_name="date")
    for table, name, dax, fmt, folder, desc in MEASURES:
        kwargs = dict(table_name=table, measure_name=name, expression=dax, display_folder=folder, description=desc)
        if fmt:
            kwargs["format_string"] = fmt
        tom.add_measure(**kwargs)
    for role, filters, desc in ROLES:
        tom.add_role(role_name=role, model_permission="Read", description=desc)
        for table, expr in filters:
            tom.set_rls(role_name=role, table_name=table, filter_expression=expr)
print(f"Added {len(RELATIONSHIPS)} relationships, {len(MEASURES)} measures, {len(ROLES)} roles")

# %%
labs.refresh_semantic_model(dataset=MODEL_NAME)
print("Refreshed. Open the model in the workspace -> 'Open data model' to check it.")
