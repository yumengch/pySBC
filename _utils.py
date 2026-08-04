"""
Collection of common functions
"""

def check_latitude(ds):
    """
    Check the orientation of latitude

    ERA5 latitude has north down orientation. Check orientation of
    source data and flip axes if north down is found.
    """

    # get delta latitude
    dlon = ds.longitude.diff("X")
    dlat = ds.latitude.diff("Y")
    
    # sort if monotonic decreasing
    if (dlon < 0).all():
        ds = ds.isel(X=slice(None,None,-1))
    if (dlat < 0).all():
        ds = ds.isel(Y=slice(None,None,-1))

    return ds


def longitude_0_360(longitude):
    """Return longitudes in the canonical half-open interval [0, 360)."""

    normalized = longitude % 360.0
    return normalized
