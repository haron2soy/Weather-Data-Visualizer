from flask import Flask, request, render_template, jsonify, send_from_directory
import os
import json
import numpy as np
import xarray as xr
import pandas as pd
from werkzeug.utils import secure_filename
import folium
from branca.element import MacroElement
import plotly.graph_objs as go
import plotly.utils

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', 'dev-secret-key')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Store current NetCDF data globally (in production, use proper session management)
current_dataset = None
current_filename = None


def allowed_file(filename):
    """Check if file has allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'nc'


def convert_numpy_types(obj):
    """Recursively convert numpy types to Python native types for JSON serialization"""
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_numpy_types(item) for item in obj)
    else:
        return obj


def extract_netcdf_info(filepath):
    """Extract basic information from NetCDF file"""
    try:
        ds = xr.open_dataset(filepath)
        
        # Get coordinate information
        coords = {}
        for dim in ds.dims:
            if dim in ds.coords:
                coords[dim] = {
                    'min': float(ds.coords[dim].min().values),
                    'max': float(ds.coords[dim].max().values),
                    'size': int(ds.sizes[dim])
                }
        
        # Get variable information
        variables = {}
        for var in ds.data_vars:
            # Convert attributes to ensure JSON serializable
            attrs = dict(ds[var].attrs) if hasattr(ds[var], 'attrs') else {}
            safe_attrs = convert_numpy_types(attrs)
            
            variables[var] = {
                'dims': list(ds[var].dims),
                'shape': [int(x) for x in ds[var].shape],
                'attrs': safe_attrs
            }
        
        # Convert global attributes to ensure JSON serializable
        global_attrs = dict(ds.attrs) if hasattr(ds, 'attrs') else {}
        safe_global_attrs = convert_numpy_types(global_attrs)
        
        return {
            'coords': coords,
            'variables': variables,
            'global_attrs': safe_global_attrs,
            'success': True
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def create_coverage_map(ds):
    """Create a folium map showing the data coverage area"""
    # Find latitude and longitude coordinates
    lat_var = None
    lon_var = None
    
    for coord in ds.coords:
        coord_lower = str(coord).lower()
        if 'lat' in coord_lower:
            lat_var = coord
        elif 'lon' in coord_lower:
            lon_var = coord
    
    if not lat_var or not lon_var:
        return None
    
    lats = ds.coords[lat_var].values
    lons = ds.coords[lon_var].values
    
    # Create map centered on the data
    center_lat = float(np.mean(lats))
    center_lon = float(np.mean(lons))
    
    # Create the map
    m = folium.Map(location=[center_lat, center_lon], zoom_start=6)
    
    # Add a rectangle showing the data bounds
    bounds = [
        [float(np.min(lats)), float(np.min(lons))],
        [float(np.max(lats)), float(np.max(lons))]
    ]
    
    folium.Rectangle(
        bounds=bounds,
        color='red',
        fill=True,
        fillOpacity=0.2,
        popup='Data Coverage Area'
    ).add_to(m)
    
    # Add clickable markers for each grid point
    for lat in lats:
        for lon in lons:
            marker = folium.CircleMarker(
                location=[float(lat), float(lon)],
                radius=8,
                popup=f'Grid Point<br>Lat: {float(lat):.4f}<br>Lon: {float(lon):.4f}<br>Click for time series',
                color='blue',
                fill=True,
                fillColor='lightblue',
                fillOpacity=0.8,
                weight=2
            )
            marker.add_to(m)
            
            # Add hover tooltip
            marker.add_child(folium.Tooltip(f'Lat: {float(lat):.4f}, Lon: {float(lon):.4f}'))
    
    # Add click handler for point selection with grid snapping
    # Convert coordinate arrays to lists for JavaScript
    lat_values = [float(lat) for lat in lats]
    lon_values = [float(lon) for lon in lons]
    
    click_script = f"""
    <script>
    var mapObj = {m.get_name()};
    var gridLats = {lat_values};
    var gridLons = {lon_values};
    
    // Function to find nearest grid point
    function findNearestGridPoint(clickLat, clickLon) {{
        let minDist = Infinity;
        let nearestLat = clickLat;
        let nearestLon = clickLon;
        
        for (let lat of gridLats) {{
            for (let lon of gridLons) {{
                let dist = Math.sqrt(Math.pow(lat - clickLat, 2) + Math.pow(lon - clickLon, 2));
                if (dist < minDist) {{
                    minDist = dist;
                    nearestLat = lat;
                    nearestLon = lon;
                }}
            }}
        }}
        return {{lat: nearestLat, lon: nearestLon}};
    }}
    
    mapObj.on('click', function(e) {{
        const clickLat = e.latlng.lat;
        const clickLng = e.latlng.lng;
        
        // Find nearest grid point
        const nearest = findNearestGridPoint(clickLat, clickLng);
        
        // Remove previous selection markers
        mapObj.eachLayer(function(layer) {{
            if (layer.options && layer.options.className === 'selected-point') {{
                mapObj.removeLayer(layer);
            }}
        }});
        
        // Add selection marker at nearest grid point
        L.circleMarker([nearest.lat, nearest.lon], {{
            radius: 12,
            color: 'red',
            fillColor: 'yellow',
            fillOpacity: 0.9,
            weight: 3,
            className: 'selected-point'
        }}).addTo(mapObj)
          .bindPopup('Selected Grid Point<br>Lat: ' + nearest.lat.toFixed(4) + '<br>Lon: ' + nearest.lon.toFixed(4))
          .openPopup();
        
        console.log('Grid point selected:', nearest.lat, nearest.lon);
        
        // Send coordinates to Flask app
        fetch('/get_timeseries', {{
            method: 'POST',
            headers: {{
                'Content-Type': 'application/json',
            }},
            body: JSON.stringify({{lat: nearest.lat, lon: nearest.lon}})
        }})
        .then(response => response.json())
        .then(data => {{
            console.log('Time series response:', data);
            if (data.success) {{
                if (typeof window.updateCharts === 'function') {{
                    window.updateCharts(data.charts);
                }}
                // Update selected coordinates display
                const coordsEl = document.getElementById('selectedCoords');
                if (coordsEl) {{
                    coordsEl.textContent = 'Selected point: ' + nearest.lat.toFixed(4) + ', ' + nearest.lon.toFixed(4);
                }}
            }} else {{
                console.error('Time series error:', data.error);
                alert('Error generating time series: ' + data.error);
            }}
        }}).catch(error => {{
            console.error('Error fetching time series:', error);
            alert('Network error: ' + error.message);
        }});
    }});
    </script>
    """
    
    # Create MacroElement to inject the script
    from branca.element import Template
    macro = MacroElement()
    macro._template = Template(click_script)
    m.get_root().add_child(macro)
    
    return m


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle NetCDF file upload"""
    global current_dataset, current_filename
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})
    
    if file and file.filename and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Extract NetCDF information
        info = extract_netcdf_info(filepath)
        if not info['success']:
            return jsonify({'success': False, 'error': info['error']})
        
        # Load dataset
        try:
            current_dataset = xr.open_dataset(filepath)
            current_filename = filename
            
            # Create coverage map
            coverage_map = create_coverage_map(current_dataset)
            if coverage_map:
                map_html = coverage_map._repr_html_()
            else:
                map_html = None
            
            return jsonify({
                'success': True,
                'info': info,
                'map_html': map_html
            })
        except Exception as e:
            return jsonify({'success': False, 'error': f'Error loading dataset: {str(e)}'})
    
    return jsonify({'success': False, 'error': 'Invalid file type. Please upload a .nc file'})


