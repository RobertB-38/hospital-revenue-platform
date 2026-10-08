-- Closes one month: copies that month's numbers from the Lakehouse gold layer into the fin schema
-- and locks the period. Called by the pipeline after the month-end checks pass.
--   EXEC fin.usp_close_month @period_end = '2026-09-30';
--   EXEC fin.usp_close_month @period_end = '2026-09-30', @force = 1;   -- re-close a locked month (audited)
-- Reads the Lakehouse through its SQL analytics endpoint with three-part names (lh_hospital.dbo.<table>).

CREATE OR ALTER PROCEDURE fin.usp_close_month
    @period_end DATE,
    @force      BIT = 0
AS
BEGIN
    DECLARE @month_start DATE = DATEFROMPARTS(YEAR(@period_end), MONTH(@period_end), 1);
    DECLARE @failed INT, @warned INT;

    IF @period_end <> EOMONTH(@period_end)
        THROW 50001, 'period_end must be the last day of a month.', 1;

    IF @force = 0 AND EXISTS (SELECT 1 FROM fin.close_log WHERE period_end = @period_end AND is_locked = 1)
        THROW 50002, 'This month is already closed and locked. Use @force = 1 to re-close it.', 1;

    SELECT @failed = SUM(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END),
           @warned = SUM(CASE WHEN status = 'WARN' THEN 1 ELSE 0 END)
    FROM lh_hospital.dbo.gold_monthend_check
    WHERE period_end = @period_end;

    IF @failed IS NULL
        THROW 50003, 'No month-end checks found for this period. Run nb_04_monthend_checks first.', 1;
    IF @failed > 0
        THROW 50004, 'Month-end checks failed for this period. Fix the data before closing.', 1;

    -- refresh the small dimensions
    DELETE FROM fin.dim_site;
    INSERT INTO fin.dim_site SELECT site_code, site_name, region FROM lh_hospital.dbo.gold_dim_site;
    DELETE FROM fin.dim_payer;
    INSERT INTO fin.dim_payer SELECT payer_code, payer_name, payer_type FROM lh_hospital.dbo.gold_dim_payer;
    DELETE FROM fin.dim_service_line;
    INSERT INTO fin.dim_service_line SELECT service_line_code, service_line_name FROM lh_hospital.dbo.gold_dim_service_line;

    -- replace this period's frozen figures
    DELETE FROM fin.fact_close_pnl     WHERE period_end = @period_end;
    DELETE FROM fin.fact_close_budget  WHERE period_end = @period_end;
    DELETE FROM fin.fact_close_debtors WHERE period_end = @period_end;

    INSERT INTO fin.fact_close_pnl
    SELECT @period_end, site_code, service_line_code, payer_code,
           COUNT(*), SUM(gross_charges), SUM(expected_net_revenue), SUM(synthetic_direct_cost)
    FROM lh_hospital.dbo.gold_fact_encounter
    WHERE discharge_date BETWEEN @month_start AND @period_end
    GROUP BY site_code, service_line_code, payer_code;

    INSERT INTO fin.fact_close_budget
    SELECT @period_end, COALESCE(b.site_code, a.site_code), COALESCE(b.service_line_code, a.service_line_code),
           b.budget_net_revenue, b.budget_direct_cost, a.net_revenue, a.direct_cost
    FROM (SELECT site_code, service_line_code, budget_net_revenue, budget_direct_cost
          FROM lh_hospital.dbo.gold_fact_budget WHERE month_start = @month_start) AS b
    FULL OUTER JOIN
         (SELECT site_code, service_line_code, SUM(net_revenue) AS net_revenue, SUM(direct_cost) AS direct_cost
          FROM fin.fact_close_pnl WHERE period_end = @period_end
          GROUP BY site_code, service_line_code) AS a
      ON a.site_code = b.site_code AND a.service_line_code = b.service_line_code;

    INSERT INTO fin.fact_close_debtors
    SELECT @period_end, site_code, payer_code, ageing_band, COUNT(*), SUM(balance)
    FROM lh_hospital.dbo.gold_fact_ar_snapshot
    WHERE snapshot_date = @period_end
    GROUP BY site_code, payer_code, ageing_band;

    DELETE FROM fin.close_log WHERE period_end = @period_end;
    INSERT INTO fin.close_log
    VALUES (@period_end, SYSUTCDATETIME(), SUSER_SNAME(), @failed, @warned, 1,
            CASE WHEN @force = 1 THEN 'Re-closed with @force = 1' ELSE NULL END);
END;
GO
