import cv2
import time
import os
import snap7
import kiem_tra_thuoc_logic as logic
from dotenv import load_dotenv

load_dotenv()

# Cấu hình
CAM_SOURCE = "http://192.168.1.110:4747/video"
OUTPUT_DIR = "calibration_results"
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

def main():
    print("=== CHƯƠNG TRÌNH HIỆU CHUẨN DELAY CHỤP ẢNH ===")
    print(f">>> Kết nối Camera: {CAM_SOURCE}")
    vs = cv2.VideoCapture(CAM_SOURCE)
    
    if not vs.isOpened():
        print("Lỗi: Không thể mở Camera!")
        return

    print(">>> Kết nối PLC...")
    if not logic.connect_to_plc():
        print("Lỗi: Không thể kết nối PLC!")
        return

    print("\n[HƯỚNG DẪN]")
    print("1. Cho băng tải chạy.")
    print("2. Đưa vỉ thuốc đi qua cảm biến.")
    print("3. Máy sẽ chụp chuỗi ảnh từ 0.5s đến 2.0s.")
    print("4. Kiểm tra thư mục 'calibration_results' để chọn ảnh đẹp nhất.\n")

    last_sensor_state = False
    
    try:
        while True:
            current_sensor = logic.read_sensor_trigger()
            
            # Phát hiện cạnh lên của cảm biến
            if current_sensor and not last_sensor_state:
                print(">>> CẢM BIẾN KÍCH HOẠT! Bắt đầu chụp chuỗi ảnh hiệu chuẩn...")
                
                # Chụp chuỗi ảnh với delay tăng dần
                for d in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 2.0]:
                    time.sleep(0.1) # Khoảng nghỉ nhỏ giữa các lần kiểm tra delay
                    
                    # Đọc khung hình mới nhất (Xả buffer liên tục)
                    for _ in range(5): vs.read()
                    ret, frame = vs.read()
                    
                    if ret:
                        filename = f"{OUTPUT_DIR}/delay_{d}s.jpg"
                        cv2.imwrite(filename, frame)
                        print(f"  - Đã lưu ảnh với delay {d}s")
                
                print(">>> HOÀN THÀNH! Hãy kiểm tra thư mục 'calibration_results'.")
                print("Nhấn Ctrl+C để thoát hoặc tiếp tục thử vỉ tiếp theo.")
            
            last_sensor_state = current_sensor
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        print("\nĐã dừng chương trình hiệu chuẩn.")
    finally:
        vs.release()
        logic.disconnect_plc()

if __name__ == "__main__":
    main()
