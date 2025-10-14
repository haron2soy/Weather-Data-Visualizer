import numpy as np
import folium
import json


def create_coverage_map(ds):
    """
    Create a Folium map with dynamic timeseries popups.
    Markers are created on-click via JS calling /get_timeseries.
    """
    lat_var = lon_var = None
    for c in ds.coords:
        cl = str(c).lower()
        if 'lat' in cl:
            lat_var = c
        elif 'lon' in cl:
            lon_var = c
    if not lat_var or not lon_var:
        return None

    lats = ds.coords[lat_var].values
    lons = ds.coords[lon_var].values

    center_lat, center_lon = float(np.mean(lats)), float(np.mean(lons))
    m = folium.Map(location=[center_lat, center_lon], zoom_start=6, max_bounds=True)

    # Draw dataset bounds
    bounds = [[float(np.min(lats)), float(np.min(lons))],
              [float(np.max(lats)), float(np.max(lons))]]
    folium.Rectangle(bounds=bounds, color="red", fill=False, popup="Data Coverage Area").add_to(m)

    # Prepare JS arrays
    lat_js = json.dumps(lats.tolist())
    lon_js = json.dumps(lons.tolist())

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
            var nearestLat = findClosest(lat_vals, e.latlng.lat);
            var nearestLon = findClosest(lon_vals, e.latlng.lng);

            if(window.selectedMarker){{
                window.selectedMarker.setLatLng([nearestLat, nearestLon]);
            }} else {{
                window.selectedMarker = L.marker([nearestLat, nearestLon])
                    .addTo(map)
                    .bindPopup("Loading data...").openPopup();
            }}

            // Fetch timeseries asynchronously
            fetch("/get_timeseries", {{
                method: "POST",
                headers: {{
                    "Content-Type": "application/json"
                }},
                body: JSON.stringify({{lat: nearestLat, lon: nearestLon}})
            }})
            .then(resp => resp.json())
            .then(data => {{
                if(data.success){{
                    var chartDiv = document.createElement("div");
                    chartDiv.innerHTML = data.charts_html || "No data available";
                    window.selectedMarker.setPopupContent(chartDiv);
                    window.selectedMarker.openPopup();
                }} else {{
                    window.selectedMarker.setPopupContent("Error: " + data.error);
                    window.selectedMarker.openPopup();
                }}
            }})
            .catch(err => {{
                window.selectedMarker.setPopupContent("Request failed");
                window.selectedMarker.openPopup();
                console.error(err);
            }});
        }});
    }});
    </script>
    """
    m.get_root().html.add_child(folium.Element(click_script))
    return m
