import cv2
import os
import time
from datetime import datetime

# Import file logic của bạn để dùng hàm Crop (Không cần kết nối PLC)
import kiem_tra_thuoc_logic as logic

# ==============================
# CẤU HÌNH THU THẬP NỀN BĂNG TẢI
# ==============================
CAM_SOURCE = 0
# Thư mục lưu ảnh Nền
THU_MUC_LUU = r"D:\NCKH(2026)\modelok\nen_bang_tai"
os.makedirs(THU_MUC_LUU, exist_ok=True)

# THỜI GIAN GIỮA 2 LẦN CHỤP TỰ ĐỘNG (GIÂY)
# 1.0 nghĩa là cứ 1 giây máy sẽ tự chụp 1 tấm nền
THOI_GIAN_CHUP = 1.0 

# 1. Kết nối Camera
print("Đang kết nối Camera...")
cap = cv2.VideoCapture(CAM_SOURCE)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

if not cap.isOpened():
    print("LỖI: Không thể mở Camera!")
    exit()

print("\n==================================================")
print(" 🚀 ĐANG AUTO-CHỤP NỀN BĂNG TẢI TRỐNG ")
print(f" ⏳ Cứ mỗi {THOI_GIAN_CHUP} giây máy sẽ tự động chớp 1 tấm.")
print(f" 📂 Ảnh nền lưu tại: {THU_MUC_LUU}")
print(" 🔴 Bấm phím 'q' trên cửa sổ Camera để thoát.")
print("==================================================\n")

last_capture_time = time.time()
count = 0

while True:
    ret, frame = cap.read()
    if not ret: continue

    # ----- VẼ KHUNG PREVIEW -----
    display_frame = frame.copy()
    h, w = display_frame.shape[:2]
    # Tọa độ Crop dọc y hệt lúc nãy
    x1, x2 = int(w * 0.25), int(w * 0.75)
    y1, y2 = int(h * 0.05), int(h * 0.95)
    
    cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(display_frame, "Dang tu dong chup NEN TAI...", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    
    preview = cv2.resize(display_frame, (960, 540))
    cv2.imshow("Thu Thap Nen Bang Tai - Nhan 'q' de thoat", preview)

    # ----- CHỤP TỰ ĐỘNG LIÊN TỤC (BỎ QUA CẢM BIẾN) -----
    current_time = time.time()
    if current_time - last_capture_time >= THOI_GIAN_CHUP:
        # Cắt lấy đúng ô chữ nhật nền
        cropped = logic.apply_static_crop(frame)
        
        # Lưu file
        ten_file = f"nen_{datetime.now().strftime('%H%M%S')}.jpg"
        duong_dan = os.path.join(THU_MUC_LUU, ten_file)
        cv2.imwrite(duong_dan, cropped)
        
        count += 1
        print(f"   [OK] Đã chụp Nền thứ {count}: {ten_file}")
        
        last_capture_time = current_time

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
