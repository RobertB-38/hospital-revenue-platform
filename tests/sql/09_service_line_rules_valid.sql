-- Every mapping rule points to a service line that exists.
SELECT m.keyword, m.service_line_code
FROM ref_service_line_map AS m
LEFT JOIN ref_service_line AS s ON s.service_line_code = m.service_line_code
WHERE s.service_line_code IS NULL;
