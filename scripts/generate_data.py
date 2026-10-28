"""
Генератор синтетических данных WB-селлера термобелья.

Структура повторяет реальные отчёты WB Seller API:
    - sku                 — справочник артикулов (аналог карточек товара)
    - cogs_batch          — партии закупок с себестоимостью (FIFO)
    - orders              — заказы по дням
    - sales               — выкупы (аналог /api/v1/supplier/sales)
    - returns             — возвраты
    - finance_wb          — финансовый отчёт реализации WB
    - stock_daily         — остатки на дату (аналог /api/v3/stocks + snapshot)
    - ads_daily           — рекламные расходы (ВП + АРК)
    - payments            — выплаты от WB на расчётный счёт

На выходе: CSV-файлы в data/ и DuckDB-база enix_prototype.duckdb.
"""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

# В Windows-консоли по умолчанию cp1251 — не умеет ₽ и подобные символы.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# =====================================================================
# ПАРАМЕТРЫ ГЕНЕРАЦИИ
# =====================================================================

RANDOM_SEED = 42
START_DATE = date(2025, 11, 1)
END_DATE = date(2026, 10, 28)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR / "enix_prototype.duckdb"

# Параметры WB (на основе открытой документации WB Seller API и обзоров селлеров)
WB_COMMISSION_PCT = 0.245            # комиссия WB для термобелья, от выручки после СПП
WB_ACQUIRING_PCT = 0.015             # эквайринг
WB_LOGISTICS_FORWARD = (55, 95)      # ₽/шт — логистика до клиента
WB_LOGISTICS_REVERSE = (55, 95)      # ₽/шт — обратная логистика по возвратам
WB_STORAGE_PER_DAY = (0.08, 0.35)    # ₽/шт/день — хранение на складе WB
WB_ACCEPTANCE_DAY_PROB = 0.12        # вероятность, что в день будет платная приёмка
WB_ACCEPTANCE_FEE = (1.0, 5.0)       # ₽/шт платная приёмка
WB_FINE_DAILY_PROB = 0.015           # вероятность штрафа в день (по всему портфелю)
WB_FINE_RANGE = (500, 20000)         # ₽ — штраф

# Экономика
SELLER_COST_PCT = (0.26, 0.36)       # себестоимость как доля от розничной цены
PACKAGING_COST = (8, 15)             # ₽/шт — упаковка
LOGISTICS_TO_WB = (12, 25)           # ₽/шт — логистика поставщик → склад WB
SPP_RANGE = (0.15, 0.28)             # СПП (скидка Wildberries)

# Поведение покупателей — % выкупа по уровню маржи
MODEL_BUYOUT_BASE = {
    "high":   0.84,
    "normal": 0.80,
    "low":    0.76,
}

# Корректировка выкупа по размеру — XS и XL чаще возвращают
SIZE_BUYOUT_DELTA = {"XS": -0.08, "S": 0.02, "M": 0.03, "L": 0.00, "XL": -0.07}

# Распределение спроса по размерам
SIZE_WEIGHT = {"XS": 0.10, "S": 0.24, "M": 0.32, "L": 0.24, "XL": 0.10}

# Сезонность термобелья — множитель спроса по месяцу
SEASON_MULT = {
    1: 1.5, 2: 1.3, 3: 0.9,  4: 0.6,
    5: 0.4, 6: 0.3, 7: 0.3,  8: 0.4,
    9: 0.8, 10: 1.2, 11: 1.7, 12: 1.9,
}

# Задержка выкупа после заказа (дни)
BUYOUT_LAG = (2, 8)

# Реклама
ADS_SHARE_OF_REVENUE = (0.07, 0.14)   # ДРР в среднем 7-14%
ADS_CAMPAIGN_COUNT = 8                # число кампаний

# Цель портфеля по выручке — ориентируемся на масштаб ENIX 2025 (~450 млн)
TARGET_ANNUAL_REVENUE = 450_000_000

