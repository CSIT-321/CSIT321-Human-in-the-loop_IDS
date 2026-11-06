import sqlite3
import tempfile
from pathlib import Path

from packages.contracts import db

p = Path(tempfile.mkdtemp()) / "t.db"
c = sqlite3.connect(p)
c.executescript(Path("packages/contracts/schema.sql").read_text(encoding="utf-8"))
db.migrate(c)
print("user_version:", c.execute("PRAGMA user_version").fetchone()[0])
c.execute("INSERT INTO alert_groups (group_ref, grouping_key, first_seen_at, last_seen_at, member_count, "
          "representative_operational_alert_id, qualifying_member_alert_id, case_ref, created_at) "
          "VALUES ('g1','1.1.1.1','t','t',1,NULL,NULL,NULL,'t')")
for name, sql in [("rep", "UPDATE alert_groups SET representative_operational_alert_id=7 WHERE group_ref='g1'"),
                  ("last_seen", "UPDATE alert_groups SET last_seen_at='t2', member_count=2 WHERE group_ref='g1'"),
                  ("grouping_key", "UPDATE alert_groups SET grouping_key='x' WHERE group_ref='g1'")]:
    try:
        c.execute(sql)
        print(name, "OK")
    except Exception as e:
        print(name, "FAILED:", e)
c.rollback()
