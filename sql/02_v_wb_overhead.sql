-- =====================================================================
-- v_wb_sku_overhead      — удержания WB с привязкой к SKU (комиссия, логистика)
-- v_wb_daily_overhead    — общие удержания WB за день (хранение, приёмка, штрафы)
--
-- Общие удержания в v_pnl_sku_day будут аллоцироваться на SKU
-- пропорционально выручке дня.
-- =====================================================================

CREATE OR REPLACE VIEW v_wb_sku_overhead AS
SELECT
    CAST(op_date AS DATE) AS d,
    sku_id,
    SUM(CASE WHEN op_type = 'продажа'      THEN commission ELSE 0 END) AS wb_commission,
    SUM(CASE WHEN op_type = 'продажа'      THEN acquiring  ELSE 0 END) AS wb_acquiring,
    SUM(CASE WHEN op_type = 'логистика'    THEN -amount    ELSE 0 END) AS log_forward,
    SUM(CASE WHEN op_type = 'возврат_лог'  THEN -amount    ELSE 0 END) AS log_reverse
FROM finance_wb
WHERE sku_id IS NOT NULL
GROUP BY CAST(op_date AS DATE), sku_id;


CREATE OR REPLACE VIEW v_wb_daily_overhead AS
SELECT
    CAST(op_date AS DATE) AS d,
    SUM(CASE WHEN op_type = 'хранение' THEN -amount ELSE 0 END) AS storage_total,
    SUM(CASE WHEN op_type = 'приёмка'  THEN -amount ELSE 0 END) AS acceptance_total,
    SUM(CASE WHEN op_type = 'штраф'    THEN -amount ELSE 0 END) AS fine_total
FROM finance_wb
WHERE sku_id IS NULL
GROUP BY CAST(op_date AS DATE);