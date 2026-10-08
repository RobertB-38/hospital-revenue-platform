"""
Build a simulated hospital-system export from Synthea CSV output.

What this script does
---------------------
Synthea gives realistic synthetic patients and encounters, but its billing data
is not usable for revenue-cycle reporting (every charge is paid on the same day,
with no discounts, denials or debt). So this script:

1. Keeps hospital-type encounters (inpatient, day case, outpatient, emergency)
   between REPORT_START and CUTOFF, and drops GP-style care (wellness, dental,
   contraception) that an acute private hospital would not bill.
2. Moves the population to Ireland: three fictional sites, Irish counties,
   Irish insurers weighted by HIA market share, self-pay for uninsured patients.
3. Simulates the revenue cycle for every visit: charges at discharge, insurer
   remittance with contractual discount, denials, patient excess, bad debt.
   Anything that would post after CUTOFF is left out, so recent months stay
   open on the debtors ledger.
4. Writes monthly export batches (one folder per posting month) in the style of
   a hospital-system flat-file export, each with a manifest of control totals.
5. Writes a synthetic budget by site x service line x month.

Every money figure is SYNTHETIC. Nothing here is real hospital data, and the
export only imitates the shape of a hospital-system extract. It is not MEDITECH.

Usage:  python generator/build_staging.py --synthea /path/to/synthea/output/csv --out data/landing
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 2026
REPORT_START = pd.Timestamp("2024-01-01")
CUTOFF = pd.Timestamp("2026-09-30 23:59:59")

KEEP_CLASSES = {"inpatient", "emergency", "urgentcare", "outpatient", "ambulatory"}
OUT_OF_SCOPE_WORDS = ["dental", "gingiv", "teeth", "molar", "jaw", "contracept",
                      "check up", "well child", "telemedicine"]

SITES = {
    "DS": {"weight": 0.45, "counties": ["Dublin", "Dublin", "Wicklow", "Wexford"], "routing": ["A94", "D04", "D18", "A98"]},
    "DW": {"weight": 0.30, "counties": ["Dublin", "Kildare", "Meath"], "routing": ["D20", "W23", "C15"]},
    "GW": {"weight": 0.25, "counties": ["Galway", "Mayo", "Clare", "Roscommon"], "routing": ["H91", "F23", "V95", "F42"]},
}

REF = Path(__file__).resolve().parent.parent / "data" / "landing" / "reference"


def stable_hash(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest()[:12], 16)


def map_service_line(reason: str, desc: str, visit_type: str, rules: pd.DataFrame) -> str:
    text = f"{reason} {desc}".lower()
    for _, r in rules.iterrows():  # rules are sorted by priority
        if r["keyword"] in text:
            return r["service_line_code"]
    return "EMR" if visit_type == "ED" else "GEN"


def read_many(dirs: list[Path], name: str, **kw) -> pd.DataFrame:
    # on_bad_lines="skip" tolerates a truncated last line if a Synthea run was stopped early
    frames = [pd.read_csv(d / name, on_bad_lines="skip", **kw) for d in dirs if (d / name).exists()]
    return pd.concat(frames, ignore_index=True)


def main(synthea: list[Path], out: Path) -> None:
    rng = np.random.default_rng(SEED)
    payers = pd.read_csv(REF / "payer.csv").set_index("payer_code")
    sl_rules = pd.read_csv(REF / "service_line_map.csv").sort_values(["priority", "keyword"])
    sl_ref = pd.read_csv(REF / "service_line.csv").set_index("service_line_code")

    # ---------------------------------------------------------------- encounters
    enc = read_many(synthea, "encounters.csv", parse_dates=["START", "STOP"])
    enc["START"] = enc["START"].dt.tz_localize(None)
    enc["STOP"] = enc["STOP"].dt.tz_localize(None)
    enc = enc[enc["ENCOUNTERCLASS"].isin(KEEP_CLASSES)]
    enc = enc[(enc["STOP"] >= REPORT_START) & (enc["STOP"] <= CUTOFF)]
    text = (enc["DESCRIPTION"].fillna("") + " " + enc["REASONDESCRIPTION"].fillna("")).str.lower()
    enc = enc[~text.apply(lambda t: any(w in t for w in OUT_OF_SCOPE_WORDS))].copy()

    # charge lines (line-item detail) for the kept encounters
    keep_ids = set(enc["Id"])
    parts = []
    for d in synthea:
        for ch in pd.read_csv(d / "claims_transactions.csv", chunksize=500_000, on_bad_lines="skip",
                              usecols=["TYPE", "AMOUNT", "PROCEDURECODE", "NOTES", "UNITS", "APPOINTMENTID"]):
            parts.append(ch[(ch["TYPE"] == "CHARGE") & ch["APPOINTMENTID"].isin(keep_ids)])
    chg = pd.concat(parts, ignore_index=True)
    chg = chg[chg["AMOUNT"] > 0]

    # visit type as the hospital system would record it
    big_proc = chg[chg["AMOUNT"] >= 1000].groupby("APPOINTMENTID").size()
    def visit_type(row) -> str:
        c = row["ENCOUNTERCLASS"]
        if c == "inpatient":
            return "IP"
        if c in ("emergency", "urgentcare"):
            return "ED"
        if c == "outpatient" and row["Id"] in big_proc.index:
            return "DC"
        if "outpatient procedure" in str(row["DESCRIPTION"]).lower():
            return "DC"
        return "OP"
    enc["VISIT_TYPE"] = enc.apply(visit_type, axis=1)

    # ---------------------------------------------------------------- patients
    pats = read_many(synthea, "patients.csv")
    pats = pats[pats["Id"].isin(enc["PATIENT"])].copy()
    enc = enc[enc["PATIENT"].isin(pats["Id"])].copy()
    payer_names = read_many(synthea, "payers.csv").drop_duplicates("Id").set_index("Id")["NAME"]
    enc_payer_name = enc["PAYER"].map(payer_names)
    uninsured = (enc.assign(n=enc_payer_name).groupby("PATIENT")["n"]
                 .agg(lambda s: (s == "NO_INSURANCE").mean() > 0.5))

    insurers = payers[payers["payer_type"] == "Insurer"]
    ins_codes = insurers.index.to_numpy()
    ins_w = (insurers["market_share_weight"] / insurers["market_share_weight"].sum()).to_numpy()
    site_codes = np.array(list(SITES))
    site_w = np.array([SITES[s]["weight"] for s in site_codes])

    pats = pats.sort_values("Id").reset_index(drop=True)
    pats["MRN"] = [f"ARD{1000000 + i:07d}" for i in range(len(pats))]
    pats["HOME_SITE"] = rng.choice(site_codes, size=len(pats), p=site_w)
    pats["PRIMARY_PAYER_CODE"] = np.where(
        pats["Id"].map(uninsured).fillna(False).to_numpy(), "SELF",
        rng.choice(ins_codes, size=len(pats), p=ins_w))
    # a small self-pay share among insured patients is realistic (no cover for the procedure)
    flip = rng.random(len(pats)) < 0.04
    pats.loc[flip, "PRIMARY_PAYER_CODE"] = "SELF"
    idx = [rng.integers(len(SITES[s]["counties"])) for s in pats["HOME_SITE"]]
    pats["COUNTY"] = [SITES[s]["counties"][i] for s, i in zip(pats["HOME_SITE"], idx)]
    pats["EIRCODE_ROUTING"] = [SITES[s]["routing"][i % len(SITES[s]["routing"])] for s, i in zip(pats["HOME_SITE"], idx)]
    pats["MEMBERSHIP_NO"] = np.where(pats["PRIMARY_PAYER_CODE"] == "SELF", "",
                                     [f"M{stable_hash(x) % 10**9:09d}" for x in pats["Id"]])

    pid_to_mrn = pats.set_index("Id")["MRN"]
    enc["MRN"] = enc["PATIENT"].map(pid_to_mrn)
    home_site = pats.set_index("Id")["HOME_SITE"]
    # 85% of visits at the home site, the rest at another site
    other = rng.random(len(enc)) < 0.15
    enc["SITE_CODE"] = np.where(other, rng.choice(site_codes, size=len(enc), p=site_w),
                                enc["PATIENT"].map(home_site))
    enc["PAYER_CODE"] = enc["PATIENT"].map(pats.set_index("Id")["PRIMARY_PAYER_CODE"])
    enc = enc.sort_values(["STOP", "Id"]).reset_index(drop=True)
    enc["ACCOUNT_NO"] = [f"V{26000000 + i:08d}" for i in range(len(enc))]
    enc["CONSULTANT_ID"] = ["C" + str(stable_hash(p) % 900 + 100) for p in enc["PROVIDER"]]
    enc["SERVICE_LINE_CODE"] = [
        map_service_line(r, d, v, sl_rules)
        for r, d, v in zip(enc["REASONDESCRIPTION"].fillna(""), enc["DESCRIPTION"].fillna(""), enc["VISIT_TYPE"])]

    acct = enc.set_index("Id")["ACCOUNT_NO"]
    chg["ACCOUNT_NO"] = chg["APPOINTMENTID"].map(acct)
    chg = chg.merge(enc[["ACCOUNT_NO", "STOP"]], on="ACCOUNT_NO")

    # ---------------------------------------------------------------- revenue cycle simulation
    rows = []
    def post(account, ttype, subtype, payer, code, desc, qty, amount, when):
        if when <= CUTOFF:
            rows.append((account, ttype, subtype, payer, code, desc, qty, round(amount, 2), when))

    for r in chg.itertuples(index=False):
        post(r.ACCOUNT_NO, "CHG", "SERVICE", "", str(r.PROCEDURECODE), str(r.NOTES), int(r.UNITS or 1),
             float(r.AMOUNT), r.STOP)

    gross = chg.groupby("ACCOUNT_NO")["AMOUNT"].sum().round(2)
    for v in enc.itertuples(index=False):
        g = float(gross.get(v.ACCOUNT_NO, 0.0))
        if g <= 0:
            continue
        disch = v.STOP
        p = payers.loc[v.PAYER_CODE]
        if v.PAYER_CODE == "SELF":
            patient_part, insurer_part = g, 0.0
        else:
            excess = p["ip_excess_eur"] if v.VISIT_TYPE in ("IP", "DC") else p["op_excess_eur"]
            patient_part = min(float(excess), g)
            insurer_part = g - patient_part

        if insurer_part > 0:
            submit = disch + pd.Timedelta(days=int(rng.integers(2, 13)))
            mean = p["mean_days_to_pay"]
            days = max(5, int(rng.lognormal(np.log(mean), 0.35)))
            remit = submit + pd.Timedelta(days=days)
            discount = round(insurer_part * p["contractual_discount_rate"], 2)
            payable = insurer_part - discount
            if rng.random() < p["denial_rate"]:
                if rng.random() < 0.6:   # resubmitted and paid later
                    remit = remit + pd.Timedelta(days=int(rng.integers(30, 75)))
                    post(v.ACCOUNT_NO, "ADJ", "CONTRACTUAL", v.PAYER_CODE, "", "Contractual allowance", 1, -discount, remit)
                    post(v.ACCOUNT_NO, "PAY", "INSURER", v.PAYER_CODE, "", "Insurer remittance (after resubmission)", 1, -payable, remit)
                else:                     # denial upheld, written off
                    post(v.ACCOUNT_NO, "ADJ", "CONTRACTUAL", v.PAYER_CODE, "", "Contractual allowance", 1, -discount, remit)
                    post(v.ACCOUNT_NO, "WO", "DENIAL", v.PAYER_CODE, "", "Claim denied - written off", 1, -payable,
                         remit + pd.Timedelta(days=int(rng.integers(60, 120))))
            else:
                post(v.ACCOUNT_NO, "ADJ", "CONTRACTUAL", v.PAYER_CODE, "", "Contractual allowance", 1, -discount, remit)
                post(v.ACCOUNT_NO, "PAY", "INSURER", v.PAYER_CODE, "", "Insurer remittance", 1, -payable, remit)

        if patient_part > 0:
            r = rng.random()
            if r < 0.55:
                when = disch
            elif r < 0.96:
                when = disch + pd.Timedelta(days=int(rng.integers(10, 95)))
            else:
                post(v.ACCOUNT_NO, "WO", "BAD_DEBT", "SELF", "", "Patient balance written off", 1, -patient_part,
                     disch + pd.Timedelta(days=int(rng.integers(150, 210))))
                continue
            post(v.ACCOUNT_NO, "PAY", "PATIENT", "SELF", "", "Patient payment", 1, -patient_part, when)

    txn = pd.DataFrame(rows, columns=["ACCOUNT_NO", "TXN_TYPE", "TXN_SUBTYPE", "PAYER_CODE", "SERVICE_CODE",
                                      "SERVICE_DESC", "QTY", "AMOUNT", "POSTING_DTTM"])
    txn = txn.sort_values(["POSTING_DTTM", "ACCOUNT_NO", "TXN_TYPE"]).reset_index(drop=True)
    txn["TXN_ID"] = [f"T{i:09d}" for i in range(1, len(txn) + 1)]
    txn["BATCH"] = txn["POSTING_DTTM"].dt.strftime("%Y%m")

    # ---------------------------------------------------------------- export batches
    enc["BATCH"] = enc["STOP"].dt.strftime("%Y%m")
    enc["LAST_UPDATED"] = enc["STOP"] + pd.Timedelta(hours=6)
    first_visit = enc.groupby("MRN")["STOP"].min()
    pats["REG_DTTM"] = pats["MRN"].map(first_visit) - pd.Timedelta(days=1)
    pats["BATCH"] = pats["REG_DTTM"].clip(lower=REPORT_START).dt.strftime("%Y%m")
    pats["LAST_UPDATED"] = pats["REG_DTTM"]

    visit_cols = ["ACCOUNT_NO", "MRN", "SITE_CODE", "VISIT_TYPE", "ADMIT_DTTM", "DISCH_DTTM", "REASON_CODE",
                  "REASON_DESC", "VISIT_DESC", "CONSULTANT_ID", "PAYER_CODE", "LAST_UPDATED"]
    visits = enc.rename(columns={"START": "ADMIT_DTTM", "STOP": "DISCH_DTTM", "REASONCODE": "REASON_CODE",
                                 "REASONDESCRIPTION": "REASON_DESC", "DESCRIPTION": "VISIT_DESC"})
    visits["REASON_CODE"] = visits["REASON_CODE"].astype("Int64").astype(str).replace("<NA>", "")
    # data-quality issues a real feed has: a few visits with the payer missing
    miss = rng.random(len(visits)) < 0.003
    visits.loc[miss, "PAYER_CODE"] = ""

    pat_cols = ["MRN", "SURNAME", "FORENAME", "DOB", "SEX", "ADDRESS_LINE1", "COUNTY", "EIRCODE_ROUTING",
                "PRIMARY_PAYER_CODE", "MEMBERSHIP_NO", "REG_DTTM", "LAST_UPDATED"]
    patients = pats.rename(columns={"LAST": "SURNAME", "FIRST": "FORENAME", "BIRTHDATE": "DOB", "GENDER": "SEX",
                                    "ADDRESS": "ADDRESS_LINE1"})
    patients["SURNAME"] = patients["SURNAME"].str.replace(r"\d+", "", regex=True)
    patients["FORENAME"] = patients["FORENAME"].str.replace(r"\d+", "", regex=True)

    root = out / "his_export"
    root.mkdir(parents=True, exist_ok=True)
    batches = sorted(set(visits["BATCH"]) | set(txn["BATCH"]))
    resend_pool = pd.DataFrame()
    fmt = "%Y-%m-%d %H:%M:%S"
    for b in batches:
        d = root / b
        d.mkdir(exist_ok=True)
        vb = visits[visits["BATCH"] == b][visit_cols].copy()
        # corrections: re-send ~1% of last month's visits with a later LAST_UPDATED
        if len(resend_pool):
            rs = resend_pool.sample(frac=0.01, random_state=int(b)).copy()
            rs["LAST_UPDATED"] = rs["LAST_UPDATED"] + pd.Timedelta(days=20)
            vb = pd.concat([vb, rs])
        resend_pool = visits[visits["BATCH"] == b][visit_cols]
        tb = txn[txn["BATCH"] == b][["TXN_ID", "ACCOUNT_NO", "TXN_TYPE", "TXN_SUBTYPE", "PAYER_CODE",
                                     "SERVICE_CODE", "SERVICE_DESC", "QTY", "AMOUNT", "POSTING_DTTM"]].copy()
        # duplicates a real feed sometimes has: ~0.2% of rows sent twice
        dup = tb.sample(frac=0.002, random_state=int(b) + 1)
        tb = pd.concat([tb, dup]).sort_values("TXN_ID")
        pb = patients[patients["BATCH"] == b][pat_cols].copy()

        files = {
            f"PATIENT_{b}.csv": pb,
            f"VISIT_{b}.csv": vb,
            f"TXN_{b}.csv": tb,
        }
        manifest = {"batch_id": b, "source_system": "Simulated hospital information system (synthetic)",
                    "extract_run_utc": datetime(int(b[:4]), int(b[4:]), 1, tzinfo=timezone.utc).isoformat(),
                    "files": []}
        for name, df in files.items():
            df = df.copy()
            for c in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[c]):
                    df[c] = df[c].dt.strftime(fmt)
            df.to_csv(d / name, index=False)
            entry = {"file": name, "row_count": int(len(df))}
            if "AMOUNT" in df.columns:
                entry["control_total_amount"] = round(float(df["AMOUNT"].sum()), 2)
                entry["control_total_charges"] = round(float(df.loc[df["TXN_TYPE"] == "CHG", "AMOUNT"].sum()), 2)
            manifest["files"].append(entry)
        (d / f"MANIFEST_{b}.json").write_text(json.dumps(manifest, indent=2))

    # ---------------------------------------------------------------- synthetic budget
    sl_of_acct = enc.set_index("ACCOUNT_NO")[["SITE_CODE", "SERVICE_LINE_CODE", "STOP", "PAYER_CODE"]]
    e2 = sl_of_acct.join(gross.rename("gross"))
    disc = payers["contractual_discount_rate"]
    e2["net"] = e2["gross"] * (1 - e2["PAYER_CODE"].map(disc).fillna(0))
    e2["month"] = e2["STOP"].dt.to_period("M").dt.to_timestamp()
    act = e2.groupby(["SITE_CODE", "SERVICE_LINE_CODE", "month"]).agg(net=("net", "sum"), n=("net", "size")).reset_index()
    act["year"] = act["month"].dt.year
    budget_rows = []
    months = pd.date_range("2024-01-01", "2026-12-01", freq="MS")
    for (s, sl), g in act.groupby(["SITE_CODE", "SERVICE_LINE_CODE"]):
        g = g.set_index("month")
        base_2024 = g.loc[g.index.year == 2024, "net"].mean() if (g.index.year == 2024).any() else g["net"].mean()
        n_2024 = g.loc[g.index.year == 2024, "n"].mean() if (g.index.year == 2024).any() else g["n"].mean()
        for m in months:
            prior = g["net"].get(m - pd.DateOffset(years=1))
            prior_n = g["n"].get(m - pd.DateOffset(years=1))
            if m.year == 2024 or prior is None or pd.isna(prior):
                bud, bn = base_2024 * 1.03, n_2024 * 1.02
            else:
                bud, bn = prior * 1.05, prior_n * 1.03
            bud *= rng.normal(1.0, 0.04)
            ratio = sl_ref.loc[sl, "direct_cost_ratio"]
            budget_rows.append((m.date().isoformat(), s, sl, round(bud, 2), round(bud * ratio * 0.98, 2), round(bn, 1)))
    budget = pd.DataFrame(budget_rows, columns=["month_start", "site_code", "service_line_code",
                                                "budget_net_revenue_eur", "budget_direct_cost_eur", "budget_activity"])
    budget["is_synthetic"] = "Y"
    budget.to_csv(out / "reference" / "budget.csv", index=False)

    print(f"patients {len(patients):,}  visits {len(visits):,}  txn {len(txn):,}  batches {len(batches)}")
    print(enc["VISIT_TYPE"].value_counts().to_string())
    print(enc["SERVICE_LINE_CODE"].value_counts().to_string())
    print(pats["PRIMARY_PAYER_CODE"].value_counts(normalize=True).round(3).to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthea", required=True, type=Path, nargs="+")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    main(a.synthea, a.out)
