import sqlite3

conn = sqlite3.connect("database.db")
cur = conn.cursor()

# Safe add columns
def add_column(column_sql):
    try:
        cur.execute(column_sql)
        print("Added:", column_sql)
    except:
        print("Already exists:", column_sql)

add_column("ALTER TABLE players ADD COLUMN current_bid INTEGER DEFAULT 0")
add_column("ALTER TABLE players ADD COLUMN highest_bidder_id INTEGER")
add_column("ALTER TABLE players ADD COLUMN is_sold INTEGER DEFAULT 0")
add_column("ALTER TABLE players ADD COLUMN is_unsold INTEGER DEFAULT 0")

add_column("ALTER TABLE users ADD COLUMN budget INTEGER DEFAULT 500")

cur.execute("""
CREATE TABLE IF NOT EXISTS auction_state (
    id INTEGER PRIMARY KEY,
    current_player_id INTEGER,
    auction_end_time INTEGER,
    phase INTEGER DEFAULT 1
)
""")

conn.commit()
conn.close()

print("Database upgraded successfully.")