@app.route('/get_timeseries', methods=['POST'])
def get_timeseries():
    """Get time series data for selected coordinates"""
    global current_dataset
    
    if current_dataset is None:
        return jsonify({'success': False, 'error': 'No dataset loaded'})
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No JSON data provided'})
    
    target_lat = data.get('lat')
    target_lon = data.get('lon')
    
    if target_lat is None or target_lon is None:
        return jsonify({'success': False, 'error': 'Coordinates not provided'})
    
    try:
        # Find the nearest grid point
        ds = current_dataset
        
        # Find latitude and longitude variable names
        lat_var = None
        lon_var = None
        time_var = None
        
        for coord in ds.coords:
            coord_lower = str(coord).lower()
            if 'lat' in coord_lower:
                lat_var = coord
            elif 'lon' in coord_lower:
                lon_var = coord
            elif 'time' in coord_lower:
                time_var = coord
        
        if not lat_var or not lon_var:
            return jsonify({'success': False, 'error': 'Could not find latitude/longitude coordinates'})
        
        # Find nearest point
        point = ds.sel({lat_var: target_lat, lon_var: target_lon}, method='nearest')
        
        charts = {}
        
        # Create time series for each data variable
        for var_name in ds.data_vars:
            var_data = point[var_name]
            
            # Skip if variable doesn't have time dimension
            if time_var and time_var in var_data.dims:
                # Extract time series data
                times = var_data[time_var].values
                values = var_data.values
                
                # Create plotly chart
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=times,
                    y=values,
                    mode='lines+markers',
                    name=var_name,
                    line=dict(width=2)
                ))
                
                var_title = str(var_name).title() if hasattr(var_name, 'title') else str(var_name).capitalize()
                fig.update_layout(
                    title=f'{var_title} Time Series',
                    xaxis_title='Time',
                    yaxis_title=f'{var_name} ({var_data.attrs.get("units", "")})' if hasattr(var_data, 'attrs') else str(var_name),
                    template='plotly_white'
                )
                
                charts[var_name] = json.loads(plotly.utils.PlotlyJSONEncoder().encode(fig))
        
        return jsonify({
            'success': True,
            'charts': charts,
            'coordinates': {'lat': float(point[lat_var].values), 'lon': float(point[lon_var].values)}
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error processing coordinates: {str(e)}'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)