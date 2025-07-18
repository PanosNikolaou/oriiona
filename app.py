import logging
import threading
import time

from flask import Flask, request, jsonify, render_template
from datetime import datetime
from math import radians, cos, sin, asin, sqrt
import os
import json

import paho.mqtt.client as mqtt

from exports import export_bp
from imports import import_bp

from threading import Lock

latest_coords = {}
coords_lock = Lock()

ROUTES_DIR = 'routes'
os.makedirs(ROUTES_DIR, exist_ok=True)

app = Flask(__name__, static_folder='static', template_folder='templates')
app.register_blueprint(export_bp)
app.register_blueprint(import_bp)

LIVE_THRESHOLD_SECONDS = 30
NEAR_DISTANCE_METERS = 20
MAX_POINTS_PER_FILE = 500

current_log = None
last_point = {"lat": None, "lng": None, "ts": None}

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "orriona-gps"


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to HiveMQ broker")
        client.subscribe(MQTT_TOPIC)
    else:
        logger.error(f"Failed to connect to MQTT broker, return code {rc}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        lat = payload.get("latitude")
        lng = payload.get("longitude")
        mac = payload.get("mac")

        logger.debug(f"Raw MQTT payload: {payload}")

        if not mac:
            logger.warning("MQTT message missing MAC address")
            return

        normalized_mac = mac.strip().upper()
        logger.debug(f"Normalized MAC: {normalized_mac}")

        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            logger.info(f"📡 MQTT received -> MAC: {normalized_mac}, Lat: {lat}, Lng: {lng}")
            with coords_lock:
                latest_coords[normalized_mac] = {
                    'lat': float(lat),
                    'lng': float(lng),
                    'timestamp': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                }
            write_to_log(normalized_mac, lat, lng)
        else:
            logger.warning(f"Incomplete or invalid GPS coordinates in MQTT payload: {payload}")
    except Exception as e:
        logger.exception("Error processing MQTT message")

def write_to_log(mac, lat, lng):
    today = datetime.utcnow().strftime('%Y-%m-%d')
    log_dir = './logs'
    os.makedirs(log_dir, exist_ok=True)

    # Check for existing files for that MAC address
    log_file_pattern = f'{log_dir}/gps_log_{mac.replace(":", "-").upper()}_{today}_'
    existing_files = [f for f in os.listdir(log_dir) if f.startswith(log_file_pattern)]
    log_file = log_file_pattern + '0.txt'  # Default to first file

    # Determine the next available file or split the current one if too many points
    if existing_files:
        last_file = sorted(existing_files)[-1]
        with open(os.path.join(log_dir, last_file), 'r') as f:
            lines = f.readlines()
            if len(lines) >= MAX_POINTS_PER_FILE:
                next_file_num = int(last_file.split('_')[-1].replace('.txt', '')) + 1
                log_file = f'{log_file_pattern}{next_file_num}.txt'

    # Write each coordinate with its own timestamp
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')  # Generate timestamp for each point
    logger.debug(f"Timestamp to be written: {timestamp}")  # Debugging line to print the timestamp

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"{timestamp},{lat},{lng},{mac}\n")
    logger.debug(f"Data written to: {log_file}")

import requests

def get_utc_time_with_retry(retries=3, delay=5):
    url = 'https://api.exchangerate-api.com/v4/latest/UTC'  # Example API that can return UTC time, can be replaced with others
    for attempt in range(retries):
        try:
            response = requests.get(url)
            response.raise_for_status()  # Raise an error for invalid status codes
            data = response.json()
            utc_time = data['time']  # Adjust based on API response structure
            return utc_time
        except (requests.RequestException, KeyError) as e:
            print(f"Error fetching UTC time (Attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(delay)  # Wait before retrying
            else:
                print("Max retries reached. Using local time instead.")
                return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')  # Fallback to local system time


def haversine(lat1, lon1, lat2, lon2):
    logger.debug("Function: haversine()")
    R = 6371000
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return R * 2 * asin(sqrt(a))


@app.route('/')
def index():
    logger.debug("Function: index()")
    return render_template('index.html')


@app.route('/map')
def show_map():
    logger.debug("Function: show_map()")
    return render_template('map.html')


# Define the logs directory one level up from the current directory
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.', 'logs')

# Ensure the logs directory exists, create it if it doesn't
if not os.path.exists(LOGS_DIR):
    logger.info(f"Logs directory does not exist. Creating it at: {LOGS_DIR}")
    os.makedirs(LOGS_DIR)

# Route to show logs with filters
@app.route('/logs', methods=['GET', 'POST'])
def show_logs():
    logger.debug("Function: show_logs()")

    # Get the date filter from the form or default to today's date
    date_filter = request.args.get('date', datetime.utcnow().strftime('%Y-%m-%d'))

    # Get the filename filter if provided (default to empty string)
    file_filter = request.args.get('file', '')

    # List all log files matching the filters in the specific logs directory
    log_files = [
        f for f in os.listdir(LOGS_DIR)
        if f.startswith('gps_log_') and f.endswith('.txt')  # No date filter, just looking for gps_log_ files
           and (file_filter in f)  # Apply file name filter
    ]

    # Sort files by the filename (for order)
    log_files.sort()

    # Initialize an empty list to hold logs
    rows = []

    # Read logs from the filtered files
    for log_file in log_files:
        file_path = os.path.join(LOGS_DIR, log_file)
        with open(file_path, 'r') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) == 4:
                    rows.append({
                        'timestamp': parts[0],
                        'lat': parts[1],
                        'lng': parts[2],
                        'mac': parts[3]
                    })

    # Render the logs template with filtered data
    return render_template('logs.html', logs=rows, date=date_filter, files=log_files)

