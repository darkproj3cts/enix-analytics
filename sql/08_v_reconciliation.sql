-- =====================================================================
-- v_reconciliation — сверка выплат WB с расчётной выручкой
-- =====================================================================
-- По неделям:
--   expected_payment = выручка выкупов + все удержания WB (отрицательные)
--   actual_payment   = сумма, фактически пришедшая на расчётный счёт
--   diff_pct         = (actual − expected) / expected
--
-- Если diff_pct > 0.5% — алерт.
-- Это та витрина, после которой основатель начинает доверять системе
-- "по деньгам".
-- =====================================================================

CREATE OR REPLACE VIEW v_reconciliation AS
WITH
sales_week AS (
    SELECT strftime(CAST(sale_date AS DATE), '%G-W%V') AS week,
           SUM(revenue_after_spp) AS revenue_sales
    FROM sales
    GROUP BY strftime(CAST(sale_date AS DATE), '%G-W%V')
),
fin_week AS (
    SELECT strftime(CAST(op_date AS DATE), '%G-W%V') AS week,
           SUM(amount) AS wb_deductions
    FROM finance_wb
    GROUP BY strftime(CAST(op_date AS DATE), '%G-W%V')
),
pay_week AS (
    SELECT week, SUM(amount_received) AS actual_payment
    FROM payments
    GROUP BY week
),
weeks AS (
    SELECT week FROM sales_week
    UNION
    SELECT week FROM fin_week
    UNION
    SELECT week FROM pay_week
)
SELECT
    w.week,
    ROUND(COALESCE(sw.revenue_sales,  0), 2) AS revenue_sales,
    ROUND(COALESCE(fw.wb_deductions,  0), 2) AS wb_deductions,
    ROUND(COALESCE(sw.revenue_sales, 0) + COALESCE(fw.wb_deductions, 0), 2) AS expected_payment,
    ROUND(COALESCE(pw.actual_payment, 0), 2) AS actual_payment,
    ROUND(
        COALESCE(pw.actual_payment, 0)
        - (COALESCE(sw.revenue_sales, 0) + COALESCE(fw.wb_deductions, 0))
    , 2) AS diff_rub,
    ROUND(
        100.0 * (
            COALESCE(pw.actual_payment, 0)
            - (COALESCE(sw.revenue_sales, 0) + COALESCE(fw.wb_deductions, 0))
        ) / NULLIF(COALESCE(sw.revenue_sales, 0) + COALESCE(fw.wb_deductions, 0), 0)
    , 3) AS diff_pct,
    CASE
        WHEN ABS(
            100.0 * (
                COALESCE(pw.actual_payment, 0)
                - (COALESCE(sw.revenue_sales, 0) + COALESCE(fw.wb_deductions, 0))
            ) / NULLIF(COALESCE(sw.revenue_sales, 0) + COALESCE(fw.wb_deductions, 0), 0)
        ) > 0.5 THEN 'ALERT: расхождение > 0,5%'
        ELSE 'OK'
    END AS status
FROM weeks w
LEFT JOIN sales_week sw ON sw.week = w.week
LEFT JOIN fin_week   fw ON fw.week = w.week
LEFT JOIN pay_week   pw ON pw.week = w.week
ORDER BY w.week;