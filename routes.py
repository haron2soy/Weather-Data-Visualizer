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
from docx import Document


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
@bp.route('/extract_file_info', methods=["POST"])
def extract_file_info():
    data = request.get_json()
    filepath = data.get('filepath') or current_dataset.get('filename')
    if not filepath or not os.path.exists(filepath):
        return jsonify({'success': False, 'error': 'File not found'})

    try:
        info = extract_file_info_logic(filepath)
        return jsonify(info)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


def extract_file_info_logic(filepath):
    try:
        ext = filepath.rsplit('.', 1)[1].lower()
        if ext == 'nc':
            with xr.open_dataset(filepath, chunks="auto", cache=False) as ds:
                info = _collect_dataset_info(ds)
        else:
            with xr.open_dataset(filepath, engine="cfgrib", chunks="auto", cache=False) as ds:
                info = _collect_dataset_info(ds)

        # we only keep metadata, not the open handle
        current_dataset["ds"] = None
        current_dataset["filename"] = filepath
        return {"success": True, **info}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _collect_dataset_info(ds):
    coords = {
        dim: {
            "min": float(ds.coords[dim].min().values),
            "max": float(ds.coords[dim].max().values),
            "size": int(ds.sizes[dim]),
        }
        for dim in ds.dims if dim in ds.coords
    }
    variables = {
        var: {
            "dims": list(ds[var].dims),
            "shape": [int(x) for x in ds[var].shape],
            "attrs": convert_numpy_types(dict(ds[var].attrs)),
        }
        for var in ds.data_vars
    }
    global_attrs = convert_numpy_types(dict(ds.attrs))
    return {"coords": coords, "variables": variables, "global_attrs": global_attrs}

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
    logging.info("there is an issue use here")
    file = request.files.get('file')
    if not file or not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Invalid file'})
    
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filepath = os.path.join(UPLOAD_FOLDER, secure_filename(file.filename))
    file.save(filepath)
    current_dataset['filename'] = filepath
    current_dataset['ds'] = None
    logging.info(f"current_dataset: {current_dataset}")

    processed = process_file(filepath)
    logging.info(f"Processed data: {processed}")
    return jsonify({'success': True, 'filepath': filepath, **processed})




