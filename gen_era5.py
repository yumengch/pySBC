import os, sys, glob
import numpy  as np
import datetime
import xarray as xr
import config
import _utils

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
        self.chunks={'valid_time':50}

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
           os.system( command )
    
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
                    "{1}/{0}_y*.nc".format(nameVar, self.path_EXTRACT), nameVar,
                          chunks=self.chunks)
    
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
                xrds = xr.open_dataset(finput, chunks=self.chunks)
                interp_time(xrds, finput, foutInterp)

    def interpolate_by_year(self, nameVar):
        """
        Loop over each extracted year interpolating to the half
        time-step, saving each year.
        """
    
        for iY in range(self.year_init, self.year_end+1) :

            # output name
            fout = self.path_FORCING + '/ERA5_' + nameVar + '_y' + \
                   str(iY) +'.nc'

            if self.clean : os.system( "rm {0}".format( fout ) )
            if not os.path.exists( fout ) :
                print (iY)

                # open year0 file
                path = self.path_EXTRACT + '/' + nameVar + '_y' 
                f0 = path + str(iY) + '.nc'
                ds0 = xr.open_dataarray(f0, chunks=self.chunks)

                # open year1 file
                if iY+1 != self.year_end+1:
                    f1 = path + str(iY+1) + '.nc'
                    ds1 = xr.open_dataarray(f1, chunks=self.chunks)
                    ds1 = ds1.isel(valid_time=0)
                    ds = xr.concat([ds0,ds1], dim='valid_time')
                else:
                    ds = ds0

                # interpolate to half time-step
                Time = ds.valid_time.values
                dt = (Time[1] - Time[0]) / 2
                half_time = (ds.valid_time + dt).sel(valid_time=str(iY)).values
                ds = ds.interp(valid_time=half_time)

                # format indexes and coords
                self.ds = self.format_nc(ds, nameVar)

                # check orientation of latitude
                self.ds = _utils.check_latitude(self.ds)

                # maintain encoding for storage savings
                scale_factor = ds0.encoding['scale_factor']
                add_offset   = ds0.encoding['add_offset']

                # save with encoding
                self.ds.to_netcdf(fout, encoding={nameVar: {
                                  "dtype": 'int16',
                                  "scale_factor": scale_factor,
                                  "add_offset": add_offset,
                                  "_FillValue": -32767}},
                                  unlimited_dims="valid_time")

    def format_nc(self, da, nameVar):
        """
        Add netCDF attributes and format coordinates
        """

        # mesh lat and lon
        mlon, mlat = np.meshgrid(da.longitude, da.latitude)
        lon_attrs={'long_name':'longitude','units':'degrees_east'}
        lat_attrs={'long_name':'latitude', 'units':'degrees_north'}
        mlon = xr.DataArray(mlon, dims=['Y','X'], attrs=lon_attrs)
        mlat = xr.DataArray(mlat, dims=['Y','X'], attrs=lat_attrs)
      
        # assign X/Y as indexes
        da = da.drop_vars(['longitude','latitude'])
        da = da.rename({'longitude':'X','latitude':'Y'})
        da = da.assign_coords({'longitude':mlon,'latitude':mlat})
      
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
        
        # read
        d2m_path = self.path_FORCING + '/ERA5_d2m_y' + str(iY) + '.nc'
        sp_path  = self.path_FORCING + '/ERA5_sp_y' + str(iY) + '.nc'
        d2m = xr.open_dataarray(d2m_path, chunks=self.chunks)
        sp  = xr.open_dataarray(sp_path,  chunks=self.chunks) 
        
        # calculate sph
        esat = 611.21 * np.exp( 17.502 * (d2m-273.16) / (d2m-32.19) )
        dyrvap = 287.0597 / 461.5250
        sph = dyrvap * esat / ( sp - (1-dyrvap) * esat)
        sph.attrs = {'units':'1', 'standard_name':'specific humidity'}

        # name variable
        sph.name = 'sph'
        
        # save
        fout = self.path_FORCING + '/ERA5_sph_y' + str(iY) + '.nc'
        sph.to_netcdf(fout, unlimited_dims="valid_time")

    def process_all(self, step1=True, step2=True):
        os.system("mkdir {0} {1}".format(
                  self.path_EXTRACT, self.path_FORCING ) )
        if self.west < 0 : self.west = 360.+self.west
        if self.east < 0 : self.east = 360.+self.east
        
        ## Loop over each variable
        for dirVar, nameVar in self.var_path.items() :
        
            print ("================== {0} - {1} ==================".format(
                    dirVar, nameVar ))
        
            ## --------------------------------------------------
            ## -------- step 1: EXTRACT -------------------------
            ## --------------------------------------------------
            if step1: self.extract_loop(nameVar, dirVar)
        
            ## --------------------------------------------------
            #### ------ step 2: INTERPOLATE ---------------------
            ## --------------------------------------------------
            if step2:
                self.interpolate_by_year(nameVar)
        
        if self.sph_ON : # get specific humidity
            for iY in range(self.year_init, self.year_end+1):
                self.process_specific_himiditiy(iY)

if __name__ == '__main__':
    era = era5()
    era.process_all()
