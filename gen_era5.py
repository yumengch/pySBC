import argparse
import glob
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor, as_completed

import dask
import numpy  as np
import datetime
from pathlib import Path
import xarray as xr
import config

class era5(object):
    """
    Generate ERA5 atmospheric forcing for regional NEMO config
    Loosly based on code by Nico.

    Defaults parameters are for AMM15
    """

    def __init__(self, pythonic=False):
        self.year_init = config.y0                ## First year to process
        self.year_end  = config.y1                ## Last one [included]
        self.east      = config.east              ## East Border
        self.west      = config.west              ## West Border
        self.north     = config.north             ## North Border
        self.south     = config.south             ## South Border
        # ROOT PATH OF ERA5 DATA
        self.path_ERA5 = config.raw_path + '/ERA5/SURFACE_FORCING'
        # WHERE TO EXTRACT YOUR REGION
        self.path_EXTRACT = config.tmp_path
        # NEMO FORCING
        self.path_FORCING = config.processed_path
        self.clean        = False    ## Clean extraction (longest bit)
        self.sph_ON = config.sph_ON  ## Switch for specific humidity calculation
        self.var_path = config.var_list

    def timeit(func):
        """ decorator for timing a function """

        def inner():
            t0 = datetime.datetime.now()
            func()
            t1 = datetime.datetime.now()
            print ('time elapsed = ', t1-t0)

        return inner

    def read_NetCDF_all_years(self, fname, KeyVar, chunks=None):
        """Read NetCDF file"""

        lfiles = sorted( glob.glob( fname ) )
        ds = xr.open_mfdataset(lfiles, chunks=chunks, parallel=True,
                               decode_times=False)

        return ds[KeyVar]

    def add_global_attrs(self, ds):
        """ set global attributes for netcdf """

        fmt = "%Y-%m-%d %H:%M:%S"
        ds.attrs['Created'] = datetime.datetime.now().strftime(fmt)
        ds.attrs['Description'] = 'ERA5 Atmospheric conditions for AMM15 NEMO'

        return ds

    def interp_time(self, ds, fin, fout):
        """
        interpolate time to half timestep
        cdo version of interpolation
        """
        if self.clean : os.system( "rm {0}".format( fout ) )
        if not os.path.exists( fout ) :
           fmt = "%Y-%m-%d"
           day0 = ds.valid_time.dt.strftime(fmt)[0].values
           command = "cdo inttime,{0},{1},1hour {2} {3}".format(
                      day0, '00:30:00', fin, fout )
           print (command)
           os.system( command )

    def extract(self, fin, fout) :
        """
        extract regional domain
        """

        if self.clean : os.system( "rm {0}".format( fout ) )
        if not os.path.exists( fout ) :
           cmd_str = "ncks -d latitude,{0},{1} -d longitude,{2},{3} {4} {5}"
           command = cmd_str.format(
                         float(self.south), float(self.north),
                         float(self.west),  float(self.east), fin, fout )
           print (command)
           os.system(command)


    def extract_loop(self, nameVar, dirVar):
        """
        loop extraction over each year
        """

        for iY in range( self.year_init, self.year_end+1 ) :
            ## Files
            finput  = "{0}/{1}/{2}_{1}.nc".format(
              self.path_ERA5, dirVar, iY )
            foutput = "{2}/{0}_y{1}.nc".format(
              nameVar, iY, self.path_EXTRACT )
            ## Extract the subdomain
            self.extract(finput, foutput)

            # adjust for new file formatting
            varLabel = xr.open_dataarray(finput).name
            if varLabel in ["avg_sdlwrf", "avg_sdswrf"]:
                os.system(f"ncrename -v {varLabel},{nameVar} {finput}")

    def interpolate_all(self, nameVar, foutInterp, pythonic=False):
        """
        Interpolate to the half time-step via one of 2 methods:
            (1) pythonic - uses xarray to lazy loading
            (2) uses CDO

        (1) 4x slower than (2), but has a lower storage footprint.
        interpolate_by_year is both fast and has a smaller footprint.
        ----> this function may need removing RDP 22-05-23.
        """

        if not os.path.exists( foutInterp ) :
            if pythonic:
                ds = self.read_NetCDF_all_years(
                    "{1}/{0}_y*.nc".format(nameVar, self.path_EXTRACT), nameVar)

                ## assume to be constant in time
                Time = ds.valid_time.values
                dt  = (Time[1] - Time[0])#.astype('timedelta64[s]')
                dt2 = dt / 2
                print ("dt", dt, dt2)

                # Center in mid-time step (00:30)
                # NEMO assumes this timing according to documentation
                ds = ds.interp(valid_time=Time + dt2)
                ds.to_netcdf(foutInterp)
                ds.close()

            else: # cdo
                # merge all years
                command = "cdo mergetime {1}/{0}_y*.nc {1}/{0}_all.nc".format(
                                                     nameVar, self.path_EXTRACT)
                os.system(command)

                # interpolate
                finput = "{1}/{0}_all.nc".format(nameVar, self.path_EXTRACT)
                xrds = xr.open_dataset(finput)
                interp_time(xrds, finput, foutInterp)

    def interpolate_by_year(self, nameVar):
        """
        Loop over each extracted year interpolating to the half
        time-step, saving each year. Ensemble realizations are written to
        ens_1, ens_2, ...; deterministic input retains the legacy layout.
        """

        for iY in range(self.year_init, self.year_end+1) :

            print (iY)

            # open year0 file
            path = Path(self.path_EXTRACT) / (nameVar + '_y')
            f0 = Path(str(path) + str(iY) + '.nc')
            ds0 = xr.open_dataarray(f0)

            # open year1 file for interp across year end
            f1 = Path(str(path) + str(iY+1) + '.nc')
            if f1.exists():
                ds1 = xr.open_dataarray(f1)
                ds1 = ds1.isel(valid_time=0)
                ds = xr.concat([ds0,ds1], dim='valid_time')
            else:
                ds = ds0

            if 'expver' in ds.coords:
                ds = ds.drop_vars('expver')

            # Interpolate to the half source-data time step. ERA5 ensemble
            # analyses are three-hourly, so this preserves that cadence.
            times = ds.valid_time.values
            if len(times) < 2:
                raise ValueError(f"{f0} contains fewer than two time records")
            half_step = (times[1] - times[0]) / 2
            half_time = (ds.valid_time + half_step).sel(
                valid_time=str(iY)).values
            ds = ds.interp(valid_time=half_time)

            for member, source_number, member_data in self.iter_members(ds):
                output_dir = Path(self.path_FORCING)
                if member is not None:
                    output_dir /= f"ens_{member}"
                output_dir.mkdir(parents=True, exist_ok=True)
                fout = output_dir / f"ERA5_{nameVar.upper()}_y{iY}.nc"

                if self.clean and fout.exists():
                    fout.unlink()
                if fout.exists():
                    print(f"Skipping existing file: {fout}")
                    continue

                output = self.format_nc(member_data, nameVar)
                if source_number is not None:
                    output.attrs['source_ensemble_number'] = source_number
                    output.attrs['model_ensemble_member'] = member
                output.to_netcdf(fout, unlimited_dims="time")

            ds0.close()
            if f1.exists():
                ds1.close()

    def iter_members(self, da):
        """Yield model member number, ERA5 realization ID, and member data."""

        if 'number' not in da.dims:
            yield None, None, da
            return

        source_numbers = da['number'].values.tolist()
        if len(source_numbers) != len(set(source_numbers)):
            raise ValueError("ERA5 ensemble realization IDs are not unique")

        for member, source_number in enumerate(source_numbers, start=1):
            member_data = da.sel(number=source_number, drop=True)
            yield member, int(source_number), member_data

    def format_nc(self, da, nameVar):
        """
        Add netCDF attributes and format coordinates
        """

        if 'number' in da.dims:
            raise ValueError("format_nc expects a single ensemble realization")

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

        # assign X/Y as indexes
        auxiliary_coords = [name for name in ('expver',) if name in da.coords]
        if auxiliary_coords:
            da = da.drop_vars(auxiliary_coords)
        da = da.drop_vars(['longitude','latitude'])
        da = da.rename({'valid_time':'time', 'longitude':'nLon',
                        'latitude':'nLat'})
        da = da.assign_coords({'lon':mlon, 'lat':mlat})
        da.name = nameVar.upper()
        da['time'].attrs.update({
            'long_name': 'time',
            'standard_name': 'time',
        })

        # file information
        self.add_global_attrs(da)

        return da

    def split_by_year(self, ds, outpath, var):
        for ind, year in ds_all.groupby('valid_time.year'):
            print (ind)
            var = var.upper()
            year = self.cf_to_int_time(year)
            if nameVar in [ "d2m", "sp" ] :
                fout = "{2}/SPH_ERA5_{0}_y{1}.nc".format(var, ind, outpath)
            else:
                fout = "{2}/ERA5_{0}_y{1}.nc".format(var, ind, outpath)
            if clean : os.system( "rm {0}".format( fout ) )
            if not os.path.exists( fout ) :
                year.to_netcdf(fout)

    def process_specific_himiditiy(self, iY):
        """
        PROCESS SPECIFIC HUMIDITY

        Compute Specific Humidity according to ECMWF documentation.
        """

        forcing_path = Path(self.path_FORCING)
        member_dirs = sorted(forcing_path.glob('ens_*'))
        output_dirs = member_dirs if member_dirs else [forcing_path]

        for output_dir in output_dirs:
            self.process_member_specific_humidity(iY, output_dir)

    def process_member_specific_humidity(self, iY, output_dir):
        """Calculate specific humidity for one member output directory."""

        d2m_path = output_dir / f'ERA5_D2M_y{iY}.nc'
        sp_path = output_dir / f'ERA5_SP_y{iY}.nc'
        d2m = xr.open_dataarray(d2m_path, chunks={'time':50})
        sp = xr.open_dataarray(sp_path, chunks={'time':50})

        # calculate sph
        esat = 611.21 * np.exp( 17.502 * (d2m-273.16) / (d2m-32.19) )
        dyrvap = 287.0597 / 461.5250
        sph = dyrvap * esat / ( sp - (1-dyrvap) * esat)
        sph.attrs = {'units':'1', 'standard_name':'specific humidity'}

        # name variable
        sph.name = 'SPH'

        # save
        fout = output_dir / f'ERA5_SPH_y{iY}.nc'
        sph.to_netcdf(fout, unlimited_dims="time")
        d2m.close()
        sp.close()

    def process_variable(self, dirVar, nameVar, step1=True, step2=True):
        """Extract and interpolate one forcing variable."""

        print("================== {0} - {1} ==================".format(
              dirVar, nameVar), flush=True)

        if step1:
            self.extract_loop(nameVar, dirVar)

        if step2:
            self.interpolate_by_year(nameVar)

    def process_all(self, step1=True, step2=True, workers=1):
        Path(self.path_EXTRACT).mkdir(parents=True, exist_ok=True)
        Path(self.path_FORCING).mkdir(parents=True, exist_ok=True)

        variables = list(self.var_path.items())
        if not variables:
            raise ValueError("No ERA5 variables are configured")
        if workers < 1:
            raise ValueError("workers must be positive")
        workers = min(workers, len(variables))
        print(f"Processing {len(variables)} variables with {workers} worker(s)",
              flush=True)

        if workers == 1:
            for dirVar, nameVar in variables:
                self.process_variable(dirVar, nameVar, step1, step2)
        else:
            # Spawn before any datasets are opened in the parent. Each process
            # owns one variable's intermediate and final files. Dask executes
            # synchronously inside a worker to avoid workers creating another
            # layer of threads and oversubscribing the Slurm CPU allocation.
            context = multiprocessing.get_context("spawn")
            with ProcessPoolExecutor(max_workers=workers,
                                     mp_context=context) as executor:
                futures = {
                    executor.submit(
                        process_variable_worker,
                        dirVar, nameVar, step1, step2,
                    ): nameVar
                    for dirVar, nameVar in variables
                }
                for future in as_completed(futures):
                    nameVar = futures[future]
                    future.result()
                    print(f"Completed variable: {nameVar}", flush=True)

        # This is intentionally a barrier: SPH requires both D2M and SP files.
        if self.sph_ON : # get specific humidity
            for iY in range(self.year_init, self.year_end+1):
                self.process_specific_himiditiy(iY)


