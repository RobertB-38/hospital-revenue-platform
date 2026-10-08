-- Warehouse: wh_hospital
-- Purpose: hold the FROZEN month-end numbers that finance signs off.
-- The Lakehouse gold layer is the live view and is rebuilt every day; once a month is closed,
-- the figures reported for that month must never change. They are copied here and locked.
-- Run once in the wh_hospital SQL editor.

CREATE SCHEMA fin;
GO

CREATE TABLE fin.dim_site (
    site_code       VARCHAR(10)  NOT NULL,
    site_name       VARCHAR(100) NOT NULL,
    region          VARCHAR(50)  NULL
);

CREATE TABLE fin.dim_payer (
    payer_code      VARCHAR(10)  NOT NULL,
    payer_name      VARCHAR(100) NOT NULL,
    payer_type      VARCHAR(20)  NOT NULL
);

CREATE TABLE fin.dim_service_line (
    service_line_code VARCHAR(10)  NOT NULL,
    service_line_name VARCHAR(100) NOT NULL
);

CREATE TABLE fin.fact_close_pnl (
    period_end          DATE          NOT NULL,
    site_code           VARCHAR(10)   NOT NULL,
    service_line_code   VARCHAR(10)   NOT NULL,
    payer_code          VARCHAR(10)   NOT NULL,
    encounters          INT           NOT NULL,
    gross_charges       DECIMAL(18,2) NOT NULL,
    net_revenue         DECIMAL(18,2) NOT NULL,
    direct_cost         DECIMAL(18,2) NOT NULL
);

CREATE TABLE fin.fact_close_budget (
    period_end          DATE          NOT NULL,
    site_code           VARCHAR(10)   NOT NULL,
    service_line_code   VARCHAR(10)   NOT NULL,
    budget_net_revenue  DECIMAL(18,2) NULL,
    budget_direct_cost  DECIMAL(18,2) NULL,
    actual_net_revenue  DECIMAL(18,2) NULL,
    actual_direct_cost  DECIMAL(18,2) NULL
);

CREATE TABLE fin.fact_close_debtors (
    period_end          DATE          NOT NULL,
    site_code           VARCHAR(10)   NOT NULL,
    payer_code          VARCHAR(10)   NOT NULL,
    ageing_band         VARCHAR(10)   NOT NULL,
    open_accounts       INT           NOT NULL,
    balance             DECIMAL(18,2) NOT NULL
);

CREATE TABLE fin.close_log (
    period_end          DATE          NOT NULL,
    closed_at           DATETIME2(6)  NOT NULL,
    closed_by           VARCHAR(200)  NULL,
    checks_failed       INT           NOT NULL,
    checks_warned       INT           NOT NULL,
    is_locked           BIT           NOT NULL,
    note                VARCHAR(400)  NULL
);
GO
