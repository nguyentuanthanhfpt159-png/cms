import os
import psycopg2
from dotenv import load_dotenv

def check_counts():
    load_dotenv()
    db_url = os.getenv("SUPABASE_URL")
    
    if not db_url:
        print("Error: SUPABASE_URL not found in .env")
        return

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM inspections;")
        inspections_count = cur.fetchone()[0]
        print(f"Total rows in 'inspections': {inspections_count}")

        print("\n--- Columns in 'inspections' ---")
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'inspections';")
        cols_insp = cur.fetchall()
        for col in cols_insp:
            print(f"  - {col[0]}")

        print("\n--- Columns in 'system_status' ---")
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'system_status';")
        columns = cur.fetchall()
        for col in columns:
            print(f"  - {col[0]}")

        print("\n--- System Status (ID 1) ---")
        cur.execute("SELECT * FROM system_status WHERE id = 1;")
        status = cur.fetchone()
        if status:
            print(f"Data: {status}")
        else:
            print("Row ID 1 not found.")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_counts()
