import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("SUPABASE_URL")

try:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT * FROM inspections LIMIT 1")
    colnames = [desc[0] for desc in cur.description]
    print(colnames)
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
