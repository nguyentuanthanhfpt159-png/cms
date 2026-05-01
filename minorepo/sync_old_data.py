import os
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from datetime import datetime

def sync_data():
    load_dotenv()
    db_url = os.getenv("SUPABASE_URL")
    csv_path = r"D:\Code\captured_medicine\Lich_su_phan_loai.csv"

    if not os.path.exists(csv_path):
        print(f"ERROR: CSV file not found at: {csv_path}")
        return

    print(f"--- Reading data from: {csv_path} ---")
    try:
        df = pd.read_csv(csv_path, encoding='utf-8')
        df.columns = df.columns.str.strip()
        
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        count = 0
        for _, row in df.iterrows():
            product_name = str(row['Sản phẩm'])
            result_full = str(row['Kết quả'])
            time_str = str(row['Thời gian'])
            
            is_ng = "[NG]" in result_full
            
            dt = None
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y%m%d_%H%M%S"]:
                try:
                    dt = datetime.strptime(time_str, fmt)
                    break
                except:
                    continue
            
            if not dt:
                dt = datetime.now()

            cur.execute("""
                INSERT INTO inspections (product_name, result, is_ng, details, created_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (product_name, result_full, is_ng, "", dt))
            count += 1

        conn.commit()
        print(f"--- SYNC SUCCESS: {count} records pushed to Supabase ---")
        cur.close()
        conn.close()

    except Exception as e:
        print(f"ERROR DURING SYNC: {e}")

if __name__ == "__main__":
    sync_data()
