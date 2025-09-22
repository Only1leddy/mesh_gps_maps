# mesh_gps_maps
Gps tracking logging system for Meshtastic dev using Pizero2w displayed on a LCD touch screen.

# LDMEC GPS System

A Raspberry Pi–based GPS and messaging system using **Meshtastic** nodes, **Pygame** for the GUI, and **SQLite** for logging.  
It includes a **fan controller** to manage CPU temperature automatically.

---

## ✨ Features
- Real-time GPS node tracking on multiple maps
- Zoom, pan, and drag support for maps
- Send and receive custom text messages over Meshtastic
- Logs saved in `mesh_logs.db` (with filtering: All, 24h, 7d, 1h)
- Tracking view with arrows showing movement paths
- Custom map selection with preview
- On-screen buttons for navigation
- Automatic **fan control** on GPIO pin 26
- Touchscreen (or mouse) support

---

## 🛠️ Requirements

- Raspberry Pi (tested on Pi Zero2w / Pi 4)
- Python 3.9+
- Installed Python packages:
  ```bash
  pip install pygame meshtastic pypubsub RPi.GPIO
HELTEC_IP = "192.168.x.xxx"   # IP of your Meshtastic node
TCP_PORT = 7801
FAN_PIN = 26                  # GPIO pin used for fan
current_map = "Home_small"    # default map



Database

SQLite file: mesh_logs.db

Table: logs

timestamp

node_id

latitude

longitude

message

🔘 Controls

Main Menu

Tracking Data → View GPS paths

View Logs → Show stored messages & positions

Custom Msg → Send text messages

Zoom In / Zoom Out → Map navigation

LDMEC GPS Options... → Select map

Quit → Exit and power off Pi

Logs

Scroll, filter by time, flush database

Tracking

Cycle filters, zoom, select specific node paths

🖼️ Screens

(TODO: Add screenshots of main screen, logs, and tracking)

⚡ Notes

The fan will automatically toggle when CPU temp > 60°C.

Touch input (FINGERDOWN, FINGERMOTION, FINGERUP) is enabled for Pi touchscreen.

If connection to Meshtastic node fails, the app will retry every 5 seconds.