# =====================================================================
# СПРАВОЧНИК МОДЕЛЕЙ (реалистичная матрица женского термобелья)
# =====================================================================

MODELS = [
    # (id, название, базовая цена, уровень маржи, категория)
    (1,  "Термобелье классика базовое",        900,  "normal", "Термобелье"),
    (2,  "Термобелье шерсть мерино",           2800, "high",   "Термобелье"),
    (3,  "Леггинсы повседневные",              650,  "low",    "Леггинсы"),
    (4,  "Леггинсы спортивные",                1200, "normal", "Леггинсы"),
    (5,  "Леггинсы утеплённые на флисе",       1800, "normal", "Леггинсы"),
    (6,  "Боди бесшовное",                     1500, "normal", "Термобелье"),
    (7,  "Футболка термо длинный рукав",       1100, "normal", "Термобелье"),
    (8,  "Шорты велосипедки",                  850,  "low",    "Спортивное"),
    (9,  "Леггинсы push-up",                   1400, "normal", "Леггинсы"),
    (10, "Комбинезон термо",                   2500, "high",   "Термобелье"),
    (11, "Леггинсы бесшовные",                 950,  "low",    "Леггинсы"),
    (12, "Топ спортивный",                     1300, "normal", "Спортивное"),
    (13, "Водолазка термо",                    1200, "normal", "Термобелье"),
    (14, "Леггинсы коррекционные",             1600, "normal", "Леггинсы"),
    (15, "Костюм термо (комплект)",            3200, "high",   "Термобелье"),
]

SIZES = ["XS", "S", "M", "L", "XL"]

# Для каждой модели — список (цвет, размеры). Так получаем ~80 реальных SKU.
MODEL_VARIANTS = {
    1:  [("чёрный", SIZES), ("графит", SIZES)],
    2:  [("чёрный", SIZES), ("какао", ["S", "M", "L"])],
    3:  [("чёрный", SIZES), ("серый", ["S", "M", "L"])],
    4:  [("чёрный", SIZES), ("графит", ["S", "M", "L", "XL"])],
    5:  [("чёрный", SIZES)],
    6:  [("чёрный", SIZES), ("бежевый", ["S", "M", "L"])],
    7:  [("чёрный", ["S", "M", "L", "XL"])],
    8:  [("чёрный", ["S", "M", "L"])],
    9:  [("чёрный", SIZES)],
    10: [("чёрный", SIZES)],
    11: [("чёрный", SIZES)],
    12: [("чёрный", ["S", "M", "L"])],
    13: [("чёрный", SIZES)],
    14: [("чёрный", ["S", "M", "L"])],
    15: [("чёрный", ["S", "M", "L", "XL"])],
}

# Относительная «популярность» модели — влияет на объём продаж
MODEL_POPULARITY = {
    1: 3.0, 2: 1.2, 3: 2.5, 4: 2.0, 5: 1.5,
    6: 1.3, 7: 1.4, 8: 1.1, 9: 1.6, 10: 0.8,
    11: 1.8, 12: 1.0, 13: 1.2, 14: 1.0, 15: 0.7,
}


# =====================================================================
# УТИЛИТЫ
# =====================================================================

