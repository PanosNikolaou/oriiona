# exports.py
import os
from flask import Blueprint, request, send_file, Response
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

export_bp = Blueprint('exports', __name__)

@export_bp.route('/export/csv')
def export_csv():
    date = request.args.get('date') or datetime.utcnow().strftime('%Y-%m-%d')
    session_files = sorted([f for f in os.listdir('.') if f.startswith(f'gps_log_{date}_') and f.endswith('.txt')])
    if not session_files:
        return "No data", 404

    merged = '\n'.join(open(f, 'r').read() for f in session_files)
    tmp_file = f'tmp_export_{date}.csv'
    with open(tmp_file, 'w') as f:
        f.write(merged)

    return send_file(tmp_file, as_attachment=True, download_name=f'gps_{date}.csv')


@export_bp.route('/export/gpx')
def export_gpx():
    date = request.args.get('date') or datetime.utcnow().strftime('%Y-%m-%d')
    session_files = sorted([f for f in os.listdir('.') if f.startswith(f'gps_log_{date}_') and f.endswith('.txt')])
    if not session_files:
        return "No data", 404

    gpx = Element('gpx', version="1.1", creator="Oriiona", xmlns="http://www.topografix.com/GPX/1/1")
    trk = SubElement(gpx, 'trk')
    trkseg = SubElement(trk, 'trkseg')

    for log_file in session_files:
        with open(log_file) as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) == 3:
                    SubElement(trkseg, 'trkpt', lat=parts[1], lon=parts[2])

    xml_str = minidom.parseString(tostring(gpx)).toprettyxml(indent="  ")
    return Response(xml_str, mimetype='application/gpx+xml')
