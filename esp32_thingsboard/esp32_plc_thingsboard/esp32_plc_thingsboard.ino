/*
 * ============================================================
 *  ESP32: ĐỌC PLC → WEB LOCAL + THINGSBOARD IoT
 *  (Bỏ LCD, thêm MQTT ThingsBoard)
 *
 *  THƯ VIỆN CẦN CÀI (Library Manager):
 *    - PubSubClient  (Nick O'Leary)
 *    - ArduinoJson   (Benoit Blanchon)
 * ============================================================
 */

#include <WiFi.h>
#include <WebServer.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ============================================================
//  ⚙️  CẤU HÌNH - CHỈNH TẠI ĐÂY
// ============================================================
const char* ssid     = "HeThong_PLC";
const char* password = "12345678";

IPAddress plcIP(192, 168, 1, 50);

// ThingsBoard: lấy token tại Devices → esp32_pharma → Credentials
const char* TB_HOST  = "thingsboard.cloud";
const int   TB_PORT  = 1883;
const char* TB_TOKEN = "RbdItkwcixlgcBlXFdFo";   // ← DÁN TOKEN VÀO ĐÂY

// ============================================================
//  BIẾN TOÀN CỤC
// ============================================================
WiFiClient  plcClient;           // Kết nối TCP tới PLC
WiFiClient  mqttWifiClient;      // Kết nối TCP tới ThingsBoard (RIÊNG)
PubSubClient mqttClient(mqttWifiClient);
WebServer   server(80);

// data[0]=Tổng  data[1]=OK  data[2]=NG  data[3]=Hệ thống  data[4]=ProductID  data[5]=CMD
uint16_t data[6] = {0, 0, 0, 0, 1, 0};

unsigned long lastRead    = 0;
unsigned long lastPublish = 0;

// ============================================================
//  GIAO DIỆN WEB LOCAL (Điện thoại xem qua WiFi)
// ============================================================
const char PAGE_MAIN[] PROGMEM = R"=====(
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Smart Pharma Monitor</title>
  <style>
    :root { --bg: #0f172a; --card: #1e293b; --primary: #3b82f6; --success: #22c55e; --danger: #ef4444; }
    body { font-family: 'Segoe UI', sans-serif; background: var(--bg); color: white; text-align: center; padding: 20px; }
    .card { background: var(--card); padding: 15px; border-radius: 12px; margin: 10px; border-bottom: 4px solid var(--primary); }
    .val { font-size: 35px; font-weight: bold; }
    .stt { padding: 10px; border-radius: 8px; font-weight: bold; margin-top: 15px; }
  </style>
</head>
<body>
  <h2 style="color:var(--primary)">PHARMA IOT MONITOR</h2>
  <div class="card"><div>TỔNG SẢN LƯỢNG</div><div class="val" id="t">0</div></div>
  <div class="card" style="border-color:var(--success)"><div>SẢN PHẨM ĐẠT</div><div class="val" id="ok">0</div></div>
  <div class="card" style="border-color:var(--danger)"><div>SẢN PHẨM LỖI</div><div class="val" id="ng">0</div></div>
  <div id="stt" class="stt">ĐANG KẾT NỐI...</div>
  <script>
    setInterval(() => {
      fetch('/api').then(r => r.json()).then(d => {
        document.getElementById('t').innerText  = d[0];
        document.getElementById('ok').innerText = d[1];
        document.getElementById('ng').innerText = d[2];
        let s = document.getElementById('stt');
        if(d[3] == 1) { s.innerText = "HỆ THỐNG: ĐANG CHẠY"; s.style.background = "#22c55e"; }
        else          { s.innerText = "HỆ THỐNG: ĐANG DỪNG"; s.style.background = "#ef4444"; }
      });
    }, 1000);
  </script>
</body>
</html>
)=====";

