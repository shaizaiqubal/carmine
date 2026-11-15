import os
import uuid
import libsql

conn = libsql.connect(database=os.environ["TURSO_DATABASE_URL"], auth_token=os.environ["TURSO_AUTH_TOKEN"])
conn.execute("CREATE TABLE IF NOT EXISTS workflow_checks (id TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
check_id = str(uuid.uuid4())
conn.execute("INSERT INTO workflow_checks (id) VALUES (?)", (check_id,))
conn.commit()
print(f"wrote workflow_checks row {check_id}")
