import cv2
import kiem_tra_thuoc_logic as logic
from ultralytics import YOLO
import os

# Tự động lấy ảnh NG mới nhất trong thư mục captured_history/NG
NG_DIR = r"d:\cms\minorepo\captured_history\NG"
MODEL_PATH = r"C:\Users\admin\Downloads\thuoc_yolov8s_best.pt"

def get_latest_ng_image():
    files = [os.path.join(NG_DIR, f) for f in os.listdir(NG_DIR) if f.endswith(".jpg")]
    if not files: return None
    return max(files, key=os.path.getctime)

def debug_image(img_path):
    print(f"\n" + "="*50)
    print(f"PHÂN TÍCH ẢNH: {os.path.basename(img_path)}")
    print("="*50)
    
    model = YOLO(MODEL_PATH)
    class_names = model.names
    
    frame = cv2.imread(img_path)
    if frame is None:
        print("Lỗi: Không đọc được ảnh!")
        return

    # 1. Chạy phát hiện trực tiếp để xem AI thấy những gì (để conf thấp 0.2 để soi lỗi)
    results = model(frame, conf=0.2, verbose=False)
    result = results[0]
    
    print("\n[1. CÁC VẬT THỂ AI NHÌN THẤY TRỰC TIẾP]")
    print(f"{'Nhãn':<15} | {'Độ tự tin (Conf)':<20}")
    print("-" * 40)
    
    boxes_count = 0
    if result.boxes:
        for box in result.boxes:
            cls = int(box.cls[0])
            label = class_names[cls]
            conf = float(box.conf[0])
            # Lấy tọa độ
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            w_obj, h_obj = x2 - x1, y2 - y1
            print(f"{label:<15} | {conf:<8.4f} | Kích thước: {int(w_obj)}x{int(h_obj)} px")
            boxes_count += 1
    
    print(f"\n=> Tổng số vật thể AI phát hiện: {boxes_count}")

    # 2. Chạy qua logic xử lý chính của hệ thống để xem phán quyết cuối cùng
    # Lưu ý: logic.process_frame có thực hiện crop ảnh bên trong
    annotated, status, code, err, detail, n_ok, n_ng = logic.process_frame(frame, model, class_names)
    
    print("\n[2. KẾT QUẢ TỪ LOGIC KIỂM TRA (Hệ thống đang chạy)]")
    print(f"Trạng thái hiển thị: {status}")
    print(f"Mã kết quả (PLC): {code}")
    print(f"Phán định Lỗi: {err}")
    print(f"Chi tiết lỗi ghi nhận:")
    for d in detail:
        print(f"  • {d}")

    # Lưu ảnh kết quả debug để bạn xem tận mắt AI khoanh vùng gì
    debug_output = "debug_result.jpg"
    cv2.imwrite(debug_output, annotated)
    print(f"\n=> Đã lưu ảnh kết quả soi lỗi tại: {os.path.abspath(debug_output)}")
    print("Hãy mở ảnh này lên để xem AI khoanh vùng nhầm ở đâu.")

if __name__ == "__main__":
    latest_img = get_latest_ng_image()
    if latest_img:
        debug_image(latest_img)
    else:
        print("Không tìm thấy ảnh NG nào trong thư mục captured_history/NG")
