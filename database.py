import sqlite3
from datetime import datetime

DB_NAME = "ecotrack.db"

def init_db():
    """Creates the necessary tables if they don't exist."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Create a table for waste reports
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS waste_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            item_type TEXT,
            estimated_value REAL,
            latitude REAL,
            longitude REAL,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("Database initialized.")

def log_scan(user_id, item_type, estimated_value, lat, lon):
    """Inserts a successful AI detection into the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        INSERT INTO waste_reports (user_id, item_type, estimated_value, latitude, longitude, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, item_type, estimated_value, lat, lon))
    
    conn.commit()
    conn.close()