@app.route('/gps', methods=['POST'])
def get_latest_mqtt_coords():
    logger.debug("Function: get_latest_mqtt_coords() called")
    mac = request.args.get("mac")
    logger.debug(f"Received request for latest GPS for MAC: {mac}")

    if not mac:
        return jsonify({"error": "MAC address is required"}), 400

    with coords_lock:
        data = latest_coords.get(mac)

    if not data:
        return jsonify({"error": "No data available for this MAC"}), 404

    return jsonify({
        "mac": mac,
        "latitude": data['lat'],
        "longitude": data['lng'],
        "timestamp": data['timestamp'],
        "source": "MQTT"
    }), 200


# @app.route('/gps/live', methods=['GET'])
# from flask import Flask, request, jsonify
# import logging
# import threading
#
# app = Flask(__name__)
#
# # Setup logger
# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)
#
# # Simulated data store
# latest_coords = {}
# coords_lock = threading.Lock()

@app.route("/gps/live", methods=["GET"])
def get_latest_mqtt_coords_live():
    logger.debug("Function: get_latest_mqtt_coords_live() called")

    mac = request.args.get("mac")
    client_ip = request.remote_addr

    logger.debug(f"Raw MAC from request: {mac} | Client IP: {client_ip}")

    if not mac:
        logger.warning(f"[{client_ip}] MAC address missing from request")
        return jsonify({"error": "MAC address is required"}), 400

    normalized_mac = mac.strip().upper()
    logger.debug(f"Normalized MAC: {normalized_mac}")

    try:
        with coords_lock:
            logger.debug("Acquired coords_lock")
            data = latest_coords.get(normalized_mac)
    except Exception as e:
        logger.exception("Exception occurred while accessing latest_coords")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        logger.debug("Released coords_lock")

    if not data:
        logger.warning(f"[{client_ip}] No data found for MAC: {normalized_mac}")
        return jsonify({"error": "No data available for this MAC"}), 404

    if not isinstance(data, dict):
        logger.error(f"Invalid data type for MAC {normalized_mac}: {type(data)}")
        return jsonify({"error": "Corrupted data format"}), 500

    if not all(k in data for k in ['lat', 'lng', 'timestamp']):
        logger.error(f"Incomplete data found for MAC {normalized_mac}: {data}")
        return jsonify({"error": "Corrupted GPS data"}), 500

    try:
        lat = float(data['lat'])
        lng = float(data['lng'])
    except Exception as e:
        logger.exception(f"Failed to convert coordinates to float for MAC {normalized_mac}")
        return jsonify({"error": "Invalid coordinate values"}), 500

    logger.info(f"[{client_ip}] Returning GPS for {normalized_mac} → lat={lat}, lng={lng}, ts={data['timestamp']}")

    return jsonify({
        "mac": normalized_mac,
        "latitude": lat,
        "longitude": lng,
        "timestamp": data['timestamp'],
        "source": "MQTT"
    }), 200


