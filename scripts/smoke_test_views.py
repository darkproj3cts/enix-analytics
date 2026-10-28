"""
Smoke-тесты SQL-витрин. Запускаем показательные запросы по каждой витрине —
это и демонстрация, и проверка корректности.
"""

import sys
from pathlib import Path

import duckdb
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 220)
pd.set_option("display.max_colwidth", 40)

DB_PATH = Path(__file__).resolve().parent.parent / "enix_prototype.duckdb"
con = duckdb.connect(str(DB_PATH), read_only=True)


def q(title: str, sql: str, limit: int = 10):
    print(f"\n{'═' * 72}")
    print(title)
    print("═" * 72)
    df = con.execute(sql).fetch_df()
    if len(df) > limit:
        print(f"(показаны первые {limit} из {len(df)} строк)")
        print(df.head(limit).to_string(index=False))
    else:
        print(df.to_string(index=False))


# ─── 1. P&L SKU-день ─────────────────────────────────────────────────
q("1. v_pnl_sku_day — ТОП-10 убыточных SKU за весь период",
  """SELECT article, model_name, size,
            SUM(qty_sold)                           AS qty_sold,
            ROUND(SUM(revenue_after_spp)/1000, 0)   AS revenue_tys_rub,
            ROUND(SUM(gross_margin_rub)/1000, 0)    AS margin_tys_rub,
            ROUND(100.0 * SUM(gross_margin_rub)
                        / NULLIF(SUM(revenue_after_spp), 0), 1) AS margin_pct
     FROM v_pnl_sku_day
     GROUP BY article, model_name, size
     ORDER BY margin_tys_rub ASC
     LIMIT 10""")

q("1b. v_pnl_sku_day — ТОП-10 прибыльных SKU",
  """SELECT article, model_name, size,
            SUM(qty_sold)                           AS qty_sold,
            ROUND(SUM(revenue_after_spp)/1e6, 2)    AS revenue_mln_rub,
            ROUND(SUM(gross_margin_rub)/1e6, 2)     AS margin_mln_rub,
            ROUND(100.0 * SUM(gross_margin_rub)
                        / NULLIF(SUM(revenue_after_spp), 0), 1) AS margin_pct
     FROM v_pnl_sku_day
     GROUP BY article, model_name, size
     ORDER BY margin_mln_rub DESC
     LIMIT 10""")

q("1c. v_pnl_sku_day — ИТОГО по компании",
  """SELECT ROUND(SUM(revenue_after_spp)/1e6, 1)  AS revenue_mln,
            ROUND(SUM(wb_commission)/1e6, 1)      AS commission_mln,
            ROUND(SUM(log_forward+log_reverse)/1e6, 1) AS logistics_mln,
            ROUND(SUM(ads_spend)/1e6, 1)          AS ads_mln,
            ROUND(SUM(cogs_fifo)/1e6, 1)          AS cogs_mln,
            ROUND(SUM(gross_margin_rub)/1e6, 1)   AS margin_mln,
            ROUND(100.0 * SUM(gross_margin_rub)
                        / NULLIF(SUM(revenue_after_spp), 0), 1) AS margin_pct
     FROM v_pnl_sku_day""")

# ─── 2. Юнит-экономика ────────────────────────────────────────────────
q("2. v_unit_economics — SKU с 'дорогой' или 'убыточной' рекламой",
  """SELECT article, model_name, size,
            qty_ordered, buyout_pct,
            ROUND(revenue_rub/1000, 0)  AS revenue_tys,
            ROUND(ads_rub/1000, 0)      AS ads_tys,
            ROUND(margin_before_ads_rub/1000, 0) AS margin_before_ads_tys,
            drr_pct, ads_to_margin_pct, ads_efficiency_tier
     FROM v_unit_economics
     WHERE ads_efficiency_tier IN ('дорогая', 'убыточная')
     ORDER BY ads_rub DESC
     LIMIT 10""")