def daterange(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def uni(a: float, b: float) -> float:
    return random.uniform(a, b)


def ri(a: int, b: int) -> int:
    return random.randint(a, b)


# =====================================================================
# 1. СПРАВОЧНИК SKU
# =====================================================================

def build_sku() -> pd.DataFrame:
    rows = []
    sku_id = 1
    for model_id, name, base_price, tier, category in MODELS:
        for color, sizes in MODEL_VARIANTS[model_id]:
            for size in sizes:
                article = f"ENX-{model_id:03d}-{{color_code}}-{size}"
                article = article.format(color_code=color[:2].upper())
                barcode = f"46000{sku_id:08d}"
                rows.append({
                    "sku_id": sku_id,
                    "article": article,
                    "barcode": barcode,
                    "model_id": model_id,
                    "model_name": name,
                    "category": category,
                    "size": size,
                    "color": color,
                    "margin_tier": tier,
                    "base_price": base_price,
                    "started_at": START_DATE.isoformat(),
                })
                sku_id += 1
    return pd.DataFrame(rows)


# =====================================================================
# 2. ПАРТИИ ЗАКУПОК (CoGS по FIFO)
# =====================================================================

def build_batches(sku_df: pd.DataFrame) -> pd.DataFrame:
    """Партии приходят раз в 60-90 дней на SKU, объём ~ 2 месяца спроса."""
    rows = []
    batch_id = 1

    # Для реалистичности — все модели одной серии приходят в одну партию поставщика
    # Но для простоты: партия на SKU
    for _, sku in sku_df.iterrows():
        price = sku["base_price"]
        tier = sku["margin_tier"]
        cost_pct = uni(*SELLER_COST_PCT)
        if tier == "high":
            cost_pct = max(0.30, cost_pct)  # дорогие товары — выше себестоимость
        base_cost = round(price * cost_pct, 2)

        # Первая партия до старта продаж
        current_date = START_DATE - timedelta(days=ri(5, 20))
        batch_num = 0
        while current_date < END_DATE + timedelta(days=30):
            # Объём партии зависит от популярности модели
            popularity = MODEL_POPULARITY[sku["model_id"]]
            size_share = SIZE_WEIGHT[sku["size"]]
            # Партия ≈ 3-5 месяцев спроса (так в реальности закупают из Китая под сезон)
            qty = int(400 * popularity * size_share * uni(3.5, 5.5))
            qty = max(qty, 200)
            # «Паразитные» размеры (XS, XL) часто перезакупают — так появляются неликвиды
            if sku["size"] in ("XS", "XL"):
                qty = int(qty * uni(1.3, 1.8))

            # Инфляция себестоимости между партиями (курс юаня + подорожание)
            inflation = 1 + 0.025 * batch_num + uni(-0.01, 0.02)
            cost_per_unit = round(base_cost * inflation, 2)
            packaging = round(uni(*PACKAGING_COST), 2)
            logistics_to_wb = round(uni(*LOGISTICS_TO_WB), 2)
            total_cost_per_unit = cost_per_unit + packaging + logistics_to_wb

            rows.append({
                "batch_id": batch_id,
                "sku_id": sku["sku_id"],
                "arrival_date": current_date.isoformat(),
                "qty_received": qty,
                "cost_per_unit": cost_per_unit,
                "packaging_cost": packaging,
                "logistics_to_wb": logistics_to_wb,
                "total_cost_per_unit": round(total_cost_per_unit, 2),
            })
            batch_id += 1
            batch_num += 1
            current_date += timedelta(days=ri(55, 90))

    return pd.DataFrame(rows)


# =====================================================================
# 3. ЗАКАЗЫ (с сезонностью термобелья)
# =====================================================================

def build_orders(sku_df: pd.DataFrame) -> pd.DataFrame:
    """Генерация заказов по дням. Распределение по SKU — по популярности × сезон × размер."""
    rows = []
    order_id = 1

    # Веса SKU
    sku_weights = []
    for _, sku in sku_df.iterrows():
        w = MODEL_POPULARITY[sku["model_id"]] * SIZE_WEIGHT[sku["size"]]
        # Чёрный популярнее
        if sku["color"] == "чёрный":
            w *= 1.6
        sku_weights.append(w)
    sku_weights = np.array(sku_weights)

    # Калибровка целевого числа заказов, чтобы попасть в TARGET_ANNUAL_REVENUE
    avg_price = (sku_df["base_price"] * sku_weights).sum() / sku_weights.sum()
    avg_price_after_spp = avg_price * (1 - np.mean(SPP_RANGE))
    season_avg = np.mean(list(SEASON_MULT.values()))
    expected_days = (END_DATE - START_DATE).days + 1
    daily_orders_base = TARGET_ANNUAL_REVENUE / (expected_days * season_avg * avg_price_after_spp)

    for day in daterange(START_DATE, END_DATE):
        season = SEASON_MULT[day.month]
        # Небольшая недельная сезонность (выходные выше)
        weekday_mult = 1.15 if day.weekday() >= 5 else 1.0
        day_orders_total = int(daily_orders_base * season * weekday_mult * uni(0.85, 1.15))

        # Распределение по SKU
        probs = sku_weights / sku_weights.sum()
        sku_choices = np.random.choice(sku_df["sku_id"].values, size=day_orders_total, p=probs)

        # Группировка — пакуем заказы на тот же SKU в день
        unique, counts = np.unique(sku_choices, return_counts=True)
        for sku_id, qty in zip(unique, counts):
            sku_row = sku_df[sku_df["sku_id"] == sku_id].iloc[0]
            base_price = sku_row["base_price"]
            spp = uni(*SPP_RANGE)
            price_before_spp = base_price
            price_after_spp = round(base_price * (1 - spp), 2)
            rows.append({
                "order_id": order_id,
                "order_date": day.isoformat(),
                "sku_id": int(sku_id),
                "qty": int(qty),
                "price_before_spp": float(price_before_spp),
                "spp_pct": round(spp, 4),
                "price_after_spp": float(price_after_spp),
                "revenue_after_spp": round(price_after_spp * qty, 2),
                "warehouse_type": "FBO",
            })
            order_id += 1

    return pd.DataFrame(rows)


# =====================================================================
# 4. ВЫКУПЫ И ВОЗВРАТЫ
# =====================================================================

def build_sales_and_returns(orders: pd.DataFrame, sku_df: pd.DataFrame):
    sales_rows = []
    returns_rows = []
    sale_id = 1
    return_id = 1

    sku_lookup = sku_df.set_index("sku_id").to_dict("index")

    for _, order in orders.iterrows():
        sku_info = sku_lookup[order["sku_id"]]
        tier = sku_info["margin_tier"]
        size = sku_info["size"]
        buyout_pct = MODEL_BUYOUT_BASE[tier] + SIZE_BUYOUT_DELTA[size]
        buyout_pct = min(0.95, max(0.55, buyout_pct + uni(-0.05, 0.05)))

        qty = order["qty"]
        qty_bought = int(round(qty * buyout_pct))
        qty_returned = qty - qty_bought

        order_date = date.fromisoformat(order["order_date"])
        sale_date = order_date + timedelta(days=ri(*BUYOUT_LAG))

        if qty_bought > 0 and sale_date <= END_DATE:
            sales_rows.append({
                "sale_id": sale_id,
                "order_id": order["order_id"],
                "sale_date": sale_date.isoformat(),
                "sku_id": int(order["sku_id"]),
                "qty_sold": qty_bought,
                "revenue_after_spp": round(order["price_after_spp"] * qty_bought, 2),
            })
            sale_id += 1

        if qty_returned > 0:
            return_date = order_date + timedelta(days=ri(5, 15))
            if return_date <= END_DATE:
                returns_rows.append({
                    "return_id": return_id,
                    "order_id": order["order_id"],
                    "return_date": return_date.isoformat(),
                    "sku_id": int(order["sku_id"]),
                    "qty_returned": qty_returned,
                    "return_reason": random.choice(
                        ["не подошёл размер", "брак", "не понравился цвет",
                         "не подошла посадка", "передумал клиент"]
                    ),
                })
                return_id += 1

    return pd.DataFrame(sales_rows), pd.DataFrame(returns_rows)


# =====================================================================
# 5. ФИНАНСОВЫЙ ОТЧЁТ WB (построчно, аналог reportDetailByPeriod)
# =====================================================================

def build_finance_wb(sales: pd.DataFrame, returns: pd.DataFrame,
                     orders: pd.DataFrame) -> pd.DataFrame:
    """
    Строки финотчёта по категориям:
        - 'продажа'       — комиссия WB и эквайринг от выручки
        - 'логистика'     — доставка до клиента по заказам
        - 'возврат_лог'   — обратная логистика
        - 'хранение'      — ежедневное хранение (упрощённо — на уровне дня, не SKU)
        - 'приёмка'       — платная приёмка
        - 'штраф'         — штрафы
    """
    rows = []
    fin_id = 1

    # 1) Строки по продажам: комиссия + эквайринг
    for _, sale in sales.iterrows():
        rev = sale["revenue_after_spp"]
        commission = round(rev * WB_COMMISSION_PCT, 2)
        acquiring = round(rev * WB_ACQUIRING_PCT, 2)
        rows.append({
            "fin_id": fin_id, "op_date": sale["sale_date"], "op_type": "продажа",
            "sku_id": int(sale["sku_id"]), "qty": sale["qty_sold"],
            "revenue": rev, "amount": -(commission + acquiring),
            "commission": commission, "acquiring": acquiring,
        })
        fin_id += 1

    # 2) Логистика до клиента — по каждому заказу
    for _, order in orders.iterrows():
        qty = order["qty"]
        log_cost = round(uni(*WB_LOGISTICS_FORWARD) * qty, 2)
        rows.append({
            "fin_id": fin_id, "op_date": order["order_date"], "op_type": "логистика",
            "sku_id": int(order["sku_id"]), "qty": qty,
            "revenue": 0.0, "amount": -log_cost,
            "commission": 0.0, "acquiring": 0.0,
        })
        fin_id += 1

    # 3) Обратная логистика — по возвратам
    for _, ret in returns.iterrows():
        qty = ret["qty_returned"]
        log_cost = round(uni(*WB_LOGISTICS_REVERSE) * qty, 2)
        rows.append({
            "fin_id": fin_id, "op_date": ret["return_date"], "op_type": "возврат_лог",
            "sku_id": int(ret["sku_id"]), "qty": qty,
            "revenue": 0.0, "amount": -log_cost,
            "commission": 0.0, "acquiring": 0.0,
        })
        fin_id += 1

    # 4) Хранение — ежедневно, зависит от реального запаса × сезонного тарифа WB.
    # WB периодически повышает тариф на хранение в пик сезона.
    # Считаем через последний известный остаток на день (линейное приближение между снимками).
    # Для простоты: средний запас в день * сезонный тариф + небольшая случайность.
    orders_qty_cum = 0  # накопление заказов для оценки запаса
    sales_qty_cum = 0
    orders_by_day = orders.groupby("order_date")["qty"].sum().to_dict() if not orders.empty else {}
    sales_by_day = sales.groupby("sale_date")["qty_sold"].sum().to_dict() if not sales.empty else {}
    # Начальный запас — сумма всех приходов на старте
    stock_approx = 0

    for day in daterange(START_DATE, END_DATE):
        # Грубое приближение: запас = заказанные - выкупленные (с учётом возвратов 80% обратно)
        sales_qty_cum += sales_by_day.get(day.isoformat(), 0)
        # Сезонный тариф: пик дек-янв = x1.5, лето = x0.7
        season_tariff = SEASON_MULT[day.month] / 1.0
        base_rate = 0.15  # ₽ за единицу хранения в день
        # Приблизительная оценка живого остатка на складе (упрощённо)
        stock_approx = max(5000, 30000 - sales_qty_cum % 10000)
        storage_cost = round(stock_approx * base_rate * season_tariff * uni(0.9, 1.1), 2)

        rows.append({
            "fin_id": fin_id, "op_date": day.isoformat(), "op_type": "хранение",
            "sku_id": None, "qty": None,
            "revenue": 0.0, "amount": -storage_cost,
            "commission": 0.0, "acquiring": 0.0,
        })
        fin_id += 1

        # 5) Платная приёмка — иногда
        if random.random() < WB_ACCEPTANCE_DAY_PROB:
            fee = round(uni(500, 5000), 2)
            rows.append({
                "fin_id": fin_id, "op_date": day.isoformat(), "op_type": "приёмка",
                "sku_id": None, "qty": None,
                "revenue": 0.0, "amount": -fee,
                "commission": 0.0, "acquiring": 0.0,
            })
            fin_id += 1

        # 6) Штрафы — редко
        if random.random() < WB_FINE_DAILY_PROB:
            fine = round(uni(*WB_FINE_RANGE), 2)
            rows.append({
                "fin_id": fin_id, "op_date": day.isoformat(), "op_type": "штраф",
                "sku_id": None, "qty": None,
                "revenue": 0.0, "amount": -fine,
                "commission": 0.0, "acquiring": 0.0,
            })
            fin_id += 1

    return pd.DataFrame(rows)


# =====================================================================
# 6. ОСТАТКИ НА ДЕНЬ (снимок)
# =====================================================================

def build_stock_daily(sku_df: pd.DataFrame, batches: pd.DataFrame,
                      sales: pd.DataFrame, returns: pd.DataFrame) -> pd.DataFrame:
    """
    Остаток на день = сумма партий, пришедших ≤ дня
                    - сумма выкупов ≤ дня
                    + сумма возвратов, которые физически вернулись на склад
                      (считаем 80% возвратов возвращаются обратно в сток через 7-14 дней;
                       20% идут в брак / распродажу).

    Снимки — раз в неделю (понедельник), чтобы не раздувать таблицу.
    """
    rows = []

    sales_by_sku_date = sales.groupby(["sku_id", "sale_date"])["qty_sold"].sum().reset_index()
    batches_by_sku_date = batches.groupby(["sku_id", "arrival_date"])["qty_received"].sum().reset_index()

    # Возвраты назад в сток: 80% возвратов возвращаются через 10 дней
    returns_back = returns.copy()
    if not returns_back.empty:
        returns_back["back_date"] = pd.to_datetime(returns_back["return_date"]).dt.date \
                                    + pd.Timedelta(days=10)
        returns_back["qty_back"] = (returns_back["qty_returned"] * 0.8).round().astype(int)
        returns_by_sku_date = returns_back.groupby(["sku_id", "back_date"])["qty_back"].sum().reset_index()
    else:
        returns_by_sku_date = pd.DataFrame(columns=["sku_id", "back_date", "qty_back"])

    for sku_id in sku_df["sku_id"].unique():
        batch_slice = batches_by_sku_date[batches_by_sku_date["sku_id"] == sku_id].copy()
        batch_slice["arrival_date"] = pd.to_datetime(batch_slice["arrival_date"]).dt.date
        sale_slice = sales_by_sku_date[sales_by_sku_date["sku_id"] == sku_id].copy()
        sale_slice["sale_date"] = pd.to_datetime(sale_slice["sale_date"]).dt.date
        ret_slice = returns_by_sku_date[returns_by_sku_date["sku_id"] == sku_id].copy()

        batch_lookup = dict(zip(batch_slice["arrival_date"], batch_slice["qty_received"]))
        sale_lookup = dict(zip(sale_slice["sale_date"], sale_slice["qty_sold"]))
        ret_lookup = dict(zip(ret_slice["back_date"], ret_slice["qty_back"]))

        stock = 0
        for day in daterange(START_DATE, END_DATE):
            stock += batch_lookup.get(day, 0)
            stock -= sale_lookup.get(day, 0)
            stock += ret_lookup.get(day, 0)
            stock = max(stock, 0)
            if day.weekday() == 0 or day == END_DATE:
                rows.append({
                    "stock_date": day.isoformat(),
                    "sku_id": int(sku_id),
                    "warehouse_type": "FBO",
                    "qty_on_stock": int(stock),
                })

    return pd.DataFrame(rows)


# =====================================================================
# 7. ВЫПЛАТЫ WB НА РАСЧЁТНЫЙ СЧЁТ (банковская выписка)
# =====================================================================

def build_payments(finance: pd.DataFrame, sales: pd.DataFrame) -> pd.DataFrame:
    """
    Еженедельная выплата = выручка выкупов за неделю + все удержания WB.
    Для реалистичности добавим ошибку -0.3..+0.3% (имитация расхождений).
    """
    rows = []
    pay_id = 1

    sales = sales.copy()
    sales["sale_date"] = pd.to_datetime(sales["sale_date"])
    finance = finance.copy()
    finance["op_date"] = pd.to_datetime(finance["op_date"])

    # Группируем по ISO-неделям
    sales["week"] = sales["sale_date"].dt.strftime("%G-W%V")
    finance["week"] = finance["op_date"].dt.strftime("%G-W%V")

    rev_by_week = sales.groupby("week")["revenue_after_spp"].sum()
    fin_by_week = finance.groupby("week")["amount"].sum()  # amount отрицательный → удержания

    weeks = sorted(set(rev_by_week.index) | set(fin_by_week.index))

    for week in weeks:
        rev = float(rev_by_week.get(week, 0.0))
        fin = float(fin_by_week.get(week, 0.0))
        settlement = rev + fin  # выплата = выручка минус удержания
        noise = uni(-0.003, 0.003) * abs(settlement)
        pay = round(settlement + noise, 2)

        # Привязываем выплату к пятнице этой недели
        year, w = week.split("-W")
        pay_date = date.fromisocalendar(int(year), int(w), 5)
        if START_DATE <= pay_date <= END_DATE + timedelta(days=7):
            rows.append({
                "payment_id": pay_id,
                "payment_date": pay_date.isoformat(),
                "week": week,
                "amount_calculated": round(settlement, 2),
                "amount_received": pay,
                "diff": round(pay - settlement, 2),
            })
            pay_id += 1

    return pd.DataFrame(rows)


# =====================================================================
# 8. РЕКЛАМНЫЕ РАСХОДЫ (ВП + АРК)
# =====================================================================

def build_ads(sku_df: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    """
    Логика: кампании (ВП и АРК) тратят в день бюджет, пропорциональный выручке
    на закреплённых за кампанией SKU, с ДРР 7-14%.
    Часть кампаний «неэффективные» — ДРР 20-35% на отдельных SKU
    (это и будет цепляться витриной «ROMI < 0»).
    """
    rows = []

    # Распределим SKU по кампаниям
    sku_ids = sku_df["sku_id"].tolist()
    random.shuffle(sku_ids)
    campaigns = []
    chunk = max(1, len(sku_ids) // ADS_CAMPAIGN_COUNT)
    for i in range(ADS_CAMPAIGN_COUNT):
        slice_ = sku_ids[i * chunk:(i + 1) * chunk]
        if i == ADS_CAMPAIGN_COUNT - 1:
            slice_ = sku_ids[i * chunk:]
        camp_type = random.choice(["ВП", "АРК"])
        is_inefficient = random.random() < 0.25  # 25% кампаний — убыточные
        campaigns.append({
            "campaign_id": i + 1,
            "campaign_name": f"{camp_type}-{i+1:02d}",
            "campaign_type": camp_type,
            "sku_ids": slice_,
            "efficient": not is_inefficient,
        })

    # Выручка по SKU по дням — для аллокации
    orders_rev = orders.groupby(["order_date", "sku_id"])["revenue_after_spp"].sum().reset_index()

    for camp in campaigns:
        for _, row in orders_rev.iterrows():
            if int(row["sku_id"]) not in camp["sku_ids"]:
                continue
            rev = row["revenue_after_spp"]
            drr = uni(*ADS_SHARE_OF_REVENUE)
            if not camp["efficient"]:
                drr = uni(0.20, 0.35)
            ads_spend = round(rev * drr, 2)
            if ads_spend < 1:
                continue
            rows.append({
                "ads_date": row["order_date"],
                "campaign_id": camp["campaign_id"],
                "campaign_name": camp["campaign_name"],
                "campaign_type": camp["campaign_type"],
                "sku_id": int(row["sku_id"]),
                "ads_spend": ads_spend,
            })

    return pd.DataFrame(rows)


# =====================================================================
# ЗАГРУЗКА В DUCKDB
# =====================================================================

def load_to_duckdb(tables: dict[str, pd.DataFrame]):
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = duckdb.connect(str(DB_PATH))
    for name, df in tables.items():
        con.register(f"{name}_df", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM {name}_df")
        print(f"  → {name}: {len(df):>8,} строк")
    con.close()


# =====================================================================
# MAIN
# =====================================================================

def main():
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("1/8  Справочник SKU...")
    sku = build_sku()
    sku.to_csv(DATA_DIR / "sku.csv", index=False, encoding="utf-8-sig")
    print(f"      SKU: {len(sku)}")

    print("2/8  Партии закупок (FIFO)...")
    batches = build_batches(sku)
    batches.to_csv(DATA_DIR / "cogs_batch.csv", index=False, encoding="utf-8-sig")
    print(f"      Партий: {len(batches)}")

    print("3/8  Заказы по дням (с сезонностью термобелья)...")
    orders = build_orders(sku)
    orders.to_csv(DATA_DIR / "orders.csv", index=False, encoding="utf-8-sig")
    print(f"      Заказов (строк агрегатов): {len(orders)}, суммарно шт: {orders['qty'].sum():,}")
    print(f"      Выручка после СПП (брутто): {orders['revenue_after_spp'].sum()/1e6:.1f} млн ₽")

    print("4/8  Выкупы и возвраты...")
    sales, returns = build_sales_and_returns(orders, sku)
    sales.to_csv(DATA_DIR / "sales.csv", index=False, encoding="utf-8-sig")
    returns.to_csv(DATA_DIR / "returns.csv", index=False, encoding="utf-8-sig")
    buyout_pct = sales["qty_sold"].sum() / orders["qty"].sum()
    print(f"      Выкупов: {len(sales)}, выкуплено шт: {sales['qty_sold'].sum():,} ({buyout_pct*100:.1f}%)")
    print(f"      Возвратов: {len(returns)}")

    print("5/8  Финансовый отчёт WB (построчно)...")
    finance = build_finance_wb(sales, returns, orders)
    finance.to_csv(DATA_DIR / "finance_wb.csv", index=False, encoding="utf-8-sig")
    print(f"      Строк: {len(finance):,}")

    print("6/8  Остатки на день (снимок понедельниками)...")
    stock = build_stock_daily(sku, batches, sales, returns)
    stock.to_csv(DATA_DIR / "stock_daily.csv", index=False, encoding="utf-8-sig")
    print(f"      Строк: {len(stock):,}")

    print("7/8  Выплаты WB на расчётный счёт...")
    payments = build_payments(finance, sales)
    payments.to_csv(DATA_DIR / "payments.csv", index=False, encoding="utf-8-sig")
    print(f"      Выплат: {len(payments)}, сумма: {payments['amount_received'].sum()/1e6:.1f} млн ₽")

    print("8/8  Рекламные расходы (ВП + АРК)...")
    ads = build_ads(sku, orders)
    ads.to_csv(DATA_DIR / "ads_daily.csv", index=False, encoding="utf-8-sig")
    print(f"      Строк: {len(ads):,}, бюджет: {ads['ads_spend'].sum()/1e6:.1f} млн ₽")

    print("\nЗагрузка в DuckDB...")
    load_to_duckdb({
        "sku": sku,
        "cogs_batch": batches,
        "orders": orders,
        "sales": sales,
        "returns": returns,
        "finance_wb": finance,
        "stock_daily": stock,
        "payments": payments,
        "ads_daily": ads,
    })

    print(f"\nГотово. База: {DB_PATH}")


if __name__ == "__main__":
    main()
