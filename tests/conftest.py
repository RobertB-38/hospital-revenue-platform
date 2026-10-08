"""Loads the landing export and reference files into an in-memory DuckDB database for the tests."""
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parent.parent
LANDING = ROOT / "data" / "landing"


@pytest.fixture(scope="session")
def db():
    con = duckdb.connect()
    exp = (LANDING / "his_export").as_posix()
    ref = (LANDING / "reference").as_posix()
    con.execute(f"""
        CREATE VIEW visit_raw AS SELECT * FROM read_csv('{exp}/*/VISIT_*.csv', header=true, all_varchar=true,
                                                        union_by_name=true);
        CREATE VIEW visit AS
            SELECT ACCOUNT_NO AS account_no, MRN AS mrn, SITE_CODE AS site_code, VISIT_TYPE AS visit_type,
                   TRY_CAST(ADMIT_DTTM AS TIMESTAMP) AS admit_dttm, TRY_CAST(DISCH_DTTM AS TIMESTAMP) AS disch_dttm,
                   REASON_DESC AS reason_desc, VISIT_DESC AS visit_desc, PAYER_CODE AS payer_code,
                   TRY_CAST(LAST_UPDATED AS TIMESTAMP) AS last_updated
            FROM visit_raw
            QUALIFY ROW_NUMBER() OVER (PARTITION BY ACCOUNT_NO ORDER BY LAST_UPDATED DESC) = 1;
        CREATE VIEW txn AS
            SELECT DISTINCT TXN_ID AS txn_id, ACCOUNT_NO AS account_no, TXN_TYPE AS txn_type,
                   CAST(AMOUNT AS DECIMAL(18,2)) AS amount, TRY_CAST(POSTING_DTTM AS TIMESTAMP) AS posting_dttm
            FROM read_csv('{exp}/*/TXN_*.csv', header=true, all_varchar=true);
        CREATE VIEW ref_site AS SELECT * FROM read_csv('{ref}/site.csv', header=true);
        CREATE VIEW ref_payer AS SELECT * FROM read_csv('{ref}/payer.csv', header=true);
        CREATE VIEW ref_service_line AS SELECT * FROM read_csv('{ref}/service_line.csv', header=true);
        CREATE VIEW ref_service_line_map AS SELECT * FROM read_csv('{ref}/service_line_map.csv', header=true);
        CREATE VIEW ref_budget AS SELECT * FROM read_csv('{ref}/budget.csv', header=true);
        -- same service-line rule as the silver notebook: lowest priority keyword found in the text
        CREATE VIEW visit_with_service_line AS
            SELECT v.*, COALESCE(m.service_line_code, CASE WHEN v.visit_type = 'ED' THEN 'EMR' ELSE 'GEN' END)
                        AS service_line_code
            FROM visit AS v
            LEFT JOIN (
                SELECT account_no, service_line_code FROM (
                    SELECT v2.account_no, r.service_line_code,
                           ROW_NUMBER() OVER (PARTITION BY v2.account_no ORDER BY r.priority, r.keyword) AS rn
                    FROM visit AS v2
                    JOIN ref_service_line_map AS r
                      ON POSITION(LOWER(r.keyword) IN LOWER(CONCAT_WS(' ', v2.reason_desc, v2.visit_desc))) > 0
                ) WHERE rn = 1
            ) AS m USING (account_no);
    """)
    yield con
    con.close()