def process_variable_worker(dirVar, nameVar, step1, step2):
    """Process entry point used by spawned worker processes."""

    with dask.config.set(scheduler="synchronous"):
        processor = era5()
        processor.process_variable(dirVar, nameVar, step1, step2)


def default_worker_count():
    """Use the CPUs granted by Slurm without consuming a login node."""

    slurm_cpus = os.environ.get("SLURM_CPUS_PER_TASK")
    if slurm_cpus is None:
        return 1

    try:
        workers = int(slurm_cpus)
    except ValueError as exc:
        raise ValueError(
            f"Invalid SLURM_CPUS_PER_TASK value: {slurm_cpus!r}"
        ) from exc

    if workers < 1:
        raise ValueError("SLURM_CPUS_PER_TASK must be positive")
    return workers


def positive_int(value):
    """argparse type for a positive process count."""

    value = int(value)
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate ERA5 forcing files for NEMO",
    )
    parser.add_argument(
        "--workers",
        type=positive_int,
        default=None,
        help=("number of variables to process concurrently; defaults to "
              "SLURM_CPUS_PER_TASK inside Slurm and 1 otherwise"),
    )
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    allocated_workers = default_worker_count()
    workers = args.workers if args.workers is not None else allocated_workers
    if os.environ.get("SLURM_CPUS_PER_TASK") and workers > allocated_workers:
        raise ValueError(
            f"--workers={workers} exceeds the {allocated_workers} CPUs "
            "allocated by Slurm"
        )
    era = era5()
    era.process_all(workers=workers)
