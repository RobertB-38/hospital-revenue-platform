-- No account may be paid more than it was charged (final balance below zero).
SELECT account_no, ROUND(SUM(amount), 2) AS final_balance
FROM txn
GROUP BY account_no
HAVING SUM(amount) < -0.01;
