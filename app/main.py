"""
ENIX Коммерческая аналитика — дашборд на Streamlit.

Запуск:
    .venv\\Scripts\\streamlit.exe run app/main.py

Фильтры в сайдбаре применяются ко всем вкладкам.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from streamlit_option_menu import option_menu

DB_PATH = Path(__file__).resolve().parent.parent / "enix_prototype.duckdb"


# =====================================================================
# НАСТРОЙКА СТРАНИЦЫ
# =====================================================================

st.set_page_config(
    page_title="ENIX · Коммерческая аналитика",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =====================================================================
# ГЛОБАЛЬНЫЙ CSS — forced light, матовая эстетика
# =====================================================================

EXTERNAL_HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Golos+Text:wght@400;500;600;700&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0" rel="stylesheet">
"""
st.markdown(EXTERNAL_HEAD, unsafe_allow_html=True)

CSS = """
<style>

/* ============================================================
   FORCED LIGHT THEME — переопределяем всё, даже если браузер dark
   ============================================================ */
:root, html, body {
    color-scheme: light !important;
    --primary-color: #4F46E5 !important;
    --background-color: #FAFAFB !important;
    --secondary-background-color: #FFFFFF !important;
    --text-color: #0F172A !important;
}
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > div,
section.main,
[data-testid="stMain"] {
    background-color: #FAFAFB !important;
    color: #0F172A !important;
}
[data-testid="stHeader"] {
    background: transparent !important;
}

/* Основной шрифт */
html, body, [class*="css"], button, input, textarea, select,
[data-testid="stAppViewContainer"] * {
    font-family: 'Golos Text', -apple-system, BlinkMacSystemFont,
                 'Segoe UI', Roboto, sans-serif;
}

/* Прячем лишние элементы, но header оставляем — там кнопка сайдбара */
#MainMenu, footer { display: none !important; }
header[data-testid="stHeader"] {
    background: transparent !important;
    height: auto !important;
}
/* Прячем декорации в header, но оставляем кнопку сворачивания */
header[data-testid="stHeader"] [data-testid="stDecoration"] { display: none !important; }
header[data-testid="stHeader"] [data-testid="stStatusWidget"] { display: none !important; }
[data-testid="stAppDeployButton"],
.stAppDeployButton {
    display: none !important;
}

/* Кнопка сворачивания сайдбара — всегда видима */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"] {
    display: flex !important;
    visibility: visible !important;
    color: #64748B !important;
}

/* Material Symbols — применяем шрифт */
.material-symbols-rounded,
.material-symbols-outlined,
.material-icons,
[data-testid*="icon"] span,
[data-testid*="Icon"] span {
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined',
                 'Material Icons' !important;
    font-weight: normal !important;
    font-style: normal !important;
    font-size: 20px !important;
    line-height: 1 !important;
    letter-spacing: normal !important;
    text-transform: none !important;
    white-space: nowrap !important;
    word-wrap: normal !important;
    direction: ltr !important;
    -webkit-font-feature-settings: 'liga' !important;
    -webkit-font-smoothing: antialiased !important;
    font-feature-settings: 'liga' !important;
    color: #64748B !important;
}

/* Форсируем Material Symbols на все кнопки сворачивания */
[data-testid="stSidebarCollapseButton"] span,
[data-testid="collapsedControl"] span,
[data-testid="stSidebarCollapsedControl"] span,
button[kind="headerNoPadding"] span {
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined' !important;
    font-weight: 400 !important;
    font-style: normal !important;
    font-size: 20px !important;
    line-height: 1 !important;
    color: #64748B !important;
    font-feature-settings: 'liga' !important;
    -webkit-font-feature-settings: 'liga' !important;
}

/* ============================================================
   КОНТЕЙНЕР
   ============================================================ */
.block-container {
    padding-top: 2.5rem !important;
    padding-bottom: 3rem !important;
    max-width: 1440px !important;
}

/* ============================================================
   ТИПОГРАФИКА
   ============================================================ */
h1, h2, h3, h4, h5, h6, p, span, div, label {
    color: #0F172A;
}
h1 { font-weight: 700 !important; letter-spacing: -0.02em !important; }
h2, h3 { font-weight: 600 !important; letter-spacing: -0.015em !important; }

/* ============================================================
   САЙДБАР — чистый белый (перебиваем BaseWeb)
   ============================================================ */
section[data-testid="stSidebar"],
section[data-testid="stSidebar"] > div {
    background: #FFFFFF !important;
    border-right: 1px solid #E2E8F0 !important;
}
section[data-testid="stSidebar"] > div:first-child {
    padding-top: 2rem !important;
}
section[data-testid="stSidebar"] * { color: #0F172A; }
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    color: #334155 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
}
section[data-testid="stSidebar"] hr {
    border-color: #EEF0F3 !important;
    margin: 1.5rem 0 !important;
}

/* ============================================================
   ПОЛЯ ВВОДА В САЙДБАРЕ: date_input, multiselect
   Перебиваем BaseWeb тёмную тему через высокую специфичность
   ============================================================ */
html body section[data-testid="stSidebar"] div[data-baseweb="input"],
html body section[data-testid="stSidebar"] div[data-baseweb="base-input"],
html body section[data-testid="stSidebar"] div[data-baseweb="input"] > div,
html body section[data-testid="stSidebar"] div[data-baseweb="select"] > div,
html body section[data-testid="stSidebar"] div[data-baseweb="select"] div[role="combobox"],
html body section[data-testid="stSidebar"] div[data-baseweb="select"] div[role="button"],
html body section[data-testid="stSidebar"] [data-testid="stDateInput"] div,
html body section[data-testid="stSidebar"] [data-testid="stMultiSelect"] div[data-baseweb="select"] > div,
html body section[data-testid="stSidebar"] [data-testid="stMultiSelect"] div[data-baseweb="select"] div {
    background-color: #FFFFFF !important;
    background: #FFFFFF !important;
    border-color: #E2E8F0 !important;
    color: #0F172A !important;
}

/* Внутренние элементы (input, span, placeholder) */
html body section[data-testid="stSidebar"] [data-baseweb] input,
html body section[data-testid="stSidebar"] [data-baseweb] span,
html body section[data-testid="stSidebar"] [data-baseweb] div[role="button"] {
    background: transparent !important;
    color: #0F172A !important;
    caret-color: #0F172A !important;
}
html body section[data-testid="stSidebar"] [data-baseweb] input::placeholder {
    color: #94A3B8 !important;
    opacity: 1 !important;
}

/* Иконки SVG внутри полей */
html body section[data-testid="stSidebar"] [data-baseweb] svg {
    fill: #64748B !important;
}

/* Иконка календаря и стрелки селекта */
section[data-testid="stSidebar"] [data-baseweb="input"] svg,
section[data-testid="stSidebar"] [data-baseweb="select"] svg {
    fill: #64748B !important;
    color: #64748B !important;
}

/* Контейнер поля (общий) */
section[data-testid="stSidebar"] [data-testid="stDateInput"] > div,
section[data-testid="stSidebar"] [data-testid="stMultiSelect"] > div,
section[data-testid="stSidebar"] [data-testid="stSelectbox"] > div,
section[data-testid="stSidebar"] [data-testid="stTextInput"] > div {
    background-color: #FFFFFF !important;
}

/* Dropdown popover (когда открыто) — тоже светлый */
[data-baseweb="popover"] [data-baseweb="menu"] {
    background-color: #FFFFFF !important;
    border: 1px solid #EEF0F3 !important;
    box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08) !important;
}
[data-baseweb="popover"] [data-baseweb="menu"] li {
    background-color: #FFFFFF !important;
    color: #0F172A !important;
}
[data-baseweb="popover"] [data-baseweb="menu"] li:hover {
    background-color: #F7F8FA !important;
}

/* Календарь */
[data-baseweb="calendar"] {
    background-color: #FFFFFF !important;
}
[data-baseweb="calendar"] * {
    color: #0F172A !important;
}

/* ============================================================
   БРЕНД
   ============================================================ */
.enix-brand {
    font-size: 24px;
    font-weight: 700;
    color: #0F172A;
    letter-spacing: 0.08em;
    margin: 0 0 4px 0;
    line-height: 1;
}
.enix-brand-sub {
    color: #94A3B8;
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 28px;
}

/* ============================================================
   ЗАГОЛОВОК СТРАНИЦЫ
   ============================================================ */
.page-title {
    font-size: 26px;
    font-weight: 700;
    color: #0F172A;
    letter-spacing: -0.02em;
    margin-bottom: 2px;
}
.page-sub {
    font-size: 14px;
    color: #64748B;
    margin-bottom: 28px;
    font-weight: 400;
}

.section-h {
    font-size: 13px;
    font-weight: 600;
    color: #475569;
    letter-spacing: 0.02em;
    margin: 24px 0 12px 0;
}

/* ============================================================
   МЕТРИКИ — спокойные белые карточки
   ============================================================ */
[data-testid="stMetric"] {
    background: #FFFFFF !important;
    border: 1px solid #EEF0F3 !important;
    padding: 18px 20px !important;
    border-radius: 12px !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
[data-testid="stMetric"]:hover {
    border-color: #CBD5E1 !important;
    box-shadow: 0 4px 10px rgba(15, 23, 42, 0.06);
}
[data-testid="stMetricLabel"] p {
    font-size: 12px !important;
    color: #64748B !important;
    font-weight: 500 !important;
    letter-spacing: 0 !important;
    text-transform: none !important;
}
[data-testid="stMetricValue"] {
    font-size: 26px !important;
    font-weight: 700 !important;
    color: #0F172A !important;
    letter-spacing: -0.02em;
    line-height: 1.2 !important;
}
[data-testid="stMetricDelta"] {
    font-size: 12px !important;
    font-weight: 500 !important;
}
[data-testid="stMetricDelta"] svg { display: none; }

/* ============================================================
   ALERTS — переопределяем нативные, используем свои
   ============================================================ */
[data-testid="stAlert"] {
    background: #FFFFFF !important;
    border: 1px solid #EEF0F3 !important;
    border-left-width: 3px !important;
    color: #0F172A !important;
    border-radius: 10px !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
    padding: 14px 18px !important;
}
[data-testid="stAlert"] * {
    color: #0F172A !important;
}

/* Разделитель */
hr {
    margin: 2rem 0 1.5rem 0 !important;
    border: none !important;
    border-top: 1px solid #EEF0F3 !important;
}

/* Caption */
[data-testid="stCaptionContainer"] {
    color: #64748B !important;
    font-size: 13px !important;
}

/* ============================================================
   РАДИО как pills
   ============================================================ */
div[role="radiogroup"] { gap: 6px; }
div[role="radiogroup"] > label {
    background: #FFFFFF;
    padding: 7px 14px;
    border-radius: 8px;
    border: 1px solid #EEF0F3;
    cursor: pointer;
    transition: all 0.15s ease;
    font-size: 13px;
    color: #334155;
}
div[role="radiogroup"] > label:hover {
    background: #F7F8FA;
    border-color: #CBD5E1;
}
div[role="radiogroup"] > label[data-baseweb="radio"] input:checked + div {
    color: #4F46E5;
}

/* ============================================================
   AGGRID
   ============================================================ */
.ag-theme-alpine, .ag-theme-alpine .ag-root-wrapper {
    --ag-font-family: 'Golos Text', sans-serif;
    --ag-font-size: 13px;
    --ag-header-background-color: #FAFAFB;
    --ag-header-foreground-color: #475569;
    --ag-odd-row-background-color: #FFFFFF;
    --ag-background-color: #FFFFFF;
    --ag-border-color: #EEF0F3;
    --ag-row-border-color: #F1F5F9;
    --ag-row-hover-color: #FAFAFB;
    --ag-selected-row-background-color: #EEF2FF;
    border-radius: 10px !important;
    border: 1px solid #EEF0F3 !important;
    overflow: hidden;
}
.ag-theme-alpine .ag-header-cell-text {
    font-weight: 600 !important;
    font-size: 12px !important;
    letter-spacing: 0.02em;
}

/* ============================================================
   SELECTBOX, MULTISELECT, DATE INPUT
   ============================================================ */
[data-baseweb="select"] > div,
[data-baseweb="input"] > div {
    background: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 8px !important;
}
[data-baseweb="tag"] {
    background: #EEF2FF !important;
    color: #4338CA !important;
    border: none !important;
}

/* ============================================================
   ПОЛЬЗОВАТЕЛЬСКИЕ ALERT-КАРТОЧКИ (через наш markdown)
   ============================================================ */
.alert-card {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    background: #FFFFFF;
    border: 1px solid #EEF0F3;
    border-left: 3px solid #94A3B8;
    border-radius: 10px;
    padding: 14px 18px;
    margin: 8px 0;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}
.alert-card .alert-dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    margin-top: 6px;
    flex-shrink: 0;
    box-shadow: 0 0 0 3px rgba(255, 255, 255, 1), 0 0 0 4px currentColor;
    opacity: 0.9;
}
.alert-card .alert-text {
    color: #0F172A;
    font-size: 14px;
    line-height: 1.5;
}
.alert-card .alert-text strong {
    color: #0F172A;
    font-weight: 600;
}
.alert-card.warn   { border-left-color: #F59E0B; }
.alert-card.warn   .alert-dot { background: #F59E0B; }
.alert-card.danger { border-left-color: #EF4444; }
.alert-card.danger .alert-dot { background: #EF4444; }
.alert-card.info   { border-left-color: #4F46E5; }
.alert-card.info   .alert-dot { background: #4F46E5; }
.alert-card.ok     { border-left-color: #10B981; }
.alert-card.ok     .alert-dot { background: #10B981; }
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)


# =====================================================================
# ПАЛИТРА И PLOTLY СТИЛЬ
# =====================================================================

PALETTE = {
    "primary": "#4F46E5",
    "success": "#10B981",
    "warn":    "#F59E0B",
    "danger":  "#EF4444",
    "neutral": "#94A3B8",
    "dark":    "#0F172A",
}

# Приглушённая палитра для plotly (менее кислотная)
PLOTLY_SEQ = ["#4F46E5", "#10B981", "#F59E0B", "#EF4444", "#06B6D4", "#8B5CF6"]


def style_fig(fig, height: int = 360):
    fig.update_layout(
        font=dict(family="Golos Text, sans-serif", size=12, color="#334155"),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        height=height,
        margin=dict(l=10, r=10, t=50, b=20),
        xaxis=dict(
            gridcolor="#F1F5F9", linecolor="#EEF0F3",
            tickcolor="#EEF0F3", title=dict(text=""),
            showline=False, zeroline=False,
            tickfont=dict(size=11, color="#64748B"),
        ),
        yaxis=dict(
            gridcolor="#F1F5F9", linecolor="#EEF0F3",
            tickcolor="#EEF0F3", showline=False, zeroline=False,
            tickfont=dict(size=11, color="#64748B"),
        ),
        legend=dict(
            bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)",
            orientation="h", y=1.08, x=0,
            font=dict(size=12, color="#475569", family="Golos Text"),
            itemsizing="constant",
        ),
    )
    return fig


# =====================================================================
# ПОДКЛЮЧЕНИЕ К БАЗЕ
# =====================================================================

@st.cache_resource
def get_con():
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data
def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    return get_con().execute(sql, params).fetchdf()


@st.cache_data
def dim_values():
    return q("SELECT DISTINCT category, model_name, size, color FROM sku")


@st.cache_data
def period_bounds():
    row = get_con().execute("SELECT MIN(day), MAX(day) FROM v_pnl_sku_day").fetchone()
    return row[0], row[1]


# =====================================================================
# ХЕЛПЕРЫ
# =====================================================================

def quote_list(values):
    return ",".join(f"'{v}'" for v in values)


def build_where(date_col: str = "day") -> str:
    conds = []
    period = st.session_state.get("period")
    if period and isinstance(period, tuple) and len(period) == 2:
        conds.append(f"{date_col} BETWEEN DATE '{period[0]}' AND DATE '{period[1]}'")
    for col, key in [
        ("category", "categories"),
        ("model_name", "models"),
        ("size", "sizes"),
        ("color", "colors"),
    ]:
        vals = st.session_state.get(key)
        if vals:
            conds.append(f"{col} IN ({quote_list(vals)})")
    return "WHERE " + " AND ".join(conds) if conds else ""


def fmt_rub(x: float, suffix: str = "") -> str:
    if pd.isna(x):
        return "—"
    if abs(x) >= 1e9:
        return f"{x / 1e9:.2f} млрд{suffix}"
    if abs(x) >= 1e6:
        return f"{x / 1e6:.1f} млн{suffix}"
    if abs(x) >= 1e3:
        return f"{x / 1e3:.0f} тыс{suffix}"
    return f"{x:.0f}{suffix}"


def fmt_pct(x: float) -> str:
    if pd.isna(x):
        return "—"
    return f"{x:.1f}%"


def alert(level: str, text: str):
    """level: warn | danger | info | ok"""
    st.markdown(
        f'<div class="alert-card {level}">'
        f'<div class="alert-dot"></div>'
        f'<div class="alert-text">{text}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def aggrid_table(df: pd.DataFrame, height: int = 420, pin_col: str | None = None):
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(
        filterable=True, sortable=True, resizable=True,
        minColumnWidth=90,
    )
    if pin_col and pin_col in df.columns:
        gb.configure_column(pin_col, pinned="left", width=180)
    gb.configure_grid_options(
        domLayout="normal",
        animateRows=True,
        rowHeight=36,
        headerHeight=38,
    )
    AgGrid(
        df,
        gridOptions=gb.build(),
        height=height,
        theme="alpine",
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        update_mode=GridUpdateMode.NO_UPDATE,
    )


def page_header(title: str, sub: str = ""):
    st.markdown(f'<div class="page-title">{title}</div>', unsafe_allow_html=True)
    if sub:
        st.markdown(f'<div class="page-sub">{sub}</div>', unsafe_allow_html=True)


def section(text: str):
    st.markdown(f'<div class="section-h">{text}</div>', unsafe_allow_html=True)


# =====================================================================
# СТРАНИЦЫ
# =====================================================================

def render_overview():
    page_header("Обзор",
                "Ключевые цифры компании за выбранный период и что болит прямо сейчас.")

    where = build_where()
    kpi = q(f"""
        SELECT
            SUM(revenue_after_spp) AS revenue,
            SUM(gross_margin_rub)  AS margin,
            SUM(cogs_fifo)         AS cogs,
            SUM(ads_spend)         AS ads,
            SUM(qty_sold)          AS qty_sold
        FROM v_pnl_sku_day {where}
    """).iloc[0]

    rev = kpi["revenue"] or 0
    mgn = kpi["margin"] or 0
    cogs = kpi["cogs"] or 0
    ads = kpi["ads"] or 0
    qty = kpi["qty_sold"] or 0
    margin_pct = (mgn / rev * 100) if rev else 0
    drr = (ads / rev * 100) if rev else 0
    aov = rev / qty if qty else 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Выручка после СПП", fmt_rub(rev, " ₽"))
    c2.metric("Валовая маржа", fmt_rub(mgn, " ₽"), fmt_pct(margin_pct))
    c3.metric("Себестоимость", fmt_rub(cogs, " ₽"))
    c4.metric("Реклама", fmt_rub(ads, " ₽"), f"ДРР {fmt_pct(drr)}")
    c5.metric("Выкуплено, шт", f"{int(qty):,}".replace(",", " "))
    c6.metric("Средний чек", fmt_rub(aov, " ₽"))

    st.markdown("")

    cL, cR = st.columns([3, 2])

    with cL:
        section("Выручка и маржа по месяцам")
        trend = q(f"""
            SELECT strftime(day, '%Y-%m') AS month,
                   SUM(revenue_after_spp)/1e6 AS revenue_mln,
                   SUM(gross_margin_rub)/1e6  AS margin_mln
            FROM v_pnl_sku_day {where}
            GROUP BY 1 ORDER BY 1
        """)
        fig = px.bar(
            trend, x="month", y=["revenue_mln", "margin_mln"],
            barmode="group",
            labels={"value": "млн ₽", "month": "", "variable": ""},
            color_discrete_map={"revenue_mln": PALETTE["primary"],
                                "margin_mln":  PALETTE["success"]},
        )
        fig.for_each_trace(lambda t: t.update(name={
            "revenue_mln": "Выручка",
            "margin_mln": "Маржа",
        }.get(t.name, t.name)))
        style_fig(fig, height=380)
        st.plotly_chart(fig, use_container_width=True)

    with cR:
        section("Что болит прямо сейчас")

        oos = q("""SELECT COUNT(*) AS cnt FROM v_turnover
                   WHERE days_of_stock < 30 AND avg_daily_sales_60d > 0""").iloc[0]["cnt"]
        illiquid = q("""SELECT COUNT(*) AS cnt FROM v_turnover
                        WHERE stock_tier = 'неликвид'""").iloc[0]["cnt"]
        parasites = q("""SELECT COUNT(*) AS cnt, SUM(avg_inventory_rub) AS inv
                         FROM v_gmroi WHERE gmroi_tier = 'паразит'""").iloc[0]
        bad_ads = q("""SELECT COUNT(*) AS cnt, SUM(ads_rub) AS ads
                       FROM v_unit_economics
                       WHERE ads_efficiency_tier IN ('дорогая', 'убыточная')""").iloc[0]

        alert("warn",
              f"<strong>{int(oos)} SKU</strong> уйдут в OOS в ближайшие 30 дней — "
              f"срочно пополнять.")
        alert("danger",
              f"<strong>{int(illiquid)} SKU</strong> в глубоком неликвиде. "
              f"Паразитов: {int(parasites['cnt'])}, заморожено "
              f"{fmt_rub(parasites['inv'] or 0, ' ₽')}.")
        alert("info",
              f"<strong>{int(bad_ads['cnt'])} SKU</strong> с дорогой или убыточной рекламой. "
              f"Бюджет {fmt_rub(bad_ads['ads'] or 0, ' ₽/год')} — кандидаты на отключение.")


def render_pnl():
    page_header("P&L", "Структура доходов и затрат по моделям и SKU.")
    where = build_where()

    section("По моделям")
    by_model = q(f"""
        SELECT model_name AS "Модель",
               SUM(qty_sold) AS "Выкуплено, шт",
               ROUND(SUM(revenue_after_spp)/1e6, 2) AS "Выручка, млн ₽",
               ROUND(SUM(gross_margin_rub)/1e6, 2)  AS "Маржа, млн ₽",
               ROUND(100.0 * SUM(gross_margin_rub) / NULLIF(SUM(revenue_after_spp), 0), 1)
                   AS "Маржа, %"
        FROM v_pnl_sku_day {where}
        GROUP BY model_name
        ORDER BY "Выручка, млн ₽" DESC
    """)
    aggrid_table(by_model, height=460, pin_col="Модель")

    cL, cR = st.columns(2)
    with cL:
        section("Топ-10 убыточных SKU")
        bottom = q(f"""
            SELECT article AS "Артикул", model_name AS "Модель", size AS "Р-р",
                   SUM(qty_sold) AS "Шт",
                   ROUND(SUM(revenue_after_spp)/1e3, 0) AS "Выручка, тыс ₽",
                   ROUND(SUM(gross_margin_rub)/1e3, 0)  AS "Маржа, тыс ₽"
            FROM v_pnl_sku_day {where}
            GROUP BY article, model_name, size
            ORDER BY SUM(gross_margin_rub) ASC
            LIMIT 10
        """)
        aggrid_table(bottom, height=380, pin_col="Артикул")

    with cR:
        section("Топ-10 прибыльных SKU")
        top = q(f"""
            SELECT article AS "Артикул", model_name AS "Модель", size AS "Р-р",
                   SUM(qty_sold) AS "Шт",
                   ROUND(SUM(revenue_after_spp)/1e6, 2) AS "Выручка, млн ₽",
                   ROUND(SUM(gross_margin_rub)/1e6, 2)  AS "Маржа, млн ₽"
            FROM v_pnl_sku_day {where}
            GROUP BY article, model_name, size
            ORDER BY SUM(gross_margin_rub) DESC
            LIMIT 10
        """)
        aggrid_table(top, height=380, pin_col="Артикул")

    section("Структура затрат по компании")
    struct = q(f"""
        SELECT
            SUM(wb_commission)                       AS "Комиссия WB",
            SUM(wb_acquiring)                        AS "Эквайринг",
            SUM(log_forward)                         AS "Логистика до клиента",
            SUM(log_reverse)                         AS "Обратная логистика",
            SUM(storage_alloc + acceptance_alloc)    AS "Хранение и приёмка",
            SUM(fine_alloc)                          AS "Штрафы",
            SUM(ads_spend)                           AS "Реклама",
            SUM(cogs_fifo)                           AS "Себестоимость"
        FROM v_pnl_sku_day {where}
    """).T.reset_index()
    struct.columns = ["Статья", "Сумма"]
    struct["млн ₽"] = (struct["Сумма"] / 1e6).round(2)
    struct = struct.sort_values("Сумма", ascending=False)

    fig = px.bar(struct, x="Статья", y="млн ₽", text="млн ₽",
                 color_discrete_sequence=[PALETTE["primary"]])
    fig.update_traces(textposition="outside", textfont=dict(size=11, color="#64748B"))
    style_fig(fig, height=380)
    st.plotly_chart(fig, use_container_width=True)


def render_unit():
    page_header("Юнит-экономика",
                "Экономика на 1 заказ и 1 выкуп. Подсветка SKU, где реклама съедает маржу.")

    tier = st.radio(
        "Эффективность рекламы",
        options=["все", "здоровая", "дорогая", "убыточная", "без рекламы"],
        horizontal=True,
    )
    where_tier = "" if tier == "все" else f"WHERE ads_efficiency_tier = '{tier}'"

    ue = q(f"""
        SELECT article AS "Артикул", model_name AS "Модель",
               size AS "Р-р", color AS "Цвет",
               qty_ordered AS "Заказов",
               qty_sold AS "Выкуплено",
               buyout_pct AS "Выкуп, %",
               ROUND(revenue_rub/1000, 0)           AS "Выручка, тыс ₽",
               ROUND(cogs_rub/1000, 0)              AS "COGS, тыс ₽",
               ROUND(ads_rub/1000, 0)               AS "Реклама, тыс ₽",
               ROUND(margin_before_ads_rub/1000, 0) AS "Маржа до рекламы",
               ROUND(gross_margin_rub/1000, 0)      AS "Маржа, тыс ₽",
               margin_pct_of_revenue                AS "Маржа, %",
               drr_pct                              AS "ДРР, %",
               ads_to_margin_pct                    AS "Реклама/маржа, %",
               ads_efficiency_tier                  AS "Тир рекламы"
        FROM v_unit_economics {where_tier}
        ORDER BY revenue_rub DESC NULLS LAST
    """)
    aggrid_table(ue, height=500, pin_col="Артикул")

    cL, cR = st.columns(2)
    with cL:
        section("Распределение SKU по эффективности рекламы")
        dist = q("""
            SELECT ads_efficiency_tier AS tier,
                   COUNT(*)             AS sku_count,
                   ROUND(SUM(ads_rub)/1e6, 2) AS ads_mln
            FROM v_unit_economics GROUP BY ads_efficiency_tier
        """)
        fig = px.bar(
            dist, x="tier", y="ads_mln", text="sku_count",
            color="tier",
            color_discrete_map={
                "здоровая":    PALETTE["success"],
                "дорогая":     PALETTE["warn"],
                "убыточная":   PALETTE["danger"],
                "без рекламы": PALETTE["neutral"],
            },
            labels={"ads_mln": "бюджет, млн ₽/год", "tier": ""},
        )
        fig.update_traces(textposition="outside",
                          textfont=dict(size=11, color="#64748B"))
        style_fig(fig, height=360)
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with cR:
        section("Маржа SKU vs ДРР")
        scatter = q("""
            SELECT model_name, size, color,
                   margin_pct_of_revenue, drr_pct, revenue_rub, ads_efficiency_tier
            FROM v_unit_economics WHERE revenue_rub > 0
        """)
        fig = px.scatter(
            scatter, x="drr_pct", y="margin_pct_of_revenue",
            size="revenue_rub", color="ads_efficiency_tier",
            color_discrete_map={
                "здоровая":    PALETTE["success"],
                "дорогая":     PALETTE["warn"],
                "убыточная":   PALETTE["danger"],
                "без рекламы": PALETTE["neutral"],
            },
            hover_data=["model_name", "size", "color"],
            labels={"drr_pct": "ДРР, %", "margin_pct_of_revenue": "Маржа SKU, %",
                    "ads_efficiency_tier": ""},
        )
        style_fig(fig, height=360)
        st.plotly_chart(fig, use_container_width=True)


def render_stock():
    page_header("Запасы и оборачиваемость",
                "Где заморожен капитал и какие SKU уходят в дефицит.")

    cL, cR = st.columns(2)
    with cL:
        section("GMROI по тирам")
        gm = q("""
            SELECT gmroi_tier AS "Тир",
                   COUNT(*)   AS "SKU",
                   ROUND(SUM(avg_inventory_rub)/1e6, 2) AS "Запас, млн ₽",
                   ROUND(SUM(gross_margin_rub)/1e6, 2)  AS "Маржа, млн ₽"
            FROM v_gmroi GROUP BY gmroi_tier
            ORDER BY SUM(avg_inventory_rub) DESC
        """)
        aggrid_table(gm, height=200, pin_col="Тир")

        section("SKU-паразиты и слабые")
        parasites = q("""
            SELECT article AS "Артикул", model_name AS "Модель",
                   size AS "Р-р", color AS "Цвет",
                   avg_stock_units AS "Ср. запас, шт",
                   ROUND(avg_inventory_rub/1000, 0) AS "Запас, тыс ₽",
                   gmroi AS "GMROI"
            FROM v_gmroi
            WHERE gmroi_tier IN ('паразит', 'слабо')
            ORDER BY avg_inventory_rub DESC
            LIMIT 15
        """)
        aggrid_table(parasites, height=420, pin_col="Артикул")

    with cR:
        section("Оборачиваемость по тирам")
        turn = q("""
            SELECT stock_tier AS "Тир",
                   COUNT(*)   AS "SKU",
                   ROUND(AVG(days_of_stock), 0) AS "Ср. дней запаса"
            FROM v_turnover GROUP BY stock_tier
            ORDER BY AVG(days_of_stock) ASC NULLS LAST
        """)
        aggrid_table(turn, height=200, pin_col="Тир")

        section("SKU в риске OOS в ближайший месяц")
        oos = q("""
            SELECT article AS "Артикул", model_name AS "Модель",
                   size AS "Р-р",
                   avg_daily_sales_60d AS "Прод/день",
                   current_stock       AS "Остаток",
                   days_of_stock       AS "Дней запаса",
                   projected_oos_date  AS "Дата OOS"
            FROM v_turnover
            WHERE days_of_stock < 30 AND avg_daily_sales_60d > 0
            ORDER BY days_of_stock ASC
            LIMIT 15
        """)
        aggrid_table(oos, height=420, pin_col="Артикул")


def render_leak():
    page_header("Где течёт маржа",
                "Разложение потерь по причинам и конкретные рычаги оптимизации.")

    section("Структура потерь за год")
    leak = q("""
        SELECT leak_source, amount_rub, pct_of_revenue
        FROM v_margin_leak
        ORDER BY amount_rub DESC
    """)
    leak["млн ₽"] = (leak["amount_rub"] / 1e6).round(2)

    fig = px.bar(
        leak, x="leak_source", y="млн ₽", text="млн ₽",
        color_discrete_sequence=[PALETTE["danger"]],
    )
    fig.update_traces(textposition="outside",
                      textfont=dict(size=11, color="#64748B"),
                      marker=dict(opacity=0.85))
    style_fig(fig, height=400)
    st.plotly_chart(fig, use_container_width=True)

    display_leak = leak[["leak_source", "млн ₽", "pct_of_revenue"]].rename(columns={
        "leak_source": "Статья", "pct_of_revenue": "% от выручки",
    })
    aggrid_table(display_leak, height=320, pin_col="Статья")

    section("Кандидаты на отключение рекламы")
    st.caption("SKU, где реклама съедает более половины маржи до её учёта.")
    bad_ads = q("""
        SELECT article AS "Артикул", model_name AS "Модель",
               size AS "Р-р", color AS "Цвет",
               ROUND(revenue_rub/1000, 0)           AS "Выручка, тыс ₽",
               ROUND(ads_rub/1000, 0)               AS "Реклама, тыс ₽",
               ROUND(margin_before_ads_rub/1000, 0) AS "Маржа до рекламы",
               drr_pct                              AS "ДРР, %",
               ads_to_margin_pct                    AS "Реклама/маржа, %",
               ads_efficiency_tier                  AS "Тир"
        FROM v_unit_economics
        WHERE ads_efficiency_tier IN ('дорогая', 'убыточная')
        ORDER BY ads_rub DESC
    """)
    aggrid_table(bad_ads, height=420, pin_col="Артикул")

    total_save = q("""
        SELECT ROUND(SUM(ads_rub)/1e6, 2) AS save_mln
        FROM v_unit_economics
        WHERE ads_efficiency_tier IN ('дорогая', 'убыточная')
    """).iloc[0]["save_mln"] or 0
    alert("ok",
          f"Отключение рекламы на этих SKU даст экономию до "
          f"<strong>{total_save} млн ₽/год</strong>. Часть заказов будет потеряна, "
          f"но на этих позициях реклама стоит дороже, чем приносит.")


def render_recon():
    page_header("Сверка WB vs банк",
                "Расчётная выплата по финотчёту vs фактически пришедшее на расчётный счёт.")

    summary = q("""
        SELECT
            ROUND(SUM(expected_payment)/1e6, 1)   AS expected_mln,
            ROUND(SUM(actual_payment)/1e6, 1)     AS actual_mln,
            ROUND(SUM(actual_payment) - SUM(expected_payment), 0) AS diff_rub,
            COUNT(*) AS weeks,
            SUM(CASE WHEN status LIKE 'ALERT%' THEN 1 ELSE 0 END) AS alerts
        FROM v_reconciliation
    """).iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Расчётная выплата", f"{summary['expected_mln']} млн ₽")
    c2.metric("Факт на счёте", f"{summary['actual_mln']} млн ₽")
    c3.metric("Расхождение", fmt_rub(summary["diff_rub"] or 0, " ₽"))
    c4.metric("Недель с ALERT",
              f"{int(summary['alerts'])} из {int(summary['weeks'])}")

    st.markdown("")

    section("Понедельная сверка")
    recon = q("""
        SELECT week AS "Неделя",
               ROUND(revenue_sales/1e6, 2)     AS "Выручка, млн ₽",
               ROUND(wb_deductions/1e6, 2)     AS "Удержания WB, млн ₽",
               ROUND(expected_payment/1e6, 2)  AS "Расчёт, млн ₽",
               ROUND(actual_payment/1e6, 2)    AS "Факт, млн ₽",
               ROUND(diff_rub, 0)              AS "Разница, ₽",
               diff_pct                        AS "Разница, %",
               status                          AS "Статус"
        FROM v_reconciliation
        ORDER BY week DESC
    """)
    aggrid_table(recon, height=520, pin_col="Неделя")


# =====================================================================
# САЙДБАР
# =====================================================================

with st.sidebar:
    st.markdown('<div class="enix-brand">ENIX</div>', unsafe_allow_html=True)
    st.markdown('<div class="enix-brand-sub">Коммерческая аналитика</div>',
                unsafe_allow_html=True)

    selected = option_menu(
        menu_title=None,
        options=["Обзор", "P&L", "Юнит-экономика",
                 "Запасы", "Течь маржи", "Сверка WB"],
        icons=["speedometer2", "bar-chart-line", "calculator",
               "box-seam", "droplet-half", "bank"],
        default_index=0,
        styles={
            "container": {
                "padding": "0!important",
                "background-color": "#FFFFFF",
            },
            "icon": {"color": "#94A3B8", "font-size": "15px"},
            "nav-link": {
                "font-family": "'Golos Text', sans-serif",
                "font-size": "14px",
                "font-weight": "500",
                "color": "#475569",
                "background-color": "#FFFFFF",
                "padding": "9px 14px",
                "border-radius": "8px",
                "margin": "2px 0",
                "--hover-color": "#F7F8FA",
                "text-align": "left",
            },
            "nav-link-selected": {
                "background-color": "#EEF2FF",
                "color": "#4338CA",
                "font-weight": "600",
            },
        },
    )

    st.markdown("---")
    st.markdown('<div class="section-h">Фильтры</div>', unsafe_allow_html=True)

    d_min, d_max = period_bounds()
    st.date_input("Период", value=(d_min, d_max),
                  min_value=d_min, max_value=d_max,
                  key="period", format="DD.MM.YYYY")

    dims = dim_values()
    st.multiselect("Категория", sorted(dims["category"].unique()), key="categories")
    st.multiselect("Модель", sorted(dims["model_name"].unique()), key="models")
    st.multiselect("Размер", sorted(dims["size"].unique()), key="sizes")
    st.multiselect("Цвет", sorted(dims["color"].unique()), key="colors")

    st.markdown("---")
    st.caption(
        "Прототип под вакансию коммерческого аналитика ENIX. "
        "Данные синтетические, структура повторяет WB Seller API."
    )


# =====================================================================
# РОУТИНГ
# =====================================================================

routes = {
    "Обзор":            render_overview,
    "P&L":              render_pnl,
    "Юнит-экономика":  render_unit,
    "Запасы":           render_stock,
    "Течь маржи":       render_leak,
    "Сверка WB":        render_recon,
}
routes[selected]()
