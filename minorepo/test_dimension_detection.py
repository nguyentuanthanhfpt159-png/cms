import cv2
import torch
from ultralytics import YOLO
import time
import os
from dotenv import load_dotenv

# Cấu hình đường dẫn
MODEL_PATH = r"C:\Users\admin\Downloads\thuoc_yolov8s_best.pt"
CAM_SOURCE = "http://192.168.1.110:4747/video"

def main():
    print("=== TEST NHẬN DIỆN KÍCH THƯỚC VỈ THUỐC ===")
    
    # 1. Load Model
    print(f">>> Đang nạp model: {MODEL_PATH}")
    try:
        model = YOLO(MODEL_PATH)
        print(">>> Nạp model thành công.")
    except Exception as e:
        print(f"Lỗi nạp model: {e}")
        return

    # 2. Kết nối Camera
    cap = cv2.VideoCapture(CAM_SOURCE)
    if not cap.isOpened():
        print("Lỗi: Không thể mở Camera!")
        return

    print("\n[HƯỚNG DẪN]")
    print("- Đưa vỉ thuốc vào khung hình.")
    print("- Chương trình sẽ hiển thị Box và kích thước (Pixel).")
    print("- Nhấn 'q' để thoát.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Dự đoán bằng YOLO
        results = model.predict(frame, conf=0.5, verbose=False)
        
        annotated_frame = frame.copy()
        
        for r in results:
            boxes = r.boxes
            for box in boxes:
                # Lấy tọa độ (x1, y1, x2, y2)
                b = box.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = map(int, b)
                
                # Tính chiều dài và chiều rộng (Pixel)
                width = x2 - x1
                height = y2 - y1
                
                # Xác định loại vật thể (Class name)
                cls = int(box.cls[0])
                label = model.names[cls]
                
                # Chỉ xử lý nếu là "Vỉ thuốc" (hoặc class tương ứng của vỉ)
                # Nếu model của bạn chỉ có 1 class là vỉ thì không cần check label
                
                # Vẽ Box
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                
                # Hiển thị thông số
                info_text = f"{label} | W:{width}px, H:{height}px"
                cv2.putText(annotated_frame, info_text, (x1, y1 - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                
                print(f"\rDetected: {label} -> Chiều dài: {width}px | Chiều rộng: {height}px", end="")

        # Hiển thị kết quả
        cv2.imshow("Test Kich Thuoc Vi Thuoc", cv2.resize(annotated_frame, (800, 600)))
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
