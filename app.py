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

    # Write to the selected file
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"{timestamp},{lat},{lng},{mac}\n")
    print(f"Data written to: {log_file}")


def haversine(lat1, lon1, lat2, lon2):
    print("Function: haversine()")
    R = 6371000
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return R * 2 * asin(sqrt(a))


@app.route('/')
def index():
    print("Function: index()")
    return render_template('index.html')


@app.route('/map')
def show_map():
    print("Function: show_map()")
    return render_template('map.html')


@app.route('/logs')
def show_logs():
    print("Function: show_logs()")
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
    print("Function: receive_gps() called")

    # Parse the incoming JSON data
    data = request.get_json()  # This should read the JSON body

    if not data:
        print("Error: No JSON data received")
        return jsonify({"error": "No data received"}), 400

    # Extract the necessary parameters from the JSON data
    mac = data.get('mac')
    lat = data.get('latitude')  # Note: Use 'latitude' here
    lng = data.get('longitude')  # Note: Use 'longitude' here

    print(f"Received MAC: {mac}")
    print(f"Received Latitude: {lat}, Longitude: {lng}")

    if not mac or lat is None or lng is None:
        print("Error: Missing required parameters")
        return jsonify({"error": "Missing parameters"}), 400

    today = datetime.utcnow().strftime('%Y-%m-%d')
    log_dir = './logs'
    os.makedirs(log_dir, exist_ok=True)

    # Log the GPS data to a file
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    log_file = f'{log_dir}/gps_log_{mac.replace(":", "-").upper()}_{today}_0.txt'

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"{timestamp},{lat},{lng},{mac}\n")
        print(f"Data written to: {log_file}")

    return jsonify({"status": "success", "message": "Data logged successfully"}), 200


@app.route('/api/coords')
@app.route('/api/coords')
def get_coords():
    print("Function: get_coords()")
    mac = request.args.get('mac')

    print(f"Received MAC: {mac}")
    if not mac:
        print("Error: No MAC address provided")
        return jsonify({"error": "MAC address is required"}), 400

    today = datetime.utcnow().strftime('%Y-%m-%d')
    log_dir = './logs'
    os.makedirs(log_dir, exist_ok=True)

    try:
        # Adjust file pattern to include MAC and date
        file_prefix = f'gps_log_{mac.replace(":", "-").upper()}_{today}_'

        # List files with the adjusted prefix (matching MAC and date)
        session_files = sorted(
            [f for f in os.listdir(log_dir) if f.startswith(file_prefix) and f.endswith('.txt')])

        print(f"Session files found for today ({today}): {session_files}")  # Debug log files found

        if not session_files:
            print(f"No session files found for today ({today}).")  # Log if no session files are found
            return jsonify([])

        coords = []
        for log_file in session_files:
            print(f"Processing file: {log_file}")  # Log which file is being processed
            with open(os.path.join(log_dir, log_file), 'r') as f:
                for line in f:
                    parts = line.strip().split(',')
                    print(f"Reading line: {line.strip()}")  # Log the line being read

                    if len(parts) >= 4 and parts[3] == mac:  # Check if the MAC address matches
                        try:
                            coords.append({'lat': float(parts[1]), 'lng': float(parts[2])})
                        except ValueError:
                            print(f"Error: Invalid coordinates in line: {line.strip()}")  # Log invalid coordinates
                            continue  # Skip lines with invalid coordinates

        # Log the final coordinates found
        print(f"Coordinates found for MAC {mac}: {coords}")

        if not coords:
            print(f"No coordinates found for MAC {mac}.")  # Log when no matching coordinates are found

        return jsonify(coords)

    except Exception as e:
        print(f"Error occurred while processing request: {e}")
        return jsonify({"error": "An error occurred while processing the request"}), 500


@app.route('/routes')
def list_routes():
    print("Function: list_routes()")
    saved_routes = [f.replace('.json', '') for f in os.listdir(ROUTES_DIR) if f.endswith('.json')]
    return jsonify(saved_routes)


@app.route('/routes/save', methods=['POST'])
def save_route():
    print("Function: save_route()")
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
    print("Function: load_route()")
    path = os.path.join(ROUTES_DIR, f'{name}.json')
    if not os.path.exists(path):
        return "Route not found", 404
    with open(path, 'r') as f:
        coords = json.load(f)
    return jsonify(coords)


@app.route('/routes/delete/<name>', methods=['DELETE'])
def delete_route(name):
    print("Function: delete_route()")
    path = os.path.join(ROUTES_DIR, f'{name}.json')
    if os.path.exists(path):
        os.remove(path)
        return "Route deleted", 200
    return "Route not found", 404


if __name__ == '__main__':
    print("Function: main()")
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
