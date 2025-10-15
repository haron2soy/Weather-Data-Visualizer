import os
import json
import folium

ALLOWED_SHAPE_EXTENSIONS = ['shp', 'zip']

def allowed_shapefile(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_SHAPE_EXTENSIONS



def add_geojson_to_map(m, geojson_path):
    try:
        with open(geojson_path, 'r', encoding='utf-8') as file:
            data = json.load(file)

        folium.GeoJson(
            data,
            name=os.path.basename(geojson_path),
            style_function=lambda x: {
                "fillOpacity": 0.0,
                "weight": 2,
                "color": "green",
                "weight": 1,
            }
        ).add_to(m)

        # Make the layer togglable
        folium.LayerControl().add_to(m)
        print(f"Loaded GeoJSON: {geojson_path}")
    except Exception as e:
        print(f"Error loading GeoJSON {geojson_path}: {e}")
