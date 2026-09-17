#!/usr/bin/env python3
"""
Ingest the Annual Gridded Livestock of the World rasters as Earth Engine assets.

Uploads eight species x eighteen years (1999-2016) = 144 single-band images to
one Earth Engine folder, named `<Code>_<year>` with no file extension, which is
exactly what `LIVESTOCK` in gee/00_covariates.js indexes.

WHY THE CLIP. The source rasters are global, 8016 x 3160 at ~5 km, and span
360.03 degrees of longitude starting at -168.84 -- so their eastern edge sits at
191.2E, past the antimeridian. Earth Engine has no reason to enjoy that, and
this study never reads a pixel outside the Americas. Clipping to a generous
Americas window takes each file from ~24 MB to ~3 MB, cuts the whole upload from
2.4 GB to a few hundred MB, and sidesteps the wrap entirely. `-projwin` snaps to
the source pixel grid, so no resampling happens and pixel values are unchanged.
Pass --global to upload the untouched worldwide rasters instead.

WHY THE NODATA TAG. AGLW marks ocean with float NaN and sets no NoData tag at
all, so an unguarded ingest gives Earth Engine 34 million valid NaNs and any
coastal home range reduces to NaN. The clip writes NoData=nan; the covariate
module additionally masks on `gte(0)`, because a tag alone is one interpretation
away from being ignored.

Prerequisites
    pip install earthengine-api          # provides `earthengine`
    earthengine authenticate
    gcloud auth login                    # credentials for gcloud storage
    gdal_translate on PATH               # unless you pass --global

Usage
    export GCS_BUCKET=gs://your-staging-bucket
    python3 upload_aglw_assets.py --dry-run          # see the plan, do nothing
    python3 upload_aglw_assets.py                    # clip, stage, ingest
    python3 upload_aglw_assets.py --species Cattl    # one species
    python3 upload_aglw_assets.py --stage-only       # clip + upload to GCS only

Re-running is safe: assets that already exist are skipped unless --force, and
local clips that already exist are not redone.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# --------------------------------------------------------------- config ----

SOURCE_DIR = Path(os.environ.get(
    "AGLW_SOURCE_DIR",
    "/run/media/luveen/Extreme Pro/Thesis/Data Sets/"
    "Annual Global Livestock/LivestockMap/LivestockMap",
))

EE_ASSET_FOLDER = os.environ.get(
    "AGLW_ASSET_FOLDER", "projects/perceptive-ivy-780/assets/AGLW")

GCS_BUCKET = os.environ.get("GCS_BUCKET", "")

YEARS = range(1999, 2017)

# Five-letter AGLW file codes -> the common name written into asset properties.
SPECIES = {
    "Buffa": "Buffalo",
    "Cattl": "Cattle",
    "Chick": "Chickens",
    "Ducks": "Ducks",
    "Goats": "Goats",
    "Horse": "Horses",
    "Sheep": "Sheep",
    "Swine": "Pigs",
}

# west, north, east, south -- the order gdal_translate -projwin wants.
# The GPS fixes span lon -109.5..-42.2 and lat -25.8..29.8, and the Madre de
# Dios target site sits at about -71.5, -12.0; this leaves >10 degrees of
# margin on every side so no home-range contour can reach an edge.
CLIP_PROJWIN = (-120.0, 35.0, -30.0, -35.0)

STAGE_SUBDIR = "aglw_staging"

# --------------------------------------------------------------- helpers ---


def fail(msg: str) -> None:
    sys.exit(f"\nERROR: {msg}")


def run(cmd: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=False, text=True,
                          capture_output=capture)


def require(binary: str, hint: str) -> None:
    if shutil.which(binary) is None:
        fail(f"`{binary}` not found on PATH. {hint}")


def check_module_agrees() -> None:
    """
    Cross-check the asset folder and species codes against the Code Editor
    module, so the two cannot drift apart silently the way an asset path and
    the code that reads it usually do.
    """
    js_path = Path(__file__).with_name("gee") / "00_covariates.js"
    if not js_path.exists():
        return
    js = js_path.read_text(encoding="utf-8")

    root = re.search(r"root:\s*'([^']+)'", js)
    if root and root.group(1).rstrip("/") != EE_ASSET_FOLDER.rstrip("/"):
        fail(f"gee/00_covariates.js points LIVESTOCK.root at "
             f"{root.group(1)!r} but this script uploads to "
             f"{EE_ASSET_FOLDER!r}. Reconcile them before uploading.")

    codes = set(re.findall(r"code:\s*'(\w+)'", js))
    missing = codes - set(SPECIES)
    if missing:
        fail(f"gee/00_covariates.js expects species codes {sorted(missing)} "
             f"that this script does not know how to upload.")


def source_file(code: str, year: int) -> Path:
    return SOURCE_DIR / f"{code}_{year}.tif"


def asset_id(code: str, year: int) -> str:
    # No `.tif` in the asset id. Earth Engine asset ids are not filenames, and
    # carrying an extension into one only invites the module and the upload to
    # disagree about whether it is there.
    return f"{EE_ASSET_FOLDER.rstrip('/')}/{code}_{year}"


def existing_assets() -> set[str]:
    """One `earthengine ls` instead of 144 `earthengine asset info` calls."""
    res = run(["earthengine", "ls", EE_ASSET_FOLDER], capture=True)
    if res.returncode != 0:
        return set()
    return {line.strip() for line in res.stdout.splitlines() if line.strip()}


def manifest_for(code: str, year: int, uri: str) -> dict:
    return {
        "name": asset_id(code, year),
        "tilesets": [{"id": "src", "sources": [{"uris": [uri]}]}],
        "bands": [{
            "id": "density",
            "tilesetId": "src",
            "tilesetBandIndex": 0,
            # MEAN, not the default: these are densities, and a pyramid built
            # by sampling would make a coarse zoom read whatever pixel it
            # happened to land on rather than the area average.
            "pyramidingPolicy": "MEAN",
        }],
        "startTime": f"{year}-01-01T00:00:00Z",
        "endTime": f"{year + 1}-01-01T00:00:00Z",
        "properties": {
            "species_code": code,
            "species": SPECIES[code],
            "year": year,
            "units": "head_per_km2",
            "native_resolution_km": 5,
            "source": "Annual Gridded Livestock of the World, "
                      "doi:10.5281/zenodo.17128483",
        },
    }


# ----------------------------------------------------------------- steps ---


def plan(args) -> list[tuple[str, int]]:
    codes = args.species or list(SPECIES)
    for c in codes:
        if c not in SPECIES:
            fail(f"unknown species code {c!r}. Known: {', '.join(SPECIES)}")

    years = args.years or list(YEARS)
    jobs, missing = [], []
    for code in codes:
        for year in years:
            (jobs if source_file(code, year).exists() else missing).append(
                (code, year))

    if missing:
        preview = ", ".join(f"{c}_{y}.tif" for c, y in missing[:6])
        fail(f"{len(missing)} source file(s) not found under {SOURCE_DIR}: "
             f"{preview}{' ...' if len(missing) > 6 else ''}")
    return jobs


def clip(jobs, stage_dir: Path, args) -> list[Path]:
    stage_dir.mkdir(parents=True, exist_ok=True)
    staged = []
    for i, (code, year) in enumerate(jobs, 1):
        src = source_file(code, year)
        dst = stage_dir / f"{code}_{year}.tif"
        staged.append(dst)

        if args.globe:
            staged[-1] = src
            continue
        if dst.exists() and not args.force:
            continue

        w, n, e, s = CLIP_PROJWIN
        res = run([
            "gdal_translate", "-q",
            "-projwin", str(w), str(n), str(e), str(s),
            "-a_nodata", "nan",
            "-co", "COMPRESS=DEFLATE",
            "-co", "PREDICTOR=3",
            "-co", "TILED=YES",
            "-co", "BIGTIFF=IF_SAFER",
            str(src), str(dst),
        ])
        if res.returncode != 0:
            fail(f"gdal_translate failed on {src.name}")
        print(f"  [{i:3d}/{len(jobs)}] clipped {dst.name} "
              f"({dst.stat().st_size / 1048576:.1f} MB)")
    return staged


def stage_to_gcs(staged: list[Path], prefix: str) -> None:
    # One batched copy; gcloud storage parallelises internally and a single
    # invocation reuses the auth handshake 144 times over.
    print(f"\n--- Copying {len(staged)} file(s) to {prefix} ---")
    res = run(["gcloud", "storage", "cp"] + [str(p) for p in staged]
              + [prefix + "/"])
    if res.returncode != 0:
        fail("gcloud storage cp failed.")


def ingest(jobs, prefix: str, present: set[str], args) -> tuple[int, int, int]:
    started = skipped = failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, (code, year) in enumerate(jobs, 1):
            aid = asset_id(code, year)
            if aid in present and not args.force:
                skipped += 1
                continue

            uri = f"{prefix}/{code}_{year}.tif"
            mpath = Path(tmp) / f"{code}_{year}.json"
            mpath.write_text(json.dumps(manifest_for(code, year, uri),
                                        indent=2), encoding="utf-8")

            cmd = ["earthengine", "upload", "image", "--manifest", str(mpath)]
            if args.force:
                cmd.append("--force")
            res = run(cmd, capture=True)
            if res.returncode != 0:
                failed += 1
                print(f"  [{i:3d}/{len(jobs)}] FAILED {code}_{year}: "
                      f"{(res.stderr or res.stdout).strip().splitlines()[-1:]}")
            else:
                started += 1
                print(f"  [{i:3d}/{len(jobs)}] submitted {code}_{year}")
    return started, skipped, failed


# ------------------------------------------------------------------ main ---


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Upload AGLW livestock rasters to Earth Engine.")
    ap.add_argument("--bucket", default=GCS_BUCKET,
                    help="gs://bucket used to stage the GeoTIFFs for ingestion.")
    ap.add_argument("--species", nargs="+", metavar="CODE",
                    help=f"Subset of {', '.join(SPECIES)}. Default: all eight.")
    ap.add_argument("--years", nargs="+", type=int, metavar="YEAR",
                    help="Subset of 1999-2016. Default: all eighteen.")
    ap.add_argument("--global", dest="globe", action="store_true",
                    help="Upload the untouched global rasters (2.4 GB) "
                         "instead of the Americas clip.")
    ap.add_argument("--stage-only", action="store_true",
                    help="Clip and copy to Cloud Storage, but do not ingest.")
    ap.add_argument("--force", action="store_true",
                    help="Redo clips and overwrite assets that already exist.")
    ap.add_argument("--keep-staging", action="store_true",
                    help="Leave the gs:// copies behind after ingestion.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the plan and exit.")
    args = ap.parse_args()

    if not SOURCE_DIR.is_dir():
        fail(f"source directory not found: {SOURCE_DIR}\n"
             f"       Set AGLW_SOURCE_DIR, or mount the drive.")
    check_module_agrees()

    jobs = plan(args)
    prefix = f"{args.bucket.rstrip('/')}/{STAGE_SUBDIR}" if args.bucket else ""

    print("=== AGLW -> Earth Engine ===")
    print(f"  Source       : {SOURCE_DIR}")
    print(f"  Asset folder : {EE_ASSET_FOLDER}")
    print(f"  Staging      : {prefix or '(bucket not set)'}")
    print(f"  Extent       : {'global (unclipped)' if args.globe else 'Americas clip %s' % (CLIP_PROJWIN,)}")
    print(f"  Images       : {len(jobs)}  "
          f"({len(set(c for c, _ in jobs))} species x "
          f"{len(set(y for _, y in jobs))} years)")

    if args.dry_run:
        for code, year in jobs[:5]:
            print(f"    {source_file(code, year).name} -> {asset_id(code, year)}")
        if len(jobs) > 5:
            print(f"    ... and {len(jobs) - 5} more")
        print("\nDry run; nothing uploaded.")
        return

    require("gcloud", "Install the Google Cloud SDK.")
    if not args.globe:
        require("gdal_translate", "Install GDAL, or pass --global.")
    if not args.stage_only:
        require("earthengine", "Install with: pip install earthengine-api")
    if not args.bucket:
        fail("no staging bucket. Set GCS_BUCKET or pass --bucket gs://...\n"
             "       The Earth Engine CLI ingests only from gs:// URIs.")

    stage_dir = Path(tempfile.gettempdir()) / STAGE_SUBDIR
    print(f"\n--- Clipping to {stage_dir} ---" if not args.globe
          else "\n--- Using global rasters as-is ---")
    staged = clip(jobs, stage_dir, args)
    stage_to_gcs(staged, prefix)

    if args.stage_only:
        print(f"\n=== Staged only. Files are at {prefix}/ ===")
        return

    print(f"\n--- Ensuring {EE_ASSET_FOLDER} exists ---")
    run(["earthengine", "create", "folder", EE_ASSET_FOLDER], capture=True)

    present = existing_assets()
    if present:
        print(f"  {len(present)} asset(s) already in the folder"
              f"{'; overwriting' if args.force else '; those will be skipped'}")

    print(f"\n--- Submitting ingestion tasks ---")
    started, skipped, failed = ingest(jobs, prefix, present, args)

    if not args.keep_staging and not failed:
        print("\n--- Note ---")
        print(f"  Ingestion is asynchronous, so the staged copies at {prefix}/")
        print("  must stay until every task completes. Check the Tasks tab, or")
        print("  run `earthengine task list`, then delete them with:")
        print(f"    gcloud storage rm {prefix}/**")

    print(f"\n=== Submitted {started}, skipped {skipped}, failed {failed} ===")
    if failed:
        sys.exit(1)
    print(f"Assets will appear under {EE_ASSET_FOLDER} as <Code>_<year>.")
    print("gee/00_covariates.js already points at them; nothing to edit.")


if __name__ == "__main__":
    main()
