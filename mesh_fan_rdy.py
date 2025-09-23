import pygame
import meshtastic
import meshtastic.tcp_interface
import time
import sqlite3
from datetime import datetime, timedelta
import math
from pubsub import pub
import threading
import RPi.GPIO as GPIO
import os

#------------
FAN_PIN = 26
GPIO.setmode(GPIO.BCM)
GPIO.setup(FAN_PIN, GPIO.OUT)
#-----------
db_lock = threading.Lock()
# --- CONFIG ---
HELTEC_IP = "192.168.50.105"
TCP_PORT = 7801
#MAP_FILE = "map_scaled.png"
SCREEN_SIZE = (1024, 600)
FONT_SIZE = 20
# --- start stuff ---
interface = None
connected = False
retry_interval = 5
# change for you nodes 
NODE_NAMES = {
    "!a0ca43ac": "rome",
    "!433d7330": "ldgps",
    "!e00cea84": "base"
}
# change ref nodes above
NODE_COLORS = {
    "!a0ca43ac": (0,120,255),
    "!433d7330": (0,220,100),
    "!e00cea84": (220,100,20)
}

#del this is you dont have fan! 
def cpu_temp():
    with open("/sys/class/thermal/thermal_zone0/temp") as f:
        return int(f.read().strip()) / 1000

def fan_loop():
    try:
        while True:
            temp = cpu_temp()
            if temp > 60:
                GPIO.output(FAN_PIN, GPIO.HIGH)
            else:
                GPIO.output(FAN_PIN, GPIO.LOW)
            # optional debug
            print(f"[FAN] Temp: {temp:.1f}C Fan: {'ON' if temp > 60 else 'OFF'}")
            time.sleep(5)
    except Exception as e:
        print(f"[FAN] Error: {e}")
    finally:
        GPIO.output(FAN_PIN, GPIO.LOW)
#and this
# start fan loop in background
fan_thread = threading.Thread(target=fan_loop, daemon=True)
fan_thread.start()



# --- Map configs --- load your maps parths and Lat/Lon of each map (derived from georef files)
MAPS = {
    "Espanol Basic": {
        "file": "map_esp_basic_scaled.png",
        "LAT_TOP": 37.5469926,
        "LAT_BOTTOM": 37.3708455,
        "LON_LEFT": -2.4593738,
        "LON_RIGHT": -2.328202
    }
}

current_map = "Espanol Basic"
MAP_FILE = MAPS[current_map]["file"]
LAT_TOP = MAPS[current_map]["LAT_TOP"]
LAT_BOTTOM = MAPS[current_map]["LAT_BOTTOM"]
LON_LEFT = MAPS[current_map]["LON_LEFT"]
LON_RIGHT = MAPS[current_map]["LON_RIGHT"]


MAIN_BUTTONS = ["Tracking Data", "View Logs","Come Back", "Custom Msg", "Zoom In", "Zoom Out", "LDMEC GPS Options...", "Quit"]
MSG_BUTTONS = ["Send", "Back", "DEL"]
TIME_FILTERS = ["All", "24h", "7d", "1Hour"]

