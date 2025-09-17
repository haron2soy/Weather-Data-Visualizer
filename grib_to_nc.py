import xarray as xr

# Path to your GRIB file
grib_file = "G:\kmd\data\data4.grib"

# Path for the output NetCDF file
nc_file = "output_file.nc"

# Open GRIB file using xarray with cfgrib engine
ds = xr.open_dataset(grib_file, engine="cfgrib")

# Save as NetCDF
ds.to_netcdf(nc_file)

print(f"Converted {grib_file} to {nc_file} successfully!")