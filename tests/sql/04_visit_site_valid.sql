-- Every visit belongs to a known site.
SELECT v.account_no, v.site_code
FROM visit AS v
LEFT JOIN ref_site AS s ON s.site_code = v.site_code
WHERE s.site_code IS NULL;
