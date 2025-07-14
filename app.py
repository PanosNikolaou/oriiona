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


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return R * 2 * asin(sqrt(a))


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/map')
def show_map():
    return render_template('map.html')


@app.route('/logs')
def show_logs():
    date = request.args.get('date') or datetime.utcnow().strftime('%Y-%m-%d')
    session_files = sorted([f for f in os.listdir('.') if f.startswith(f'gps_log_{date}_') and f.endswith('.txt')])
    if not session_files:
        return "No logs found.", 404

    rows = []
    for log_file in session_files:
        with open(log_file, 'r') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) == 4:
                    rows.append({
                        'timestamp': parts[0],
                        'lat': parts[1],
                        'lng': parts[2],
                        'mac': parts[3]
                    })

    return render_template('logs.html', logs=rows, date=date)


@app.route('/gps', methods=['POST'])
def receive_gps():
    global last_point, current_log
    log_dir = './logs'  # Define a logs directory
    os.makedirs(log_dir, exist_ok=True)  # Ensure the logs directory exists

    # Fetch the incoming GPS data from the POST request
    lat = request.form.get('gps_data_lat')
    lng = request.form.get('gps_data_lng')
    mac = request.form.get('mac') or "UNKNOWN"

    # Ensure latitude and longitude are provided
    if not lat or not lng:
        return "Missing parameters", 400

    # Try to convert latitude and longitude to float
    try:
        lat = float(lat)
        lng = float(lng)
    except ValueError:
        return "Invalid coordinates", 400

    # Get current timestamp and format it
    now = datetime.utcnow()
    timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
    today = now.strftime('%Y-%m-%d')

    # Clean the MAC address to make it safe for filenames
    mac_safe = mac.replace(":", "-").upper()

    # Set the initial log file name if not already set
    if not current_log:
        current_log = f'{log_dir}/gps_log_{mac_safe}_{today}_0.txt'

    # Log the current log file name for debugging
    print(f"Writing to log file: {current_log}")

    # Check if a rollover is needed (i.e., file has too many entries)
    rollover_needed = False
    if os.path.exists(current_log):
        with open(current_log, 'r', encoding='utf-8', errors='ignore') as f:
            if sum(1 for _ in f) >= MAX_POINTS_PER_FILE:
                rollover_needed = True

    # If a rollover is needed, create a new log file
    if rollover_needed:
        try:
            index = int(current_log.split("_")[-1].split(".")[0])
        except:
            index = 0
        current_log = f'{log_dir}/gps_log_{mac_safe}_{today}_{index + 1}.txt'

    # Update the last point
    last_point = {"lat": lat, "lng": lng, "ts": now}

    # Write the new GPS data to the log file
    with open(current_log, 'a', encoding='utf-8', errors='ignore') as f:
        f.write(f"{timestamp},{lat},{lng},{mac}\n")

    # Log the file where data is written
    print(f"Data written to: {current_log}")

    # Return a success message
    return f"Data received from {mac} and logged to {current_log}.", 200


@app.route('/api/coords')
def get_coords():
    mac = request.args.get('mac')  # Retrieve 'mac' parameter from query string

    if not mac:
        print("Error: No MAC address provided")  # Log error if no MAC is provided
        return jsonify({"error": "MAC address is required"}), 400  # Return error if no mac is provided

    today = datetime.utcnow().strftime('%Y-%m-%d')
    log_dir = './logs'  # Define the logs directory
    os.makedirs(log_dir, exist_ok=True)  # Create the directory if it doesn't exist

    try:
        # Check if session files exist for today
        session_files = sorted(
            [f for f in os.listdir(log_dir) if f.startswith(f'gps_log_{today}_') and f.endswith('.txt')])

        if not session_files:
            print(f"No session files found for today ({today}).")  # Log if no session files are found
            return jsonify([])  # Return empty list if no session files for today

        coords = []
        for log_file in session_files:
            print(f"Processing file: {log_file}")  # Log the file being processed
            with open(os.path.join(log_dir, log_file), 'r') as f:  # Ensure we're reading from the correct directory
                for line in f:
                    parts = line.strip().split(',')
                    print(f"Reading line: {line.strip()}")  # Log the line being read

                    if len(parts) >= 4 and parts[3] == mac:  # Ensure the mac address matches
                        try:
                            coords.append({'lat': float(parts[1]), 'lng': float(parts[2])})
                        except ValueError:
                            print(f"Error: Invalid coordinates in line: {line.strip()}")  # Log invalid coordinates
                            continue  # Skip lines with invalid coordinates

        # Debugging: Log the final coordinates returned
        print(f"Coordinates found for MAC {mac}: {coords}")
        return jsonify(coords)

    except Exception as e:
        # Catch any exception and return an error message
        print(f"Error occurred while processing request: {e}")
        return jsonify({"error": "An error occurred while processing the request"}), 500


@app.route('/routes')
def list_routes():
    saved_routes = [f.replace('.json', '') for f in os.listdir(ROUTES_DIR) if f.endswith('.json')]
    return jsonify(saved_routes)


@app.route('/routes/save', methods=['POST'])
def save_route():
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
    path = os.path.join(ROUTES_DIR, f'{name}.json')
    if not os.path.exists(path):
        return "Route not found", 404
    with open(path, 'r') as f:
        coords = json.load(f)
    return jsonify(coords)


@app.route('/routes/delete/<name>', methods=['DELETE'])
def delete_route(name):
    path = os.path.join(ROUTES_DIR, f'{name}.json')
    if os.path.exists(path):
        os.remove(path)
        return "Route deleted", 200
    return "Route not found", 404


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
