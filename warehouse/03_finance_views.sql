-- Finance views over the frozen month-end figures. Use these for the month-end pack and ad hoc SQL.

CREATE OR ALTER VIEW fin.vw_close_status AS
SELECT period_end, closed_at, closed_by, checks_failed, checks_warned, is_locked, note
FROM fin.close_log;
GO

CREATE OR ALTER VIEW fin.vw_budget_variance AS
SELECT b.period_end, s.site_name, l.service_line_name,
       b.actual_net_revenue, b.budget_net_revenue,
       b.actual_net_revenue - b.budget_net_revenue AS variance_eur,
       CASE WHEN b.budget_net_revenue = 0 THEN NULL
            ELSE (b.actual_net_revenue - b.budget_net_revenue) / b.budget_net_revenue END AS variance_pct
FROM fin.fact_close_budget AS b
JOIN fin.dim_site AS s ON s.site_code = b.site_code
JOIN fin.dim_service_line AS l ON l.service_line_code = b.service_line_code;
GO

CREATE OR ALTER VIEW fin.vw_payer_mix AS
SELECT p.period_end, py.payer_name, SUM(p.net_revenue) AS net_revenue,
       SUM(p.net_revenue) / NULLIF(SUM(SUM(p.net_revenue)) OVER (PARTITION BY p.period_end), 0) AS share_of_net_revenue
FROM fin.fact_close_pnl AS p
JOIN fin.dim_payer AS py ON py.payer_code = p.payer_code
GROUP BY p.period_end, py.payer_name;
GO

CREATE OR ALTER VIEW fin.vw_debtors_ageing AS
SELECT d.period_end, s.site_name, py.payer_name, d.ageing_band, d.open_accounts, d.balance
FROM fin.fact_close_debtors AS d
JOIN fin.dim_site AS s ON s.site_code = d.site_code
JOIN fin.dim_payer AS py ON py.payer_code = d.payer_code;
GO
