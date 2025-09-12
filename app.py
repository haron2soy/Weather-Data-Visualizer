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
            variables[var] = {
                'dims': list(ds[var].dims),
                'shape': [int(x) for x in ds[var].shape],
                'attrs': dict(ds[var].attrs) if hasattr(ds[var], 'attrs') else {}
            }
        
        return {
            'coords': coords,
            'variables': variables,
            'global_attrs': dict(ds.attrs) if hasattr(ds, 'attrs') else {},
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
    
    # Add click handler for point selection
    # Add click handler using MacroElement to properly access the map object
    click_script = f"""
    <script>
    var mapObj = {m.get_name()};
    mapObj.on('click', function(e) {{
        const lat = e.latlng.lat;
        const lng = e.latlng.lng;
        
        // Remove previous markers
        mapObj.eachLayer(function(layer) {{
            if (layer instanceof L.Marker) {{
                mapObj.removeLayer(layer);
            }}
        }});
        
        // Add new marker
        L.marker([lat, lng]).addTo(mapObj)
            .bindPopup('Selected Point<br>Lat: ' + lat.toFixed(4) + '<br>Lon: ' + lng.toFixed(4));
        
        // Send coordinates to Flask app
        fetch('/get_timeseries', {{
            method: 'POST',
            headers: {{
                'Content-Type': 'application/json',
            }},
            body: JSON.stringify({{lat: lat, lon: lng}})
        }})
        .then(response => response.json())
        .then(data => {{
            if (data.success) {{
                if (typeof window.updateCharts === 'function') {{
                    window.updateCharts(data.charts);
                }}
                // Update selected coordinates display
                const coordsEl = document.getElementById('selectedCoords');
                if (coordsEl) {{
                    coordsEl.textContent = 'Selected point: ' + lat.toFixed(4) + ', ' + lng.toFixed(4);
                }}
            }}
        }}).catch(error => {{
            console.error('Error fetching time series:', error);
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