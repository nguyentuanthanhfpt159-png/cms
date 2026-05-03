import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("SUPABASE_URL")

try:
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    print("Checking 'inspections' table...")
    cur.execute("SELECT product_name, result, is_ng FROM inspections WHERE is_ng = true LIMIT 20")
    rows = cur.fetchall()
    for row in rows:
        print(f"Product: {row[0]}, Result: {row[1]}, IsNG: {row[2]}")
    
    cur.execute("SELECT COUNT(*) FROM inspections WHERE is_ng = true")
    count_ng = cur.fetchone()[0]
    print(f"\nTotal NG records: {count_ng}")
    
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
