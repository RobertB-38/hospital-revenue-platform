-- One-off: close every past month that has passing checks, oldest first.
-- Only needed once, after the first full load, to fill the close history.
-- nb_04 checks one period per run, so run it for each month first, or close only the latest month.
EXEC fin.usp_close_month @period_end = '2026-09-30';
SELECT * FROM fin.vw_close_status ORDER BY period_end;
