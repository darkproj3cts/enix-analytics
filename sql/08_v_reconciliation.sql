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
--
-- Отсекаются неполные крайние недели (где начало/конец данных попадает
-- в середину ISO-недели). Иначе получаем вечные ALERT: удержания есть,
-- выплат ещё нет.
-- =====================================================================

CREATE OR REPLACE VIEW v_reconciliation AS
WITH
sales_week AS (
    SELECT strftime(CAST(sale_date AS DATE), '%G-W%V') AS week,
           SUM(revenue_after_spp)                      AS revenue_sales,
           COUNT(DISTINCT CAST(sale_date AS DATE))     AS days_with_sales
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
),
-- Отсекаем неполные крайние недели: оставляем только недели где было
-- продаж минимум 5 дней из 7. Это надёжнее фильтра "revenue > % от среднего",
-- который хрупок к сезонности.
weeks_filtered AS (
    SELECT w.week
    FROM weeks w
    JOIN sales_week sw ON sw.week = w.week
    WHERE sw.days_with_sales >= 5
),
computed AS (
    SELECT
        w.week,
        COALESCE(sw.revenue_sales,  0) AS revenue_sales,
        COALESCE(fw.wb_deductions,  0) AS wb_deductions,
        COALESCE(sw.revenue_sales, 0) + COALESCE(fw.wb_deductions, 0) AS expected_payment,
        COALESCE(pw.actual_payment, 0) AS actual_payment
    FROM weeks_filtered w
    LEFT JOIN sales_week sw ON sw.week = w.week
    LEFT JOIN fin_week   fw ON fw.week = w.week
    LEFT JOIN pay_week   pw ON pw.week = w.week
),
with_diff AS (
    SELECT *,
        actual_payment - expected_payment AS diff_rub,
        CASE WHEN expected_payment = 0 THEN NULL
             ELSE 100.0 * (actual_payment - expected_payment) / expected_payment
        END AS diff_pct
    FROM computed
)
SELECT
    week,
    ROUND(revenue_sales,   2) AS revenue_sales,
    ROUND(wb_deductions,   2) AS wb_deductions,
    ROUND(expected_payment, 2) AS expected_payment,
    ROUND(actual_payment,   2) AS actual_payment,
    ROUND(diff_rub,         2) AS diff_rub,
    ROUND(diff_pct,         3) AS diff_pct,
    CASE
        WHEN diff_pct IS NULL THEN 'нет данных'
        WHEN ABS(diff_pct) > 0.5 THEN 'ALERT: расхождение > 0,5%'
        ELSE 'OK'
    END AS status
FROM with_diff
ORDER BY week;
