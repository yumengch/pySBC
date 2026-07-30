from pathlib import Path

import numpy as np
import xarray as xr

import config

class LandSeaMask(object):
    """ Generate ERA5 Land Sea Mask for NEMO  """

    def __init__(self):
        canonical_path = Path(config.raw_path) / 'ERA5_LSM_20040101.nc'
        # get_era5.py historically omitted the separator before this filename.
        legacy_path = Path(str(config.raw_path) + 'ERA5_LSM_20040101.nc')
        self.input_path = (
            legacy_path if legacy_path.exists() and not canonical_path.exists()
            else canonical_path
        )
        self.output_path = Path(config.processed_path) / 'ERA5_LSM.nc'

        self.cut_off = 0.5  # flooding cell fraction
        self.east = config.east
        self.west = config.west
        self.north = config.north
        self.south = config.south

    def format_lat_lon(self, da):
        """Format the downloaded grid like the processed NEMO forcing."""

        # ERA5 latitude is north-to-south; NEMO forcing is south-to-north.
        if da.longitude.values[0] > da.longitude.values[-1]:
            da = da.isel(longitude=slice(None, None, -1))
        if da.latitude.values[0] > da.latitude.values[-1]:
            da = da.isel(latitude=slice(None, None, -1))
        # mesh lat and lon
        mlon, mlat = np.meshgrid(da.longitude, da.latitude)
        lon_attrs = {'long_name':'Longitude', 'units':'degree_east',
                     'standard_name':'longitude'}
        lat_attrs = {'long_name':'Latitude', 'units':'degree_north',
                     'standard_name':'latitude'}
        mlon = xr.DataArray(mlon, dims=['nLat','nLon'], attrs=lon_attrs)
        mlat = xr.DataArray(mlat, dims=['nLat','nLon'], attrs=lat_attrs)
      
        # assign NEMO forcing dimensions and two-dimensional coordinates
        da = da.drop_vars(['longitude','latitude'])
        da = da.rename({'longitude':'nLon', 'latitude':'nLat'})
        da = da.assign_coords({'lon':mlon, 'lat':mlat})
      
        return da

    def gen_land_sea_mask(self):
        """Create one shared NEMO mask from the ERA5 ensemble product."""

        if not self.input_path.exists():
            raise FileNotFoundError(f"ERA5 land-sea mask not found: {self.input_path}")
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        da = xr.open_dataarray(self.input_path)

        for time_dim in ('valid_time', 'time'):
            if time_dim in da.dims:
                da = da.isel({time_dim: 0}, drop=True)
                break
        if 'expver' in da.coords:
            da = da.drop_vars('expver')

        source_numbers = []
        if 'number' in da.dims:
            source_numbers = [int(value) for value in da.number.values]
            reference = da.isel(number=0, drop=True)
            for index in range(1, da.sizes['number']):
                candidate = da.isel(number=index, drop=True)
                if not np.array_equal(
                        reference.values, candidate.values, equal_nan=True):
                    raise ValueError(
                        "ERA5 land-sea masks differ between ensemble members"
                    )
            da = reference
        elif 'number' in da.coords:
            source_numbers = [int(da.number.values)]
            da = da.drop_vars('number')

        if not np.isfinite(da.values).all():
            raise ValueError("ERA5 land-sea mask contains non-finite values")
        expected_bounds = {
            'longitude': (self.west, self.east),
            'latitude': (self.south, self.north),
        }
        for coordinate, bounds in expected_bounds.items():
            values = da[coordinate].values
            if not np.allclose((values.min(), values.max()), bounds):
                raise ValueError(f"Unexpected {coordinate} bounds in {self.input_path}")

        da = self.format_lat_lon(da)


        # mask (sea = 0, land = 1)
        da = xr.where(da < self.cut_off, 0, 1).astype(np.int8)

        # capitalise variable
        da.name = "LSM"
        da.attrs = {
            'long_name': 'ERA5 binary land-sea mask',
            'units': '1',
            'flag_values': np.array([0, 1], dtype=np.int8),
            'flag_meanings': 'sea land',
            'threshold': self.cut_off,

        }

        # save
        output = da.to_dataset()
        output.attrs = {
            'Description': 'ERA5 land-sea mask for NEMO atmospheric forcing',
            'source_product_type': 'ensemble_members',
            'source_ensemble_numbers': ','.join(map(str, source_numbers)),
            'ensemble_masks_verified_identical': int(bool(source_numbers)),
        }
        output.to_netcdf(self.output_path)
        print(f"Wrote {self.output_path}")

if __name__ == '__main__':
    LSM = LandSeaMask()
    LSM.gen_land_sea_mask()
