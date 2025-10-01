"""
Set ERA5 user defined parameters
"""

y0 = 2004 # Initial year
y1 = 2004 # Final year

## Compute specific humidity or not
sph_ON = False

# Variable list
var_list = { 
       "10m_u_component_of_wind" : "u10",
       "10m_v_component_of_wind" : "v10",
       "2m_temperature"          : "t2m", 
       "mean_sea_level_pressure" : "msl", 
       "mean_snowfall_rate"      : "msr" ,
       "mean_surface_downward_long_wave_radiation_flux"  : "msdwlwrf",
       "mean_surface_downward_short_wave_radiation_flux" : "msdwswrf",
       "mean_total_precipitation_rate" : "mtpr" }

if sph_ON :
   var_list[ "surface_pressure"  ] = 'sp'
   var_list[ "2m_dewpoint_temperature" ] = 'd2m'

head = '/projectsa/NEMO/ryapat/' # head path
raw_path       = head + 'Raw'    # raw data
tmp_path       = head + 'Extract'  # temp extraction space
processed_path = head + 'Forcing'  # processed forcing

# set domain extent
east  =   19.  # east border
west  =  -28.  # west border
north =   68.  # north border
south =   38.  # south border
