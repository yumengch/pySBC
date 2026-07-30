#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"

source_grid="${1:-${repo_root}/pySBC/dataForcing/ERA5_LSM.nc}"
nemo_grid="${2:-${repo_root}/run/exp_test/ens_1/domain_cfg.nc}"
work_dir="${3:-${script_dir}/work}"
weights_tools="${NEMO_WEIGHTS_TOOLS:-${repo_root}/code/nemo/tools/WEIGHTS}"
namelist_name="namelist_era5_0p5_bicubic"
output_name="weights_era5_0p5_bicubic.nc"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

command -v ncdump >/dev/null 2>&1 || \
    fail "ncdump is unavailable; load the repository ARCHER2 modules first"

test -e "${source_grid}" || fail "source grid does not exist: ${source_grid}"
test -e "${nemo_grid}" || fail "NEMO grid does not exist: ${nemo_grid}"

source_grid="$(realpath "${source_grid}")"
nemo_grid="$(realpath "${nemo_grid}")"

for executable in scripgrid.exe scrip.exe scripshape.exe; do
    test -x "${weights_tools}/${executable}" || \
        fail "missing ${weights_tools}/${executable}; build NEMO WEIGHTS first"
done

source_header="$(ncdump -h "${source_grid}")"
grep -Eq 'nLon = 95 ;|longitude = 95 ;' <<<"${source_header}" || \
    fail "ERA5 source longitude dimension is not 95"
grep -Eq 'nLat = 61 ;|latitude = 61 ;' <<<"${source_header}" || \
    fail "ERA5 source latitude dimension is not 61"
grep -Eq '(double|float) lon\(' <<<"${source_header}" || \
    fail "ERA5 source grid has no lon coordinate"
grep -Eq '(double|float) lat\(' <<<"${source_header}" || \
    fail "ERA5 source grid has no lat coordinate"

nemo_header="$(ncdump -h "${nemo_grid}")"
grep -Eq 'x = 297 ;' <<<"${nemo_header}" || \
    fail "AMM7 destination x dimension is not 297"
grep -Eq 'y = 375 ;' <<<"${nemo_header}" || \
    fail "AMM7 destination y dimension is not 375"
grep -Eq 'glamt\(' <<<"${nemo_header}" || fail "NEMO grid has no glamt"
grep -Eq 'gphit\(' <<<"${nemo_header}" || fail "NEMO grid has no gphit"
grep -Eq 'glamf\(' <<<"${nemo_header}" || fail "NEMO grid has no glamf"
grep -Eq 'gphif\(' <<<"${nemo_header}" || fail "NEMO grid has no gphif"

if test -d "${work_dir}" && find "${work_dir}" -mindepth 1 -print -quit | grep -q .; then
    fail "work directory is not empty: ${work_dir}; choose a new directory"
fi
mkdir -p "${work_dir}"

ln -s "${source_grid}" "${work_dir}/era5_source_grid.nc"
ln -s "${nemo_grid}" "${work_dir}/domain_cfg.nc"
cp "${script_dir}/${namelist_name}" "${work_dir}/${namelist_name}"

cd "${work_dir}"
"${weights_tools}/scripgrid.exe" "${namelist_name}"
"${weights_tools}/scrip.exe" "${namelist_name}"
"${weights_tools}/scripshape.exe" "${namelist_name}"

test -s "${output_name}" || fail "weights output was not created"
output_header="$(ncdump -h "${output_name}")"
grep -Eq 'lon = 297 ;' <<<"${output_header}" || \
    fail "weights longitude dimension is not 297"
grep -Eq 'lat = 375 ;' <<<"${output_header}" || \
    fail "weights latitude dimension is not 375"

for index in $(seq -w 1 16); do
    for prefix in src dst wgt; do
        grep -Eq "${prefix}${index}\\(lat, lon\\)" <<<"${output_header}" || \
            fail "weights output is missing ${prefix}${index}"
    done
done

grep -Fq 'ew_wrap = -1' <<<"${output_header}" || \
    fail "weights output does not record ew_wrap=-1"
grep -Fq 'Bicubic remapping' <<<"${output_header}" || \
    fail "weights output is not labelled as bicubic"

echo "Created and structurally validated: ${work_dir}/${output_name}"
