import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("SUPABASE_URL")

try:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT * FROM inspections ORDER BY created_at DESC LIMIT 1")
    row = cur.fetchone()
    colnames = [desc[0] for desc in cur.description]
    for col, val in zip(colnames, row):
        v_str = str(val)
        if "base64" in v_str.lower() or "data:image" in v_str.lower():
            print(f"{col}: Found potential Base64 image")
        elif "http" in v_str.lower():
            print(f"{col}: Found potential URL")
        else:
            print(f"{col}: No image pattern found")
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
