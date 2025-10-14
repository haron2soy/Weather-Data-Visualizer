import os
import numpy as np
import netCDF4 as nc
from wrf import getvar, latlon_coords, ALL_TIMES
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")
import io
import base64

# ✅ Universal loader
def load_variable_with_coords(filepath, var_name="T2"):
    ncfile = nc.Dataset(filepath)

    wrf_lat_names = {"XLAT", "XLAT_M"}
    wrf_lon_names = {"XLONG", "XLONG_M"}

    has_wrf_lat = any(name in ncfile.variables for name in wrf_lat_names)
    has_wrf_lon = any(name in ncfile.variables for name in wrf_lon_names)

    is_wrf_file = has_wrf_lat and has_wrf_lon

    if is_wrf_file:
        print("Using getvar() — WRF-style dataset detected.")
        data = getvar(ncfile, var_name, timeidx=ALL_TIMES)
        lats, lons = latlon_coords(data)
        data_c = np.array(data) - 273.15  # Kelvin → Celsius
        return data_c, np.array(lats), np.array(lons)

    # --- Non-WRF NetCDF
    print("Using direct access — Generic NetCDF dataset detected.")
    temp_candidates = ["T2", "T_2M", "TEMP2M", "T2M"]

    var_name = None
    nc_vars_lower = {v.lower(): v for v in ncfile.variables.keys()}  # map lowercase -> actual name

    for candidate in temp_candidates:
        candidate_lower = candidate.lower()
        if candidate_lower in nc_vars_lower:
            var_name = nc_vars_lower[candidate_lower]
            break

    if var_name is None:
        raise ValueError("No 2m temperature variable found in file")

    print(f"Using variable: {var_name}")

            
    data = ncfile.variables[var_name][:]
    lat_name = next((n for n in ["lat", "latitude", "y"] if n in ncfile.variables), None)
    lon_name = next((n for n in ["lon", "longitude", "x"] if n in ncfile.variables), None)

    if lat_name is None or lon_name is None:
        raise ValueError("Latitude or longitude variables not found")

    lats = ncfile.variables[lat_name][:]
    lons = ncfile.variables[lon_name][:]

    if np.nanmean(data) > 100:  # likely Kelvin
        data = data - 273.15

    # Ensure shapes are (time, lat, lon)
    if data.ndim == 2:
        data = data[np.newaxis, :, :]

    return data, lats, lons

# ✅ Load file
filepath = "../../kmdwork/data/data_stream-enda_stepType-instant.nc"
temp_c_all, lats, lons = load_variable_with_coords(filepath, "T2")
print("Loaded data shape:", temp_c_all.shape)

# ✅ Create Folium map centered on Kenya
m = folium.Map(location=[0.5, 37.0], zoom_start=6, tiles="OpenStreetMap")

# ✅ Optional: Kenya county shapefile
shapefile_path  = r"../gadm41_KEN_shp/gadm41_KEN_1.shp"
if os.path.exists(shapefile_path ):
    gdf = gpd.read_file(shapefile_path)  # Read shapefile
    folium.GeoJson(gdf, name="Kenya Counties").add_to(m)
else:
    print("kenya shapefile not found.")
# ✅ Popup generator
def generate_timeseries_popup(lat, lon, timeseries):
    plt.figure(figsize=(4, 3))
    plt.plot(timeseries, marker='o')
    plt.title(f"Temperature Timeseries\nLat: {lat:.2f}, Lon: {lon:.2f}")
    plt.ylabel("°C")
    plt.xlabel("Time Index")
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    html = f'<img src="data:image/png;base64,{encoded}">'
    return html

# ✅ Add markers
marker_cluster = MarkerCluster().add_to(m)


# ✅ Handle 1D lat/lon (common in non-WRF NetCDF)
if lats.ndim == 1 and lons.ndim == 1:
    for i in range(len(lats)):
        for j in range(len(lons)):
           # lat = lats[i]
            #lon = lons[j]
            try:
                # Get actual lat/lon values depending on dimensionality
                if lats.ndim == 1 and lons.ndim == 1:
                    lat_val = float(lats[i])
                    lon_val = float(lons[j])
                    timeseries = temp_c_all[:, i, j]  # Confirm this matches your data shape
                else:
                    lat_val = float(lats[i, j])
                    lon_val = float(lons[i, j])
                    timeseries = temp_c_all[:, i, j]

                popup_html = generate_timeseries_popup(lat_val, lon_val, timeseries)

                folium.Marker(
                    location=[lat_val, lon_val],
                    popup=folium.Popup(popup_html, max_width=300),
                    icon=folium.Icon(icon_size=(20, 20), icon='info-sign')  # smaller icon
                ).add_to(marker_cluster)

            except Exception as e:
                print(f"Skipped point dm1 ({i},{j}): {e}")


# ✅ Handle 2D lat/lon (WRF-style)
elif lats.ndim == 2 and lons.ndim == 2:
    for i in range(0, lats.shape[0], 5):
        for j in range(0, lats.shape[1], 5):
            lat = lats[i, j]
            lon = lons[i, j]
            try:
                popup_html = generate_timeseries_popup(i, j)
                folium.Marker(
                    location=[lat, lon],
                    popup=folium.Popup(popup_html, max_width=300)
                ).add_to(marker_cluster)
            except Exception as e:
                print(f"Skipped point dm2 ({i},{j}): {e}")

else:
    raise ValueError(f"Unexpected lat/lon shapes: {lats.shape}, {lons.shape}")


# ✅ Save output
m.save("kenya_temperature_map.html")
print("Map saved as kenya_temperature_map.html")
