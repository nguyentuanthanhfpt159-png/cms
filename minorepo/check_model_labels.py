from ultralytics import YOLO

MODEL_PATH = r"C:\Users\admin\Downloads\thuoc_yolov8s_best.pt"
model = YOLO(MODEL_PATH)
print("\n" + "="*50)
print("DANH SÁCH NHÃN TRONG MODEL VỈ THUỐC:")
print("="*50)
for id, name in model.names.items():
    print(f"ID {id}: {name}")
print("="*50)
print("\nNếu model chỉ có 1 nhãn 'vi_thuoc' và khi chụp nó bao quanh cả cái vỉ,")
print("thì chúng ta cần sửa lại logic đếm (không so sánh với số 10 nữa).")
