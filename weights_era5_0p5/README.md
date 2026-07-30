# ERA5 0.5-degree interpolation weights

This directory generates one bicubic interpolation-weights file from the
shared 0.5-degree ERA5 ensemble grid to the AMM7 NEMO T grid. The weights
depend on the grids, not the realization values, so all ensemble members use
the same output file.

## Prerequisites

Generate the processed source mask first:

```bash
cd pySBC
python gen_LSM.py
```

The expected file is `pySBC/dataForcing/ERA5_LSM.nc`, with dimensions
`nLon=95` and `nLat=61`. The default destination is
`run/exp_test/ens_1/domain_cfg.nc`, with dimensions `x=297` and `y=375`.

Build NEMO's serial WEIGHTS utilities if they are not already available. From
the repository root, the intended ARCHER2 command is:

```bash
source scripts/config.sh
cd code/nemo/tools
./maketools -m "$NEMO_ARCH" -n WEIGHTS -j 4
```

Compilation is not performed by the generation script.

## Generate

From the repository root:

```bash
source scripts/config.sh
pySBC/weights_era5_0p5/generate_weights.sh
```

The default output is:

```text
pySBC/weights_era5_0p5/work/weights_era5_0p5_bicubic.nc
```

To use alternative inputs or a fresh work directory:

```bash
pySBC/weights_era5_0p5/generate_weights.sh \
    /path/to/ERA5_LSM.nc \
    /path/to/domain_cfg.nc \
    /path/to/new_work_directory
```

The script refuses to overwrite a non-empty work directory. It verifies source
and destination dimensions, required coordinate variables, all 16 bicubic
`src`, `dst`, and `wgt` fields, `ew_wrap=-1`, and bicubic metadata.

After validation, deploy the result as an experiment-specific input and update
all atmospheric `sn_*` entries in `namelist_cfg` to its filename. Do not replace
the existing file through the shared `inputs` symlink.
