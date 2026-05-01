import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("SUPABASE_URL")

try:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT details FROM inspections WHERE details IS NOT NULL LIMIT 1")
    row = cur.fetchone()
    if row:
        print(f"Details length: {len(row[0])}")
        print(f"Details start: {row[0][:100]}")
    else:
        print("No details found")
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
