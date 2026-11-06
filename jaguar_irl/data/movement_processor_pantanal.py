"""Select auditable Pantanal cohorts and observed approximately two-hour fixes.

Run from the repository root:
    python -m jaguar_irl.data.movement_processor_pantanal --help

This is a data pipeline, independent of the legacy model prototypes. Original
animal IDs, event IDs, timestamps and elapsed gaps are preserved in CSV exports.
See README_PANTANAL.md for threshold definitions and validation assumptions.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import json
import logging
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import median, pvariance

from pyproj import CRS, Transformer

from .pantanal_temporal import TemporalConfig, find_week_candidates
from .pantanal_calendar import CALENDAR_FIELDS, summarize_calendar
from .pantanal_metric_notes import METRIC_SOURCES
from .pantanal_spatial import (SpatialConfig, build_full_study_mcps,
    grow_cluster_candidates, extent_for_members, export_geojson, polygon_distance_m)

LOG = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
PANTANAL_IDS = (
    12,13,14,15,18,19,22,23,25,27,28,29,30,31,32,33,41,51,52,53,54,55,56,
    57,59,60,61,68,69,74,75,79,81,84,86,87,88,91,92,101,102,103,104,105,
    106,107,108,109,110,111,112,113,114,115,116,117,
)
PANTANAL_STUDIES = (
    "Jaguar_Taiama", "jaguar_Oncafari Project", "Panthera_Pantanal-Jaguar-Project",
    "Pantanal", "Paraguayan Pantanal", "Rio Negro", "Sao Bento",
)
SOURCES = [
    {"title":"Signer et al. (2019): regular sampling bursts","url":"https://doi.org/10.1002/ece3.4823"},
    {"title":"Hofmann et al. (2024): incomplete movement data","url":"https://doi.org/10.1186/s40462-024-00476-8"},
    {"title":"Roberts et al. (2017): structured cross-validation","url":"https://doi.org/10.1111/ecog.02881"},
    {"title":"Frair et al. (2010): habitat-dependent GPS data loss","url":"https://doi.org/10.1098/rstb.2010.0084"},
    {"title":"Calenge: adehabitatHR MCP radial trimming convention","url":"https://stat.ethz.ch/CRAN/web/packages/adehabitatHR/vignettes/adehabitatHR.pdf"},
    {"title":"Cavalcanti & Gese (2009): southern Pantanal jaguar ranges","url":"https://digitalcommons.unl.edu/icwdm_usdanwrc/880/"},
    {"title":"Morato et al. (2016): jaguar space use and estimator limitations","url":"https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0168176"},
    *METRIC_SOURCES,
]


@dataclass
class ProcessorConfig:
    csv_path: str = str(ROOT / "data" / "jaguar_movement_data.csv")
    output_dir: str = str(ROOT / "analysis" / "pantanal_selection")
    individual_ids: tuple[int,...] = PANTANAL_IDS
    top_n: int = 7
    report_limit: int | None = None  # None renders every generated candidate.
    min_group_members: int = 2
    temporal: TemporalConfig = field(default_factory=TemporalConfig)
    spatial: SpatialConfig = field(default_factory=SpatialConfig)


def json_default(value):
    if isinstance(value,(datetime,Path)):
        return str(value)
    if hasattr(value,"item"):
        return value.item()
    raise TypeError(type(value).__name__)


def write_csv(path, rows):
    rows = list(rows)
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open("w",newline="",encoding="utf-8") as handle:
        writer = csv.DictWriter(handle,fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(v,default=json_default) if isinstance(v,(list,tuple,dict)) else v
                             for k,v in row.items()})


def count_evenness(counts):
    """Jain's index: 1 means equal per-animal contributions; also report spread."""
    values = list(counts)
    if not values or min(values)<=0:
        raise ValueError("Point counts must be positive")
    total = sum(values)
    avg = total/len(values)
    return {"length_evenness":total**2/(len(values)*sum(n*n for n in values)),
            "point_count_cv":math.sqrt(pvariance(values))/avg,
            "min_max_point_ratio":min(values)/max(values)}


