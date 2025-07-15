import logging
from flask import Flask, request, jsonify, render_template
from datetime import datetime
from math import radians, cos, sin, asin, sqrt
import os
import json

from exports import export_bp
from imports import import_bp

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

    # Create timestamp
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    logger.debug(f"Timestamp to be written: {timestamp}")  # Debugging line to print the timestamp

    # Write to the selected file
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"{timestamp},{lat},{lng},{mac}\n")
    logger.debug(f"Data written to: {log_file}")


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


from datetime import datetime


def filter_coords(new_coord, last_coord, threshold=0.00001):
    """
    Filters out coordinates that haven't changed significantly (based on a threshold).
    """
    if not last_coord:
        return True  # Always accept the first coordinate

    lat_diff = abs(new_coord['lat'] - last_coord['lat'])
    lng_diff = abs(new_coord['lng'] - last_coord['lng'])

    return lat_diff >= threshold or lng_diff >= threshold


@app.route('/api/coords')
def get_coords():
    logger.debug("Function: get_coords()")
    mac = request.args.get('mac')

    # Log the full request arguments to debug if 'mac' is being passed correctly
    logger.debug(f"Request arguments: {request.args}")

    # Check if `mac` is None or an empty string
    if not mac:
        logger.error("Error: No MAC address provided")
        return jsonify({"error": "MAC address is required"}), 400

    logger.debug(f"Received MAC: {mac}")  # Ensure `mac` is being set correctly here

    today = datetime.utcnow().strftime('%Y-%m-%d')
    log_dir = './logs'
    os.makedirs(log_dir, exist_ok=True)

    try:
        # Adjust file pattern to include MAC and date
        file_prefix = f'gps_log_{mac.replace(":", "-").upper()}_{today}_'

        # List files with the adjusted prefix (matching MAC and date)
        session_files = sorted(
            [f for f in os.listdir(log_dir) if f.startswith(file_prefix) and f.endswith('.txt')])

        logger.debug(f"Session files found for today ({today}): {session_files}")

        if not session_files:
            logger.warning(f"No session files found for MAC {mac} on {today}.")
            return jsonify([])

        coords = []
        last_coord = None  # Track the last coordinate added to the list

        for log_file in session_files:
            logger.debug(f"Processing file: {log_file}")

            try:
                with open(os.path.join(log_dir, log_file), 'r') as f:
                    logger.debug(f"Opened file {log_file} for reading.")
                    for line in f:
                        line = line.strip()  # Clean up the line
                        logger.debug(f"Reading line: {line}")

                        parts = line.split(',')
                        logger.debug(f"Line split into parts: {parts}")

                        if len(parts) >= 4:
                            if parts[3] == mac:
                                try:
                                    lat = float(parts[1])
                                    lng = float(parts[2])
                                    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

                                    new_coord = {'lat': lat, 'lng': lng, 'timestamp': timestamp}

                                    # Only append the new coordinate if it differs significantly from the last one
                                    if filter_coords(new_coord, last_coord):
                                        coords.append(new_coord)
                                        logger.debug(f"Coordinates added: lat={lat}, lng={lng}, timestamp={timestamp}")
                                        last_coord = new_coord
                                    else:
                                        logger.debug("Coordinates haven't changed significantly. Skipping update.")
                                except ValueError as e:
                                    logger.error(f"Invalid coordinates in line: {line}. Error: {e}")
                                    continue
                            else:
                                logger.debug(f"Skipping line with mismatched MAC address: {parts[3]} != {mac}")
                        else:
                            logger.warning(f"Skipping line with incorrect number of parts: {line}")

            except Exception as e:
                logger.error(f"Error processing file {log_file} for MAC {mac}: {e}")

        logger.debug(f"Total coordinates collected for MAC {mac}: {len(coords)}")
        if coords:
            logger.info(f"Coordinates found for MAC {mac}: {coords[:5]}...")
        else:
            logger.warning(f"No coordinates found for MAC {mac}.")

        return jsonify(coords)

    except Exception as e:
        logger.error(f"Error occurred while processing request: {e}")
        return jsonify({"error": "An error occurred while processing the request"}), 500


@app.route('/routes')
def list_routes():
    logger.debug("Function: list_routes()")
    saved_routes = [f.replace('.json', '') for f in os.listdir(ROUTES_DIR) if f.endswith('.json')]
    return jsonify(saved_routes)


@app.route('/routes/save', methods=['POST'])
def save_route():
    logger.debug("Function: save_route()")
    data = request.json
    name = data.get('name')
    coords = data.get('coords')
    if not name or not coords:
        return "Missing data", 400
    if any(c not in name for c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-'):
        return "Invalid characters in route name", 400
    with open(os.path.join(ROUTES_DIR, f'{name}.json'), 'w') as f:
        json.dump(coords, f)
    return "Route saved", 200


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


if __name__ == '__main__':
    logger.debug("Function: main()")
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)