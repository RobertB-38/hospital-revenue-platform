-- Visit payer must be a known payer. Blank is allowed here (silver fills it and flags it).
SELECT v.account_no, v.payer_code
FROM visit AS v
LEFT JOIN ref_payer AS p ON p.payer_code = v.payer_code
WHERE v.payer_code IS NOT NULL AND v.payer_code <> '' AND p.payer_code IS NULL;
