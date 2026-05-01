import os
import psycopg2
from dotenv import load_dotenv

def test_connection():
    load_dotenv()
    db_url = os.getenv("SUPABASE_URL")
    
    # Hide password in logs
    safe_url = db_url.split('@')[-1] if db_url else "None"
    print(f"--- Testing connection to: {safe_url} ---")
    
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("SELECT version();")
        record = cur.fetchone()
        print(f"--- CONNECTION SUCCESS! ---")
        print(f"PostgreSQL version: {record}")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"--- CONNECTION FAILED! ---")
        print(f"Error: {e}")

if __name__ == "__main__":
    test_connection()
