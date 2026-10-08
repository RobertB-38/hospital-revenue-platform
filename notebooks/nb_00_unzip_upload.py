# %% [markdown]
# # 00 · Unpack an uploaded zip into Files/
#
# The browser upload of a whole folder can fail with many files. Instead, upload **one zip file** to the
# root of `Files` (Files → … → Upload → Upload files), then run this notebook. It extracts the zip so the data
# lands in `Files/landing/...`, exactly where `nb_01_bronze_ingest` looks for it.
#
# - First time: `zip_name = "landing.zip"` (Jan 2024 – Jun 2026 + reference files)
# - Later, to show incremental loading: `zip_name = "landing_next.zip"` (Jul – Sep 2026)

# %%
%%configure -f
{"defaultLakehouse": {"name": "lh_hospital"}}

# %% tags=["parameters"]
zip_name = "landing.zip"

# %%
import os
import zipfile

src = f"/lakehouse/default/Files/{zip_name}"
dst = "/lakehouse/default/Files/"
if not os.path.exists(src):
    raise FileNotFoundError(f"{zip_name} not found in Files/. Upload it to the root of Files first.")
with zipfile.ZipFile(src) as z:
    names = [n for n in z.namelist() if not n.startswith("__MACOSX") and not n.endswith(".DS_Store")]
    for n in names:
        z.extract(n, dst)
batches = sorted(d for d in os.listdir(f"{dst}landing/his_export") if d.isdigit())
print(f"Extracted {len(names)} entries. Batches now in Files/landing/his_export: {batches[0]} .. {batches[-1]} ({len(batches)})")
print("Reference files:", sorted(os.listdir(f"{dst}landing/reference")))
