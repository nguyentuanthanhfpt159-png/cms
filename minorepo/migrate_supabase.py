import os
import psycopg2
from dotenv import load_dotenv

def migrate():
    load_dotenv()
    db_url = os.getenv("SUPABASE_URL")
    
    if not db_url:
        print("Error: SUPABASE_URL not found in .env")
        return

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        print("Adding missing columns to 'system_status'...")
        cur.execute("""
            ALTER TABLE system_status 
            ADD COLUMN IF NOT EXISTS vien_ok INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS vien_ng INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS vi_ok INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS vi_ng INTEGER DEFAULT 0;
        """)
        
        conn.commit()
        print("Migration successful!")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    migrate()
