-- =====================================================================
-- v_margin_leak — где течёт маржа
-- =====================================================================
-- Разложение потерь по причинам (годовая сумма):
--     1. Комиссия WB
--     2. Эквайринг
--     3. Прямая логистика
--     4. Обратная логистика (на возвратах)
--     5. Хранение
--     6. Платная приёмка
--     7. Штрафы
--     8. Реклама с низким ROMI — SKU с тиром "дорогая" или "убыточная"
--        (ads > 50% маржи до рекламы). Их отключение даёт экономию без
--        существенной потери прибыли.
--
-- Эта витрина — главный аргумент на интервью: показывает конкретные
-- рычаги оптимизации с цифрами в ₽.
-- =====================================================================

CREATE OR REPLACE VIEW v_margin_leak AS
WITH
totals AS (
    SELECT
        SUM(wb_commission)                       AS commission,
        SUM(wb_acquiring)                        AS acquiring,
        SUM(log_forward)                         AS log_forward,
        SUM(log_reverse)                         AS log_reverse,
        SUM(storage_alloc)                       AS storage,
        SUM(acceptance_alloc)                    AS acceptance,
        SUM(fine_alloc)                          AS fine,
        SUM(revenue_after_spp)                   AS revenue_total
    FROM v_pnl_sku_day
),
-- Реклама на SKU, где она "дорогая" или "убыточная": на 1₽ рекламы приходится < 1₽ дополнительной маржи.
-- Отключение этих SKU из рекламы — чистая экономия без потери прибыли.
inefficient_ads AS (
    SELECT SUM(ads_rub) AS inefficient_ads_rub
    FROM v_unit_economics
    WHERE ads_efficiency_tier IN ('дорогая', 'убыточная')
)
SELECT 'Комиссия WB'            AS leak_source, ROUND(commission, 0)   AS amount_rub,
       ROUND(100.0 * commission / revenue_total, 2) AS pct_of_revenue
FROM totals
UNION ALL
SELECT 'Эквайринг',             ROUND(acquiring, 0),
       ROUND(100.0 * acquiring / revenue_total, 2) FROM totals
UNION ALL
SELECT 'Логистика до клиента',  ROUND(log_forward, 0),
       ROUND(100.0 * log_forward / revenue_total, 2) FROM totals
UNION ALL
SELECT 'Обратная логистика',    ROUND(log_reverse, 0),
       ROUND(100.0 * log_reverse / revenue_total, 2) FROM totals
UNION ALL
SELECT 'Хранение',              ROUND(storage, 0),
       ROUND(100.0 * storage / revenue_total, 2) FROM totals
UNION ALL
SELECT 'Платная приёмка',       ROUND(acceptance, 0),
       ROUND(100.0 * acceptance / revenue_total, 2) FROM totals
UNION ALL
SELECT 'Штрафы',                ROUND(fine, 0),
       ROUND(100.0 * fine / revenue_total, 2) FROM totals
UNION ALL
SELECT 'Реклама с низким ROMI (кандидаты на отключение)',
       ROUND(COALESCE((SELECT inefficient_ads_rub FROM inefficient_ads), 0), 0),
       ROUND(100.0 * COALESCE((SELECT inefficient_ads_rub FROM inefficient_ads), 0) / revenue_total, 2)
FROM totals;