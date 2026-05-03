import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("SUPABASE_URL")

def check():
    if not DB_URL:
        print("Error: No SUPABASE_URL")
        return

    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT id, product_name, result, image_url FROM inspections ORDER BY created_at DESC LIMIT 5")
        rows = cur.fetchall()
        
        print(f"{'ID':<5} | {'Product':<15} | {'Result':<15} | {'Image URL'}")
        print("-" * 100)
        for r in rows:
            print(f"{r[0]:<5} | {r[1]:<15} | {r[2]:<15} | {r[3]}")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check()
