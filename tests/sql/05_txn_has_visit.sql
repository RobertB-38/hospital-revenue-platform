-- No ledger posting without a visit (orphans would break the debtors ledger).
SELECT t.txn_id, t.account_no
FROM txn AS t
LEFT JOIN visit AS v ON v.account_no = t.account_no
WHERE v.account_no IS NULL;
