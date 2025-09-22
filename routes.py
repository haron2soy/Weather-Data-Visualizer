from flask import Blueprint, render_template, request, jsonify, send_file, Response
import os
import io
import logging
import numpy as np
import pandas as pd
import xarray as xr
import folium
from werkzeug.utils import secure_filename
from openpyxl import Workbook
from openpyxl.styles import NamedStyle, Font
import json
import plotly.graph_objs as go
import plotly.utils
import re

bp = Blueprint('main', __name__)
UPLOAD_FOLDER = 'uploads'
current_dataset = {'ds': None, 'filename': None}

# -----------------------------
# Helpers
# -----------------------------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ['nc', 'grib', 'grb']

def convert_numpy_types(obj):
    if isinstance(obj, np.integer): return int(obj)
    elif isinstance(obj, np.floating): return float(obj)
    elif isinstance(obj, np.ndarray): return obj.tolist()
    elif isinstance(obj, dict): return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list): return [convert_numpy_types(i) for i in obj]
    elif isinstance(obj, tuple): return tuple(convert_numpy_types(i) for i in obj)
    else: return obj

def sanitize_text(text):
    if text is None or pd.isna(text): return "NaN"
    text = str(text)
    text = re.sub(r'[^\x20-\x7E\u00A0-\uFFFF]', '', text)
    return text

# -----------------------------
# Extract basic dataset info
# -----------------------------
@bp.route('/extract_file_info', methods = ["POST"])
def extract_file_info(filepath:None):

    print("typeof filepath passed: ", type(filepath), filepath)
    print("@calling extract_file")
    if filepath==None:
        print("filepath not provided")
        data = request.get_json()
        filepath = data.get('filepath')
    try:
        

        ext = filepath.rsplit('.',1)[1].lower()
        if ext == 'nc':
            ds = xr.open_dataset(filepath, chunks='auto', cache=False)
        else:
            ds = xr.open_dataset(filepath, engine='cfgrib', chunks='auto', cache=False)
        current_dataset['ds'] = ds
        current_dataset['filename'] = os.path.basename(filepath)

        # Coordinates
        coords = {
            dim: {
                'min': float(ds.coords[dim].min().values),
                'max': float(ds.coords[dim].max().values),
                'size': int(ds.sizes[dim]),
            }
            for dim in ds.dims if dim in ds.coords
        }

        variables = {
            var: {
                'dims': list(ds[var].dims),
                'shape': [int(x) for x in ds[var].shape],
                'attrs': convert_numpy_types(dict(ds[var].attrs)),
            }
            for var in ds.data_vars
        }

        global_attrs = convert_numpy_types(dict(ds.attrs))

        return jsonify({'coords': coords, 'variables': variables, 'global_attrs': global_attrs, 'success': True})
    except Exception as e:
        return jsonify( {'success': False, 'error': str(e)})

# -----------------------------
# Map creation (optimized)
# -----------------------------
def create_coverage_map(ds, max_markers=500):
    lat_var = lon_var = None
    for c in ds.coords:
        cl = str(c).lower()
        if 'lat' in cl: lat_var = c
        elif 'lon' in cl: lon_var = c
    if not lat_var or not lon_var:
        return None

    lats = ds.coords[lat_var].values
    lons = ds.coords[lon_var].values

    '''    # Subsample points for faster map
    total_points = len(lats) * len(lons)
    step = max(1, int(np.sqrt(total_points / max_markers)))
    lats_sub = lats[::step]
    lons_sub = lons[::step]'''

    center_lat, center_lon = float(np.mean(lats)), float(np.mean(lons))
    m = folium.Map(location=[center_lat, center_lon], zoom_start=6, max_bounds=True)

    # Rectangle bounds for dataset
    bounds = [[float(np.min(lats)), float(np.min(lons))],
              [float(np.max(lats)), float(np.max(lons))]]
    folium.Rectangle(
        bounds=bounds, 
        color="red", 
        fill=False, 
        popup='Data Coverage Area')\
        .add_to(m)

    # Only add limited markers
    for lat in lats:
        for lon in lons:
            folium.CircleMarker(
                location=[float(lat), 
                float(lon)], 
                radius=2, 
                color=None,
                fill=True,
                fill_color=None, 
                fill_opacity=0,
                weight=0.5,
                tooltip=f"Click: Lat {lat:.4f}, Lon: {lon:.4f}",)\
            .add_to(m)

    # Snap click to nearest original lat/lon
    lat_js = "[" + ",".join(map(str, lats)) + "]"
    lon_js = "[" + ",".join(map(str, lons)) + "]"
    click_script = f"""
    <script>
    window.addEventListener("load", function() {{
        var map = {m.get_name()};
        var lat_vals = {lat_js};
        var lon_vals = {lon_js};
        function findClosest(arr, val) {{
            return arr.reduce(function(prev,curr) {{
                return (Math.abs(curr-val)<Math.abs(prev-val)?curr:prev);
            }});
        }}
        map.on('click', function(e) {{
            var nearestLat=findClosest(lat_vals,e.latlng.lat);
            var nearestLon=findClosest(lon_vals,e.latlng.lng);
            if(window.parent && typeof window.parent.handleGridClick==='function'){{
                window.parent.handleGridClick(nearestLat,nearestLon);
            }}
        }});
    }});
    </script>
    """
    m.get_root().html.add_child(folium.Element(click_script))
    return m

