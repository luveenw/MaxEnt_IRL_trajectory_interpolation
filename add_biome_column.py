#!/usr/bin/env python3
"""
Step 4 - Join confirmed RESOLVE biome labels back onto the movement CSV.

Reads the export produced by the Step 2 Earth Engine review app and writes
jaguar_movement_data_with_biome.csv: the original 134,690 GPS fixes plus the
biome, ecoregion, and sex columns the MaxEnt IRL pipeline filters on.

THE PAIRING RULE
    `biome_type`, `ecoregion_name`, `usage_weight` and `area_weight` are all
    pipe-delimited and positionally paired -- element i of each describes the
    same ecoregion, ordered by weight of use. A biome name repeats when an
    individual's range covers two ecoregions of the same biome; that repetition
    is deliberate, because de-duplicating would break the alignment.
    `biome_type_primary` is provided for the common case of filtering on a
    single coarse class.

TWO OUTPUTS, ON PURPOSE
    Per-individual facts are written once to a 117-row profile rather than
    repeated across 134,690 GPS rows. The movement CSV carries only what a
    per-fix analysis needs; the profile carries the Tier 2 habitat covariates,
    the candidates the reviewer rejected, and the review flags. Anything
    downstream joins them on `individual.local.identifier (ID)`.

Usage:
    python3 add_biome_column.py
    python3 add_biome_column.py --assignments path/to/biome_assignments_export.csv
    python3 add_biome_column.py --covariates path/to/individual_covariates.csv
    python3 add_biome_column.py --allow-missing     # warn instead of failing
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent

MOVEMENT_CSV = BASE_DIR / "jaguar_movement_data.csv"
ADDITIONAL_INFO_CSV = BASE_DIR / "Jaguar_additional_information_fixed.csv"
DEFAULT_OUTPUT = BASE_DIR / "jaguar_movement_data_with_biome.csv"
DEFAULT_PROFILE = BASE_DIR / "jaguar_individual_profile.csv"

# Where the Step 2 export is looked for, in order, when --assignments is absent.
DEFAULT_ASSIGNMENT_PATHS = [
    BASE_DIR / "biome_assignments_export.geojson",
    BASE_DIR / "biome_assignments_export.csv",
    BASE_DIR / "gee_export" / "biome_assignments_export.geojson",
    BASE_DIR / "gee_export" / "biome_assignments_export.csv",
]

ID_COL = "individual.local.identifier (ID)"

# jaguar_movement_data.csv uses classic-Mac CR-only line terminators.
MOVEMENT_LINETERMINATOR = "\r"

EXPECTED_ROWS = 134690
EXPECTED_INDIVIDUALS = 117

# Fields that must agree across every contour row of the same individual.
ASSIGNMENT_FIELDS = [
    "biome_type",
    "ecoregion_name",
    "usage_weight",
    "area_weight",
    "n_fixes_inside",
    "assignment_status",
    "assignment_method",
    "rank_mode",
    "review_flags",
    "rejected_ecoregion_name",
    "rejected_biome_type",
    "rejected_usage_weight",
    "rejected_area_weight",
]

# The lists whose pipe-delimited element counts must always match. All five
# are emitted from one rows.map() in the review app, so a count mismatch means
# the export is malformed rather than merely surprising.
PAIRED_LIST_FIELDS = [
    "biome_type",
    "ecoregion_name",
    "usage_weight",
    "area_weight",
    "n_fixes_inside",
]

# Copied onto every GPS fix. Deliberately short: everything else lives in the
# per-individual profile, because repeating it 134,690 times buys nothing.
PER_FIX_FIELDS = [
    "biome_type",
    "ecoregion_name",
    "usage_weight",
    "area_weight",
    "biome_type_primary",
    "biome_type_unique",
    "ecoregion_primary",
    "n_biomes",
    "assignment_status",
    "assignment_method",
]

# The subset of PAIRED_LIST_FIELDS that survives the join onto the movement
# CSV. n_fixes_inside is checked on the assignment table but deliberately not
# copied onto all 134,690 fixes, so the post-join re-check runs over four
# columns where the pre-join one runs over five.
MERGED_PAIRED_FIELDS = [f for f in PAIRED_LIST_FIELDS if f in PER_FIX_FIELDS]

# Weights are percentages; a little over 100 is rounding, a lot is a bug.
WEIGHT_TOLERANCE_PCT = 100.5


class ValidationError(Exception):
    """Raised when the merged output fails a correctness check."""


# ---------------------------------------------------------------------------
# Loading the Step 2 export
# ---------------------------------------------------------------------------


def find_assignments_file(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.exists():
            sys.exit(f"ERROR: {path} not found.")
        return path

    for candidate in DEFAULT_ASSIGNMENT_PATHS:
        if candidate.exists():
            return candidate

    sys.exit(
        "ERROR: no biome assignment export found. Looked for:\n  "
        + "\n  ".join(str(p) for p in DEFAULT_ASSIGNMENT_PATHS)
        + "\n\nRun the Step 2 review app (gee/01_biome_review_app.js), run its\n"
        "export task, download the file from Drive into this directory, or pass\n"
        "--assignments <path>."
    )


def load_assignment_records(path: Path) -> list[dict]:
    """Extract per-feature property dicts from either export format."""
    if path.suffix.lower() in (".geojson", ".json"):
        with path.open(encoding="utf-8") as fh:
            payload = json.load(fh)

        features = payload.get("features")
        if features is None:
            sys.exit(f"ERROR: {path} is not a GeoJSON FeatureCollection.")
        return [f.get("properties") or {} for f in features]

    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
        # Earth Engine's CSV export carries geometry in a `.geo` column and an
        # opaque `system:index`; neither is wanted here.
        frame = frame.drop(columns=[c for c in (".geo", "system:index")
                                    if c in frame.columns])
        return frame.to_dict("records")

    sys.exit(f"ERROR: unsupported assignment file type: {path.suffix}")


def build_assignment_table(records: list[dict]) -> pd.DataFrame:
    """Collapse the per-contour export to one authoritative row per individual.

    The Step 2 app stamps the same assignment onto every contour belonging to an
    individual -- both isopleths, every temporal segment, the MCP -- so the many
    rows per individual are expected to agree. Disagreement means the export was
    stitched together from more than one review session, which would silently
    pick a winner here, so it is raised instead.
    """
    if not records:
        sys.exit("ERROR: the assignment export contains no features.")

    frame = pd.DataFrame(records)

    missing = [c for c in ["individual_id", "biome_type", "ecoregion_name"]
               if c not in frame.columns]
    if missing:
        sys.exit(
            f"ERROR: assignment export is missing column(s): {', '.join(missing)}.\n"
            "Was it produced by gee/01_biome_review_app.js?"
        )

    # An export made before the weight columns existed would otherwise fail
    # later with a confusing "unequal element counts" error, because the
    # missing columns get filled with a single empty element. Say what is
    # actually wrong instead.
    stale = [f for f in ("usage_weight", "area_weight") if f not in frame.columns]
    if stale:
        sys.exit(
            f"ERROR: the assignment export has no {', '.join(stale)} column.\n"
            "It predates the weighted-assignment schema. Re-run the export from\n"
            "the current gee/01_biome_review_app.js, which emits usage_weight and\n"
            "area_weight alongside biome_type and ecoregion_name."
        )

    for field in ASSIGNMENT_FIELDS:
        if field not in frame.columns:
            frame[field] = ""
    frame = frame.fillna({field: "" for field in ASSIGNMENT_FIELDS})

    frame["individual_id"] = frame["individual_id"].astype(int)

    # Rows with a blank biome are individuals that were never confirmed; the
    # Step 2 export already filters them out, but a hand-edited file might not.
    frame = frame[frame["biome_type"].astype(str).str.len() > 0]

    conflicts = []
    rows = []
    for ind_id, group in frame.groupby("individual_id"):
        unique = group[ASSIGNMENT_FIELDS].drop_duplicates()
        if len(unique) > 1:
            # Name the field that actually diverged. Reporting only biome_type
            # would be actively misleading now that weights and flags are part
            # of the comparison -- the biome can agree while a weight does not.
            differing = [
                field for field in ASSIGNMENT_FIELDS
                if group[field].astype(str).nunique() > 1
            ]
            detail = "; ".join(
                f"{field}={sorted(set(group[field].astype(str)))[:3]}"
                for field in differing
            )
            conflicts.append(f"  ID {ind_id}: {detail}")
        row = unique.iloc[0].to_dict()
        row["individual_id"] = int(ind_id)
        # Descriptive, not part of the assignment, so it is taken rather than
        # consistency-checked.
        if "study_name" in group.columns:
            row["study_name"] = group["study_name"].iloc[0]
        rows.append(row)

    if conflicts:
        raise ValidationError(
            "Conflicting assignments for the same individual:\n"
            + "\n".join(conflicts)
            + "\nRe-export from a single review session."
        )

    table = pd.DataFrame(rows)

    # Element 0 of every list is the dominant ecoregion, because the review app
    # emits all four lists ordered by the ranking weight it was set to.
    table["biome_type_primary"] = (
        table["biome_type"].astype(str).str.split("|").str[0]
    )
    table["ecoregion_primary"] = (
        table["ecoregion_name"].astype(str).str.split("|").str[0]
    )
    table["n_biomes"] = table["biome_type"].astype(str).str.split("|").apply(len)

    # Distinct coarse classes, for the common "is this a forest animal" filter
    # where the positional repeat of a biome name is noise rather than signal.
    table["biome_type_unique"] = (
        table["biome_type"].astype(str)
        .apply(lambda v: "|".join(dict.fromkeys(v.split("|"))))
    )
    return table


def _element_counts(series: pd.Series) -> pd.Series:
    return series.astype(str).str.split("|").apply(len)


def check_pairing(table: pd.DataFrame) -> None:
    """Enforce equal element counts across every paired list column.

    This is the invariant the whole schema rests on: element i of every list
    describes the same ecoregion. If the counts ever diverge, a downstream
    zip() would silently pair a biome with another ecoregion's weight, so this
    fails loudly rather than warning.
    """
    counts = {f: _element_counts(table[f]) for f in PAIRED_LIST_FIELDS}
    reference = counts[PAIRED_LIST_FIELDS[0]]

    mismatch_mask = pd.Series(False, index=table.index)
    for field in PAIRED_LIST_FIELDS[1:]:
        mismatch_mask |= counts[field] != reference

    if mismatch_mask.any():
        detail = []
        for idx in table[mismatch_mask].index:
            row = table.loc[idx]
            sizes = ", ".join(
                f"{f}={counts[f].loc[idx]}" for f in PAIRED_LIST_FIELDS
            )
            detail.append(f"  ID {int(row['individual_id'])}: {sizes}")
        raise ValidationError(
            "All paired list columns must have equal element counts.\n"
            + "\n".join(detail)
        )

    blank = table[
        (table["biome_type"].astype(str).str.strip() == "")
        | (table["ecoregion_name"].astype(str).str.strip() == "")
    ]
    if not blank.empty:
        raise ValidationError(
            "Blank biome_type or ecoregion_name for ID(s): "
            + ", ".join(str(int(i)) for i in blank["individual_id"])
        )

    # Weights must parse as numbers, or the aligned lists are decorative.
    suspicious = []
    for field in ("usage_weight", "area_weight"):
        for idx in table.index:
            ind_id = int(table.at[idx, "individual_id"])
            values = []
            for token in str(table.at[idx, field]).split("|"):
                try:
                    values.append(float(token))
                except ValueError:
                    raise ValidationError(
                        f"{field} for ID {ind_id} contains a non-numeric "
                        f"element: {token!r}"
                    )

            # -1 is the documented "not applicable" marker for the point-only
            # individuals, which have no home range polygon to take a share of.
            real = [v for v in values if v >= 0]
            if any(v > WEIGHT_TOLERANCE_PCT for v in real):
                suspicious.append(f"ID {ind_id} {field}: element > 100%")
            elif sum(real) > WEIGHT_TOLERANCE_PCT:
                suspicious.append(
                    f"ID {ind_id} {field}: sums to {sum(real):.1f}%"
                )

    if suspicious:
        print("  WARNING: weight values outside the expected 0-100% range:")
        for line in suspicious[:10]:
            print(f"    {line}")
        if len(suspicious) > 10:
            print(f"    ... and {len(suspicious) - 10} more")


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


def load_covariates(path_arg: str | None) -> pd.DataFrame | None:
    """Load the Tier 2 habitat table, if one was exported.

    Returns None when no file is given or found. Habitat covariates are an
    enrichment, not a prerequisite -- the biome assignment stands on its own,
    so a missing file downgrades the profile rather than failing the run.
    """
    if path_arg:
        path = Path(path_arg).expanduser()
        if not path.exists():
            sys.exit(f"ERROR: {path} not found.")
    else:
        candidates = [
            BASE_DIR / "individual_covariates.csv",
            BASE_DIR / "gee_export" / "individual_covariates.csv",
        ]
        path = next((c for c in candidates if c.exists()), None)
        if path is None:
            return None

    frame = pd.read_csv(path)
    frame = frame.drop(columns=[c for c in (".geo", "system:index")
                                if c in frame.columns])
    if "individual_id" not in frame.columns:
        sys.exit(f"ERROR: {path} has no individual_id column.")

    frame["individual_id"] = frame["individual_id"].astype(int)
    print(f"  Habitat covariates from {path.name}: "
          f"{len(frame)} individuals, {len(frame.columns) - 1} fields")
    return frame


def build_profile(
    table: pd.DataFrame,
    covariate_frame: pd.DataFrame | None,
    sex_lookup: pd.Series,
    movement: pd.DataFrame,
) -> pd.DataFrame:
    """One row per individual: the assignment, what was rejected, and habitat.

    This is where everything that is a property of the *animal* rather than of
    a *fix* belongs. Keeping it out of the movement CSV is what stops that file
    growing a column every time another covariate is added.
    """
    profile = table.copy()
    profile["sex"] = profile["individual_id"].map(sex_lookup)

    fixes = movement.groupby(ID_COL).size().rename("n_fixes_total")
    profile = profile.merge(
        fixes, how="left", left_on="individual_id", right_index=True
    )

    if covariate_frame is not None:
        overlap = [c for c in covariate_frame.columns
                   if c != "individual_id" and c in profile.columns]
        joinable = covariate_frame.drop(columns=overlap)
        profile = profile.merge(joinable, how="left", on="individual_id")

    lead = ["individual_id", "study_name", "sex", "n_fixes_total",
            "biome_type", "ecoregion_name", "usage_weight", "area_weight",
            "biome_type_primary", "ecoregion_primary", "biome_type_unique",
            "n_biomes"]
    ordered = [c for c in lead if c in profile.columns]
    ordered += [c for c in profile.columns if c not in ordered]
    return profile[ordered]


def load_sex_lookup() -> pd.Series:
    info = pd.read_csv(ADDITIONAL_INFO_CSV)
    # The file is padded with several hundred blank trailing rows.
    info = info.dropna(subset=["Sex"])
    info["ID"] = info["ID"].astype(int)
    return info.set_index("ID")["Sex"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--assignments",
        help="Path to biome_assignments_export.geojson or .csv from Step 2.",
    )
    parser.add_argument(
        "--covariates",
        help="Path to individual_covariates.csv from the review app's Tier 2 "
             "export. Optional; the profile omits habitat columns without it.",
    )
    parser.add_argument(
        "--output", default=str(DEFAULT_OUTPUT),
        help="Destination CSV (default: jaguar_movement_data_with_biome.csv).",
    )
    parser.add_argument(
        "--profile", default=str(DEFAULT_PROFILE),
        help="Destination per-individual profile CSV "
             "(default: jaguar_individual_profile.csv).",
    )
    parser.add_argument(
        "--allow-missing", action="store_true",
        help="Warn instead of failing when some individuals have no assignment.",
    )
    args = parser.parse_args()

    # ---- assignments ------------------------------------------------------
    assignments_path = find_assignments_file(args.assignments)
    print(f"--- Loading assignments from {assignments_path.name} ---")

    records = load_assignment_records(assignments_path)
    table = build_assignment_table(records)
    check_pairing(table)

    covariate_frame = load_covariates(args.covariates)
    if covariate_frame is None:
        print("  No habitat covariate export found — profile will omit Tier 2 "
              "columns. Run the review app's 'Export habitat covariates' task "
              "to add them.")

    print(f"  {len(records)} features -> {len(table)} individuals with an assignment")
    method_counts = table["assignment_method"].value_counts()
    for method, count in method_counts.items():
        print(f"    {method or '(unspecified)'}: {count}")

    # ---- movement data ----------------------------------------------------
    print("\n--- Loading movement data ---")
    movement = pd.read_csv(
        MOVEMENT_CSV, lineterminator=MOVEMENT_LINETERMINATOR, low_memory=False
    )
    movement.columns = [c.strip() for c in movement.columns]
    print(f"  {len(movement)} rows, {movement[ID_COL].nunique()} individuals")

    if len(movement) != EXPECTED_ROWS:
        print(f"  WARNING: expected {EXPECTED_ROWS} rows, read {len(movement)}")

    # ---- join -------------------------------------------------------------
    print("\n--- Joining ---")
    movement[ID_COL] = movement[ID_COL].astype(int)

    merged = movement.merge(
        table[["individual_id"] + PER_FIX_FIELDS],
        how="left",
        left_on=ID_COL,
        right_on="individual_id",
    ).drop(columns=["individual_id"])

    sex_lookup = load_sex_lookup()
    merged["sex"] = merged[ID_COL].map(sex_lookup)

    # ---- validation -------------------------------------------------------
    print("\n--- Validation ---")
    errors = []

    if len(merged) != len(movement):
        errors.append(
            f"Row count changed during join: {len(movement)} -> {len(merged)}. "
            "The assignment table probably has duplicate individual_id rows."
        )
    else:
        print(f"  Row count preserved: {len(merged)}")

    unassigned = sorted(
        merged.loc[merged["biome_type"].isna(), ID_COL].unique().tolist()
    )
    if unassigned:
        message = (
            f"{len(unassigned)} individual(s) have no biome assignment: "
            + ", ".join(str(i) for i in unassigned)
        )
        if args.allow_missing:
            print(f"  WARNING: {message}")
        else:
            errors.append(
                message
                + "\n    Confirm them in the Step 2 review app and re-export, "
                "or re-run with --allow-missing."
            )
    else:
        print(f"  All {merged[ID_COL].nunique()} individuals assigned")

    missing_sex = sorted(merged.loc[merged["sex"].isna(), ID_COL].unique().tolist())
    if missing_sex:
        errors.append(
            "Missing sex for ID(s): " + ", ".join(str(i) for i in missing_sex)
        )
    else:
        print("  Sex populated for every row")

    # Re-check pairing on the merged frame: a bad join would show up here even
    # if the assignment table itself was internally consistent.
    populated = merged.dropna(subset=["biome_type"])
    reference = populated["biome_type"].str.split("|").apply(len)
    bad_pairs = pd.Series(False, index=populated.index)
    for field in MERGED_PAIRED_FIELDS[1:]:
        bad_pairs |= populated[field].astype(str).str.split("|").apply(len) != reference

    if bad_pairs.any():
        errors.append(
            f"{int(bad_pairs.sum())} row(s) have unequal element counts across "
            + ", ".join(MERGED_PAIRED_FIELDS)
        )
    else:
        print(f"  All {len(MERGED_PAIRED_FIELDS)} paired list columns align "
              f"on every row")

    if errors:
        print("\nFAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1

    # ---- write ------------------------------------------------------------
    output_path = Path(args.output)
    # Written with standard LF terminators rather than the input's CR, so the
    # output loads without a `lineterminator` argument downstream.
    merged.to_csv(output_path, index=False)
    size_mb = output_path.stat().st_size / 1e6
    print(f"\n--- Wrote {output_path.name} ({len(merged)} rows, "
          f"{len(merged.columns)} cols, {size_mb:.1f} MB) ---")

    profile = build_profile(table, covariate_frame, sex_lookup, movement)
    profile_path = Path(args.profile)
    profile.to_csv(profile_path, index=False)
    profile_mb = profile_path.stat().st_size / 1e6
    print(f"--- Wrote {profile_path.name} ({len(profile)} rows, "
          f"{len(profile.columns)} cols, {profile_mb:.2f} MB) ---")
    print(f"    Join to the movement CSV on '{ID_COL}'.")

    # ---- summary ----------------------------------------------------------
    print("\n--- Biome distribution (individuals, by primary biome) ---")
    per_individual = merged.drop_duplicates(subset=[ID_COL])
    for biome, count in per_individual["biome_type_primary"].value_counts().items():
        print(f"  {count:3d}  {biome}")

    print("\n--- Fixes per primary biome ---")
    for biome, count in merged["biome_type_primary"].value_counts().items():
        print(f"  {count:7d}  {biome}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValidationError as exc:
        print(f"\nVALIDATION ERROR: {exc}")
        sys.exit(1)
