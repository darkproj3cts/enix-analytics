-- =====================================================================
-- v_pnl_sku_day — P&L по SKU по дням
-- =====================================================================
-- Каскад:
--     Выручка после СПП
--     - Комиссия WB
--     - Эквайринг
--     - Логистика до клиента (прямая)
--     - Логистика обратная (по возвратам)
--     - Аллокация хранения (пропорционально выручке дня)
--     - Аллокация платной приёмки
--     - Аллокация штрафов
--     - Реклама (ВП + АРК на SKU-день)
--     - Себестоимость FIFO выкупленных единиц
--     = Валовая маржа, ₽
-- =====================================================================

CREATE OR REPLACE VIEW v_pnl_sku_day AS
WITH
sales_day AS (
    SELECT
        CAST(sale_date AS DATE) AS d,
        sku_id,
        SUM(qty_sold)           AS qty_sold,
        SUM(revenue_after_spp)  AS revenue_after_spp
    FROM sales
    GROUP BY CAST(sale_date AS DATE), sku_id
),
cogs_day AS (
    SELECT sale_date AS d, sku_id, SUM(cogs_rub) AS cogs_rub
    FROM v_fifo_cogs
    GROUP BY sale_date, sku_id
),
ads_day AS (
    SELECT CAST(ads_date AS DATE) AS d, sku_id, SUM(ads_spend) AS ads_rub
    FROM ads_daily
    GROUP BY CAST(ads_date AS DATE), sku_id
),
sku_share AS (
    -- Доля SKU в выручке дня — для аллокации общих удержаний
    SELECT
        d,
        sku_id,
        revenue_after_spp,
        revenue_after_spp
            / NULLIF(SUM(revenue_after_spp) OVER (PARTITION BY d), 0) AS share
    FROM sales_day
)
SELECT
    sd.d                                              AS day,
    sd.sku_id,
    sk.article,
    sk.model_name,
    sk.category,
    sk.size,
    sk.color,
    sk.margin_tier,
    sd.qty_sold,
    sd.revenue_after_spp,

    COALESCE(wh.wb_commission, 0)                     AS wb_commission,
    COALESCE(wh.wb_acquiring,  0)                     AS wb_acquiring,
    COALESCE(wh.log_forward,   0)                     AS log_forward,
    COALESCE(wh.log_reverse,   0)                     AS log_reverse,
    ROUND(COALESCE(sh.share * oh.storage_total,    0), 2) AS storage_alloc,
    ROUND(COALESCE(sh.share * oh.acceptance_total, 0), 2) AS acceptance_alloc,
    ROUND(COALESCE(sh.share * oh.fine_total,       0), 2) AS fine_alloc,
    COALESCE(ad.ads_rub,  0)                          AS ads_spend,
    COALESCE(cg.cogs_rub, 0)                          AS cogs_fifo,

    ROUND(
        sd.revenue_after_spp
        - COALESCE(wh.wb_commission, 0)
        - COALESCE(wh.wb_acquiring,  0)
        - COALESCE(wh.log_forward,   0)
        - COALESCE(wh.log_reverse,   0)
        - COALESCE(sh.share * oh.storage_total,    0)
        - COALESCE(sh.share * oh.acceptance_total, 0)
        - COALESCE(sh.share * oh.fine_total,       0)
        - COALESCE(ad.ads_rub,  0)
        - COALESCE(cg.cogs_rub, 0)
    , 2) AS gross_margin_rub,

    ROUND(100.0 * (
        sd.revenue_after_spp
        - COALESCE(wh.wb_commission, 0)
        - COALESCE(wh.wb_acquiring,  0)
        - COALESCE(wh.log_forward,   0)
        - COALESCE(wh.log_reverse,   0)
        - COALESCE(sh.share * oh.storage_total,    0)
        - COALESCE(sh.share * oh.acceptance_total, 0)
        - COALESCE(sh.share * oh.fine_total,       0)
        - COALESCE(ad.ads_rub,  0)
        - COALESCE(cg.cogs_rub, 0)
    ) / NULLIF(sd.revenue_after_spp, 0), 2) AS gross_margin_pct

FROM sales_day         sd
JOIN sku               sk ON sk.sku_id = sd.sku_id
LEFT JOIN v_wb_sku_overhead   wh ON wh.d = sd.d AND wh.sku_id = sd.sku_id
LEFT JOIN v_wb_daily_overhead oh ON oh.d = sd.d
LEFT JOIN sku_share    sh ON sh.d = sd.d AND sh.sku_id = sd.sku_id
LEFT JOIN cogs_day     cg ON cg.d = sd.d AND cg.sku_id = sd.sku_id
LEFT JOIN ads_day      ad ON ad.d = sd.d AND ad.sku_id = sd.sku_id;