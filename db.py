import sqlite3

conn = sqlite3.connect("database.db")
cur = conn.cursor()

# USERS TABLE
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    budget INTEGER DEFAULT 1000,
    role TEXT DEFAULT 'user'
)
""")

# PLAYERS TABLE
cur.execute("""
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    position TEXT,
    rating INTEGER,
    pac INTEGER DEFAULT 80,
    sho INTEGER DEFAULT 80,
    pas INTEGER DEFAULT 80,
    dri INTEGER DEFAULT 80,
    def INTEGER DEFAULT 80,
    phy INTEGER DEFAULT 80,
    current_bid INTEGER DEFAULT 0,
    highest_bidder TEXT,
    is_sold INTEGER DEFAULT 0,
    auction_status TEXT DEFAULT 'waiting',
    auction_end_time INTEGER
)
""")

# FOLDS TABLE
cur.execute("""
CREATE TABLE IF NOT EXISTS auction_folds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER,
    username TEXT
)
""")

conn.commit()
conn.close()

print("Database Ready.")