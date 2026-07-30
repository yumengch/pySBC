#!/usr/bin/env python
#====================== DOCSTRING ============================
"""

  Download ERA5 ECMWF 2D forcing fields for NEMO bulk formulation
  You need to have an account on CDS,
  https://cds.climate.copernicus.eu/cdsapp#!/dataset/reanalysis-era5-single-levels?tab=form

  You will nee to install the python package and  add your security key
  https://cds.climate.copernicus.eu/api-how-to

--------------------------------------------------------------
"""
__author__      = "Nicolas Bruneau"
__copyright__   = "Copyright 2017, National Oceanography Centre (NOC)"
__version__     = "1.0.1"
__maintainer__  = "Nicolas Bruneau"
__email__       = "nibrun@noc.ac.uk"
__status__      = "Development"
__date__        = "2019-02"

#====================== LOAD MODULES =========================

import os
import cdsapi
import config

#===================== USER PARAMETERS =======================

YEAR_0   = config.y0        # Initial year
YEAR_1   = config.y1        # Final year
VAR_INST = config.var_list  # Variables to process
out_path = config.raw_path  # Path for saving data
LSM      = True            # Get LSM
# Match the ERA5 grid used by run/exp_test/ens_1/fluxes.  The longitude in
# those files is stored as 332--359.75, 0--19 degrees east (28 W--19 E).
AREA     = [68, -28, 38, 19]  # North, west, south, east

#======================= CORE CODE ===========================

## Initiate connection to server
server = cdsapi.Client()

# LOOP OVER YEARS
for iY in range( YEAR_0, YEAR_1+1 ) :

    ## LOOP OVER SURFACE INSTANTANEOUS VARIABLES
    for nV, kV in enumerate(VAR_INST.keys()) :

        directory = "{0}/ERA5/SURFACE_FORCING/{1}".format(out_path,kV)
        if not os.path.exists( directory ): os.makedirs( directory )

        fname = "{0}/{2}_{1}.nc".format( directory, kV, iY )
        fname2 = "{0}/{2}_{1}.nsddsdsc".format( directory, kV, iY )
        if not os.path.exists( fname2 ) :

           server.retrieve(
    'reanalysis-era5-single-levels',
    {
        'product_type':'ensemble_members',
        'format':'netcdf',
        'area':AREA,
        'variable':[
            kV,
        ],
        'year':'{0}'.format( iY ),
        'month':[
            '01','02','03',
            '04','05','06',
            '07','08','09',
            '10','11','12'
        ],
        'day':[
            '01','02','03',
            '04','05','06',
            '07','08','09',
            '10','11','12',
            '13','14','15',
            '16','17','18',
            '19','20','21',
            '22','23','24',
            '25','26','27',
            '28','29','30',
            '31'
        ],
        'time':[
            '00:00','01:00','02:00',
            '03:00','04:00','05:00',
            '06:00','07:00','08:00',
            '09:00','10:00','11:00',
            '12:00','13:00','14:00',
            '15:00','16:00','17:00',
            '18:00','19:00','20:00',
            '21:00','22:00','23:00'
        ]
    },
    '{0}'.format( fname ) )

if LSM:
    # get land-sea mask
    server.retrieve(
        'reanalysis-era5-single-levels',
        {
            'product_type': 'ensemble_members',
            'format': 'netcdf',
            'area': AREA,
            'variable': 'land_sea_mask',
            'time': '00:00',
            'day': '01',
            'month': '01',
            'year': '2004',
        },
        out_path + 'ERA5_LSM_20040101.nc')
