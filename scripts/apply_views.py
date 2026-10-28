"""
Применяет все SQL-файлы из sql/ к базе enix_prototype.duckdb в алфавитном порядке.
Файлы с префиксом цифры (01_, 02_, ...) обеспечивают нужный порядок зависимостей.
"""

import sys
from pathlib import Path

import duckdb

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
SQL_DIR = BASE_DIR / "sql"
DB_PATH = BASE_DIR / "enix_prototype.duckdb"

if not DB_PATH.exists():
    print(f"База не найдена: {DB_PATH}")
    print("Сначала запустите scripts/generate_data.py")
    sys.exit(1)

sql_files = sorted(SQL_DIR.glob("*.sql"))
if not sql_files:
    print(f"В {SQL_DIR} нет .sql файлов")
    sys.exit(1)

con = duckdb.connect(str(DB_PATH))

for sql_file in sql_files:
    print(f"→ {sql_file.name}")
    sql = sql_file.read_text(encoding="utf-8")
    try:
        con.execute(sql)
    except Exception as e:
        print(f"  ОШИБКА: {e}")
        con.close()
        sys.exit(1)

views = con.execute(
    "SELECT view_name FROM duckdb_views() WHERE schema_name = 'main' ORDER BY view_name"
).fetchall()
print(f"\nСоздано представлений: {len(views)}")
for (v,) in views:
    print(f"  • {v}")

con.close()