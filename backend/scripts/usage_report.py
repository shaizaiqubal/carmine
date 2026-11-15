import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.config import Settings
from app.db import Database, apply_migrations


parser = argparse.ArgumentParser()
parser.add_argument("--date", help="UTC date in YYYY-MM-DD format; defaults to today")
args = parser.parse_args()
db = Database(Settings())
apply_migrations(db, Path(__file__).parents[1] / "app" / "migrations")
date = args.date or "now"
expression = "date(created_at) = date('now')" if date == "now" else "date(created_at) = ?"
params = () if date == "now" else (date,)
rows = db.execute(
    f"SELECT provider, COUNT(*), COALESCE(SUM(COALESCE(tokens_in, 0)), 0), COALESCE(SUM(COALESCE(tokens_out, 0)), 0) FROM llm_calls WHERE {expression} GROUP BY provider ORDER BY provider",
    params,
).fetchall()
print("provider,requests,tokens_in,tokens_out")
for row in rows:
    print(f"{row[0]},{row[1]},{row[2]},{row[3]}")
db.close()
