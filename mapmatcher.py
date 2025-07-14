# mapmatcher.py
import osmnx as ox
import numpy as np
from shapely.geometry import Point
from scipy.spatial import cKDTree

# Load road graph
G = ox.graph_from_place("Tripolis, Greece", network_type='drive')
nodes, edges = ox.graph_to_gdfs(G)
centers = edges.geometry.centroid
coords = np.array([[geom.y, geom.x] for geom in centers])
tree = cKDTree(coords)

def match_trace(coords):
    matched = []
    for lat, lon in coords:
        dist, idx = tree.query([lat, lon])
        if dist < 0.0005:  # Approx. 50m
            edge = edges.iloc[idx]
            nearest = edge.geometry.interpolate(edge.geometry.project(Point(lon, lat)))
            matched.append({'lat': nearest.y, 'lng': nearest.x})
        else:
            matched.append({'lat': lat, 'lng': lon})
    return matched
