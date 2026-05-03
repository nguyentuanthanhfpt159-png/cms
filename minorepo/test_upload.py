import os
import requests
from dotenv import load_dotenv

load_dotenv()
SUPABASE_API_URL = os.getenv("SUPABASE_API_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def test():
    if not SUPABASE_API_URL or not SUPABASE_KEY:
        print("Error: Missing credentials in .env")
        return

    # Thử upload một file test (nếu có) hoặc tạo file giả
    test_file = "test_upload_image.jpg"
    with open(test_file, "wb") as f:
        f.write(b"fake image data")

    url = f"{SUPABASE_API_URL}/storage/v1/object/inspection-images/{test_file}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "image/jpeg"
    }
    
    print(f"Testing upload to: {url}")
    try:
        with open(test_file, "rb") as f:
            res = requests.post(url, headers=headers, data=f)
            print(f"Status Code: {res.status_code}")
            print(f"Response: {res.text}")
            
            if res.status_code == 200:
                public_url = f"{SUPABASE_API_URL}/storage/v1/object/public/inspection-images/{test_file}"
                print(f"Success! Public URL: {public_url}")
            else:
                print("Failed to upload.")
    except Exception as e:
        print(f"Exception: {e}")
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)

if __name__ == "__main__":
    test()