q("2c. v_unit_economics — распределение SKU по эффективности рекламы",
  """SELECT ads_efficiency_tier,
            COUNT(*)                             AS sku_count,
            ROUND(SUM(ads_rub)/1e6, 2)           AS ads_mln_rub,
            ROUND(AVG(ads_to_margin_pct), 1)     AS avg_ads_share_of_margin_pct
     FROM v_unit_economics
     GROUP BY ads_efficiency_tier
     ORDER BY ads_mln_rub DESC""")

q("2b. v_unit_economics — Средние показатели по категориям",
  """SELECT category,
            COUNT(*)                       AS sku_count,
            ROUND(AVG(buyout_pct), 1)      AS avg_buyout_pct,
            ROUND(AVG(margin_pct_of_revenue), 1) AS avg_margin_pct,
            ROUND(AVG(drr_pct), 1)         AS avg_drr_pct
     FROM v_unit_economics
     GROUP BY category""")

# ─── 3. GMROI ─────────────────────────────────────────────────────────
q("3. v_gmroi — SKU-паразиты (GMROI < 1)",
  """SELECT article, model_name, size, color,
            gross_margin_rub/1000 AS margin_tys,
            avg_stock_units,
            avg_inventory_rub/1000 AS inv_tys,
            gmroi, gmroi_tier
     FROM v_gmroi
     WHERE gmroi < 1
     ORDER BY avg_inventory_rub DESC
     LIMIT 10""")

q("3b. v_gmroi — Распределение SKU по тирам",
  """SELECT gmroi_tier, COUNT(*) AS sku_count,
            ROUND(SUM(avg_inventory_rub)/1e6, 1) AS inventory_mln_rub,
            ROUND(SUM(gross_margin_rub)/1e6, 1)  AS margin_mln_rub
     FROM v_gmroi
     GROUP BY gmroi_tier
     ORDER BY inventory_mln_rub DESC""")

# ─── 4. Оборачиваемость ──────────────────────────────────────────────
q("4. v_turnover — SKU в риске OOS в ближайшие 30 дней",
  """SELECT article, model_name, size,
            avg_daily_sales_60d, current_stock,
            days_of_stock, stock_tier, projected_oos_date
     FROM v_turnover
     WHERE days_of_stock < 30 AND avg_daily_sales_60d > 0
     ORDER BY days_of_stock ASC
     LIMIT 10""")

q("4b. v_turnover — Распределение SKU по оборачиваемости",
  """SELECT stock_tier, COUNT(*) AS sku_count,
            ROUND(AVG(days_of_stock), 0) AS avg_days
     FROM v_turnover
     GROUP BY stock_tier
     ORDER BY avg_days ASC""")

# ─── 5. Где течёт маржа ───────────────────────────────────────────────
q("5. v_margin_leak — Где именно теряется маржа (годовая сумма)",
  """SELECT leak_source,
            ROUND(amount_rub/1e6, 2) AS amount_mln_rub,
            pct_of_revenue
     FROM v_margin_leak
     ORDER BY amount_rub DESC""")

# ─── 6. Сверка выплат ─────────────────────────────────────────────────
q("6. v_reconciliation — Первые 5 и последние 5 недель сверки",
  """(SELECT * FROM v_reconciliation ORDER BY week ASC LIMIT 5)
     UNION ALL
     (SELECT * FROM v_reconciliation ORDER BY week DESC LIMIT 5)""", limit=20)

q("6b. v_reconciliation — Недели с ALERT (расхождение > 0,5%)",
  """SELECT week, revenue_sales, wb_deductions,
            expected_payment, actual_payment,
            diff_rub, diff_pct, status
     FROM v_reconciliation
     WHERE status LIKE 'ALERT%'
     ORDER BY ABS(diff_pct) DESC
     LIMIT 10""")

con.close()
print("\n" + "═" * 72)
print("Smoke-тесты прошли. Все витрины живы.")
print("═" * 72)
