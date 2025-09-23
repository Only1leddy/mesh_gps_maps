import xml.etree.ElementTree as ET
import math

def mercator_x_to_lon(x):
    return x / 6378137.0 * 180 / math.pi

def mercator_y_to_lat(y):
    return (2 * math.atan(math.exp(y / 6378137.0)) - math.pi/2) * 180 / math.pi

def geo_bounds(geo_file, img_width_px, img_height_px):
    """
    Returns (LAT_TOP, LAT_BOTTOM, LON_LEFT, LON_RIGHT)
    geo_file: path to .geo file
    img_width_px: width of PNG image in pixels
    img_height_px: height of PNG image in pixels
    """
    tree = ET.parse(geo_file)
    root = tree.getroot()
    
    x_origin = float(root.find('origin/x').text)
    y_origin = float(root.find('origin/y').text)
    cell_w = float(root.find('cell-width').text)
    cell_h = float(root.find('cell-height').text)
    
    x_right = x_origin + cell_w * img_width_px
    y_bottom = y_origin + cell_h * img_height_px
    
    lon_left = mercator_x_to_lon(x_origin)
    lon_right = mercator_x_to_lon(x_right)
    lat_top = mercator_y_to_lat(y_origin)
    lat_bottom = mercator_y_to_lat(y_bottom)
    
    return lat_top, lat_bottom, lon_left, lon_right

# --- Example usage ---
maps_info = {
    "home_small.png": (956, 889),
    "home_small_goggle.png": (956, 889),
    "map_spain_small.png":(1629, 1441)    
}

for filename, (w, h) in maps_info.items():
    lat_top, lat_bottom, lon_left, lon_right = geo_bounds(f"{filename}.georef", w, h)
    print(f"{filename}:")
    print(f"  LAT_TOP = {lat_top}")
    print(f"  LAT_BOTTOM = {lat_bottom}")
    print(f"  LON_LEFT = {lon_left}")
    print(f"  LON_RIGHT = {lon_right}\n")
