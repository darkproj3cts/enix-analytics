-- =====================================================================
-- v_unit_economics — юнит-экономика на SKU
-- =====================================================================
-- За весь период истории. Две базы расчёта:
--     - на 1 заказ (с учётом невыкупа и обратной логистики)
--     - на 1 выкуп (чистая экономика выкупленного товара)
--
-- Используется для решений:
--     - на заказ → для планирования рекламы
--     - на выкуп → для решений по ассортименту и цене
-- =====================================================================

CREATE OR REPLACE VIEW v_unit_economics AS
WITH
orders_agg AS (
    SELECT sku_id,
           SUM(qty)                 AS qty_ordered,
           AVG(price_before_spp)    AS price_before_spp_avg,
           AVG(price_after_spp)     AS price_after_spp_avg
    FROM orders
    GROUP BY sku_id
),
sales_agg AS (
    SELECT sku_id,
           SUM(qty_sold)            AS qty_sold,
           SUM(revenue_after_spp)   AS revenue_rub
    FROM sales
    GROUP BY sku_id
),
cogs_agg AS (
    SELECT sku_id, SUM(cogs_rub) AS cogs_rub
    FROM v_fifo_cogs
    GROUP BY sku_id
),
ads_agg AS (
    SELECT sku_id, SUM(ads_spend) AS ads_rub
    FROM ads_daily
    GROUP BY sku_id
),
pnl_agg AS (
    SELECT sku_id,
           SUM(wb_commission)       AS wb_commission,
           SUM(wb_acquiring)        AS wb_acquiring,
           SUM(log_forward)         AS log_forward,
           SUM(log_reverse)         AS log_reverse,
           SUM(storage_alloc + acceptance_alloc + fine_alloc) AS other_overhead,
           SUM(gross_margin_rub)    AS gross_margin_rub
    FROM v_pnl_sku_day
    GROUP BY sku_id
)
SELECT
    sk.sku_id,
    sk.article,
    sk.model_name,
    sk.category,
    sk.size,
    sk.color,
    sk.margin_tier,

    oa.qty_ordered,
    sa.qty_sold,
    ROUND(100.0 * sa.qty_sold / NULLIF(oa.qty_ordered, 0), 1) AS buyout_pct,

    ROUND(oa.price_after_spp_avg, 2) AS price_after_spp_avg,
    sa.revenue_rub,
    ROUND(ca.cogs_rub, 2)   AS cogs_rub,
    ROUND(aa.ads_rub, 2)    AS ads_rub,
    ROUND(pa.gross_margin_rub, 2) AS gross_margin_rub,

    -- На 1 выкуп
    ROUND(sa.revenue_rub       / NULLIF(sa.qty_sold, 0), 2) AS revenue_per_sale,
    ROUND(ca.cogs_rub          / NULLIF(sa.qty_sold, 0), 2) AS cogs_per_sale,
    ROUND(pa.gross_margin_rub  / NULLIF(sa.qty_sold, 0), 2) AS margin_per_sale,
    ROUND(100.0 * pa.gross_margin_rub / NULLIF(sa.revenue_rub, 0), 1) AS margin_pct_of_revenue,

    -- На 1 заказ
    ROUND(sa.revenue_rub       / NULLIF(oa.qty_ordered, 0), 2) AS revenue_per_order,
    ROUND(pa.gross_margin_rub  / NULLIF(oa.qty_ordered, 0), 2) AS margin_per_order,

    -- Доля рекламы в выручке и в заказах
    ROUND(100.0 * aa.ads_rub / NULLIF(sa.revenue_rub, 0), 1)   AS drr_pct,
    ROUND(aa.ads_rub / NULLIF(oa.qty_ordered, 0), 2)           AS cac_rub,

    -- Маржа ДО рекламы (чтобы отделить эффективность рекламы от экономики SKU)
    ROUND(pa.gross_margin_rub + aa.ads_rub, 2) AS margin_before_ads_rub,

    -- ROMI (классический): (маржа_до_рекламы − реклама) / реклама × 100 =
    --                      маржа_после_рекламы / реклама × 100.
    -- Интерпретация:
    --   > 100% — на каждый ₽ рекламы приходится > 1₽ чистой маржи сверху того
    --            что реклама вернула себя: маржа_до = ads × (1 + romi/100).
    --   = 100% — маржа_после_рекламы равна бюджету рекламы, маржа_до_рекламы = 2×ads.
    --   = 0%   — реклама вернула себя ровно, SKU работает "в ноль" после рекламы.
    --   < 0%   — реклама загоняет SKU в минус (маржа_после_рекламы отрицательна).
    ROUND(100.0 * pa.gross_margin_rub / NULLIF(aa.ads_rub, 0), 1) AS romi_pct,

    -- Главный рычаг: сколько % маржи до рекламы съедает реклама
    -- > 100 — реклама убыточна (нужно отключать)
    -- 50-100 — "дорогая реклама", SKU-кандидат на снижение бюджета
    -- < 50 — здоровая
    ROUND(100.0 * aa.ads_rub / NULLIF(pa.gross_margin_rub + aa.ads_rub, 0), 1) AS ads_to_margin_pct,

    CASE
        WHEN aa.ads_rub IS NULL OR aa.ads_rub = 0 THEN 'без рекламы'
        WHEN aa.ads_rub > pa.gross_margin_rub + aa.ads_rub THEN 'убыточная'
        WHEN aa.ads_rub > 0.5 * (pa.gross_margin_rub + aa.ads_rub) THEN 'дорогая'
        ELSE 'здоровая'
    END AS ads_efficiency_tier

FROM sku sk
LEFT JOIN orders_agg oa ON oa.sku_id = sk.sku_id
LEFT JOIN sales_agg  sa ON sa.sku_id = sk.sku_id
LEFT JOIN cogs_agg   ca ON ca.sku_id = sk.sku_id
LEFT JOIN ads_agg    aa ON aa.sku_id = sk.sku_id
LEFT JOIN pnl_agg    pa ON pa.sku_id = sk.sku_id;