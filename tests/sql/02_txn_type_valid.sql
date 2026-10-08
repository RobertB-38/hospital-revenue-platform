-- Only the four ledger types the model understands.
SELECT txn_id, txn_type FROM txn WHERE txn_type NOT IN ('CHG', 'PAY', 'ADJ', 'WO');