@app.route('/gps/legacy', methods=['POST'])
def receive_gps():
    logger.debug("Function: receive_gps() called")

    # Parse the incoming JSON data
    data = request.get_json()  # This should read the JSON body
    logger.debug(f"Received raw data: {data}")

    if not data:
        logger.error("Error: No JSON data received")
        return jsonify({"error": "No data received"}), 400

    # Extract the necessary parameters from the JSON data
    mac = data.get('mac')
    lat = data.get('latitude')
    lng = data.get('longitude')
    logging_enabled = data.get('logging_enabled', True)  # Default to True if not provided

    logger.debug(f"Received MAC: {mac}")
    logger.debug(f"Received Latitude: {lat}, Longitude: {lng}")
    logger.debug(f"Logging Enabled: {logging_enabled}")

    if not mac or lat is None or lng is None:
        logger.error("Error: Missing required parameters")
        return jsonify({"error": "Missing parameters"}), 400

    # Debugging for logging enabled/disabled
    if logging_enabled:
        logger.info("Logging is ENABLED. Proceeding to log GPS data.")
    else:
        logger.info("Logging is DISABLED. Skipping GPS data logging.")

    # Check for duplicate coordinates (compare with previous ones)
    today = datetime.utcnow().strftime('%Y-%m-%d')
    log_dir = './logs'
    os.makedirs(log_dir, exist_ok=True)

    file_prefix = f'gps_log_{mac.replace(":", "-").upper()}_{today}_'
    session_files = sorted(
        [f for f in os.listdir(log_dir) if f.startswith(file_prefix) and f.endswith('.txt')])

    if session_files:
        last_log_file = session_files[-1]  # Get the most recent file
        with open(os.path.join(log_dir, last_log_file), 'r') as f:
            last_line = f.readlines()[-1].strip()
            last_lat, last_lng = last_line.split(',')[1:3]
            logger.debug(f"Last saved coordinates: Latitude: {last_lat}, Longitude: {last_lng}")

            if str(lat) == last_lat and str(lng) == last_lng:
                logger.warning("Received coordinates are the same as the previous ones. Skipping logging.")
                return jsonify({"status": "success", "message": "Duplicate coordinates received"}), 200

    # Call the write_to_log function if logging is enabled
    if logging_enabled:
        logger.info("Logging is enabled, writing data to log.")
        write_to_log(mac, lat, lng)

    logger.info("Returning success response.")
    return jsonify({"status": "success", "message": "Data received and processed"}), 200


def filter_coords(new_coord, last_coord, threshold_lat=0.000000009, threshold_lng=0.000000009):
    """
    Filters out coordinates that haven't changed significantly (based on a threshold in degrees).
    The threshold is based on a 0.1 cm change in latitude/longitude.

    :param new_coord: The new coordinates to compare
    :param last_coord: The previous coordinates
    :param threshold_lat: The threshold for latitude (default 1 cm)
    :param threshold_lng: The threshold for longitude (default 1 cm)
    :return: Boolean indicating whether the new coordinates are significantly different
    """
    if not last_coord:
        return True  # Always accept the first coordinate

    lat_diff = abs(new_coord['lat'] - last_coord['lat'])
    lng_diff = abs(new_coord['lng'] - last_coord['lng'])

    return lat_diff >= threshold_lat or lng_diff >= threshold_lng


from datetime import datetime

@app.route('/api/coords')
def get_coords():
    logger.debug("Function: get_coords()")

    # Extract MAC and optional date from query parameters
    mac = request.args.get('mac')
    date_filter = request.args.get('date', datetime.utcnow().strftime('%Y-%m-%d'))

    logger.debug(f"Request arguments: {request.args}")
    logger.debug(f"Received MAC: {mac}, Date Filter: {date_filter}")

    if not mac:
        logger.error("Error: No MAC address provided")
        return jsonify({"error": "MAC address is required"}), 400

    log_dir = './logs'
    os.makedirs(log_dir, exist_ok=True)

    try:
        # Create the log file prefix using the provided date (or today's date by default)
        file_prefix = f'gps_log_{mac.replace(":", "-").upper()}_{date_filter}_'

        # Find all log files for this MAC and date
        session_files = sorted([
            f for f in os.listdir(log_dir)
            if f.startswith(file_prefix) and f.endswith('.txt')
        ])

        logger.debug(f"Session files found for {mac} on {date_filter}: {session_files}")

        if not session_files:
            logger.warning(f"No session files found for MAC {mac} on {date_filter}.")
            return jsonify([])

        coords = []

        for log_file in session_files:
            logger.debug(f"Processing file: {log_file}")
            try:
                with open(os.path.join(log_dir, log_file), 'r') as f:
                    for line in f:
                        line = line.strip()
                        parts = line.split(',')

                        if len(parts) >= 4 and parts[3] == mac:
                            try:
                                lat = float(parts[1])
                                lng = float(parts[2])
                                timestamp = parts[0]  # Use original timestamp from file

                                coords.append({
                                    'lat': lat,
                                    'lng': lng,
                                    'timestamp': timestamp
                                })
                                logger.debug(f"Coordinates added: lat={lat}, lng={lng}, timestamp={timestamp}")
                            except ValueError as e:
                                logger.error(f"Invalid coordinates in line: {line}. Error: {e}")
                                continue
                        else:
                            logger.debug(f"Skipping line: {line}")
            except Exception as e:
                logger.error(f"Error reading file {log_file}: {e}")

        logger.debug(f"Total coordinates collected for MAC {mac}: {len(coords)}")
        return jsonify(coords)

    except Exception as e:
        logger.error(f"Unexpected error in get_coords(): {e}")
        return jsonify({"error": "An error occurred while processing the request"}), 500