# --- DB setup ---
conn = sqlite3.connect("mesh_logs.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    node_id TEXT,
    latitude REAL,
    longitude REAL,
    message TEXT
)
""")
conn.commit()

# --- Pygame setup ---
pygame.init()
screen = pygame.display.set_mode(SCREEN_SIZE)
pygame.display.set_caption("LDMEC GPS SYSYEM")
font = pygame.font.Font(None, FONT_SIZE)
clock = pygame.time.Clock()

# --- Helpers ---
def draw_text(text, pos, color=(0,0,0)):
    txt = font.render(text, True, color)
    screen.blit(txt, pos)
    
# dont ask dont touch dont brake
X_OFFSET_DEG = 0.00000   # + right
Y_OFFSET_DEG = 0.00000   # + down

    
def gps_to_screen(lat, lon, lat_top, lat_bottom, lon_left, lon_right, scaled_width, scaled_height, pan_offset):
    # normalize 0..1
    if lat is None or lon is None:
        return None 
    rel_x = (lon - lon_left) / (lon_right - lon_left)
    rel_y = (lat_top - lat) / (lat_top - lat_bottom)  # y is inverted

    # apply scale + pan
    x = pan_offset[0] + int(rel_x * scaled_width)
    y = pan_offset[1] + int(rel_y * scaled_height)
    return x, y

def gps_to_screen1(lat, lon, map_width, map_height, zoom, offset):
    off_set(current_map)
    lat += -Y_OFFSET_DEG   # subtract if you want to move down
    lon += X_OFFSET_DEG
    x = (lon - LON_LEFT) / (LON_RIGHT - LON_LEFT) * map_width * zoom + offset[0]
    y = (LAT_TOP - lat) / (LAT_TOP - LAT_BOTTOM) * map_height * zoom + offset[1]
    return int(x), int(y)

def draw_buttons(labels, panel_x, panel_y, btn_width, padding=10):
    btn_height = 50
    rects = []
    for i, label in enumerate(labels):
        y = panel_y + i*(btn_height + padding)
        rect = pygame.Rect(panel_x, y, btn_width, btn_height)
        pygame.draw.rect(screen, (0,100,200), rect)
        draw_text(label, (rect.x+10, rect.y+10), (255,255,255))
        rects.append((rect,label))
    return rects

def filter_logs(logs, time_filter):
    if time_filter == "All":
        return logs
    now = datetime.now()
    if time_filter == "24h":
        cutoff = now - timedelta(days=1)
    elif time_filter == "7d":
        cutoff = now - timedelta(days=7)
    elif time_filter == "1Hour":
        cutoff = now - timedelta(hours=1)
    else:
        return logs
    return [l for l in logs if datetime.fromisoformat(l[1]) >= cutoff]







def on_receive(packet, interface):
    try:
        from_id = packet.get('fromId', 'unknown')
        text = packet.get('decoded', {}).get('text', '')

        timestamp = datetime.now().isoformat()
        with db_lock:
            cur.execute("INSERT INTO logs (timestamp,node_id,latitude,longitude,message) VALUES (?,?,?,?,?)",
                        (timestamp, from_id, None, None, text))
            conn.commit()

        global last_message
        last_message = f"{NODE_NAMES[from_id]}: {text}"
        print(f"MessIn:{NODE_NAMES[from_id]}:{text}")

    except Exception as e:
        print("Error parsing message:", e)


while not connected:
    try:
        interface = meshtastic.tcp_interface.TCPInterface(HELTEC_IP, TCP_PORT)
        time.sleep(1)  # give time to init
        connected = True
        pub.subscribe(on_receive, "meshtastic.receive.text")
        #interface.onReceive = on_receive
    except Exception as e:
        print("Connection failed:", e)
        # Show message on Pygame screen
        screen.fill((0,0,0))
        draw_text("Connecting... waiting for host/mesh device", (50, SCREEN_SIZE[1]//2), (255,0,0))
        pygame.display.flip()
        # Check for quit events so you don’t get stuck forever
        waiting = True
        start_time = time.time()
        while time.time() - start_time < retry_interval:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    conn.close()
                    raise SystemExit
            time.sleep(0.1)




# --- Connect to Heltec ---
#interface = meshtastic.tcp_interface.TCPInterface(HELTEC_IP, TCP_PORT)
#time.sleep(1)

# --- State ---
zoom_factor = 1.0
pan_offset = [0,0]
last_message = ""
screen_mode = "main"  # "main", "custom_msg", "view_logs", "tracking"
custom_message = ""
dragging = False
drag_start = (0,0)
offset_start = (0,0)
last_positions = {}  # keep latest positions on main map
start_x, start_y = 0, 0
map_scroll = 0
DRAG_THRESHOLD = 15 
# Global time filter
current_filter_idx = 0
time_filter = TIME_FILTERS[current_filter_idx]
selected_node = "All"
# Scroll position for logs
log_scroll = 0


def draw_arrow(surface, color, start, end, arrow_size=10, pos_fraction=0.5):
    pygame.draw.line(surface, color, start, end, 2)
    """Draw a filled triangle arrow along the line from start to end at pos_fraction."""
    x = start[0] + (end[0]-start[0]) * pos_fraction
    y = start[1] + (end[1]-start[1]) * pos_fraction
    
    angle = math.atan2(end[1]-start[1], end[0]-start[0])
    
    # Triangle points
    p1 = (x, y)
    p2 = (x - arrow_size * math.cos(angle - math.pi/6),
          y - arrow_size * math.sin(angle - math.pi/6))
    p3 = (x - arrow_size * math.cos(angle + math.pi/6),
          y - arrow_size * math.sin(angle + math.pi/6))
    
    pygame.draw.polygon(screen, color, [p1, p2, p3])



# --- Main Loop ---
running = True

while running:
    screen.fill((173, 216, 230))  # background
    # --- MAIN SCREEN ---
    if screen_mode == "main":
        map_width = int(SCREEN_SIZE[0]*0.7)
        map_height = SCREEN_SIZE[1]
        try:
            map_img = pygame.image.load(MAP_FILE)
            img_rect = map_img.get_rect()
            aspect = img_rect.width / img_rect.height

            # scale keeping aspect ratio
            scaled_width = int(map_width * zoom_factor)
            scaled_height = int(scaled_width / aspect)

            # if taller than area, resize by height instead
            if scaled_height > map_height * zoom_factor:
                scaled_height = int(map_height * zoom_factor)
                scaled_width = int(scaled_height * aspect)

            map_img_scaled = pygame.transform.smoothscale(map_img, (scaled_width, scaled_height))
            screen.blit(map_img_scaled, pan_offset)

        except Exception as e:
            draw_text(f"Map image missing! ({e})", (50, 50), (255, 0, 0))
     
             # Draw latest node positions
        for node_id, node_info in interface.nodes.items():
            pos = node_info.get("position", {})
            lat = pos.get("latitude") or pos.get("lat")
            lon = pos.get("longitude") or pos.get("lon")
            if lat is not None and lon is not None:
                
                # Only save if changed
                last = last_positions.get(node_id)
                if not last or last != (lat, lon):
                    timestamp = datetime.now().isoformat()
                    cur.execute("INSERT INTO logs (timestamp,node_id,latitude,longitude,message) VALUES (?,?,?,?,?)",
                                (timestamp,node_id,lat,lon,"GPS"))
                    conn.commit()
                    last_positions[node_id] = (lat, lon)
                    
                x, y = gps_to_screen(
                    lat, lon,
                    LAT_TOP, LAT_BOTTOM, LON_LEFT, LON_RIGHT,
                    scaled_width, scaled_height,
                    pan_offset
                )
                
                ##x, y = gps_to_screen(lat, lon, map_width, map_height, zoom_factor, pan_offset)
                color = NODE_COLORS.get(node_id,(255,0,0))
                # Example when drawing your GPS point
                pygame.draw.circle(screen, color, (x, y), 8)
                name = NODE_NAMES.get(node_id,node_id)
                draw_text(name, (x+10,y-10), color)
            
         

        # Right panel
        panel_x = map_width
        panel_w = SCREEN_SIZE[0] - panel_x
        pygame.draw.rect(screen, (200,220,240), (panel_x,0,panel_w,SCREEN_SIZE[1]))
        if last_message:
            draw_text("Mes "+last_message, (panel_x+10,20))
        # Draw main buttons
        button_rects = draw_buttons(MAIN_BUTTONS, panel_x+10, 60, panel_w-20)
        draw_text(f"Time Filter: {time_filter}", (panel_x+10, 40))

    # --- CUSTOM MESSAGE SCREEN ---
    elif screen_mode=="custom_msg":
        draw_text("Custom Message Screen", (20,20))
        pygame.draw.rect(screen,(255,255,255),(20,60,SCREEN_SIZE[0]-40,40))
        draw_text(custom_message, (30,70))
        # Keyboard
        keys = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        keys += " "  # add space as last key
        key_rects=[]
        rows=3
        cols=9
        key_w=60
        key_h=50
        for i,ch in enumerate(keys):
            row=i//cols
            col=i%cols
            x=20+col*(key_w+5)
            y=120+row*(key_h+5)
            rect=pygame.Rect(x,y,key_w,key_h)
            pygame.draw.rect(screen,(0,100,200),rect)
            if ch==" ":
                draw_text("SPACE",(x+5,y+15),(255,255,255))
            else:
                draw_text(ch,(x+15,y+15),(255,255,255))
            key_rects.append((rect,ch))
        # Send, Back, DEL
        button_rects = draw_buttons(MSG_BUTTONS, SCREEN_SIZE[0]-160, 120, 140)

    # --- VIEW LOGS SCREEN ---
    elif screen_mode=="view_logs":
        draw_text(f"Logs ({time_filter})", (20,20))
        panel_y = 60
        cur.execute("SELECT * FROM logs ORDER BY timestamp DESC")
        logs = cur.fetchall()
        logs = filter_logs(logs,time_filter)
        # Scrollable list
        max_lines = (SCREEN_SIZE[1]-panel_y)//25
        visible_logs = logs[log_scroll:log_scroll+max_lines]
        y=panel_y
        for log in visible_logs:
            ts,node,lat,lon,msg=log[1],log[2],log[3],log[4],log[5]
            if lat is not None and lon is not None:
                draw_text(f"{ts} {NODE_NAMES.get(node, node)} ({lat:.5f},{lon:.5f}) {msg}", (20, y))
            else:
                draw_text(f"{ts} {NODE_NAMES.get(node, node)} {msg}", (20, y))

            ##draw_text(f"{ts} {NODE_NAMES.get(node,node)} ({lat:.5f},{lon:.5f}) {msg}",(20,y))
            y+=25
        button_rects = draw_buttons(["Back","Scroll Up","Scroll Down","Cycle Filter", "Flush Logs"], SCREEN_SIZE[0]-150, panel_y, 140)

    # --- TRACKING SCREEN ---
    elif screen_mode=="tracking":
        try:
            map_img = pygame.image.load(MAP_FILE)
            img_rect = map_img.get_rect()
            aspect = img_rect.width / img_rect.height

            # scale keeping aspect ratio
            scaled_width = int(map_width * zoom_factor)
            scaled_height = int(scaled_width / aspect)

            # if taller than area, resize by height instead
            if scaled_height > map_height * zoom_factor:
                scaled_height = int(map_height * zoom_factor)
                scaled_width = int(scaled_height * aspect)

            map_img_scaled = pygame.transform.smoothscale(map_img, (scaled_width, scaled_height))
            screen.blit(map_img_scaled, pan_offset)

        except Exception as e:
            draw_text(f"Map image missing! ({e})", (50, 50), (255, 0, 0))
        
        
            
        #draw_text(f"Tracking Map ({time_filter})", (200,20),(0,0,0))
        map_width=int(SCREEN_SIZE[0]*0.7)
        map_height=SCREEN_SIZE[1]
        # Draw GPS logs as lines with arrows
        cur.execute("SELECT * FROM logs ORDER BY timestamp")
        logs=cur.fetchall()
        logs=filter_logs(logs,time_filter)
        
        if selected_node != "All":
            logs = [l for l in logs if NODE_NAMES.get(l[2], l[2]) == selected_node]
            
        node_points={}
        for log in logs:
            ts,node,lat,lon,msg=log[1],log[2],log[3],log[4],log[5]
            coords = gps_to_screen(
                lat, lon,
                LAT_TOP, LAT_BOTTOM, LON_LEFT, LON_RIGHT,
                scaled_width, scaled_height,
                pan_offset
            )

            if coords is None:
                continue  # skip logs with no GPS
            x, y = coords
            #x,y=gps_to_screen(lat,lon,map_width,map_height,zoom_factor,pan_offset)
            if node not in node_points:
                node_points[node]=[]
            node_points[node].append((x,y))
            
        for node,pts in node_points.items():
            color=NODE_COLORS.get(node,(255,0,0))
            for i in range(1,len(pts)):
                draw_arrow(screen,color,pts[i-1],pts[i],arrow_size=10,pos_fraction=0.5)
                #draw_arrow1(screen,color,pts[i-1],pts[i],arrow_size=10)
                
            for p in pts:
                pygame.draw.circle(screen,color,p,4)
        panel_x=map_width
        panel_w=SCREEN_SIZE[0]-panel_x
        pygame.draw.rect(screen,(200,220,240),(panel_x,0,panel_w,SCREEN_SIZE[1]))
        button_rects=draw_buttons(["Back","Cycle Filter", "Zoom In", "Zoom Out", "All Nodes"]+ list(NODE_NAMES.values()), panel_x+10,60,panel_w-20)
        draw_text(f"Tracking Map ({time_filter}) - {selected_node}", (20,20), (0,0,0))

    # --- CHOSE MAP SCREEN ----
    elif screen_mode == "gps_options":
        draw_text("Select Map:", (20,20))
        maps_list = list(MAPS.keys())
        max_maps_visible = 6
        visible_maps = maps_list[map_scroll:map_scroll+max_maps_visible]
        
        # left side buttons
        button_rects = draw_buttons(visible_maps, 20, 60, 300)
        
        # right side buttons
        side_buttons = draw_buttons(
            ["Back","Scroll Up","Scroll Down"],
            SCREEN_SIZE[0]-220,
            60,
            200
        )
        button_rects += side_buttons

        # --- Map preview in center ---
        if "preview_map" not in globals():
            preview_map = current_map  # start with current map
        
        try:
            preview_file = MAPS[preview_map]["file"]
            preview_img = pygame.image.load(preview_file)
            img_rect = preview_img.get_rect()

            # scale to a fixed square area (force scale)
            preview_size = min(SCREEN_SIZE[0]//3, SCREEN_SIZE[1]//2)  # ~square box
            preview_img = pygame.transform.smoothscale(preview_img, (preview_size, preview_size))

            # draw in middle of screen
            center_x = SCREEN_SIZE[0]//2 - preview_size//2
            center_y = SCREEN_SIZE[1]//2 - preview_size//2
            screen.blit(preview_img, (center_x, center_y))

            draw_text(preview_map, (center_x, center_y-30), (0,0,0))
        except Exception as e:
            draw_text(f"Preview error: {e}", (400,300), (255,0,0))

    
    pygame.display.flip()

    # --- EVENT HANDLING ---
    for event in pygame.event.get():
        if event.type==pygame.QUIT:
            running=False
        elif event.type == pygame.FINGERDOWN:    
        ##elif event.type==pygame.MOUSEBUTTONDOWN:
            x = int(event.x * SCREEN_SIZE[0])
            y = int(event.y * SCREEN_SIZE[1])

            ##x,y=event.pos ##
            #main screen
            if screen_mode=="main":
                
                if x<int(SCREEN_SIZE[0]*0.7):
                    dragging = True
                    drag_start = (x, y)
                    map_drag_start_offset = pan_offset.copy()
                    #offset_start = pan_offset.copy()
                    
                else:
                    for rect,label in button_rects:
                        if rect.collidepoint(x,y):
                            if label=="Quit": running=False##!! option to turn off fully; os.system("sudo poweroff")
                            
                            elif label=="Zoom In":
                                old_center = (SCREEN_SIZE[0]//2, SCREEN_SIZE[1]//2)
                                zoom_factor *= 1.25
                                pan_offset[0] = int(old_center[0] - (old_center[0] - pan_offset[0]) * 1.25)
                                pan_offset[1] = int(old_center[1] - (old_center[1] - pan_offset[1]) * 1.25)

                            elif label=="Zoom Out":
                                old_center = (SCREEN_SIZE[0]//2, SCREEN_SIZE[1]//2)
                                zoom_factor = max(0.4, zoom_factor / 1.25)
                                pan_offset[0] = int(old_center[0] - (old_center[0] - pan_offset[0]) / 1.25)
                                pan_offset[1] = int(old_center[1] - (old_center[1] - pan_offset[1]) / 1.25)
                                
                            elif label=="Custom Msg": screen_mode="custom_msg"
                            elif label=="View Logs": screen_mode="view_logs"
                            elif label=="LDMEC GPS Options...": screen_mode="gps_options"
                            elif label=="Tracking Data": screen_mode="tracking"
                            elif label=="Come Back":
                                try: interface.sendText("Come Back"); last_message="Sent: Come Back"
                                except: last_message="Error sending"
            #mes screen
            elif screen_mode=="custom_msg":
                for rect,label in button_rects:
                    if rect.collidepoint(x,y):
                        if label=="Send":
                            try: interface.sendText(custom_message); last_message="Sent: "+custom_message
                            except: last_message="Error sending"
                            custom_message=""; screen_mode="main"
                        elif label=="Back": screen_mode="main"
                        elif label=="DEL": custom_message=custom_message[:-1]
                for rect,ch in key_rects:
                    if rect.collidepoint(x,y):
                        if ch==" ": custom_message+=" "
                        else: custom_message+=ch
            #logs screen
            elif screen_mode=="view_logs":
                for rect,label in button_rects:
                    if rect.collidepoint(x,y):
                        if label=="Back": screen_mode="main"
                        elif label=="Scroll Up": log_scroll=max(0,log_scroll-5)
                        elif label=="Scroll Down": log_scroll=min(max(0,len(logs)-5),log_scroll+5)
                        elif label=="Cycle Filter":
                            current_filter_idx=(current_filter_idx+1)%len(TIME_FILTERS)
                            time_filter=TIME_FILTERS[current_filter_idx]; log_scroll=0
                        elif label=="Flush Logs":
                            cur.execute("DELETE FROM logs"); conn.commit(); last_message="DB Flushed"; last_positions.clear(); log_scroll =0
            #tracking screen                
            elif screen_mode=="tracking":    
                if x<int(SCREEN_SIZE[0]*0.7):
                    dragging = True
                    drag_start = (x, y)
                    map_drag_start_offset = pan_offset.copy()
                    #offset_start = pan_offset.copy()
                else:    
                    for rect,label in button_rects:
                        if rect.collidepoint(x,y):
                            if label=="Back": screen_mode="main"
                            elif label=="Cycle Filter":
                                current_filter_idx=(current_filter_idx+1)%len(TIME_FILTERS)
                                time_filter=TIME_FILTERS[current_filter_idx]
                            elif label=="All Nodes":
                                selected_node = "All"
                            elif label in NODE_NAMES.values():
                                selected_node = label
                            elif label=="Zoom In":
                                old_center = (SCREEN_SIZE[0]//2, SCREEN_SIZE[1]//2)
                                zoom_factor *= 1.25
                                pan_offset[0] = int(old_center[0] - (old_center[0] - pan_offset[0]) * 1.25)
                                pan_offset[1] = int(old_center[1] - (old_center[1] - pan_offset[1]) * 1.25)

                            elif label=="Zoom Out":
                                old_center = (SCREEN_SIZE[0]//2, SCREEN_SIZE[1]//2)
                                zoom_factor = max(0.4, zoom_factor / 1.25)
                                pan_offset[0] = int(old_center[0] - (old_center[0] - pan_offset[0]) / 1.25)
                                pan_offset[1] = int(old_center[1] - (old_center[1] - pan_offset[1]) / 1.25)
                                
            #gps screen 
            elif screen_mode == "gps_options":
                for rect,label in button_rects:
                    if rect.collidepoint(x,y):
                        if label == "Back":
                            # lock in preview as current
                            current_map = preview_map
                            MAP_FILE = MAPS[current_map]["file"]
                            LAT_TOP = MAPS[current_map]["LAT_TOP"]
                            LAT_BOTTOM = MAPS[current_map]["LAT_BOTTOM"]
                            LON_LEFT = MAPS[current_map]["LON_LEFT"]
                            LON_RIGHT = MAPS[current_map]["LON_RIGHT"]
                            last_message = f"Map set: {current_map}"
                            screen_mode = "main"

                        elif label == "Scroll Up":
                            map_scroll = max(0, map_scroll-5)

                        elif label == "Scroll Down":
                            map_scroll = min(max(0, len(MAPS)-max_maps_visible), map_scroll+5)

                        elif label in MAPS:
                            preview_map = label  # just change preview, not current yet
                            
        ##elif event.type == pygame.MOUSEBUTTONUP:##
        elif event.type == pygame.FINGERUP:
            dragging=False
        
        ##elif event.type == pygame.MOUSEMOTION and dragging and screen_mode in ["main", "tracking"]:##
        elif event.type == pygame.FINGERMOTION and dragging and screen_mode in ["main", "tracking"]:
            ##dx = event.pos[0] - drag_start[0]##
            ##dy = event.pos[1] - drag_start[1]##
            x = int(event.x * SCREEN_SIZE[0])
            y = int(event.y * SCREEN_SIZE[1])
            dx = x - drag_start[0]
            dy = y - drag_start[1]
            if abs(dx) > DRAG_THRESHOLD or abs(dy) > DRAG_THRESHOLD:
            # Update pan relative to the map's position at drag start
                pan_offset[0] = map_drag_start_offset[0] + dx
                pan_offset[1] = map_drag_start_offset[1] + dy
     
    clock.tick(30)

pygame.quit()
conn.close()
GPIO.output(FAN_PIN, GPIO.LOW)
#GPIO.cleanup()
print("Shutting down cleanly")









