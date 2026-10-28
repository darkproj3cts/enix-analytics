-- =====================================================================
-- v_fifo_cogs — себестоимость каждой продажи по FIFO
-- =====================================================================
-- Логика:
--   Каждой партии сопоставляем интервал позиций [pos_start, pos_end) по
--   хронологии поступления. Каждой продаже — такой же интервал по хронологии.
--   Пересечение интервалов даёт количество единиц, списанных с партии.
--   Умножаем на себестоимость партии (ед.) и суммируем.
--
-- Это честный FIFO на SQL без курсоров и процедур.
-- =====================================================================

CREATE OR REPLACE VIEW v_fifo_cogs AS
WITH
batch_pos AS (
    SELECT
        sku_id,
        batch_id,
        arrival_date,
        qty_received,
        total_cost_per_unit,
        COALESCE(
            SUM(qty_received) OVER (
                PARTITION BY sku_id ORDER BY arrival_date, batch_id
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ), 0
        ) AS pos_start,
        SUM(qty_received) OVER (
            PARTITION BY sku_id ORDER BY arrival_date, batch_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS pos_end
    FROM cogs_batch
),
sales_pos AS (
    SELECT
        sale_id,
        sku_id,
        CAST(sale_date AS DATE) AS sale_date,
        qty_sold,
        revenue_after_spp,
        COALESCE(
            SUM(qty_sold) OVER (
                PARTITION BY sku_id ORDER BY sale_date, sale_id
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ), 0
        ) AS pos_start,
        SUM(qty_sold) OVER (
            PARTITION BY sku_id ORDER BY sale_date, sale_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS pos_end
    FROM sales
)
SELECT
    s.sale_id,
    s.sku_id,
    s.sale_date,
    s.qty_sold,
    s.revenue_after_spp,
    SUM(
        GREATEST(0, LEAST(s.pos_end, b.pos_end) - GREATEST(s.pos_start, b.pos_start))
        * b.total_cost_per_unit
    ) AS cogs_rub,
    -- Для диагностики: средневзвешенная себестоимость на единицу выкупа
    SUM(
        GREATEST(0, LEAST(s.pos_end, b.pos_end) - GREATEST(s.pos_start, b.pos_start))
        * b.total_cost_per_unit
    ) / NULLIF(s.qty_sold, 0) AS cogs_per_unit
FROM sales_pos s
LEFT JOIN batch_pos b
    ON b.sku_id = s.sku_id
   AND b.pos_start < s.pos_end
   AND b.pos_end  > s.pos_start
GROUP BY s.sale_id, s.sku_id, s.sale_date, s.qty_sold, s.revenue_after_spp;
