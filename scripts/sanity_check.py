"""
Проверка консистентности сгенерированных данных.
Выводит ключевые бизнес-метрики, которые должен уметь объяснить аналитик.
"""

import sys
from pathlib import Path

import duckdb

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB_PATH = Path(__file__).resolve().parent.parent / "enix_prototype.duckdb"
con = duckdb.connect(str(DB_PATH), read_only=True)


def q(title: str, sql: str):
    print(f"\n── {title} ──")
    df = con.execute(sql).fetch_df()
    print(df.to_string(index=False))


q("Таблицы в базе",
  "SELECT table_name, estimated_size AS rows FROM duckdb_tables() ORDER BY table_name")

q("Период данных",
  """SELECT MIN(order_date) AS start_date,
            MAX(order_date) AS end_date,
            COUNT(DISTINCT order_date) AS days
     FROM orders""")

q("Выручка и выкупы по месяцам (сезонность термобелья)",
  """SELECT strftime(CAST(sale_date AS DATE), '%Y-%m')         AS month,
            ROUND(SUM(revenue_after_spp)/1e6, 1)                AS revenue_mln_rub,
            SUM(qty_sold)                                       AS units_sold
     FROM sales
     GROUP BY 1 ORDER BY 1""")

q("% выкупа по размерам (XS и XL должны быть ниже)",
  """SELECT s.size,
            SUM(o.qty)         AS qty_ordered,
            COALESCE(SUM(sa.qty_sold), 0) AS qty_sold,
            ROUND(100.0 * COALESCE(SUM(sa.qty_sold), 0) / NULLIF(SUM(o.qty), 0), 1) AS buyout_pct
     FROM orders o
     JOIN sku s ON s.sku_id = o.sku_id
     LEFT JOIN sales sa ON sa.order_id = o.order_id
     GROUP BY s.size
     ORDER BY s.size""")

q("Топ-5 моделей по выручке",
  """SELECT s.model_name,
            ROUND(SUM(sa.revenue_after_spp)/1e6, 1) AS revenue_mln_rub,
            SUM(sa.qty_sold) AS units_sold
     FROM sales sa
     JOIN sku s ON s.sku_id = sa.sku_id
     GROUP BY s.model_name
     ORDER BY revenue_mln_rub DESC
     LIMIT 5""")

q("Финансовый отчёт WB — удержания по типу (годовые суммы)",
  """SELECT op_type,
            ROUND(SUM(amount)/1e6, 2) AS amount_mln_rub,
            COUNT(*)                  AS rows
     FROM finance_wb
     GROUP BY op_type
     ORDER BY amount_mln_rub""")

q("Сверка: выручка выкупов vs фактические выплаты WB",
  """WITH rev AS (
       SELECT ROUND(SUM(revenue_after_spp)/1e6, 1) AS revenue_sales_mln FROM sales
     ),
     fin AS (
       SELECT ROUND(SUM(amount)/1e6, 1) AS wb_deductions_mln FROM finance_wb
     ),
     pay AS (
       SELECT ROUND(SUM(amount_received)/1e6, 1) AS paid_to_account_mln FROM payments
     )
     SELECT rev.revenue_sales_mln,
            fin.wb_deductions_mln,
            ROUND(rev.revenue_sales_mln + fin.wb_deductions_mln, 1) AS expected_payment_mln,
            pay.paid_to_account_mln,
            ROUND(pay.paid_to_account_mln - (rev.revenue_sales_mln + fin.wb_deductions_mln), 2) AS diff_mln
     FROM rev, fin, pay""")

q("Рекламный бюджет vs выручка (ДРР)",
  """SELECT ROUND(SUM(ads_spend)/1e6, 1) AS ads_mln,
            (SELECT ROUND(SUM(revenue_after_spp)/1e6, 1) FROM sales) AS revenue_sales_mln,
            ROUND(100.0 * SUM(ads_spend) /
                  (SELECT SUM(revenue_after_spp) FROM sales), 1) AS drr_pct
     FROM ads_daily""")

q("Партии закупок: средняя себестоимость в % от цены",
  """SELECT ROUND(AVG(100.0 * b.total_cost_per_unit / s.base_price), 1) AS avg_cogs_pct_of_price,
            MIN(b.total_cost_per_unit) AS min_cost,
            MAX(b.total_cost_per_unit) AS max_cost,
            COUNT(*)                   AS batches
     FROM cogs_batch b
     JOIN sku s ON s.sku_id = b.sku_id""")

con.close()
