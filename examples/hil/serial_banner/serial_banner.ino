// Deterministic target fixture for Hardware Pentest Agent serial HIL.
//
// Flash this to an owned Arduino-compatible development board and expose its
// serial interface to the host. The HIL profile expects the banner below.

constexpr unsigned long kBaudrate = 115200;
constexpr unsigned long kBannerIntervalMs = 100;
constexpr char kBanner[] = "NULLSQUARE-HIL-READY";

void setup() {
  Serial.begin(kBaudrate);
  delay(250);
}

void loop() {
  Serial.println(kBanner);
  delay(kBannerIntervalMs);
}
