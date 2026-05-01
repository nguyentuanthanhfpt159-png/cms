/*
 * ============================================================
 *  ESP32: HỆ THỐNG IoT GIÁM SÁT & ĐIỀU KHIỂN PLC (BẢN CHUẨN)
 *  - Giám sát: OK, NG, Tổng, Trạng thái Power/Camera/PLC
 *  - Điều khiển: Nút Switch (Khóa/Mở) & Nút Tròn (Bật máy từ xa)
 * ============================================================
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ============================================================
//  ⚙️  CẤU HÌNH (Đã kiểm tra kỹ theo thông tin của bạn)
// ============================================================
const char* ssid     = "Bon Chi Em 2.4GHZ";
const char* password = "01989897";
IPAddress plcIP(192, 168, 1, 50);

const char* TB_HOST  = "thingsboard.cloud";
const char* TB_TOKEN = "RbdItkwcixlgcBlXFdFo"; 

WiFiClient plcClient; WiFiClient mqttWifiClient;
PubSubClient mqttClient(mqttWifiClient);

uint16_t data[9] = {0, 0, 0, 0, 0, 0, 0, 0, 0}; // Mảng lưu 9 thanh ghi PLC
unsigned long lastRead = 0, lastPublish = 0, lastRetry = 0;

// ============================================================
//  HÀM GHI MODBUS (Register 9 tương ứng DB1.DBW18)
// ============================================================
void writeModbusRegister(uint16_t regAddr, uint16_t value) {
  if (!plcClient.connected() && !plcClient.connect(plcIP, 502)) return;
  
  // Gửi lệnh ghi
  uint8_t req[] = {0, 3, 0, 0, 0, 6, 255, 6, (uint8_t)(regAddr >> 8), (uint8_t)(regAddr & 0xFF), (uint8_t)(value >> 8), (uint8_t)(value & 0xFF)};
  plcClient.write(req, 12);
  
  // DỌN RÁC BỘ ĐỆM: Đợi gói phản hồi từ PLC và đọc vứt đi
  unsigned long timeout = millis();
  while (plcClient.available() < 12 && millis() - timeout < 500);
  while (plcClient.available()) {
    plcClient.read(); // Đọc và xóa khỏi buffer
  }
  
  Serial.printf(">>> Modbus Write: Reg %d = %d\n", regAddr, value);
}

// ============================================================
//  HÀM XỬ LÝ LỆNH TỪ WEB (RPC)
// ============================================================
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String responseTopic = String(topic); responseTopic.replace("request", "response");
  StaticJsonDocument<200> doc; deserializeJson(doc, payload, length);
  String method = doc["method"];
  
  // 1. Lệnh từ nút "Switch" (Khóa/Mở - Gửi 1 hoặc 0)
  if (method == "setValue") {
    bool params = doc["params"];
    writeModbusRegister(9, params ? 1 : 0);
    Serial.println(params ? ">>> LENH: MO KHOA (READY)" : ">>> LENH: KHOA/DUNG MAY");
  } 
  
  // 2. Lệnh từ nút "Tròn" (Bật máy từ xa - Gửi 2)
  else if (method == "remoteStart") {
    Serial.println(">>> LENH: KICH HOAT START TU XA...");
    writeModbusRegister(9, 2); delay(500); writeModbusRegister(9, 1);
  }

  // 3. Lệnh Reset Viên Rời (Gửi 3)
  else if (method == "resetP1") {
    Serial.println(">>> LENH: RESET VIEN ROI...");
writeModbusRegister(9, 3); delay(500); writeModbusRegister(9, 1);
    Serial.println(">>> DA RESET VIEN ROI XONG.");
  }

  // 4. Lệnh Reset Vỉ Thuốc (Gửi 4)
  else if (method == "resetP2") {
    Serial.println(">>> LENH: RESET VI THUOC...");
    writeModbusRegister(9, 4); delay(500); writeModbusRegister(9, 1);
    Serial.println(">>> DA RESET VI THUOC XONG.");
  }
  
  mqttClient.publish(responseTopic.c_str(), "{}");
}

// ============================================================
//  HÀM ĐỌC DỮ LIỆU PLC
// ============================================================
void readModbusRaw() {
  if (!plcClient.connected()) {
    if (!plcClient.connect(plcIP, 502)) { Serial.println(">>> PLC Offline!"); return; }
  }
  uint8_t req[] = {0, 1, 0, 0, 0, 6, 255, 3, 0, 0, 0, 9};
  plcClient.write(req, 12);
  unsigned long timeout = millis();
  while (plcClient.available() < 27 && millis() - timeout < 500);
  if (plcClient.available() >= 27) {
    uint8_t res[27]; for (int i = 0; i < 27; i++) res[i] = plcClient.read();
    if (res[7] == 0x03) { for (int i = 0; i < 9; i++) data[i] = (res[9 + i*2] << 8) | res[10 + i*2]; }
  } else { while(plcClient.available()) plcClient.read(); plcClient.stop(); }
}

// ============================================================
//  HÀM GỬI TELEMETRY LÊN THINGSBOARD
// ============================================================
void publishToThingsBoard() {
  if (!mqttClient.connected()) return;

  uint16_t bits = data[0];
  uint16_t prod_id = data[4]; 

  // Đọc trực tiếp các con số tổng từ PLC (Register 1, 2, 3 tương ứng Offset 2, 4, 6)
  uint16_t total_ok    = data[1]; 
  uint16_t total_ng    = data[2];
  uint16_t total_all   = data[3];

  StaticJsonDocument<1024> doc;
  // Gửi các số tổng chung (Để hiện lên các widget chính)
  doc["total_ok"]     = total_ok; 
  doc["total_ng"]     = total_ng; 
  doc["total_all"]    = total_all;
  
  // Gửi chi tiết từng loại (Để vẽ biểu đồ)
  doc["ok1"] = data[5]; doc["ng1"] = data[6]; // Viên rời
  doc["ok2"] = data[7]; doc["ng2"] = data[8]; // Vỉ thuốc

  doc["sys_active"]   = (bits >> 11) & 0x01;
  doc["cam_online"]   = (bits >> 13) & 0x01;
  doc["plc_online"]   = plcClient.connected() ? 1 : 0;
  doc["product_id"]   = prod_id;
  doc["product_name"] = (prod_id == 1) ? "Vien roi" : (prod_id == 2) ? "Vi thuoc" : "Chua ro";

  char payload[1024]; 
  serializeJson(doc, payload);
  mqttClient.publish("v1/devices/me/telemetry", payload);
  
  Serial.printf(">>> TB Publish: OK:%d | NG:%d | Model:%d\n", total_ok, total_ng, prod_id);
}


void connectToThingsBoard() {
  if (millis() - lastRetry > 5000) { // Thử lại sau mỗi 5 giây, không dùng while gây treo máy
    lastRetry = millis();
    Serial.print(">>> Connecting ThingsBoard...");
    if (mqttClient.connect("ESP32_Pharma_Final", TB_TOKEN, NULL)) {
      Serial.println(" OK!"); 
      mqttClient.subscribe("v1/devices/me/rpc/request/+");
    } else {
Serial.println(" Failed, will retry in 5s.");
    }
  }
}

void setup() {
  Serial.begin(115200);
  // Cấu hình IP tĩnh
  IPAddress local_IP(192, 168, 1, 100), gateway(192, 168, 1, 1), subnet(255, 255, 255, 0), dns(8, 8, 8, 8);
  WiFi.config(local_IP, gateway, subnet, dns);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) delay(500);
  Serial.println("\n>>> WiFi OK!");
  mqttClient.setServer(TB_HOST, 1883); mqttClient.setCallback(mqttCallback);
}

void loop() {
  // Kết nối lại ThingsBoard nếu mất mạng (không chặn)
  if (!mqttClient.connected()) {
    connectToThingsBoard();
  } else {
    mqttClient.loop();
  }
  
  if (millis() - lastRead > 1000) { lastRead = millis(); readModbusRaw(); }
  if (millis() - lastPublish > 3000) { lastPublish = millis(); publishToThingsBoard(); }
}