# -----------------------------
# Routes
# -----------------------------
@bp.route('/')
def index():
    return render_template('index.html')

@bp.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Invalid file type. Upload .nc/.grib only'})

        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        if os.path.exists(filepath):
            os.remove(filepath)
            file.save(filepath)

        info = extract_file_info(filepath)
        if not info['success']:
            print("subscriptable something here")
            return jsonify({'success': False, 'error': info['error']})

        map_obj = create_coverage_map(current_dataset['ds'])
        map_html = map_obj._repr_html_() if map_obj else None
        print("2subscriptable something here")
        return jsonify({'success': True, 'filepath': filepath, 'map_html': map_html})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/get_timeseries', methods=['POST'])
def get_timeseries():
    ds = current_dataset.get('ds')
    if ds is None:
        return jsonify({'success': False, 'error': 'No dataset loaded'})
    
    data = request.get_json()
    lat, lon = data.get('lat'), data.get('lon')
    start = pd.to_datetime(data.get("startDate")) if data.get("startDate") else None
    end   = pd.to_datetime(data.get("endDate")) if data.get("endDate") else None
    if lat is None or lon is None:
        return jsonify({'success': False, 'error': 'Coordinates not provided'})

    lat_var = lon_var = time_var = None
    for c in ds.coords:
        cl = str(c).lower()
        if 'lat' in cl: lat_var = c
        elif 'lon' in cl: lon_var = c
        elif 'time' in cl or 'date' in cl: time_var = c

    if not lat_var or not lon_var:
        return jsonify({'success': False, 'error': 'Lat/Lon not found'})

    # Slice time early (lazy)
    sliced_ds = ds
    '''if time_var and start and end:
        sliced_ds = ds.sel({time_var: slice(start, end)})'''
        # --- Slice dataset if time coord + range given ---
    if time_var and start is not None and end is not None:
        # Match tz-awareness
        if pd.api.types.is_datetime64tz_dtype(ds[time_var]):
            if start.tzinfo is None:
                start = start.tz_localize(ds[time_var].dt.tz)
            if end.tzinfo is None:
                end = end.tz_localize(ds[time_var].dt.tz)
        else:
            if start.tzinfo is not None:
                start = start.tz_convert(None)
            if end.tzinfo is not None:
                end = end.tz_convert(None)
  
        ds = ds.sel({time_var: slice(start, end)})

    point = sliced_ds.sel({lat_var: lat, lon_var: lon}, method='nearest')
    charts = {}
    for var in point.data_vars:
        var_data = point[var]
        if var_data.size == 0 or var_data.isnull().all():
            print(f"Skipping {var} (empty or all NaN)")
            continue
        units = var_data.attrs.get('units', '').lower()
        if any(u in units for u in ["k", "kelvin"]) and (var_data >= 100).all():
            var_data = var_data - 273.15
        if time_var and time_var in var_data.dims:
            times = var_data[time_var].values
            values = var_data.values
            if len(times) == 0 or len(values) == 0:
                continue
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=times, y=values, mode='lines+markers', name=var))
            fig.update_layout(title=f"Time Series of {var}", xaxis_title='Time', yaxis_title=var_data.attrs.get('units','Value'))
            charts[var] = json.loads(plotly.utils.PlotlyJSONEncoder().encode(fig))

    return jsonify({'success': True, 'charts': charts, 'coordinates': {'lat': float(point[lat_var].values), 'lon': float(point[lon_var].values)}})

# -----------------------------
# Download / export
# -----------------------------
@bp.route("/download_timeseries_csv", methods=["POST"])
def download_timeseries_csv():
    ds = current_dataset.get("ds")
    if ds is None:
        return "No dataset loaded", 400
    data = request.get_json()
    lat, lon = data.get("lat"), data.get("lon")
    start = pd.to_datetime(data.get("startDate")) if data.get("startDate") else None
    end   = pd.to_datetime(data.get("endDate")) if data.get("endDate") else None
    filetype = data.get("filetype", "csv")
    
    lat_var = lon_var = time_var = None
    for c in ds.coords:
        cl = str(c).lower()
        if 'lat' in cl: lat_var = c
        elif 'lon' in cl: lon_var = c
        elif 'time' in cl or 'date' in cl: time_var = c

    sliced_ds = ds
    '''if time_var and start and end:
        sliced_ds = ds.sel({time_var: slice(start, end)})'''
    
    # --- Slice time range if provided ---
    if time_var and start is not None and end is not None:
        ds = ds.sel({time_var: slice(start, end)})
        end = end - pd.Timedelta(days=1)
        if ds[time_var].size == 0:
            return "No data in selected date range", 400

    point = sliced_ds.sel({lat_var: lat, lon_var: lon}, method='nearest')
    df = point.to_dataframe().reset_index()
    df = df.dropna(axis=1, how='all')

    # Export logic
    if filetype == "csv":
        csv_output = df.to_csv(index=False)
        return Response(csv_output, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=timeseries.csv"})
    elif filetype == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.append(df.columns.tolist())
        for row in df.itertuples(index=False, name=None):
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name="timeseries.xlsx")
    elif filetype == "txt":
        buf = io.StringIO()
        buf.write(df.to_string(index=False))
        buf.seek(0)
        return Response(buf.getvalue(), mimetype="text/plain", headers={"Content-Disposition": "attachment;filename=timeseries.txt"})
    else:
        return "Unsupported filetype", 400
