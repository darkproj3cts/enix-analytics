-- =====================================================================
-- v_turnover — оборачиваемость SKU и классификация неликвида
-- =====================================================================
-- Метрики:
--     avg_daily_sales — средние дневные продажи за последние 60 дней
--     current_stock   — текущий остаток (последний снимок)
--     days_of_stock   — на сколько дней хватит остатка при текущей скорости продаж
--     stock_tier      — классификация неликвида
--     oos_date        — прогнозная дата OOS (out of stock)
--
-- Тир-классификация:
--     < 30     — дефицит, OOS
--     30-60    — норма
--     60-90    — медленно
--     90-180   — риск неликвида
--     > 180    — неликвид
-- =====================================================================

CREATE OR REPLACE VIEW v_turnover AS
WITH
last_date AS (
    SELECT MAX(CAST(sale_date AS DATE)) AS d FROM sales
),
recent_sales AS (
    SELECT s.sku_id, SUM(s.qty_sold) / 60.0 AS avg_daily_sales
    FROM sales s, last_date ld
    WHERE CAST(s.sale_date AS DATE) >= ld.d - INTERVAL 60 DAY
    GROUP BY s.sku_id
),
current_stock AS (
    SELECT sku_id, qty_on_stock AS stock_qty
    FROM (
        SELECT sku_id, qty_on_stock,
               ROW_NUMBER() OVER (PARTITION BY sku_id ORDER BY stock_date DESC) AS rn
        FROM stock_daily
    ) t
    WHERE rn = 1
)
SELECT
    sk.sku_id,
    sk.article,
    sk.model_name,
    sk.category,
    sk.size,
    sk.color,
    ROUND(COALESCE(rs.avg_daily_sales, 0), 1) AS avg_daily_sales_60d,
    COALESCE(cs.stock_qty, 0)                 AS current_stock,
    ROUND(
        COALESCE(cs.stock_qty, 0)
        / NULLIF(rs.avg_daily_sales, 0)
    , 0) AS days_of_stock,
    CASE
        WHEN rs.avg_daily_sales IS NULL OR rs.avg_daily_sales = 0 THEN 'мёртвый сток'
        WHEN cs.stock_qty / rs.avg_daily_sales <  30 THEN 'дефицит/OOS скоро'
        WHEN cs.stock_qty / rs.avg_daily_sales <  60 THEN 'норма'
        WHEN cs.stock_qty / rs.avg_daily_sales <  90 THEN 'медленно'
        WHEN cs.stock_qty / rs.avg_daily_sales < 180 THEN 'риск неликвида'
        ELSE 'неликвид'
    END AS stock_tier,
    CASE
        WHEN rs.avg_daily_sales > 0 THEN
            (ld.d + CAST(cs.stock_qty / rs.avg_daily_sales AS INTEGER) * INTERVAL 1 DAY)::DATE
        ELSE NULL
    END AS projected_oos_date
FROM sku sk
LEFT JOIN recent_sales  rs ON rs.sku_id = sk.sku_id
LEFT JOIN current_stock cs ON cs.sku_id = sk.sku_id
CROSS JOIN last_date    ld;