-- =====================================================================
-- v_gmroi — GMROI (Gross Margin Return on Inventory Investment)
-- =====================================================================
-- GMROI = Валовая маржа за период / Средний товарный запас по себестоимости
-- Бенчмарк для одежды:
--     > 3   — отлично
--     1 - 3 — норма
--     < 1   — SKU-паразит, замораживает капитал
--
-- Период — вся история данных. Для реального проекта обычно 90/180/365 дней.
-- =====================================================================

CREATE OR REPLACE VIEW v_gmroi AS
WITH
margin_by_sku AS (
    SELECT sku_id,
           SUM(gross_margin_rub) AS gross_margin_rub,
           SUM(cogs_fifo)        AS cogs_total
    FROM v_pnl_sku_day
    GROUP BY sku_id
),
-- Средняя себестоимость единицы (по всем партиям SKU, взвешенно)
avg_cost_per_unit AS (
    SELECT sku_id,
           SUM(qty_received * total_cost_per_unit) / NULLIF(SUM(qty_received), 0) AS avg_cost
    FROM cogs_batch
    GROUP BY sku_id
),
-- Средний запас в штуках (по снимкам stock_daily)
avg_stock_qty AS (
    SELECT sku_id, AVG(qty_on_stock) AS avg_qty
    FROM stock_daily
    GROUP BY sku_id
)
SELECT
    sk.sku_id,
    sk.article,
    sk.model_name,
    sk.category,
    sk.size,
    sk.color,
    ROUND(COALESCE(m.gross_margin_rub, 0), 2) AS gross_margin_rub,
    ROUND(COALESCE(asq.avg_qty, 0))           AS avg_stock_units,
    ROUND(COALESCE(acpu.avg_cost, 0), 2)      AS avg_cost_per_unit,
    ROUND(COALESCE(asq.avg_qty * acpu.avg_cost, 0), 2) AS avg_inventory_rub,
    ROUND(
        COALESCE(m.gross_margin_rub, 0)
        / NULLIF(asq.avg_qty * acpu.avg_cost, 0)
    , 2) AS gmroi,
    CASE
        WHEN m.gross_margin_rub / NULLIF(asq.avg_qty * acpu.avg_cost, 0) >= 3 THEN 'отлично'
        WHEN m.gross_margin_rub / NULLIF(asq.avg_qty * acpu.avg_cost, 0) >= 1 THEN 'норма'
        WHEN m.gross_margin_rub / NULLIF(asq.avg_qty * acpu.avg_cost, 0) >= 0 THEN 'слабо'
        ELSE 'паразит'
    END AS gmroi_tier
FROM sku sk
LEFT JOIN margin_by_sku     m    ON m.sku_id    = sk.sku_id
LEFT JOIN avg_cost_per_unit acpu ON acpu.sku_id = sk.sku_id
LEFT JOIN avg_stock_qty     asq  ON asq.sku_id  = sk.sku_id;