import sqlite3
import os

db = os.path.join("data", "ibkr_system.db")
print("DB PATH:", db)

con = sqlite3.connect(db)
cur = con.cursor()

print("\nTABLES:")
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
for row in cur.fetchall():
    print(row)

print("\nRECENT SCANNER STATE:")
cur.execute("""
    SELECT symbol, session, pct_change, avg_volume_20d, float_shares
    FROM scanner_symbol_state
    ORDER BY last_seen_utc DESC
    LIMIT 5
""")
for row in cur.fetchall():
    print(row)

con.close()