@bp.route('/get_timeseries', methods=['POST'])
def get_timeseries():
    filepath = current_dataset.get('filename')
    if not filepath or not os.path.exists(filepath):
        return jsonify({'success': False, 'error': 'No dataset loaded'})

    data = request.get_json()
    lat, lon = data.get('lat'), data.get('lon')
    start = pd.to_datetime(data.get("startDate")) if data.get("startDate") else None
    end   = pd.to_datetime(data.get("endDate")) if data.get("endDate") else None

    try:
        ext = filepath.rsplit('.', 1)[1].lower()
        engine = None if ext == 'nc' else 'cfgrib'

        with xr.open_dataset(filepath, engine=engine, chunks='auto', cache=False) as ds:
            # your existing slicing & chart logic here
            lat_var = lon_var = time_var = None
            for c in ds.coords:
                cl = str(c).lower()
                if 'lat' in cl: lat_var = c
                elif 'lon' in cl: lon_var = c
                elif 'time' in cl or 'date' in cl: time_var = c
            if not lat_var or not lon_var:
                return jsonify({'success': False, 'error': 'Lat/Lon not found'})

            '''# slice time
            sliced_ds = ds
            if time_var and start is not None and end is not None:
                sliced_ds = ds.sel({time_var: slice(start, end)})

            point = sliced_ds.sel({lat_var: lat, lon_var: lon}, method='nearest')'''
            
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
                end_inclusive = end + pd.Timedelta(days=1)    
                ds = ds.sel({time_var: slice(start, end_inclusive)})

                
                #point = ds.sel({time_var: slice(start, end)})

            else:
                
                logging.info("No time slicing applied; using full dataset")
            
            point = ds.sel({lat_var: lat, lon_var: lon}, method='nearest')
            
            charts = {}
            for var in point.data_vars:
                var_data = point[var]
                if var_data.size == 0 or var_data.isnull().all():
                    continue
                units = var_data.attrs.get('units', '').lower()
                if any(u in units for u in ['k', 'kelvin']) and (var_data >= 100).all():
                    var_data = var_data - 273.15
                if time_var and time_var in var_data.dims:
                    times = var_data[time_var].values
                    values = var_data.values
                    if len(times) == 0 or len(values) == 0:
                        continue
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=times,
                        y=values,
                        mode='lines+markers',
                        name=var,
                        line=dict(color='#1f77b4', width=2),
                        marker=dict(size=6, symbol='circle'),
                        hovertemplate=f'{var}: %{{y:.2f}} {var_data.attrs.get("units", "")}<br>Time: %{{x}}'
                    ))
                    valid_values = values[~np.isnan(values)]
                    if valid_values.size == 0:
                        continue
                    ymin = float(np.nanmin(values))
                    ymax = float(np.nanmax(values))
                    pad = max(1.0, (ymax - ymin) * 0.1)  # Increased padding for better visibility
                    ymin = np.floor(ymin - pad)
                    ymax = np.ceil(ymax + pad)

                    # Horizontal grid lines
                    h_lines = []
                    for y in np.arange(ymin, ymax + 1, 1.0):
                        h_lines.append({
                            'type': 'line',
                            'xref': 'paper', 'x0': 0, 'x1': 1,
                            'yref': 'y', 'y0': y, 'y1': y,
                            'line': {'width': 0.1, 'color': 'rgba(200, 200, 200, 0.5)'}
                        })



                    # Enhanced layout
                    fig.update_layout(
                        title=dict(
                            text=f"Time Series of {var}",
                            x=0.5,
                            xanchor='center',
                            font=dict(size=16, color='#333333')
                        ),
                        xaxis_title="Time",
                        yaxis_title=f"{var} ({var_data.attrs.get('units', 'Value')})",
                        xaxis=dict(
                            showgrid=True,
                            gridcolor='rgba(200, 200, 200, 0.3)',
                            tickformat='%Y-%m-%d',
                            tickangle=45
                        ),
                        yaxis=dict(
                            showgrid=True,
                            gridcolor='rgba(200, 200, 200, 0.3)',
                            dtick=2,
                            range=[ymin, ymax],
                            zeroline=False,
                                title=dict(
                                    text=f"{var} ({var_data.attrs.get('units', 'Value')})",
                                    font=dict(size=14)
                                ),
                            #titlefont=dict(size=14),
                            tickfont=dict(size=12)
                        ),
                        shapes=h_lines,
                        margin=dict(t=50, b=70, l=70, r=30),
                        plot_bgcolor='white',
                        paper_bgcolor='white',
                        font=dict(family="Arial", size=12, color='#333333'),
                        hovermode='x unified',
                        showlegend=True
                    )

                    charts[var] = json.loads(plotly.utils.PlotlyJSONEncoder().encode(fig))

            return jsonify({
                'success': True,
                'charts': charts,
                'coordinates': {'lat': float(point[lat_var].values.item()), 'lon': float(point[lon_var].values.item())}
            })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# -----------------------------