class MovementProcessor:
    def __init__(self, config: ProcessorConfig | None = None):
        self.config = config or ProcessorConfig()
        if not 3<=self.config.top_n<=7:
            raise ValueError("top_n must be between 3 and 7")
        if self.config.report_limit is not None and self.config.report_limit < self.config.top_n:
            raise ValueError("report_limit must include at least the top_n groups")
        self.records = []
        self.parse_audit = Counter()
        self.individual_sexes = {}

    def parse(self):
        """Read exactly the requested cohort, with explicit study provenance."""
        wanted = set(self.config.individual_ids)
        seen,study_ids = set(),set()
        self.records = []
        self.parse_audit = Counter()
        with Path(self.config.csv_path).open(newline="",encoding="utf-8-sig") as handle:
            for line,row in enumerate(csv.DictReader(handle),2):
                individual = int(row["individual.local.identifier (ID)"])
                study = row["study.name"].strip()
                if study in PANTANAL_STUDIES:
                    study_ids.add(individual)
                if individual not in wanted:
                    continue
                self.parse_audit["raw_cohort_rows"] += 1
                try:
                    timestamp = datetime.strptime(row["timestamp"],"%m/%d/%y %H:%M")
                    lon,lat = float(row["location.long"]),float(row["location.lat"])
                    if not (-180<=lon<=180 and -90<=lat<=90):
                        raise ValueError("coordinate outside WGS84 range")
                except (ValueError,TypeError):
                    self.parse_audit["invalid_rows"] += 1
                    continue
                if study not in PANTANAL_STUDIES:
                    raise ValueError(f"ID {individual} has unexpected study {study!r}")
                key = (individual,timestamp)
                if key in seen:
                    raise ValueError(f"Duplicate individual/timestamp at source row {line}; resolve explicitly")
                seen.add(key)
                self.records.append({"individual_id":individual,"timestamp":timestamp,
                    "longitude":lon,"latitude":lat,"event_id":row["Event_ID"],"study":study,
                    "country":row["country"],"source_row":line})
        actual = {row["individual_id"] for row in self.records}
        if actual!=wanted:
            raise ValueError(f"Missing requested individuals: {sorted(wanted-actual)}")
        if wanted==set(PANTANAL_IDS) and study_ids!=wanted:
            raise ValueError(f"Requested IDs and study cohort disagree: {sorted(study_ids^wanted)}")
        self.records.sort(key=lambda row:(row["individual_id"],row["timestamp"]))
        LOG.info("Verified %d individuals, %d fixes across %d studies",len(actual),len(self.records),
                 len({r["study"] for r in self.records}))
        return self.records

    @staticmethod
    def window_rank(row):
        return (row["selected_fixes"],-row["short_fragment_loss"],
                -row["affected_point_fraction"],-row["n_subtrajectories"],
                -row["mean_interval_error_hours"])

    def candidate_extent(self, mcps, ids, windows, allow_over_budget=False):
        """Include selected fixes outside MCP95 before checking the map budget."""
        points = [(p["longitude"],p["latitude"]) for w in windows for p in w["points"]]
        extent = extent_for_members(mcps,ids,self.config.spatial,extra_lonlat=points)
        if not extent["within_budget"] and not allow_over_budget:
            return None
        return {"bounds":extent["bounds_m"],"width_km":extent["width_km"],
                "height_km":extent["height_km"],"area_km2":extent["area_km2"],
                "grid_cols":extent["grid_columns"],"grid_rows":extent["grid_rows"],
                "n_grid_cells":extent["grid_cells"],"epsg":CRS(self.config.spatial.metric_crs).to_epsg(),
                "bounds_wgs84":extent["bounds_wgs84"]}

    def candidate_pools(self, candidates):
        """One best window per animal, grouped by its start month/year.

        This anchor controls candidate generation only. Observed month/year
        coverage is computed separately from retained timestamps.
        """
        by_month = defaultdict(list)
        for row in candidates:
            by_month[row["month"]].append(row)
        for month, rows in sorted(by_month.items()):
            for year in [None, *sorted({row["year"] for row in rows})]:
                best = {}
                for row in rows:
                    if year is not None and row["year"] != year:
                        continue
                    ident = row["individual_id"]
                    # Prefer an available qualifying week over a relaxed week,
                    # even when a shorter-span relaxed window has more points.
                    priority = (not row.get("requires_week_relaxation", False), self.window_rank(row))
                    if ident not in best or priority > (
                            not best[ident].get("requires_week_relaxation", False), self.window_rank(best[ident])):
                        best[ident] = row
                yield month, best

    def build_group(self, month, ids, best, mcps, extent, spatial_codes=(), spatial_text="",
                    new_ids=(), method="bounded_growth", pair_gap_km=None):
        windows = [best[i] for i in ids]
        counts = [row["selected_fixes"] for row in windows]
        evenness = count_evenness(counts)
        starts = [row["observed_start"] for row in windows]
        ends = [row["observed_end"] for row in windows]
        full_starts = [datetime.fromisoformat(mcps[i].full_start) for i in ids]
        full_ends = [datetime.fromisoformat(mcps[i].full_end) for i in ids]
        coverage = summarize_calendar(p for window in windows for p in window["points"])
        start_years = sorted({row["year"] for row in windows})
        seasons = {12:"summer",1:"summer",2:"summer",3:"autumn",4:"autumn",5:"autumn",
                   6:"winter",7:"winter",8:"winter",9:"spring",10:"spring",11:"spring"}
        codes, explanations, flagged = list(spatial_codes), [], set()
        for window in windows:
            text = " ".join(filter(None, (window.get("support_violation_text", ""),
                                         window.get("violation_text", ""))))
            if text:
                flagged.add(window["individual_id"])
                explanations.append(f"ID {window['individual_id']}: {text}")
            codes.extend(window.get("support_violation_codes", []))
            codes.extend(window.get("violation_codes", []))
        if spatial_text:
            explanations.append(spatial_text)
            flagged.update(ids)  # A joint map exception applies to the pair.
        sexes = Counter(self.individual_sexes.get(i, {}).get("sex", "unknown") for i in set(ids))
        return {"month":month,"month_name":calendar.month_name[month],
            "grouping_month":month,"grouping_years":start_years,"same_start_year":len(start_years)==1,
            "grouping_calendar_season":f"austral {seasons[month]}",
            "calendar_seasons":sorted({f"austral {seasons[m]}" for m in coverage["observed_months"]}),
            "ids":";".join(map(str,ids)),
            "n_individuals":len(ids),"total_fixes":sum(counts),"min_fixes":min(counts),
            "n_males":sexes["male"],"n_females":sexes["female"],"n_unknown_sex":sexes["unknown"],
            "max_fixes":max(counts),"median_density":median(row["coverage_fraction"] for row in windows),
            **evenness,"balanced_fixes_score":sum(counts)*evenness["length_evenness"],
            "n_subtrajectories":sum(row["n_subtrajectories"] for row in windows),
            "selected_start":min(starts),"selected_end":max(ends),
            "selected_span_days":(max(ends)-min(starts)).total_seconds()/86400,
            **coverage,"years":";".join(map(str,coverage["observed_years"])),
            "full_start":min(full_starts),"full_end":max(full_ends),
            "full_span_days":(max(full_ends)-min(full_starts)).total_seconds()/86400,
            "median_affected_fraction":median(row["affected_point_fraction"] for row in windows),
            "max_short_loss":max(row["short_fragment_loss"] for row in windows),
            "shared_week_overlap_days":max(0,(min(ends)-max(starts)).total_seconds()/86400),
            "support_warning":any(w.get("support_warning", False) for w in windows),
            "has_violations":bool(codes),"violation_codes":sorted(set(codes)),
            "violation_text":" ".join(explanations),
            "flagged_individual_ids":";".join(map(str, sorted(flagged))),
            "new_individual_ids":";".join(map(str, sorted(set(ids) & set(new_ids)))),
            "spatial_violation_codes":list(spatial_codes),"spatial_violation_text":spatial_text,
            "pair_mcp_gap_km":pair_gap_km,"generation_method":method,
            **extent,"windows":windows}

    def spatial_exceptions(self, extent, gap_km):
        cfg = self.config.spatial
        codes, text = [], []
        if max(extent["width_km"], extent["height_km"]) > cfg.max_extent_side_km + 1e-9:
            codes.append("map_side_limit")
            text.append(f"Map rectangle is {extent['width_km']:.1f} × {extent['height_km']:.1f} km; "
                        f"at least one side exceeds the {cfg.max_extent_side_km:g} km limit.")
        if extent["area_km2"] > cfg.max_extent_area_km2 + 1e-9:
            codes.append("map_area_limit")
            text.append(f"Map area is {extent['area_km2']:.2f} km², above {cfg.max_extent_area_km2:g} km².")
        if gap_km > cfg.growth_buffer_km + 1e-9:
            codes.append("mcp_proximity_limit")
            text.append(f"MCP-to-MCP gap is {gap_km:.2f} km, above the {cfg.growth_buffer_km:g} km growth limit.")
        return codes, " ".join(text)

    def rank_groups(self, candidates, mcps, secondary_for_ids=None):
        """Rank by score; a secondary list must introduce a main-absent animal.

        Ordinary growth retains every spatial cap. If it cannot represent a
        secondary animal within a month/year pool, a minimum-area pair is
        considered, preferring neighbours within the configured growth gap.
        Any cap/gap exception is measured and flagged; such pairs never grow.
        """
        secondary = secondary_for_ids is not None
        new_ids = set(secondary_for_ids or ())
        groups, signatures = [], set()
        for month, best in self.candidate_pools(candidates):
            pool_groups = []
            for cluster in grow_cluster_candidates(mcps,self.config.spatial,
                    available_ids=best,min_members=self.config.min_group_members):
                ids = tuple(sorted(cluster["members"]))
                if secondary and not (set(ids) & new_ids):
                    continue
                extent = self.candidate_extent(mcps,ids,[best[i] for i in ids])
                if extent is not None:
                    pool_groups.append(self.build_group(month, ids, best, mcps, extent, new_ids=new_ids))
            if secondary:
                represented = {int(i) for g in pool_groups for i in g["ids"].split(";")}
                for ident in sorted((new_ids & best.keys()) - represented):
                    options = []
                    for other in sorted(best):
                        if other == ident:
                            continue
                        ids = tuple(sorted((ident, other)))
                        extent = self.candidate_extent(mcps, ids, [best[i] for i in ids], allow_over_budget=True)
                        gap = polygon_distance_m(mcps[ident].polygon_xy, mcps[other].polygon_xy)/1000
                        options.append((gap > self.config.spatial.growth_buffer_km + 1e-9,
                                        extent["area_km2"], gap, other, ids, extent))
                    if options:
                        _, _, gap, _, ids, extent = min(options, key=lambda item:item[:4])
                        codes, text = self.spatial_exceptions(extent, gap)
                        pool_groups.append(self.build_group(month, ids, best, mcps, extent,
                            codes, text, new_ids, "minimum_extent_pair", gap))
            for group in pool_groups:
                # The secondary list must actually relax a weekly/spatial rule;
                # full-record span/month summaries cannot trigger relaxation.
                if secondary and not (group["spatial_violation_codes"] or
                        any(w.get("requires_week_relaxation", False) for w in group["windows"])):
                    continue
                signature = tuple((w["individual_id"],w["start"],w["end"]) for w in group["windows"])
                if signature not in signatures:
                    signatures.add(signature)
                    groups.append(group)
        groups.sort(key=lambda g:(-g["balanced_fixes_score"],-g["median_density"],
                    g["median_affected_fraction"],g["area_km2"],g["month"],g["ids"]))
        prefix = "R" if secondary else "G"
        for rank, group in enumerate(groups, 1):
            group.update(rank=rank, overall_rank=rank, group_id=f"{prefix}{rank:02d}",
                         candidate_list="relaxed" if secondary else "main")
        return groups[:self.config.top_n], groups

    def groups_for_report(self, selected, all_groups):
        """Display score rank order; the first seven are no longer reordered."""
        decorated = [dict(group, rank=position, overall_rank=position,
            group_id=f"{'R' if group.get('candidate_list') == 'relaxed' else 'G'}{position:02d}",
            report_order=position, is_shortlisted=position<=self.config.top_n,
            is_reported=self.config.report_limit is None or position<=self.config.report_limit)
            for position,group in enumerate(all_groups,1)]
        return [g for g in decorated if g["is_reported"]], decorated

    def write_selection_checkpoint(self, temporal, groups, mcps, *, checkpoint_root=None,
                                   collar_metadata_path=None):
        """Add a source checkpoint without changing selector/report products."""
        from .pantanal_checkpoint import write_selection_checkpoint
        return write_selection_checkpoint(
            self.config, self.records, temporal, groups, mcps, self.parse_audit,
            checkpoint_root=checkpoint_root,
            collar_metadata_path=collar_metadata_path or ROOT / "data" / "Jaguar_additional_information_fixed.csv")

    def run_pipeline(self, *, checkpoint_only=False, checkpoint_root=None, collar_metadata_path=None):
        self.parse()
        from .pantanal_checkpoint import load_individual_sexes, SELECTION_POLICY
        collar_metadata_path = collar_metadata_path or ROOT / "data" / "Jaguar_additional_information_fixed.csv"
        self.individual_sexes = load_individual_sexes(collar_metadata_path, self.config.individual_ids)
        out = Path(self.config.output_dir)
        out.mkdir(parents=True,exist_ok=True)
        data_dir = out / "data"
        data_dir.mkdir(parents=True,exist_ok=True)
        temporal = find_week_candidates(self.records,self.config.temporal)
        for window in [*temporal["candidates"], *temporal["relaxed_candidates"]]:
            window.update(summarize_calendar(window["points"]))
            window.update(grouping_year=window["year"], grouping_month=window["month"])
        LOG.info("Temporal selection: %d individual-month windows",len(temporal["candidates"]))
        mcps = build_full_study_mcps(self.records,self.config.individual_ids,self.config.spatial)
        selected,all_groups = self.rank_groups(temporal["candidates"],mcps)
        report_groups,all_groups = self.groups_for_report(selected,all_groups)
        main_ids = {int(i) for g in all_groups for i in g["ids"].split(";")}
        missing_ids = set(self.config.individual_ids) - main_ids
        relaxed_selected, relaxed_all = self.rank_groups(
            [*temporal["candidates"], *temporal["relaxed_candidates"]], mcps,
            secondary_for_ids=missing_ids)
        relaxed_groups, relaxed_all = self.groups_for_report(relaxed_selected, relaxed_all)
        relaxed_ids = {int(i) for g in relaxed_all for i in g["ids"].split(";")}
        by_id = {row["individual_id"]:row for row in temporal["individuals"]}
        for ident, audit in by_id.items():
            audit.update(self.individual_sexes[ident])
            audit["in_main_groups"] = ident in main_ids
            audit["in_relaxed_groups"] = ident in relaxed_ids
            if ident in main_ids:
                reason = "Represented in the main candidate list."
            elif ident in relaxed_ids:
                reason = "Represented only after relaxing a weekly or spatial requirement; see the relaxed groups."
            else:
                reason = audit.get("protected_exclusion_text") or (
                    "A protected-compliant window exists, but no group with another individual "
                    "in the same window-start calendar month was generated.")
            audit["group_membership_reason"] = reason
        checkpoint = self.write_selection_checkpoint(
            temporal, [*all_groups, *relaxed_all], mcps,
            checkpoint_root=checkpoint_root, collar_metadata_path=collar_metadata_path)
        LOG.info("Selection checkpoint: %s", checkpoint)
        if checkpoint_only:
            # Existing selection_manifest, CSVs, HTML, GeoJSON and PNGs are not
            # opened for writing in this mode. Selection/ranking above is unchanged.
            return {"checkpoint_dir": str(checkpoint)}
        members,points,trajectories = [],[],[]
        for group in [*report_groups, *relaxed_groups]:
            project = Transformer.from_crs(4326,group["epsg"],always_xy=True)
            xmin,ymin,xmax,ymax = group["bounds"]
            for window in group["windows"]:
                ident = window["individual_id"]
                meta = by_id[ident]
                full_start,full_end = map(datetime.fromisoformat,(mcps[ident].full_start,mcps[ident].full_end))
                members.append({"group_id":group["group_id"],"individual_id":ident,"study":mcps[ident].study,
                    **self.individual_sexes[ident],
                    "year":window["year"],"month":window["month"],
                    "grouping_year":window["year"],"grouping_month":window["month"],
                    **{field:window[field] for field in CALENDAR_FIELDS},
                    "selected_start":window["observed_start"],"selected_end":window["observed_end"],
                    "selected_duration_days":(window["observed_end"]-window["observed_start"]).total_seconds()/86400,
                    "usable_duration_hours":window["usable_duration_hours"],
                    "window_start":window["start"],"window_end":window["end"],
                    "window_duration_days":window["window_duration_days"],
                    "reference_window_duration_days":window.get("reference_window_duration_days",self.config.temporal.week_days),
                    "window_end_exclusive":window.get("window_end_exclusive",False),
                    "crosses_month_boundary":window["crosses_month_boundary"],
                    "crosses_year_boundary":window["crosses_year_boundary"],
                    "full_start":full_start,"full_end":full_end,
                    "full_duration_days":(full_end-full_start).total_seconds()/86400,
                    "retained_fixes":window["selected_fixes"],"n_subtrajectories":window["n_subtrajectories"],
                    "affected_point_fraction":window["affected_point_fraction"],
                    "retained_affected_points":window["retained_affected_points"],
                    "affected_point_denominator":window["affected_point_denominator"],
                    "affected_point_budget":window["affected_point_budget"],
                    "retained_affected_point_fraction":window["retained_affected_point_fraction"],
                    "affected_point_scope":window["affected_point_scope"],
                    "parent_affected_point_fraction":window["parent_affected_point_fraction"],
                    "max_segment_affected_fraction":window["max_segment_affected_fraction"],
                    "max_source_gap_hours":window["max_source_gap_hours"],
                    "short_fragment_loss":window["short_fragment_loss"],"qualifying_months":meta["qualifying_months"],
                    "resampled_fixes":window["resampled_fixes"],
                    "expected_fixes":window["expected_fixes"],
                    "coverage_fraction":window["coverage_fraction"],
                    "required_fixes":window["required_fixes"],
                    "required_observed_span_days":window["required_observed_span_days"],
                    "support_warning":window["support_warning"],
                    "support_violation_codes":window["support_violation_codes"],
                    "support_violation_text":window["support_violation_text"],
                    "weekly_violation_codes":window["violation_codes"],
                    "weekly_violation_text":window["violation_text"],
                    "spatial_violation_codes":group["spatial_violation_codes"],
                    "spatial_violation_text":group["spatial_violation_text"],
                    "has_violations":bool(window["support_warning"] or window["violation_codes"] or group["spatial_violation_codes"]),
                    "violation_codes":sorted(set(window["support_violation_codes"] + window["violation_codes"] + group["spatial_violation_codes"])),
                    "violation_text":" ".join(filter(None,(window["support_violation_text"],window["violation_text"],group["spatial_violation_text"]))),
                    "new_to_relaxed_list":ident not in main_ids})
                grouped_points = defaultdict(list)
                for point in window["points"]:
                    x,y = project.transform(point["longitude"],point["latitude"])
                    cell = self.config.spatial.cell_size_m
                    col,row = math.floor((x-xmin)/cell),math.floor((ymax-y)/cell)
                    assert xmin-1e-7<=x<=xmax+1e-7 and ymin-1e-7<=y<=ymax+1e-7
                    # Inclusive outer boundary belongs to the final grid cell.
                    col = min(max(col,0),group["grid_cols"]-1)
                    row = min(max(row,0),group["grid_rows"]-1)
                    assert 0<=col<group["grid_cols"] and 0<=row<group["grid_rows"]
                    item = dict(point,group_id=group["group_id"],grid_col=col,grid_row=row,
                                easting_m=x,northing_m=y,epsg=group["epsg"],cell_size_m=cell)
                    points.append(item)
                    grouped_points[point["trajectory_id"]].append(point)
                segment_meta = {s["trajectory_id"]:s for s in window["segments"]}
                for trajectory_id,values in grouped_points.items():
                    trajectories.append(dict(segment_meta[trajectory_id],group_id=group["group_id"],
                        individual_id=ident,split_group_id=ident))
        scalar = lambda row:{k:v for k,v in row.items() if k not in ("windows","points","segments")}
        export_geojson(mcps,out/"mcp95_full_study.geojson")
        geojson = json.loads((out/"mcp95_full_study.geojson").read_text())
        study_audit = []
        for study in PANTANAL_STUDIES:
            rows = [r for r in self.records if r["study"]==study]
            if rows:
                study_audit.append({"study":study,"n_individuals":len({r["individual_id"] for r in rows}),
                    "raw_fixes":len(rows),"start":min(r["timestamp"] for r in rows),
                    "end":max(r["timestamp"] for r in rows)})
        shortlist_ids = {g["group_id"] for g in report_groups if g["is_shortlisted"]}
        shortlisted = lambda rows:[r for r in rows if r["group_id"] in shortlist_ids]
        main_rows = lambda rows:[r for r in rows if r["group_id"].startswith("G")]
        relaxed_rows = lambda rows:[r for r in rows if r["group_id"].startswith("R")]
        coverage_rows = lambda field:[dict(group_id=g["group_id"],candidate_list=g["candidate_list"],
            rank=g["rank"],is_reported=g["is_reported"],**row)
            for g in [*all_groups,*relaxed_all] for row in g[field]]
        month_coverage_rows = coverage_rows("month_coverage")
        year_month_coverage_rows = coverage_rows("calendar_coverage")
        result = {"config":asdict(self.config),"cohort_audit":study_audit,
            "selection_policy":SELECTION_POLICY,"checkpoint_dir":str(checkpoint),
            "individuals":temporal["individuals"],"candidate_groups":[scalar(g) for g in selected],
            "report_groups":[scalar(g) for g in report_groups],
            "generated_group_count":len(all_groups),"reported_group_count":len(report_groups),
            "best_same_year_candidate":next((scalar(g) for g in all_groups if g["same_year"]),None),
            "group_members":shortlisted(members),"selected_points":shortlisted(points),
            "report_group_members":main_rows(members),"report_points":main_rows(points),
            "relaxed_report_groups":[scalar(g) for g in relaxed_groups],
            "relaxed_group_members":relaxed_rows(members),"relaxed_points":relaxed_rows(points),
            "relaxed_generated_group_count":len(relaxed_all),
            "relaxed_reported_group_count":len(relaxed_groups),
            "group_month_coverage":month_coverage_rows,
            "group_year_month_coverage":year_month_coverage_rows,
            "membership_summary":{"cohort_count":len(by_id),"main_individual_ids":sorted(main_ids),
                "relaxed_only_individual_ids":sorted(relaxed_ids-main_ids),
                "unrepresented_individual_ids":sorted(set(by_id)-main_ids-relaxed_ids)},
            "mcps_geojson":geojson,"sources":SOURCES,
            "parse_audit":dict(self.parse_audit),"provenance":{
                "input_sha256":hashlib.sha256(Path(self.config.csv_path).read_bytes()).hexdigest(),
                "collar_metadata_sha256":hashlib.sha256(Path(collar_metadata_path).read_bytes()).hexdigest()
                    if Path(collar_metadata_path).is_file() else None,
                "generated_utc":datetime.now(timezone.utc).isoformat(),
                "affected_endpoint_budget_scope":"individual_candidate_period_before_fragment_removal",
                "source_timezone":"unspecified; timestamps preserved without conversion"}}
        for name,rows in [("cohort_audit",study_audit),("individual_audit",temporal["individuals"]),
                ("all_week_candidates",map(scalar,temporal["candidates"])),
                ("relaxed_week_candidates",map(scalar,temporal["relaxed_candidates"])),
                ("all_group_candidates",map(scalar,all_groups)),("ranked_groups",result["candidate_groups"]),
                ("group_members",result["group_members"]),("selected_points",result["selected_points"]),
                ("trajectory_manifest",shortlisted(trajectories)),
                ("report_groups",result["report_groups"]),("report_group_members",main_rows(members)),
                ("report_points",main_rows(points)),("report_trajectory_manifest",main_rows(trajectories)),
                ("relaxed_group_candidates",map(scalar,relaxed_all)),
                ("relaxed_report_groups",result["relaxed_report_groups"]),
                ("relaxed_group_members",relaxed_rows(members)),("relaxed_points",relaxed_rows(points)),
                ("relaxed_trajectory_manifest",relaxed_rows(trajectories)),
                ("group_month_coverage",month_coverage_rows),
                ("group_year_month_coverage",year_month_coverage_rows),
                ("mcp95_summary",[mcp.properties() for mcp in mcps.values()])]:
            write_csv(data_dir/f"{name}.csv",rows)
        (out/"selection_manifest.json").write_text(json.dumps(result,default=json_default,indent=2),encoding="utf-8")
        from .pantanal_report import write_report
        write_report(out,result)
        LOG.info("Reported %d main and %d relaxed groups to %s",len(report_groups),len(relaxed_groups),out)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    defaults = ProcessorConfig()
    parser.add_argument("--csv",default=defaults.csv_path)
    parser.add_argument("--output",default=defaults.output_dir)
    parser.add_argument("--checkpoint-only",action="store_true",
        help="Write an immutable source checkpoint; preserve existing report/backing assets")
    parser.add_argument("--checkpoint-root",default=None,
        help="Checkpoint parent directory (default: OUTPUT/checkpoints)")
    parser.add_argument("--collar-metadata",default=None,
        help="Optional collar metadata CSV; defaults to data/Jaguar_additional_information_fixed.csv")
    parser.add_argument("--top-n",type=int,default=7,choices=range(3,8))
    parser.add_argument("--report-limit",type=int,default=None,
        help="Render this many groups per list in rank order; default renders all")
    parser.add_argument("--cell-size-m",type=float,default=500)
    parser.add_argument("--growth-buffer-km",type=float,default=5,
        help="Maximum gap from a new MCP95 to the existing group MCPs, in km")
    parser.add_argument("--map-padding-km",type=float,default=5,
        help="Covariate map margin around MCP95 and all selected fixes, in km")
    parser.add_argument("--max-extent-side-km",type=float,default=40,
        help="Hard cap on EACH padded map dimension; prevents neighbour chains")
    parser.add_argument("--max-extent-area-km2",type=float,default=1600)
    parser.add_argument("--min-subtrajectory-points",type=int,default=5)
    parser.add_argument("--max-short-fragment-loss",type=float,default=.05)
    parser.add_argument("--max-affected-point-fraction",type=float,default=.20)
    parser.add_argument("--min-days-per-month",type=int,default=7,
        help="Descriptive year-month count: minimum observed dates per month; no eligibility or warning effect")
    args = parser.parse_args()
    config = ProcessorConfig(csv_path=args.csv,output_dir=args.output,top_n=args.top_n,
        report_limit=args.report_limit,
        temporal=TemporalConfig(min_subtrajectory_points=args.min_subtrajectory_points,
            max_short_fragment_loss=args.max_short_fragment_loss,
            max_affected_point_fraction=args.max_affected_point_fraction,
            min_days_per_month=args.min_days_per_month),
        spatial=SpatialConfig(growth_buffer_km=args.growth_buffer_km,export_padding_km=args.map_padding_km,
            max_extent_side_km=args.max_extent_side_km,max_extent_area_km2=args.max_extent_area_km2,
            cell_size_m=args.cell_size_m))
    logging.basicConfig(level=logging.INFO,format="%(levelname)s %(message)s")
    MovementProcessor(config).run_pipeline(checkpoint_only=args.checkpoint_only,
        checkpoint_root=args.checkpoint_root, collar_metadata_path=args.collar_metadata)


if __name__=="__main__":
    main()
