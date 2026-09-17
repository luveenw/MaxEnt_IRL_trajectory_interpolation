#!/usr/bin/env bash
# =============================================================================
# Stage the Step 1 outputs to Cloud Storage and ingest them as Earth Engine
# table assets.
#
# The Earth Engine CLI only ingests from gs:// URIs, so each CSV is copied to a
# staging bucket first. Both assets are small enough that the Code Editor's
# Assets -> NEW -> CSV file uploader works too; this script exists so the step
# is reproducible and so the geometry-column flags are not left to the UI.
#
# Prerequisites:
#   pip install earthengine-api            # provides `earthengine`
#   earthengine authenticate
#   gcloud auth login                      # provides gsutil credentials
#
# Usage:
#   bash upload_gee_assets.sh
#   KEEP_STAGING=1 bash upload_gee_assets.sh    # leave the gs:// copies behind
# =============================================================================

set -euo pipefail

# ----------------------------------------------------------------- config ---
# EE_ASSET_ROOT is the folder your assets land in. Two accepted forms:
#   Cloud project accounts:  projects/<your-cloud-project>/assets
#   Legacy accounts:         users/<your-ee-username>
# This must match ASSET_ROOT at the top of the two Code Editor scripts.
EE_ASSET_ROOT="${EE_ASSET_ROOT:-projects/REPLACE-WITH-YOUR-PROJECT/assets}"

# Cloud Storage bucket used only as an ingestion staging area.
GCS_BUCKET="${GCS_BUCKET:-gs://REPLACE-WITH-YOUR-BUCKET}"

# Folder created under EE_ASSET_ROOT to hold this project's assets.
EE_FOLDER="${EE_FOLDER:-jaguar_biome}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPLOAD_DIR="${SCRIPT_DIR}/gee_upload"

HOME_RANGES_CSV="${UPLOAD_DIR}/home_ranges_wkt.csv"
GPS_POINTS_CSV="${UPLOAD_DIR}/jaguar_gps_points.csv"

STAGING_PREFIX="${GCS_BUCKET%/}/jaguar_biome_staging"
ASSET_FOLDER="${EE_ASSET_ROOT%/}/${EE_FOLDER}"

# ---------------------------------------------------------------- checks ----
fail() { printf '\nERROR: %s\n' "$1" >&2; exit 1; }

command -v earthengine >/dev/null 2>&1 \
  || fail "\`earthengine\` not found. Install with: pip install earthengine-api"
command -v gsutil >/dev/null 2>&1 \
  || fail "\`gsutil\` not found. Install the Google Cloud SDK."

[[ "${EE_ASSET_ROOT}" == *REPLACE-WITH-YOUR* ]] \
  && fail "Set EE_ASSET_ROOT at the top of this script (or export it)."
[[ "${GCS_BUCKET}" == *REPLACE-WITH-YOUR* ]] \
  && fail "Set GCS_BUCKET at the top of this script (or export it)."

for f in "${HOME_RANGES_CSV}" "${GPS_POINTS_CSV}"; do
  [[ -f "${f}" ]] || fail "$(basename "${f}") missing. Run: python3 prepare_gee_uploads.py"
done

echo "=== Earth Engine asset upload ==="
echo "  Asset folder : ${ASSET_FOLDER}"
echo "  Staging area : ${STAGING_PREFIX}"
echo

# ------------------------------------------------------------ ee folder -----
echo "--- Ensuring asset folder exists ---"
# `create folder` errors if the folder is already there; that is not fatal.
earthengine create folder "${ASSET_FOLDER}" 2>/dev/null \
  || echo "  (folder already exists, continuing)"

# --------------------------------------------------------------- staging ----
echo
echo "--- Staging CSVs to Cloud Storage ---"
gsutil -m cp "${HOME_RANGES_CSV}" "${GPS_POINTS_CSV}" "${STAGING_PREFIX}/"

# --------------------------------------------------------------- ingest -----
echo
echo "--- Ingesting home ranges (WKT polygons) ---"
earthengine upload table \
  --asset_id="${ASSET_FOLDER}/home_ranges" \
  --primary_geometry_column=wkt \
  --max_error=1 \
  --force \
  --wait 3600 \
  "${STAGING_PREFIX}/home_ranges_wkt.csv"

echo
echo "--- Ingesting GPS points (lon/lat) ---"
earthengine upload table \
  --asset_id="${ASSET_FOLDER}/gps_points" \
  --x_column=longitude \
  --y_column=latitude \
  --time_start=millis \
  --max_error=1 \
  --force \
  --wait 3600 \
  "${STAGING_PREFIX}/jaguar_gps_points.csv"

# -------------------------------------------------------------- cleanup -----
if [[ -z "${KEEP_STAGING:-}" ]]; then
  echo
  echo "--- Removing staged copies ---"
  gsutil -m rm "${STAGING_PREFIX}/home_ranges_wkt.csv" \
               "${STAGING_PREFIX}/jaguar_gps_points.csv" || true
fi

echo
echo "=== Done ==="
echo "Assets created:"
echo "  ${ASSET_FOLDER}/home_ranges"
echo "  ${ASSET_FOLDER}/gps_points"
echo
echo "Set ASSET_ROOT in gee/01_biome_review_app.js and gee/02_visualization_app.js to:"
echo "  ${ASSET_FOLDER}"
