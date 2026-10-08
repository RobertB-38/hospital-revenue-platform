-- Charges must be positive; payments, adjustments and write-offs reduce the balance so must be negative.
SELECT txn_id, txn_type, amount
FROM txn
WHERE (txn_type = 'CHG' AND amount <= 0)
   OR (txn_type IN ('PAY', 'ADJ', 'WO') AND amount >= 0);