// ============================================================
//  ĐỌC MODBUS TỪ PLC (Giữ nguyên logic gốc)
// ============================================================
void readModbusRaw() {
  if (!plcClient.connected() && !plcClient.connect(plcIP, 502)) {
    Serial.println(">>> Mất kết nối PLC!");
    return;
  }
  uint8_t req[] = {0, 1, 0, 0, 0, 6, 1, 3, 0, 0, 0, 6};
  plcClient.write(req, 12);
  unsigned long timeout = millis();
  while (plcClient.available() < 21 && millis() - timeout < 500);
  if (plcClient.available() >= 21) {
    uint8_t res[21];
    for (int i = 0; i < 21; i++) res[i] = plcClient.read();
    if (res[7] == 0x03) {
      for (int i = 0; i < 6; i++)
        data[i] = (res[9 + i * 2] << 8) | res[10 + i * 2];
    }
  }
}

// ============================================================
//  GỬI LÊN THINGSBOARD QUA MQTT
// ============================================================
void connectToThingsBoard() {
  if (mqttClient.connected()) return;
  Serial.print(">>> Kết nối ThingsBoard...");
  if (mqttClient.connect("ESP32_Pharma", TB_TOKEN, NULL)) {
    Serial.println(" OK!");
  } else {
    Serial.printf(" Lỗi rc=%d\n", mqttClient.state());
  }
}

void publishToThingsBoard() {
  if (!mqttClient.connected()) {
    connectToThingsBoard();
    if (!mqttClient.connected()) return;
  }

  // Tên sản phẩm từ product_id
  String productName = (data[4] == 1) ? "Vien roi" :
                       (data[4] == 2) ? "Vi thuoc" : "Unknown";

  // Tỷ lệ OK (%)
  int okRate = (data[0] > 0) ? (data[1] * 100 / data[0]) : 0;

  // Tạo JSON
  StaticJsonDocument<256> doc;
  doc["total_all"]    = data[0];   // Tổng sản lượng
  doc["total_ok"]     = data[1];   // Số đạt
  doc["total_ng"]     = data[2];   // Số lỗi
  doc["sys_active"]   = data[3];   // 1=Chạy, 0=Dừng
  doc["product_id"]   = data[4];   // 1=Viên, 2=Vỉ
  doc["product_name"] = productName;
  doc["ok_rate"]      = okRate;    // % đạt
  doc["last_result"]  = (data[2] > 0) ? "NG" : "OK";  // Trạng thái gần nhất

  char payload[256];
  serializeJson(doc, payload);

  if (mqttClient.publish("v1/devices/me/telemetry", payload)) {
    Serial.println(">>> ThingsBoard OK: " + String(payload));
  } else {
    Serial.println(">>> ThingsBoard THẤT BẠI!");
  }
}

// ============================================================
//  SETUP
// ============================================================
void setup() {
  Serial.begin(115200);
  Serial.println("\n=== ESP32 PHARMA IoT ===");

  // Kết nối WiFi
  WiFi.begin(ssid, password);
  Serial.print(">>> Kết nối WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\n>>> WiFi OK! IP: " + WiFi.localIP().toString());
  Serial.println(">>> Web local: http://" + WiFi.localIP().toString());

  // Cấu hình ThingsBoard MQTT
  mqttClient.setServer(TB_HOST, TB_PORT);
  mqttClient.setBufferSize(512);
  connectToThingsBoard();

  // Web server
  server.on("/", []() {
    server.send_P(200, "text/html", PAGE_MAIN);
  });
  server.on("/api", []() {
    String j = "[" + String(data[0]) + "," + String(data[1]) + ","
             + String(data[2]) + "," + String(data[3]) + ","
             + String(data[4]) + "]";
    server.send(200, "application/json", j);
  });
  server.begin();
}

// ============================================================
//  LOOP
// ============================================================
void loop() {
  server.handleClient();
  mqttClient.loop();  // Giữ kết nối MQTT

  // Đọc PLC mỗi 1 giây
  if (millis() - lastRead > 1000) {
    lastRead = millis();
    readModbusRaw();
    Serial.printf("[PLC] T:%d OK:%d NG:%d Sys:%d Prod:%d\n",
      data[0], data[1], data[2], data[3], data[4]);
  }

  // Gửi ThingsBoard mỗi 3 giây
  if (millis() - lastPublish > 3000) {
    lastPublish = millis();
    publishToThingsBoard();
  }
}
