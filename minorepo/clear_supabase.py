import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("SUPABASE_URL")

def clear_data():
    if not DB_URL or "MAT_KHAU" in DB_URL:
        print("Error: SUPABASE_URL not configured correctly in .env")
        return

    try:
        print("Connecting to Supabase...")
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        
        # 1. Clear all inspection history
        print("Clearing 'inspections' table...")
        cur.execute("TRUNCATE TABLE inspections RESTART IDENTITY;")
        
        # 2. Reset system status (only existing columns)
        print("Resetting 'system_status' table...")
        try:
            # Try with all columns first
            cur.execute("""
                UPDATE system_status 
                SET vien_ok = 0, vien_ng = 0, vi_ok = 0, vi_ng = 0, 
                    machine_running = false, last_update = NOW()
                WHERE id = 1;
            """)
        except:
            conn.rollback()
            print("Note: Extra columns not found, using basic reset.")
            cur.execute("""
                UPDATE system_status 
                SET machine_running = false, last_update = NOW()
                WHERE id = 1;
            """)
        
        conn.commit()
        print("=== SUCCESS: ALL DATA CLEARED ON SUPABASE ===")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    clear_data()