# Download / export
# -----------------------------
@bp.route("/download_timeseries_csv", methods=["POST"])
def download_timeseries_csv():
    filepath = current_dataset.get("filename")
    if not filepath or not os.path.exists(filepath):
        return "No dataset loaded or file not found", 400

    data = request.get_json()
    lat, lon = data.get("lat"), data.get("lon")
    start = pd.to_datetime(data.get("startDate")) if data.get("startDate") else None
    
    #end = pd.to_datetime(data.get("endDate")) if data.get("endDate") else None
    end   = pd.to_datetime(data.get("endDate")) + pd.Timedelta(days=1) if data.get("endDate") else None
    filetype = data.get("filetype", "csv")
    keep_constant = data.get("keep_constant", True)  # Option to keep zero-only columns

    try:
        ext = filepath.rsplit('.', 1)[1].lower()
        engine = None if ext == 'nc' else 'cfgrib'

        with xr.open_dataset(filepath, engine=engine, chunks='auto', cache=False) as ds:
            lat_var = lon_var = time_var = None
            for c in ds.coords:
                cl = str(c).lower()
                if 'lat' in cl: lat_var = c
                elif 'lon' in cl: lon_var = c
                elif 'time' in cl or 'date' in cl: time_var = c
            if not lat_var or not lon_var:
                return "Lat/Lon not found", 400

            # Slice time range if provided
            '''sliced_ds = ds
            if time_var and start is not None and end is not None:
                sliced_ds = ds.sel({time_var: slice(start, end)})
                end = end - pd.Timedelta(days=1)
                if sliced_ds[time_var].size == 0:
                    return "No data in selected date range", 400'''
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
               # end_inclusive = end + pd.Timedelta(days=1)
                ds = ds.sel({time_var: slice(start, end)})

                
                #point = ds.sel({time_var: slice(start, end)})

            else:
                
                logging.info("No time slicing applied; using full dataset")
            
            point = ds.sel({lat_var: lat, lon_var: lon}, method='nearest')

            
            df = point.to_dataframe().reset_index()
            df = df.dropna(axis=1, how='all')
                # --- Track and filter constant-value columns ---
            
            dropped_columns = []
            if not keep_constant:
                # Identify columns with a single unique value
                for col in df.columns:
                    if df[col].nunique(dropna=False) == 1:
                        # Get the constant value (first non-NaN value, or NaN if all NaN)
                        constant_value = df[col].iloc[0] if not df[col].isna().all() else "NaN"
                        # Format as Variable_name(constant_value_it_has)
                        dropped_columns.append(f"{col}({constant_value})")
                # Drop constant columns
                constant_cols = [col for col in df.columns if df[col].nunique(dropna=False) == 1]
                df = df.drop(columns=constant_cols)

            
        # ==============================
        # 📤 EXPORT SECTION (moved out)
        # ==============================

        
        if filetype == "csv":
            # Generate CSV string from DataFrame
            csv_output = df.to_csv(index=False)
            # Prepend comment row with dropped columns (if any)

            # Build metadata as comment lines (like paragraphs in DOCX)
            header_lines = []
            header_lines.append("# Time Series Data")
            header_lines.append(f"# Grid Point: Lat {lat:.4f}, Lon {lon:.4f}")
            if start and end:
                header_lines.append(f"# Date Range: {start.date()} → {end.date()}")
            if dropped_columns:
                header_lines.append(f"# Dropped constant columns: {' '.join(dropped_columns)}")
            header_lines.append("")  # blank line before CSV table

            # Prepend metadata to CSV
            csv_output = "\n".join(header_lines) + "\n" + csv_output
            return Response(
                csv_output,
                mimetype="text/csv",
                headers={"Content-Disposition": "attachment;filename=timeseries.csv"}
            )
        
        elif filetype == "xlsx":
            # Create workbook
            wb = Workbook()
            ws = wb.active

            # Define styles
            title_style = NamedStyle(name="title_style")
            title_style.font = Font(size=14, bold=True, color="1F497D")  # dark blue

            heading_style = NamedStyle(name="heading_style")
            heading_style.font = Font(size=11, bold=True, color="1F497D")

            # Add metadata with styles
            ws.append(["Time Series Data"])
            ws["A1"].style = title_style

            ws.append([f"Grid Point: Lat {lat:.4f}, Lon {lon:.4f}"])
            ws["A2"].style = heading_style

            if start and end:
                ws.append([f"Date Range: {start.date()} → {end.date()}"])
                ws["A3"].style = heading_style

            if dropped_columns:
                ws.append([f"Dropped constant columns: {' '.join(dropped_columns)}"])
                ws[f"A{ws.max_row}"].style = heading_style

            ws.append([])  # blank row

            # Write table headers + data
            ws.append(df.columns.tolist())
            for row in df.itertuples(index=False, name=None):
                ws.append(row)

            # Set all columns to width 20
            for col in ws.columns:
                col_letter = col[0].column_letter
                ws.column_dimensions[col_letter].width = 20

            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            return send_file(
                buf,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name="timeseries.xlsx",
            )
            '''buf = io.StringIO()
            df.to_csv(buf, index=False)
            buf.seek(0)
            return send_file(
                io.BytesIO(buf.getvalue().encode("utf-8")),
                mimetype="text/csv",
                as_attachment=True,
                download_name="timeseries.csv",
            )'''


        elif filetype == "txt":
            # Generate plain text from DataFrame
            buf = io.StringIO()
            df.to_string(buf, index=False)  # Keeps nice table-like formatting
            buf.seek(0)

            # Add metadata (lat/lon, date range, dropped columns) at top
            header = []
            header.append("Time Series Data")
            header.append(f"Grid Point: Lat {lat:.4f}, Lon {lon:.4f}")
            if start and end:
                header.append(f"Date Range: {start.date()} → {end.date()}")
            if dropped_columns:
                header.append(f"Dropped constant columns: {', '.join(dropped_columns)}")
            header.append("")  # Blank line before table

            content = "\n".join(header) + "\n" + buf.getvalue()

            # Return as downloadable .txt file
            return Response(
                content,
                mimetype="text/plain",
                headers={"Content-Disposition": "attachment;filename=timeseries.txt"}
            )
        
        elif filetype == "docx":
            print("before trying:The filetype=docx is called")
            try:
                logging.info("inside try now. elif docx called")
                print("The filetype=docx is called")
                # Create a new Word document
                doc = Document()
                
                # Add metadata as paragraphs
                doc.add_heading("Time Series Data", level=1)
                doc.add_paragraph(f"Grid Point: Lat {lat:.4f}, Lon {lon:.4f}")
                if start and end:
                    doc.add_paragraph(f"Date Range: {start.date()} → {end.date()}")
                if dropped_columns:
                    doc.add_paragraph(f"Dropped constant columns: {', '.join(dropped_columns)}")
                doc.add_paragraph("")

                # Sanitize DataFrame (column names and values)
                df_clean = df.fillna("NaN").astype(str)
                df_clean.columns = [sanitize_text(col) for col in df_clean.columns]
                for col in df_clean.columns:
                    df_clean[col] = df_clean[col].apply(sanitize_text)
                logging.debug(f"DataFrame shape: {df_clean.shape}, columns: {list(df_clean.columns)}")

                # Limit rows to prevent large tables (optional)
                max_rows = 1000
                if len(df_clean) > max_rows:
                    logging.warning(f"DataFrame truncated to {max_rows} rows for DOCX")
                    df_clean = df_clean.head(max_rows)

                # Create a table
                table = doc.add_table(rows=1 + len(df_clean), cols=len(df_clean.columns))
                table.style = "Light Grid"  # Simpler style for better compatibility

                # Add column headers
                for j, col in enumerate(df_clean.columns):
                    cell = table.cell(0, j)
                    cell.text = col
                    # Set basic formatting to avoid Word issues
                    paragraph = cell.paragraphs[0]
                    run = paragraph.runs[0] if paragraph.runs else paragraph.add_run(col)
                    run.font.name = "Calibri"
                    run.font.size = None  # Default size

                # Add data rows
                for i, row in df_clean.iterrows():
                    for j, value in enumerate(row):
                        cell = table.cell(i + 1, j)
                        cell.text = value
                        # Set basic formatting
                        paragraph = cell.paragraphs[0]
                        run = paragraph.runs[0] if paragraph.runs else paragraph.add_run(value)
                        run.font.name = "Calibri"
                        run.font.size = None

                # Auto-fit table (instead of fixed widths)
                table.autofit = True

                # Save the document to a BytesIO buffer
                buf = io.BytesIO()
                doc.save(buf)
                buf.seek(0)
                docx_content = buf.getvalue()
                logging.debug(f"Generated DOCX file size: {len(docx_content)} bytes")
                buf.close()

                # Save a copy for debugging (optional, remove in production)
                with open("debug_timeseries.docx", "wb") as f:
                    f.write(docx_content)
                logging.debug("Saved debug_timeseries.docx for inspection")

                return Response(
                    docx_content,
                    mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": "attachment;filename=timeseries.docx"}
                )
            except Exception as e:
                logging.error(f"Error generating DOCX: {str(e)}")
                return "Error generating DOCX file", 500
        else:
            return "Unsupported filetype", 400
    except Exception as e:
                logging.error(f"Error: {str(e)}")
                return 500


def process_file(filepath):
    """
    Open the dataset, extract lats/lons, generate coverage map HTML.
    Returns dict with map_html, gridLats, gridLons.
    """
    import xarray as xr

    ext = filepath.rsplit('.', 1)[1].lower()
    engine = None if ext == 'nc' else 'cfgrib'

    with xr.open_dataset(filepath, engine=engine, chunks="auto", cache=False) as ds:
        # create map
        m = create_coverage_map(ds)
        map_html = m._repr_html_() if m else ""

        # extract coordinates
        lat_var = lon_var = None
        for c in ds.coords:
            cl = str(c).lower()
            if 'lat' in cl: lat_var = c
            elif 'lon' in cl: lon_var = c
        lats = ds.coords[lat_var].values.tolist() if lat_var else []
        lons = ds.coords[lon_var].values.tolist() if lon_var else []

    return {'map_html': map_html, 'gridLats': lats, 'gridLons': lons}
