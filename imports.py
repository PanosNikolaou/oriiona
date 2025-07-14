# imports.py
import os
import io
import csv
import json
from flask import Blueprint, request, jsonify

import_bp = Blueprint('imports', __name__)

@import_bp.route('/import/csv', methods=['POST'])
def import_csv():
    file = request.files.get('file')
    if not file or not file.filename.endswith('.csv'):
        return "Invalid or missing CSV file", 400

    try:
        stream = io.StringIO(file.stream.read().decode("utf-8"))
        reader = csv.reader(stream)
        coords = []
        for row in reader:
            if len(row) == 3:
                try:
                    coords.append({'lat': float(row[1]), 'lng': float(row[2])})
                except ValueError:
                    continue
        return jsonify(coords)
    except Exception as e:
        return f"Error parsing CSV: {str(e)}", 500


@import_bp.route('/import/gpx', methods=['POST'])
def import_gpx():
    from xml.etree import ElementTree as ET

    file = request.files.get('file')
    if not file or not file.filename.endswith('.gpx'):
        return "Invalid or missing GPX file", 400

    try:
        tree = ET.parse(file)
        root = tree.getroot()

        namespace = {'default': 'http://www.topografix.com/GPX/1/1'}
        trkpts = root.findall('.//default:trkpt', namespaces=namespace)
        coords = []
        for pt in trkpts:
            lat = pt.get('lat')
            lon = pt.get('lon')
            try:
                coords.append({'lat': float(lat), 'lng': float(lon)})
            except (TypeError, ValueError):
                continue

        return jsonify(coords)
    except Exception as e:
        return f"Error parsing GPX: {str(e)}", 500