@app.route('/routes')
def list_routes():
    logger.debug("Function: list_routes()")
    try:
        # Get all route files (those ending with .json) in the routes directory
        saved_routes = [f.replace('.json', '') for f in os.listdir(ROUTES_DIR) if f.endswith('.json')]

        # Log the list of saved routes
        logger.debug(f"Saved routes found: {saved_routes}")

        return jsonify(saved_routes)
    except Exception as e:
        # Log any exception that occurs during the file reading process
        logger.error(f"Error reading saved routes: {e}")
        return jsonify({"error": "Error fetching routes"}), 500


@app.route('/routes/save', methods=['POST'])
def save_route():
    logger.debug("Function: save_route()")

    try:
        # Get the data from the request
        data = request.json
        logger.debug(f"Received data: {data}")

        name = data.get('name')
        coords = data.get('coords')

        # Validate the data
        if not name or not coords:
            logger.error("Missing data: Name or coordinates are required.")
            return "Missing data", 400

        # Validate route name (only allows alphanumeric characters, hyphens, and underscores)
        if any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in name):
            logger.error(f"Invalid route name: {name}")
            return "Invalid characters in route name", 400

        # Log the route file path
        route_file_path = os.path.join(ROUTES_DIR, f'{name}.json')
        logger.debug(f"Saving route to: {route_file_path}")

        # Save the route data to a JSON file in the `./routes` directory
        with open(route_file_path, 'w') as f:
            json.dump(coords, f)

        # Log success
        logger.debug(f"Route saved successfully to {route_file_path}")
        return "Route saved", 200

    except Exception as e:
        # Log any exception that occurs during the route saving process
        logger.error(f"Error saving route: {e}")
        return jsonify({"error": "Error saving route"}), 500


@app.route('/routes/load/<name>')
def load_route(name):
    logger.debug("Function: load_route()")
    path = os.path.join(ROUTES_DIR, f'{name}.json')
    if not os.path.exists(path):
        return "Route not found", 404
    with open(path, 'r') as f:
        coords = json.load(f)
    return jsonify(coords)


@app.route('/routes/delete/<name>', methods=['DELETE'])
def delete_route(name):
    logger.debug("Function: delete_route()")
    path = os.path.join(ROUTES_DIR, f'{name}.json')
    if os.path.exists(path):
        os.remove(path)
        return "Route deleted", 200
    return "Route not found", 404

def start_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_forever()

@app.route('/api/marine_weather')
def marine_weather_proxy():
    lat = request.args.get('lat')
    lon = request.args.get('lon')

    logger.debug("Function: marine_weather_proxy() called")
    logger.debug(f"Received lat: {lat}, lon: {lon}")

    if not lat or not lon:
        logger.warning("Missing lat or lon in request")
        return jsonify({"error": "Missing lat or lon"}), 400

    url = f'https://map.openseamap.org/weather.php?lat={lat}&lon={lon}'
    logger.debug(f"Upstream request URL: {url}")

    try:
        response = requests.get(url, timeout=5)
        logger.debug(f"Upstream status code: {response.status_code}")
        logger.debug(f"Upstream content-type: {response.headers.get('Content-Type')}")
        logger.debug(f"Upstream response preview: {response.text[:300]}")

        if response.status_code != 200:
            logger.warning(f"Upstream service failed with status: {response.status_code}")
            return jsonify({
                "error": "Upstream service failed",
                "status": response.status_code,
                "preview": response.text[:300]
            }), 502

        try:
            data = response.json()
            logger.debug(f"Parsed JSON from upstream: {data}")
            return jsonify(data)
        except ValueError:
            logger.error("Upstream returned non-JSON content")
            return jsonify({
                "error": "Invalid JSON from upstream",
                "content_type": response.headers.get("Content-Type"),
                "body": response.text[:300]
            }), 502

    except Exception as e:
        logger.exception("Exception occurred during proxy fetch")
        return jsonify({"error": str(e)}), 500



mqtt_thread = threading.Thread(target=start_mqtt)
mqtt_thread.daemon = True
mqtt_thread.start()

if __name__ == '__main__':
    logger.debug("Function: main()")
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)