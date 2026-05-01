import cv2
import os
import time
from datetime import datetime

# Import file logic của bạn để dùng chung kết nối PLC và hàm Crop
import kiem_tra_thuoc_logic as logic

# ==============================
# CẤU HÌNH THU THẬP DATA
# ==============================
CAM_SOURCE = 0
# Thời gian chờ (giây) từ lúc cảm biến sáng tới lúc thuốc vào giữa camera
DELAY_SAU_CAM_BIEN = 0.6
# Thư mục lưu ảnh đã Cắt sẵn
THU_MUC_LUU = r"D:\NCKH(2026)\modelok\vithuocok"
os.makedirs(THU_MUC_LUU, exist_ok=True)

# 1. Kết nối Camera
print("Đang kết nối Camera...")
cap = cv2.VideoCapture(CAM_SOURCE)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

if not cap.isOpened():
    print("LỖI: Không thể mở Camera! Vui lòng kiểm tra lại cổng USB hoặc DroidCam.")
    exit()

# 2. Kết nối PLC
print("Đang kết nối PLC để đọc cảm biến...")
logic.connect_to_plc()

print("\n==================================================")
print(" 🚀 PHẦN MỀM THU THẬP DATA TỰ ĐỘNG CHUẨN ")
print(f" 📂 Ảnh Crop sẽ được lưu tại: {THU_MUC_LUU}")
print(" 🔴 Bấm phím 'q' trên cửa sổ Camera để thoát.")
print("==================================================\n")

last_sensor = False

while True:
    # Đọc liên tục để xả buffer, giữ cho hình ảnh mượt mà
    ret, frame = cap.read()
    if not ret: continue

    # ----- VẼ KHUNG PREVIEW (HỖ TRỢ CĂN CHỈNH) -----
    display_frame = frame.copy()
    h, w = display_frame.shape[:2]
    # Lấy đúng tọa độ Crop mà bạn đang xài trong logic
    x1, x2 = int(w * 0.25), int(w * 0.75)
    y1, y2 = int(h * 0.05), int(h * 0.95)
    
    cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(display_frame, "Vung AI Phan Tich (Crop)", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    
    # Thu nhỏ lại 1 nửa để hiển thị cho đỡ chật màn hình
    preview = cv2.resize(display_frame, (960, 540))
    cv2.imshow("Thu Thap Data - Nhan 'q' de thoat", preview)

    # ----- ĐỌC CẢM BIẾN TỪ PLC -----
    current_sensor = logic.read_sensor_trigger()
    
    # Bắt sự kiện viên thuốc vừa đi qua làm chớp cảm biến (Sườn lên)
    if current_sensor == True and last_sensor == False:
        print("-> Phát hiện thuốc! Chờ vào giữa tâm...")
        
        # Đợi 1 chút cho thuốc trôi đúng vào ô màu xanh lá
        time.sleep(DELAY_SAU_CAM_BIEN)
        
        # Chụp 1 tấm ảnh NGAY TỨC THÌ
        ret, snap_frame = cap.read()
        if ret:
            # Tự động Cắt viền bỏ máy móc rườm rà
            cropped = logic.apply_static_crop(snap_frame)
            
            # Tạo tên file theo giờ phút giây để không bị trùng
            ten_file = f"thuoc_{datetime.now().strftime('%H%M%S_%f')[:8]}.jpg"
            duong_dan = os.path.join(THU_MUC_LUU, ten_file)
            
            # Lưu xuống ổ cứng
            cv2.imwrite(duong_dan, cropped)
            print(f"   [OK] Đã CẮT và LƯU: {ten_file}")
            
    last_sensor = current_sensor

    # Thoát chương trình
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Dọn dẹp
cap.release()
cv2.destroyAllWindows()
