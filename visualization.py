from netCDF4 import Dataset
from wrf import getvar, to_np, latlon_coords
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.io.shapereader import Reader
from cartopy.feature import ShapelyFeature
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
import geopandas as gpd
import numpy as np
import os

ncfile = Dataset("wrfout_d01_2025-07-16_06_00_00.nc")
# Get temperature data
t2 = getvar(ncfile, "T2", timeidx=0)  # temperature at 2 meters
lats, lons = latlon_coords(t2)
temp_c = to_np(t2) - 273.15  # convert Kelvin to Celsius

# Plot setup
plt.figure(figsize=(10, 8))
ax = plt.axes(projection=ccrs.PlateCarree())
# Focus map on Kenya (approx. bounding box)
ax.set_extent([33.5, 42.0, -5.0, 5.5], crs=ccrs.PlateCarree())

# Plot temperature data
contour = plt.contourf(to_np(lons), to_np(lats), temp_c, 
                      levels=10, cmap="viridis", transform=ccrs.PlateCarree())
# --- Add Gridlines ---
gl = ax.gridlines(
    crs=ccrs.PlateCarree(),
    draw_labels=True,  # Show latitude/longitude labels
    linewidth=0.5,     # Gridline width
    color='black',      # Gridline color
    alpha=0.5,         # Transparency
    linestyle='--'     # Dashed lines
)

# Customize grid labels
gl.top_labels = False    # Turn off top labels
gl.right_labels = False  # Turn off right labels
gl.xformatter = LONGITUDE_FORMATTER  # Format longitude labels
gl.yformatter = LATITUDE_FORMATTER   # Format latitude labels
gl.xlabel_style = {'size': 10}       # Longitude label font size
gl.ylabel_style = {'size': 10}       # Latitude label font size

# Add base map features
ax.coastlines(linewidth=0.8)
ax.add_feature(cfeature.BORDERS, linewidth=1.0, edgecolor='black')

# Add Kenya county borders from shapefile
shapefile_path = r"D:\kmd\Data\gadm41_KEN.shp"

if os.path.exists(shapefile_path):
    try:
        counties = ShapelyFeature(
            Reader(shapefile_path).geometries(),
            ccrs.PlateCarree(),
            edgecolor='black',
            facecolor='none',
            linewidth=0.6
        )
        ax.add_feature(counties)
    except Exception as e:
        print(f"Could not load county borders: {e}")
else:
    print(f"Shapefile not found at: {shapefile_path}")

# Add title and colorbar
ax.set_title("Temperature Distribution Over Kenya at 2m Height",
            fontsize=14, pad=20)
cbar = plt.colorbar(contour, ax=ax, shrink=0.7, pad=0.05)
cbar.set_label("Temperature (°C)", fontsize=12)

# Adjust layout and show plot
plt.tight_layout()
plt.show()