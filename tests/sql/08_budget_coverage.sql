-- Every site x service line that has activity in a month needs a budget line for that month.
SELECT a.site_code, a.service_line_code, a.month_start
FROM (
    SELECT DISTINCT site_code, service_line_code, DATE_TRUNC('month', disch_dttm)::DATE AS month_start
    FROM visit_with_service_line
) AS a
LEFT JOIN ref_budget AS b
  ON b.site_code = a.site_code AND b.service_line_code = a.service_line_code AND b.month_start = a.month_start
WHERE b.site_code IS NULL;
