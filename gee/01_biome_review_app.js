/**
 * =============================================================================
 * Step 2 - Jaguar Home Range Biome Review App
 * =============================================================================
 * Paste this whole file into the Google Earth Engine Code Editor and Run.
 *
 * WHAT IT DOES
 *   Walks you through all 117 Morato jaguars one at a time. For each animal it
 *   intersects the 95% AKDE home range with RESOLVE/ECOREGIONS/2017, shows every
 *   overlapping ecoregion with its parent biome and % overlap, pre-checks the
 *   ones above a threshold, and lets you override before confirming.
 *
 * THE PAIRING RULE
 *   The unit of selection is the ECOREGION. Every ecoregion you tick contributes
 *   exactly one element to `ecoregion_name` AND one element to `biome_type`, at
 *   the same position. The two pipe-delimited columns therefore always have an
 *   equal number of elements, and neither can be blank -- Confirm stays disabled
 *   until at least one ecoregion is ticked. Two ecoregions in the same biome
 *   deliberately repeat that biome name, because dropping the duplicate would
 *   break positional alignment between the columns.
 *
 * INDIVIDUALS 35 AND 38
 *   These two have fewer than 20 GPS fixes, so Step 1 produced no AKDE contour
 *   for them. They still appear in the list, and their overlap is computed by
 *   point-in-polygon instead (% of their fixes falling in each ecoregion). They
 *   are exported with assignment_method = 'GPS_POINT_IN_POLYGON'.
 *
 * PERSISTENCE
 *   Earth Engine apps cannot write files as you go, so review state lives in
 *   memory. Use "Copy session state" to save your progress as JSON and
 *   "Restore session" to paste it back after a reload. Export writes the real
 *   deliverable to Drive as a batch task -- remember to click RUN in the Tasks
 *   tab afterwards.
 * =============================================================================
 */

// ============================================================================
// CONFIG -- edit these two lines
// ============================================================================

/**
 * Folder holding the assets created by upload_gee_assets.sh.
 *   Cloud project accounts:  'projects/<your-cloud-project>/assets/jaguar_biome'
 *   Legacy accounts:         'users/<your-ee-username>/jaguar_biome'
 */
var ASSET_ROOT = 'projects/REPLACE-WITH-YOUR-PROJECT/assets/jaguar_biome';

/** Google Drive folder that Export tasks write into. */
var DRIVE_FOLDER = 'jaguar_biome';

/**
 * Set true for one run to print the two source audits -- which BIOME_NAME
 * values RESOLVE carries and what the guard drops, and what GRIP4 actually
 * calls its road-type attribute -- then set it back to false. Both print to
 * the Console and neither touches the app.
 */
var RUN_SOURCE_AUDITS = false;

// Ecoregions overlapping the home range by more than this are pre-checked.
var OVERLAP_THRESHOLD_PCT = 10;

// Ecoregions below this are not even listed (slivers from contour edges).
var MIN_LISTED_PCT = 0.01;

/**
 * Which weight drives ranking and pre-checking: 'usage' or 'area'.
 *
 * 'usage' is the share of the animal's actual GPS fixes inside an ecoregion;
 * 'area' is the share of the 95% AKDE polygon's area. They differ because an
 * AKDE is a utilization distribution -- an ecoregion clipping 20% of the outer
 * contour may hold 2% of real use. Usage is the better default for deciding
 * where an animal actually lived; area remains available and is exported
 * alongside, so nothing is lost either way.
 */
var RANK_BY = 'usage';

// Resolution for the Tier 2 covariate reduction, in metres. Coarser than
// Hansen's native 30 m because these are home-range means and the interactive
// panel has to stay responsive.
var COVARIATE_SCALE = 120;

// The batch export is a background task with no interactivity to protect, so
// it runs nearer native resolution.
var COVARIATE_EXPORT_SCALE = 30;

// Geometry error margin, in metres, for area and intersection operations.
// 00_covariates.js declares the same value; when the two are concatenated by
// gee/build.sh this simply re-affirms it, and keeps this file readable alone.
var MAX_ERROR = ee.ErrorMargin(1);

// ============================================================================
// DATA
// ============================================================================

var homeRanges = ee.FeatureCollection(ASSET_ROOT + '/home_ranges');
var gpsPoints = ee.FeatureCollection(ASSET_ROOT + '/gps_points');
// Terrestrial ecoregions only -- see terrestrialEcoregions() for why the
// lake and rock/ice fill polygons must not become biome candidates.
var ecoregions = terrestrialEcoregions();

// The biome decision is made on the full-trajectory 95% AKDE contour.
var hr95 = homeRanges.filter(
  ee.Filter.and(
    ee.Filter.eq('method', 'AKDE'),
    ee.Filter.eq('contour_level', 95),
    ee.Filter.eq('segment_id', 0)
  )
);

// 50% core areas, shown for context only -- they do not drive the assignment.
var hr50 = homeRanges.filter(
  ee.Filter.and(
    ee.Filter.eq('method', 'AKDE'),
    ee.Filter.eq('contour_level', 50),
    ee.Filter.eq('segment_id', 0)
  )
);

// ============================================================================
// STATE
// ============================================================================

/**
 * state[id] = {
 *   meta:      roster properties for this individual,
 *   overlaps:  [{eco_id, eco_name, biome_name, area_weight, usage_weight,
 *                fix_share_pct, overlap_km2, n_fixes_inside, color}] sorted
 *              under the active ranking mode, or null until computed,
 *   covariates: Tier 2 habitat-state record, or null until requested,
 *   flags:     derived warnings from deriveFlags(),
 *   selected:  { eco_id_string: true },
 *   status:    'unreviewed' | 'confirmed',
 *   method:    'AKDE_95' | 'GPS_POINT_IN_POLYGON'
 * }
 */
var state = {};
var roster = [];          // ordered list of meta objects
var currentId = null;
var overlapCache = {};    // id -> overlaps array, so revisiting is instant

// ============================================================================
// STYLE CONSTANTS
// ============================================================================

var S = {
  panel: { width: '300px', padding: '8px', backgroundColor: '#fafafa' },
  right: { width: '380px', padding: '8px', backgroundColor: '#fafafa' },
  h1: { fontSize: '15px', fontWeight: 'bold', margin: '4px 8px 2px 8px' },
  h2: { fontSize: '13px', fontWeight: 'bold', margin: '10px 8px 2px 8px' },
  note: { fontSize: '11px', color: '#666', margin: '0 8px 6px 8px' },
  meta: { fontSize: '12px', margin: '1px 8px' },
  listItem: { fontSize: '12px', padding: '2px', margin: '0px' },
  warn: { fontSize: '11px', color: '#b00', margin: '2px 8px' },
  ok: { fontSize: '11px', color: '#070', margin: '2px 8px' }
};

var COLOR_95 = 'FF3B30';
var COLOR_50 = 'FF9500';
var COLOR_GPS = '1C1C1E';

// ============================================================================
// UI SKELETON
// ============================================================================

var map = ui.Map();
map.setOptions('SATELLITE');
map.style().set('cursor', 'crosshair');

var leftPanel = ui.Panel({ style: S.panel });
var rightPanel = ui.Panel({ style: S.right });

var listPanel = ui.Panel({
  style: { height: '460px', margin: '0px', backgroundColor: '#fafafa' }
});
var reviewPanel = ui.Panel({ style: { margin: '0px' } });
var progressLabel = ui.Label('Loading...', S.note);

// ---- left panel: filters + roster list ----------------------------------

var studyFilter = ui.Select({
  items: ['All studies'],
  value: 'All studies',
  onChange: function () { renderRoster(); },
  style: { width: '280px', margin: '2px 8px' }
});

var statusFilter = ui.Select({
  items: ['All', 'Unreviewed only', 'Confirmed only'],
  value: 'All',
  onChange: function () { renderRoster(); },
  style: { width: '280px', margin: '2px 8px' }
});

var searchBox = ui.Textbox({
  placeholder: 'Filter by ID or study...',
  onChange: function () { renderRoster(); },
  style: { width: '280px', margin: '2px 8px' }
});

leftPanel.add(ui.Label('Jaguar Biome Review', S.h1));
leftPanel.add(progressLabel);
leftPanel.add(ui.Label('Study', S.h2));
leftPanel.add(studyFilter);
leftPanel.add(ui.Label('Status', S.h2));
leftPanel.add(statusFilter);
leftPanel.add(searchBox);
leftPanel.add(ui.Label('Individuals', S.h2));
leftPanel.add(listPanel);

// ---- layer toggles -------------------------------------------------------

var showEcoOutlines = ui.Checkbox({
  label: 'RESOLVE ecoregion outlines',
  value: true,
  onChange: function () { redrawMap(); },
  style: { fontSize: '12px', margin: '2px 8px' }
});
var showCore = ui.Checkbox({
  label: '50% core area',
  value: true,
  onChange: function () { redrawMap(); },
  style: { fontSize: '12px', margin: '2px 8px' }
});
var showGps = ui.Checkbox({
  label: 'Raw GPS fixes',
  value: false,
  onChange: function () { redrawMap(); },
  style: { fontSize: '12px', margin: '2px 8px' }
});

var rankSelect = ui.Select({
  items: [
    { label: 'Rank by fixes (usage)', value: 'usage' },
    { label: 'Rank by area', value: 'area' }
  ],
  value: RANK_BY,
  onChange: function (v) {
    RANK_BY = v;
    // Re-rank and re-suggest every individual that has not been confirmed
    // yet. Confirmed picks are left alone: the reviewer's decision outranks
    // the ranking heuristic, and silently rewriting it would be worse than
    // leaving a stale ordering.
    var resuggested = 0;
    roster.forEach(function (meta) {
      var st = state[String(meta.individual_id)];
      if (!st.overlaps) { return; }
      st.overlaps = sortByActive(st.overlaps);
      if (st.status !== 'confirmed') {
        applyAutoSuggestion(st);
        resuggested++;
      }
      refreshFlags(st);
    });
    renderRoster();
    if (currentId !== null) { renderReview(); redrawMap(); }
    exportStatus.setValue(
      'Ranking by ' + v + '. Re-suggested ' + resuggested + ' unconfirmed.');
  },
  style: { width: '280px', margin: '2px 8px' }
});

leftPanel.add(ui.Label('Suggestion ranking', S.h2));
leftPanel.add(rankSelect);
leftPanel.add(ui.Label(
  'Usage = share of GPS fixes. Area = share of the 95% AKDE polygon. ' +
  'Both are always exported; this only sets ordering and pre-ticks.', S.note));

leftPanel.add(ui.Label('Map layers', S.h2));
leftPanel.add(showEcoOutlines);
leftPanel.add(showCore);
leftPanel.add(showGps);

// ---- right panel: review + export ---------------------------------------

rightPanel.add(ui.Label('Review & Assign', S.h1));
rightPanel.add(reviewPanel);

// ============================================================================
// ROSTER LOADING
// ============================================================================

/** Metadata-only view of the AKDE individuals (geometry dropped for speed). */
var polyRoster = hr95.map(function (f) {
  return ee.Feature(null, {
    individual_id: f.get('individual_id'),
    study_name: f.get('study_name'),
    sex: f.get('sex'),
    area_km2: f.get('area_km2'),
    trajectory_days: f.get('trajectory_days'),
    n_gps_points: f.get('n_gps_points'),
    ctmm_model: f.get('ctmm_model'),
    is_range_shift: f.get('is_range_shift'),
    n_core_areas: f.get('n_core_areas'),
    year_start: f.get('year_start'),
    year_end: f.get('year_end'),
    year_mid: f.get('year_mid'),
    assignment_method: 'AKDE_95'
  });
});

// Individuals present in the GPS table but with no AKDE contour: the sub-20-fix
// skips from Step 1. Derived rather than hardcoded so the app stays correct if
// the Step 1 threshold ever changes.
var pointOnlyIds = gpsPoints.aggregate_array('individual_id').distinct()
  .removeAll(hr95.aggregate_array('individual_id'));

var pointRoster = ee.FeatureCollection(
  pointOnlyIds.map(function (id) {
    var pts = gpsPoints.filter(ee.Filter.eq('individual_id', id));
    var first = ee.Feature(pts.first());
    return ee.Feature(null, {
      individual_id: id,
      study_name: first.get('study_name'),
      sex: first.get('sex'),
      area_km2: -1,
      trajectory_days: -1,
      n_gps_points: pts.size(),
      ctmm_model: 'n/a (below 20-fix threshold)',
      is_range_shift: 0,
      n_core_areas: -1,
      year_start: first.get('year_start'),
      year_end: first.get('year_end'),
      year_mid: first.get('year_mid'),
      assignment_method: 'GPS_POINT_IN_POLYGON'
    });
  })
);

polyRoster.merge(pointRoster).sort('individual_id').evaluate(function (fc, err) {
  if (err) {
    leftPanel.add(ui.Label('Failed to load roster: ' + err, S.warn));
    leftPanel.add(ui.Label('Check that ASSET_ROOT is correct.', S.warn));
    return;
  }

  var studies = {};
  roster = fc.features.map(function (f) { return f.properties; });

  roster.forEach(function (meta) {
    var id = String(meta.individual_id);
    state[id] = {
      meta: meta,
      overlaps: null,
      covariates: null,
      flags: [],
      selected: {},
      status: 'unreviewed',
      method: meta.assignment_method
    };
    studies[meta.study_name] = true;
  });

  var studyList = ['All studies'];
  for (var s in studies) { studyList.push(s); }
  studyList.sort();
  studyFilter.items().reset(studyList);
  studyFilter.setValue('All studies', false);

  renderRoster();
  updateProgress();

  if (roster.length > 0) { selectIndividual(roster[0].individual_id); }
});

// ============================================================================
// ROSTER LIST RENDERING
// ============================================================================

function matchesFilters(meta) {
  var st = state[String(meta.individual_id)];

  if (studyFilter.getValue() !== 'All studies' &&
      meta.study_name !== studyFilter.getValue()) {
    return false;
  }

  var sf = statusFilter.getValue();
  if (sf === 'Unreviewed only' && st.status !== 'unreviewed') { return false; }
  if (sf === 'Confirmed only' && st.status !== 'confirmed') { return false; }

  var q = (searchBox.getValue() || '').toLowerCase();
  if (q) {
    var hay = (String(meta.individual_id) + ' ' + meta.study_name).toLowerCase();
    if (hay.indexOf(q) === -1) { return false; }
  }
  return true;
}

function renderRoster() {
  listPanel.clear();
  var shown = 0;

  roster.forEach(function (meta) {
    if (!matchesFilters(meta)) { return; }
    shown++;

    var id = meta.individual_id;
    var st = state[String(id)];
    var dot = st.status === 'confirmed' ? '✓ ' : '○ ';
    var marker = st.method === 'GPS_POINT_IN_POLYGON' ? ' [pts]' : '';
    var label = dot + 'ID ' + id + ' · ' + meta.study_name + marker;

    var btn = ui.Button({
      label: label,
      onClick: function () { selectIndividual(id); },
      style: {
        margin: '1px 4px',
        padding: '0px',
        fontSize: '11px',
        color: st.status === 'confirmed' ? '#0a7d28' : '#333',
        backgroundColor: (currentId === id) ? '#d8e8ff' : '#ffffff'
      }
    });
    listPanel.add(btn);
  });

  if (shown === 0) {
    listPanel.add(ui.Label('No individuals match these filters.', S.note));
  }
}

function updateProgress() {
  var done = 0;
  var total = roster.length;
  roster.forEach(function (m) {
    if (state[String(m.individual_id)].status === 'confirmed') { done++; }
  });
  progressLabel.setValue('Confirmed ' + done + ' / ' + total);
}

// ============================================================================
// OVERLAP COMPUTATION
// ============================================================================

/**
 * Hours of tracked time a point collection stands for.
 *
 * `hours_represented` is written per fix by prepare_gee_uploads.py: half the
 * gap behind the fix plus half the gap ahead, capped at four median intervals.
 * Summing it is how usage_weight becomes a share of TIME rather than a share
 * of FIXES -- see the note on computePolygonOverlap.
 *
 * aggregate_sum returns null on an empty collection, which would poison every
 * number downstream of it, so an empty result is an explicit zero.
 */
function trackedHours(points) {
  return ee.Number(ee.Algorithms.If(
    points.size().gt(0), points.aggregate_sum('hours_represented'), 0));
}

/**
 * Overlap of a 95% AKDE polygon with each intersecting RESOLVE ecoregion.
 *
 * Two weights come back for every candidate:
 *   area_weight  -- share of the 95% AKDE polygon's area in this ecoregion
 *   usage_weight -- share of the animal's tracked TIME in this ecoregion
 *
 * usage_weight is time, not fix count, and the difference is not academic.
 * Counting fixes is unbiased only while the collar samples at a constant rate,
 * and 26 of 113 individuals here change their median interval by more than
 * 1.5x partway through the track. For 17 of them that change coincides with a
 * range shift -- the animal is on different ground before and after -- so a
 * doubled interval would halve the apparent use of whichever range came later
 * and could hand the assignment to the wrong biome. Where sampling is uniform
 * the two measures agree exactly.
 *
 * n_fixes_inside is kept unweighted so the two are comparable after the fact,
 * and deriveFlags raises `sampling_schedule_bias` where they disagree.
 *
 * Computing both weights in one pass costs one extra filterBounds per
 * ecoregion and makes the area-versus-use divergence visible instead of
 * invisible.
 */
function computePolygonOverlap(id, callback) {
  var feature = ee.Feature(
    hr95.filter(ee.Filter.eq('individual_id', id)).first()
  );
  var geom = feature.geometry();
  var totalArea = geom.area(MAX_ERROR);

  var pts = gpsPoints.filter(ee.Filter.eq('individual_id', id));
  var nTotal = pts.size();
  var hoursTotal = trackedHours(pts);

  var rows = ecoregions.filterBounds(geom).map(function (eco) {
    var ecoGeom = eco.geometry();
    var interArea = ecoGeom.intersection(geom, MAX_ERROR).area(MAX_ERROR);
    var insidePts = pts.filterBounds(ecoGeom);
    var inside = insidePts.size();

    return ee.Feature(null, {
      eco_id: eco.get('ECO_ID'),
      eco_name: eco.get('ECO_NAME'),
      biome_name: eco.get('BIOME_NAME'),
      biome_num: eco.get('BIOME_NUM'),
      realm: eco.get('REALM'),
      color: eco.get('COLOR'),
      overlap_km2: interArea.divide(1e6),
      area_weight: interArea.divide(totalArea).multiply(100),
      usage_weight: trackedHours(insidePts).divide(hoursTotal).multiply(100),
      fix_share_pct: ee.Number(inside).divide(nTotal).multiply(100),
      n_fixes_inside: inside
    });
  })
  // Keep anything that holds either area or fixes: an ecoregion with a sliver
  // of area but a real cluster of fixes must not be dropped, nor the reverse.
  .filter(ee.Filter.or(
    ee.Filter.gt('area_weight', MIN_LISTED_PCT),
    ee.Filter.gt('usage_weight', 0)
  ))
  .sort(RANK_BY === 'area' ? 'area_weight' : 'usage_weight', false);

  rows.evaluate(callback);
}

/**
 * Overlap by point-in-polygon, for individuals with no AKDE contour.
 * area_weight is -1 throughout: there is no home range polygon to take an area
 * share of, and reporting the convex hull's share would imply a home range
 * estimate that Step 1 explicitly declined to make.
 */
function computePointOverlap(id, callback) {
  var pts = gpsPoints.filter(ee.Filter.eq('individual_id', id));
  var nTotal = pts.size();
  var hoursTotal = trackedHours(pts);

  var rows = ecoregions.filterBounds(pts.geometry(MAX_ERROR)).map(function (eco) {
    var insidePts = pts.filterBounds(eco.geometry());
    var inside = insidePts.size();
    return ee.Feature(null, {
      eco_id: eco.get('ECO_ID'),
      eco_name: eco.get('ECO_NAME'),
      biome_name: eco.get('BIOME_NAME'),
      biome_num: eco.get('BIOME_NUM'),
      realm: eco.get('REALM'),
      color: eco.get('COLOR'),
      overlap_km2: -1,
      area_weight: -1,
      usage_weight: trackedHours(insidePts).divide(hoursTotal).multiply(100),
      fix_share_pct: ee.Number(inside).divide(nTotal).multiply(100),
      n_fixes_inside: inside
    });
  })
  .filter(ee.Filter.gt('usage_weight', 0))
  .sort('usage_weight', false);

  rows.evaluate(callback);
}

/**
 * Pre-tick the candidates above threshold under the active ranking mode.
 *
 * If nothing clears the bar -- which happens when a range straddles many small
 * ecoregions -- the single strongest candidate is taken instead, so an animal
 * is never left with an empty assignment and a blocked Confirm button.
 */
function applyAutoSuggestion(st) {
  st.selected = {};
  if (!st.overlaps || st.overlaps.length === 0) { return; }

  var ranked = sortByActive(st.overlaps);
  var anyAbove = false;
  ranked.forEach(function (o) {
    if (activeWeight(o) > OVERLAP_THRESHOLD_PCT) {
      st.selected[String(o.eco_id)] = true;
      anyAbove = true;
    }
  });
  if (!anyAbove) { st.selected[String(ranked[0].eco_id)] = true; }
}

/** The weight currently driving ranking and pre-checks, for one candidate. */
function activeWeight(row) {
  if (RANK_BY === 'area' && row.area_weight >= 0) { return row.area_weight; }
  return row.usage_weight;
}

/** Re-sort a candidate list under the active ranking mode. */
function sortByActive(overlaps) {
  return overlaps.slice().sort(function (a, b) {
    return activeWeight(b) - activeWeight(a);
  });
}

// ============================================================================
// TIER 2 COVARIATES
// ============================================================================

/**
 * The polygon a covariate reduction runs over.
 * For the two sub-20-fix individuals there is no AKDE contour, so the convex
 * hull of their fixes stands in -- labelled as such downstream so nobody
 * mistakes it for a home range estimate.
 */
function geometryForMeta(meta) {
  var id = meta.individual_id;
  if (meta.assignment_method === 'GPS_POINT_IN_POLYGON') {
    return gpsPoints.filter(ee.Filter.eq('individual_id', id))
      .geometry(MAX_ERROR).convexHull(MAX_ERROR);
  }
  return hr95.filter(ee.Filter.eq('individual_id', id)).geometry();
}

/**
 * Habitat-state covariates for one individual, evaluated asynchronously.
 *
 * Run on request rather than on selection: the reduction touches six raster
 * sources and would add seconds to every click through the roster, while the
 * biome decision itself does not depend on it.
 */
function computeCovariatesFor(id, callback) {
  var meta = state[String(id)].meta;
  reduceCovariates(
    geometryForMeta(meta),
    meta.study_name,
    meta.year_start,
    meta.year_end,
    meta.year_mid,
    COVARIATE_SCALE
  ).evaluate(callback);
}

/**
 * Covariates for every individual, as a server-side collection.
 *
 * Built by looping the roster on the client rather than mapping server-side,
 * because the year snapping in the covariate module is plain JavaScript
 * arithmetic on values already known here. 117 iterations make a large
 * expression graph, which is exactly why this is its own export task instead
 * of being folded into the biome export.
 */
function covariateFeatureCollection() {
  var features = roster.map(function (meta) {
    var stats = reduceCovariates(
      geometryForMeta(meta),
      meta.study_name,
      meta.year_start,
      meta.year_end,
      meta.year_mid,
      COVARIATE_EXPORT_SCALE
    );
    return ee.Feature(null, stats.combine(ee.Dictionary({
      individual_id: meta.individual_id,
      study_name: meta.study_name,
      sex: meta.sex,
      year_start: meta.year_start,
      year_end: meta.year_end,
      year_mid: meta.year_mid,
      covariate_geometry: meta.assignment_method === 'GPS_POINT_IN_POLYGON'
        ? 'GPS_CONVEX_HULL' : 'AKDE_95',
      mapbiomas_region: STUDY_REGION[meta.study_name] || 'none'
    }), true));
  });
  return ee.FeatureCollection(features);
}

/** Refresh derived flags for one individual from its current state. */
function refreshFlags(st) {
  st.flags = deriveFlags(st.overlaps, selectedRows(st), st.covariates);
}

// ============================================================================
// INDIVIDUAL SELECTION
// ============================================================================

function selectIndividual(id) {
  currentId = id;
  renderRoster();
  redrawMap(true);

  var key = String(id);
  var st = state[key];

  if (st.overlaps !== null) {
    renderReview();
    return;
  }

  reviewPanel.clear();
  reviewPanel.add(ui.Label('ID ' + id + ' · ' + st.meta.study_name, S.h2));
  reviewPanel.add(ui.Label('Computing ecoregion overlap...', S.note));

  var handler = function (fc, err) {
    // Ignore results that arrive after the user has moved on.
    if (currentId !== id) { return; }

    if (err) {
      reviewPanel.clear();
      reviewPanel.add(ui.Label('Overlap computation failed:', S.warn));
      reviewPanel.add(ui.Label(String(err), S.warn));
      return;
    }

    var overlaps = fc.features.map(function (f) { return f.properties; });
    st.overlaps = overlaps;
    overlapCache[key] = overlaps;

    // Pre-check everything above the threshold. If nothing clears it -- which
    // happens when a range straddles many small ecoregions -- fall back to the
    // single largest, so the animal is never left with an empty assignment.
    st.overlaps = sortByActive(overlaps);
    applyAutoSuggestion(st);

    renderReview();
    redrawMap(true);
  };

  if (st.method === 'GPS_POINT_IN_POLYGON') {
    computePointOverlap(id, handler);
  } else {
    computePolygonOverlap(id, handler);
  }
}

// ============================================================================
// REVIEW PANEL RENDERING
// ============================================================================

function selectedRows(st) {
  // Preserves overlap-descending order, which is what makes the two exported
  // columns line up element for element.
  if (!st.overlaps) { return []; }
  return st.overlaps.filter(function (o) {
    return st.selected[String(o.eco_id)] === true;
  });
}

function fmtPct(v) { return (Math.round(v * 10) / 10) + '%'; }
function fmtArea(v) {
  if (v < 0) { return 'n/a'; }
  return (Math.round(v * 10) / 10) + ' km²';
}

function renderReview() {
  var id = currentId;
  var key = String(id);
  var st = state[key];
  var meta = st.meta;

  reviewPanel.clear();

  // ---- metadata ----------------------------------------------------------
  reviewPanel.add(ui.Label('ID ' + id + ' · ' + meta.study_name, S.h2));
  reviewPanel.add(ui.Label('Sex: ' + meta.sex, S.meta));
  reviewPanel.add(ui.Label(
    'GPS fixes: ' + meta.n_gps_points +
    (meta.trajectory_days >= 0
      ? '  ·  ' + Math.round(meta.trajectory_days) + ' days'
      : ''),
    S.meta));

  if (st.method === 'GPS_POINT_IN_POLYGON') {
    reviewPanel.add(ui.Label(
      'No AKDE contour (below the 20-fix threshold). Overlap below is the ' +
      'share of raw GPS fixes falling inside each ecoregion.', S.warn));
  } else {
    reviewPanel.add(ui.Label(
      '95% AKDE: ' + fmtArea(meta.area_km2) +
      '  ·  core areas: ' + meta.n_core_areas, S.meta));
    reviewPanel.add(ui.Label('Model: ' + meta.ctmm_model, S.meta));
    if (meta.is_range_shift === 1) {
      reviewPanel.add(ui.Label(
        'Range shift detected — the 95% contour may span more ' +
        'ecoregions than the animal actually used.', S.warn));
    }
  }

  // ---- overlap table -----------------------------------------------------
  reviewPanel.add(ui.Label('Overlapping ecoregions', S.h2));
  reviewPanel.add(ui.Label(
    'Ecoregion (bold) with its RESOLVE biome beneath. Ticking an ecoregion ' +
    'adds its name AND its biome to the export, keeping both columns aligned.',
    S.note));

  if (!st.overlaps || st.overlaps.length === 0) {
    reviewPanel.add(ui.Label('No overlapping ecoregion found.', S.warn));
    return;
  }

  st.overlaps.forEach(function (o) {
    var ecoKey = String(o.eco_id);
    var swatch = ui.Label({
      value: '█',
      style: { color: o.color, fontSize: '14px', margin: '0px 2px 0px 6px',
               padding: '0px' }
    });

    var cb = ui.Checkbox({
      label: o.eco_name,
      value: st.selected[ecoKey] === true,
      onChange: function (checked) {
        if (checked) {
          st.selected[ecoKey] = true;
        } else {
          delete st.selected[ecoKey];
        }
        // Editing an assignment invalidates the previous confirmation.
        if (st.status === 'confirmed') {
          st.status = 'unreviewed';
          updateProgress();
          renderRoster();
        }
        refreshSummary();
        redrawMap();
      },
      style: { fontSize: '12px', margin: '1px 0px', padding: '0px' }
    });

    var head = ui.Panel({
      widgets: [swatch, cb],
      layout: ui.Panel.Layout.flow('horizontal'),
      style: { margin: '0px', padding: '0px' }
    });

    // Both weights always shown, ranking one first, so a divergence between
    // where the range is and where the animal actually was stays visible
    // instead of hiding behind whichever metric happens to be active.
    var usageTxt = 'use ' + fmtPct(o.usage_weight) +
                   ' (' + o.n_fixes_inside + ' fixes)';
    var areaTxt = o.area_weight >= 0
      ? 'area ' + fmtPct(o.area_weight) + '  ·  ' + fmtArea(o.overlap_km2)
      : 'area n/a';
    var detail = RANK_BY === 'area'
      ? areaTxt + '   |   ' + usageTxt
      : usageTxt + '   |   ' + areaTxt;

    reviewPanel.add(head);
    reviewPanel.add(ui.Label(o.biome_name, {
      fontSize: '11px', color: '#444', margin: '0px 8px 0px 30px'
    }));
    reviewPanel.add(ui.Label(detail, {
      fontSize: '11px', color: '#888', margin: '0px 8px 4px 30px'
    }));
  });

  // ---- live summary of what will be exported -----------------------------
  reviewPanel.add(ui.Label('Will export as', S.h2));
  summaryBiome = ui.Label('', { fontSize: '11px', margin: '0px 8px' });
  summaryEco = ui.Label('', { fontSize: '11px', margin: '0px 8px' });
  summaryWarn = ui.Label('', S.warn);
  reviewPanel.add(summaryEco);
  reviewPanel.add(summaryBiome);
  reviewPanel.add(summaryWarn);

  // ---- derived flags -----------------------------------------------------
  refreshFlags(st);
  if (st.flags.length > 0) {
    reviewPanel.add(ui.Label('Flags', S.h2));
    st.flags.forEach(function (f) {
      reviewPanel.add(ui.Label(
        (f.level === 'warn' ? '⚠ ' : 'ℹ ') + f.text,
        f.level === 'warn' ? S.warn : S.note));
    });
  }

  // ---- Tier 2 habitat state ----------------------------------------------
  reviewPanel.add(ui.Label('Habitat state during tracking', S.h2));
  reviewPanel.add(ui.Label(
    'Years ' + meta.year_start + '–' + meta.year_end +
    ' · covariates indexed to ' + meta.year_mid + '.', S.note));

  covariatePanel = ui.Panel({ style: { margin: '0px' } });
  reviewPanel.add(covariatePanel);
  renderCovariates(st);

  // ---- actions -----------------------------------------------------------
  confirmButton = ui.Button({
    label: 'Confirm & next',
    onClick: function () { confirmCurrent(true); },
    style: { margin: '8px 8px 2px 8px', stretch: 'horizontal' }
  });
  var confirmStay = ui.Button({
    label: 'Confirm (stay)',
    onClick: function () { confirmCurrent(false); },
    style: { margin: '2px 8px', stretch: 'horizontal' }
  });
  var resetButton = ui.Button({
    label: 'Reset to auto-suggestion',
    onClick: function () { resetCurrent(); },
    style: { margin: '2px 8px 8px 8px', stretch: 'horizontal' }
  });

  reviewPanel.add(confirmButton);
  reviewPanel.add(confirmStay);
  reviewPanel.add(resetButton);

  refreshSummary();
}

var summaryBiome, summaryEco, summaryWarn, confirmButton, covariatePanel;

/**
 * Render the Tier 2 card for one individual.
 *
 * These values never change the biome suggestion. RESOLVE answers "what was
 * this landscape natively"; these answer "what condition was it in while the
 * animal wore the collar". Letting the second rewrite the first would collapse
 * exactly the distinction the two-tier design exists to keep.
 */
function renderCovariates(st) {
  if (!covariatePanel) { return; }
  covariatePanel.clear();

  if (st.covariates === null) {
    covariatePanel.add(ui.Button({
      label: 'Compute habitat covariates',
      onClick: function () {
        var id = currentId;
        covariatePanel.clear();
        covariatePanel.add(ui.Label('Reducing six raster sources...', S.note));

        computeCovariatesFor(id, function (result, err) {
          if (currentId !== id) { return; }
          if (err) {
            covariatePanel.clear();
            covariatePanel.add(ui.Label('Covariate pass failed: ' + err, S.warn));
            return;
          }
          state[String(id)].covariates = result;
          refreshFlags(state[String(id)]);
          renderReview();
        });
      },
      style: { margin: '2px 8px', stretch: 'horizontal' }
    }));
    return;
  }

  var shown = 0;
  COVARIATE_FIELDS.forEach(function (field) {
    var value = st.covariates[field];
    if (value === null || value === undefined) { return; }
    shown++;

    var unit = COVARIATE_UNITS[field] === undefined ? '' : COVARIATE_UNITS[field];
    var text = (Math.abs(value) >= 100)
      ? Math.round(value)
      : Math.round(value * 1000) / 1000;

    covariatePanel.add(ui.Panel({
      widgets: [
        ui.Label(COVARIATE_LABELS[field] || field, {
          fontSize: '11px', color: '#444', margin: '0px', padding: '0px',
          stretch: 'horizontal'
        }),
        ui.Label(text + unit, {
          fontSize: '11px', fontWeight: 'bold', margin: '0px 8px 0px 0px',
          padding: '0px'
        })
      ],
      layout: ui.Panel.Layout.flow('horizontal'),
      style: { margin: '0px 0px 0px 8px', padding: '0px', stretch: 'horizontal' }
    }));
  });

  if (shown === 0) {
    covariatePanel.add(ui.Label('No covariates returned for this range.', S.warn));
  }
  covariatePanel.add(ui.Label(
    'Context only — these do not alter the biome suggestion.', S.note));
}

function refreshSummary() {
  var st = state[String(currentId)];
  var rows = selectedRows(st);

  var ecoStr = rows.map(function (o) { return o.eco_name; }).join('|');
  var biomeStr = rows.map(function (o) { return o.biome_name; }).join('|');

  if (summaryEco) {
    summaryEco.setValue('ecoregion_name: ' + (ecoStr || '—'));
  }
  if (summaryBiome) {
    summaryBiome.setValue('biome_type: ' + (biomeStr || '—'));
  }

  if (summaryWarn) {
    summaryWarn.setValue(
      rows.length === 0
        ? 'Select at least one ecoregion — neither column may be blank.'
        : ''
    );
  }
  if (confirmButton) {
    confirmButton.setDisabled(rows.length === 0);
  }
}

function confirmCurrent(advance) {
  var st = state[String(currentId)];
  if (selectedRows(st).length === 0) { return; }

  st.status = 'confirmed';
  updateProgress();
  renderRoster();

  if (!advance) { return; }

  // Jump to the next individual that still needs review.
  var idx = -1;
  for (var i = 0; i < roster.length; i++) {
    if (roster[i].individual_id === currentId) { idx = i; break; }
  }
  for (var j = idx + 1; j < roster.length; j++) {
    if (state[String(roster[j].individual_id)].status === 'unreviewed') {
      selectIndividual(roster[j].individual_id);
      return;
    }
  }
  for (var k = 0; k < roster.length; k++) {
    if (state[String(roster[k].individual_id)].status === 'unreviewed') {
      selectIndividual(roster[k].individual_id);
      return;
    }
  }
}

function resetCurrent() {
  var st = state[String(currentId)];
  st.selected = {};
  st.status = 'unreviewed';

  applyAutoSuggestion(st);

  updateProgress();
  renderRoster();
  renderReview();
  redrawMap();
}

// ============================================================================
// MAP RENDERING
// ============================================================================

function redrawMap(recenter) {
  map.layers().reset();
  if (currentId === null) { return; }

  var id = currentId;
  var st = state[String(id)];

  if (showEcoOutlines.getValue()) {
    map.addLayer(
      ecoregions.style({ color: 'FFFFFFAA', fillColor: '00000000', width: 1 }),
      {}, 'RESOLVE ecoregions'
    );
  }

  // Highlight each candidate ecoregion in its own RESOLVE colour, so the map
  // matches the swatches beside the checkboxes.
  if (st.overlaps) {
    st.overlaps.forEach(function (o) {
      var hex = String(o.color).replace('#', '');
      var isSelected = st.selected[String(o.eco_id)] === true;
      map.addLayer(
        ecoregions.filter(ee.Filter.eq('ECO_ID', o.eco_id)).style({
          color: hex + 'FF',
          fillColor: hex + (isSelected ? '77' : '22'),
          width: isSelected ? 3 : 1
        }),
        {}, o.eco_name + ' (' + fmtPct(activeWeight(o)) + ')', true
      );
    });
  }

  if (showGps.getValue()) {
    map.addLayer(
      gpsPoints.filter(ee.Filter.eq('individual_id', id))
        .style({ color: COLOR_GPS + 'CC', pointSize: 2 }),
      {}, 'GPS fixes'
    );
  }

  if (st.method === 'GPS_POINT_IN_POLYGON') {
    var pts = gpsPoints.filter(ee.Filter.eq('individual_id', id));
    map.addLayer(pts.style({ color: COLOR_95, pointSize: 5 }), {}, 'GPS fixes');
    if (recenter) { map.centerObject(pts, 10); }
    return;
  }

  if (showCore.getValue()) {
    map.addLayer(
      hr50.filter(ee.Filter.eq('individual_id', id))
        .style({ color: COLOR_50, fillColor: COLOR_50 + '55', width: 2 }),
      {}, '50% core area'
    );
  }

  var poly = hr95.filter(ee.Filter.eq('individual_id', id));
  map.addLayer(
    poly.style({ color: COLOR_95, fillColor: '00000000', width: 3 }),
    {}, '95% AKDE'
  );
  // Only reframe when switching animals; re-centring on every checkbox toggle
  // would yank the map away from wherever the user had panned it.
  if (recenter) { map.centerObject(poly, 9); }
}

// ============================================================================
// EXPORT
// ============================================================================

/** Client-side dictionary of confirmed assignments, keyed by individual_id. */
function buildAssignmentDict(includeUnreviewed) {
  var dict = {};
  var skipped = [];

  roster.forEach(function (meta) {
    var key = String(meta.individual_id);
    var st = state[key];
    var rows = selectedRows(st);

    if (rows.length === 0) { skipped.push(meta.individual_id); return; }
    if (st.status !== 'confirmed' && !includeUnreviewed) {
      skipped.push(meta.individual_id);
      return;
    }

    // Candidates the reviewer was offered and did not take. Exported as their
    // own aligned lists rather than folded into a JSON blob: it keeps the
    // 10% threshold a re-runnable decision instead of one baked in at review
    // time, and it parses with the same split('|') as every other column.
    var rejected = (st.overlaps || []).filter(function (o) {
      return st.selected[String(o.eco_id)] !== true;
    });

    var round1 = function (v) { return Math.round(v * 10) / 10; };

    dict[key] = {
      // Every list below is positionally paired: element i of each describes
      // the same ecoregion, ordered by the active ranking weight.
      biome_type: rows.map(function (o) { return o.biome_name; }).join('|'),
      ecoregion_name: rows.map(function (o) { return o.eco_name; }).join('|'),
      usage_weight: rows.map(function (o) { return round1(o.usage_weight); }).join('|'),
      area_weight: rows.map(function (o) { return round1(o.area_weight); }).join('|'),
      n_fixes_inside: rows.map(function (o) { return o.n_fixes_inside; }).join('|'),
      n_biomes: rows.length,

      rejected_ecoregion_name: rejected.map(function (o) { return o.eco_name; }).join('|'),
      rejected_biome_type: rejected.map(function (o) { return o.biome_name; }).join('|'),
      rejected_usage_weight: rejected.map(function (o) { return round1(o.usage_weight); }).join('|'),
      rejected_area_weight: rejected.map(function (o) { return round1(o.area_weight); }).join('|'),

      rank_mode: RANK_BY,
      overlap_threshold_pct: OVERLAP_THRESHOLD_PCT,
      review_flags: (st.flags || []).map(function (f) { return f.key; }).join('|'),
      assignment_status: st.status === 'confirmed' ? 'confirmed' : 'auto',
      assignment_method: st.method
    };
  });

  return { dict: dict, skipped: skipped };
}

var EXPORT_PROPS = [
  'biome_type', 'ecoregion_name', 'usage_weight', 'area_weight',
  'n_fixes_inside', 'n_biomes',
  'rejected_ecoregion_name', 'rejected_biome_type',
  'rejected_usage_weight', 'rejected_area_weight',
  'rank_mode', 'overlap_threshold_pct', 'review_flags',
  'assignment_status', 'assignment_method'
];

/** Attach the assignment properties to a collection keyed on individual_id. */
function joinAssignments(fc, dict) {
  var eeDict = ee.Dictionary(dict);

  return fc.map(function (f) {
    var key = ee.Number(f.get('individual_id')).format('%d');
    var hit = eeDict.contains(key);
    var vals = ee.Dictionary(
      ee.Algorithms.If(hit, eeDict.get(key), ee.Dictionary({}))
    );

    var props = ee.Dictionary.fromLists(
      EXPORT_PROPS,
      EXPORT_PROPS.map(function (p) {
        return ee.Algorithms.If(vals.contains(p), vals.get(p), '');
      })
    );
    return f.set(props);
  }).filter(ee.Filter.neq('biome_type', ''));
}

/** Convex hull stand-ins so the point-only individuals carry a geometry. */
function pointOnlyFeatures() {
  return ee.FeatureCollection(
    pointOnlyIds.map(function (id) {
      var pts = gpsPoints.filter(ee.Filter.eq('individual_id', id));
      var first = ee.Feature(pts.first());
      return ee.Feature(pts.geometry(MAX_ERROR).convexHull(MAX_ERROR), {
        individual_id: id,
        study_name: first.get('study_name'),
        sex: first.get('sex'),
        segment_id: 0,
        contour_level: -1,
        area_km2: -1,
        method: 'GPS_CONVEX_HULL',
        is_range_shift: 0,
        n_core_areas: -1,
        ctmm_model: 'n/a (below 20-fix threshold)',
        n_gps_points: pts.size(),
        trajectory_days: -1
      });
    })
  );
}

function runExport(includeUnreviewed) {
  var built = buildAssignmentDict(includeUnreviewed);

  if (built.skipped.length > 0) {
    exportStatus.setValue(
      'Not exported (' + built.skipped.length + ' without a confirmed ' +
      'assignment): ' + built.skipped.join(', '));
  } else {
    exportStatus.setValue('All ' + roster.length + ' individuals included.');
  }

  // Every contour of an individual -- both levels, every segment, the MCP --
  // inherits that individual's assignment, so the Step 3 explorer can filter
  // any of them by biome.
  var allContours = homeRanges.merge(pointOnlyFeatures());
  var enriched = joinAssignments(allContours, built.dict);

  Export.table.toDrive({
    collection: enriched,
    description: 'biome_assignments_export_geojson',
    folder: DRIVE_FOLDER,
    fileNamePrefix: 'biome_assignments_export',
    fileFormat: 'GeoJSON'
  });

  // Earth Engine cannot ingest GeoJSON, so the GeoJSON above is a dead end as
  // far as Step 3 is concerned. This second task writes the same collection as
  // CSV, where geometry rides along in a `.geo` column that GEE's table
  // ingestion does accept -- that is the file to upload for the explorer app.
  Export.table.toDrive({
    collection: enriched,
    description: 'biome_assignments_export_csv',
    folder: DRIVE_FOLDER,
    fileNamePrefix: 'biome_assignments_export',
    fileFormat: 'CSV'
  });

  // Tier 2 goes out as its own 117-row table rather than being stamped onto
  // every contour. The covariates are per-individual facts; repeating them
  // across 751 polygons -- and later across 134,690 GPS rows -- would be
  // denormalisation with nothing gained, since anything downstream can join
  // on individual_id.
  Export.table.toDrive({
    collection: covariateFeatureCollection(),
    description: 'individual_covariates_csv',
    folder: DRIVE_FOLDER,
    fileNamePrefix: 'individual_covariates',
    fileFormat: 'CSV'
  });

  print('Three export tasks created. Open the Tasks tab and click RUN on each.');
  print('  biome_assignments_export.geojson -> Step 4 (add_biome_column.py)');
  print('  biome_assignments_export.csv     -> re-upload as a GEE asset for Step 3');
  print('  individual_covariates.csv        -> Step 4, joined on individual_id');
}

// ---- export + session widgets -------------------------------------------

var exportStatus = ui.Label('', S.note);

var exportButton = ui.Button({
  label: 'Export confirmed → Drive',
  onClick: function () { runExport(false); },
  style: { margin: '4px 8px 2px 8px', stretch: 'horizontal' }
});

var exportAllButton = ui.Button({
  label: 'Export all (incl. unreviewed auto-suggestions)',
  onClick: function () { runExport(true); },
  style: { margin: '2px 8px', stretch: 'horizontal' }
});

var covariateExportButton = ui.Button({
  label: 'Export habitat covariates only',
  onClick: function () {
    if (roster.length === 0) {
      exportStatus.setValue('Roster not loaded yet.');
      return;
    }
    Export.table.toDrive({
      collection: covariateFeatureCollection(),
      description: 'individual_covariates_csv',
      folder: DRIVE_FOLDER,
      fileNamePrefix: 'individual_covariates',
      fileFormat: 'CSV'
    });
    exportStatus.setValue(
      'Covariate task created for ' + roster.length + ' individuals. ' +
      'It is the slow one — run it from the Tasks tab.');
  },
  style: { margin: '2px 8px', stretch: 'horizontal' }
});

var autoConfirmButton = ui.Button({
  label: 'Auto-confirm every unreviewed individual',
  onClick: function () {
    // Only marks individuals whose overlap has already been computed; anything
    // never opened has no suggestion to accept.
    var applied = 0, pending = 0;
    roster.forEach(function (meta) {
      var st = state[String(meta.individual_id)];
      if (st.status === 'confirmed') { return; }
      if (st.overlaps === null) { pending++; return; }
      if (selectedRows(st).length > 0) { st.status = 'confirmed'; applied++; }
    });
    updateProgress();
    renderRoster();
    exportStatus.setValue(
      'Auto-confirmed ' + applied + '. ' + pending +
      ' never opened, so they have no suggestion yet.');
  },
  style: { margin: '2px 8px', stretch: 'horizontal' }
});

var sessionBox = ui.Textbox({
  placeholder: 'Session JSON',
  style: { margin: '2px 8px', stretch: 'horizontal' }
});

var saveSessionButton = ui.Button({
  label: 'Copy session state',
  onClick: function () {
    var dump = {};
    roster.forEach(function (meta) {
      var key = String(meta.individual_id);
      var st = state[key];
      if (st.status !== 'confirmed') { return; }
      dump[key] = selectedRows(st).map(function (o) {
        return [o.eco_id, o.eco_name, o.biome_name,
                o.usage_weight, o.area_weight, o.n_fixes_inside,
                o.fix_share_pct];
      });
    });
    var json = JSON.stringify(dump);
    sessionBox.setValue(json);
    print('Session state (copy this, paste it back after a reload):', json);
  },
  style: { margin: '2px 8px', stretch: 'horizontal' }
});

var restoreSessionButton = ui.Button({
  label: 'Restore session',
  onClick: function () {
    var raw = sessionBox.getValue();
    if (!raw) { exportStatus.setValue('Paste session JSON first.'); return; }

    var dump;
    try {
      dump = JSON.parse(raw);
    } catch (e) {
      exportStatus.setValue('Could not parse that JSON.');
      return;
    }

    var restored = 0;
    for (var key in dump) {
      if (!state[key]) { continue; }
      var rows = dump[key];
      // Rebuild the cached overlap rows from the dump so a restored session is
      // usable without recomputing every intersection.
      state[key].overlaps = state[key].overlaps || rows.map(function (r) {
        return {
          eco_id: r[0], eco_name: r[1], biome_name: r[2],
          usage_weight: r[3],
          area_weight: r[4] === undefined ? -1 : r[4],
          n_fixes_inside: r[5] === undefined ? 0 : r[5],
          // Sessions saved before fix_share_pct existed fall back to the time
          // weight, which reads as "no divergence" rather than a false one.
          fix_share_pct: r[6] === undefined ? r[3] : r[6],
          overlap_km2: -1, color: '#888888'
        };
      });
      state[key].selected = {};
      rows.forEach(function (r) { state[key].selected[String(r[0])] = true; });
      state[key].status = 'confirmed';
      restored++;
    }

    updateProgress();
    renderRoster();
    if (currentId !== null) { renderReview(); }
    exportStatus.setValue('Restored ' + restored + ' confirmed assignments.');
  },
  style: { margin: '2px 8px 8px 8px', stretch: 'horizontal' }
});

rightPanel.add(ui.Label('Bulk actions', S.h2));
rightPanel.add(autoConfirmButton);
rightPanel.add(ui.Label('Export', S.h2));
rightPanel.add(exportButton);
rightPanel.add(exportAllButton);
rightPanel.add(covariateExportButton);
rightPanel.add(exportStatus);
rightPanel.add(ui.Label('Session', S.h2));
rightPanel.add(ui.Label(
  'Progress is held in memory only. Copy it out before reloading.', S.note));
rightPanel.add(sessionBox);
rightPanel.add(saveSessionButton);
rightPanel.add(restoreSessionButton);

// ============================================================================
// LAUNCH
// ============================================================================

if (RUN_SOURCE_AUDITS) {
  describeBiomes();
  // Sampled over the Pantanal cluster, which holds the largest share of the
  // fixes and has enough road network to make the attribute values visible.
  describeRoadAttributes(
    ee.Geometry.Rectangle([-58.5, -19.5, -55.5, -16.5]));
}

ui.root.clear();
ui.root.setLayout(ui.Panel.Layout.flow('horizontal'));
ui.root.add(leftPanel);
ui.root.add(map);
ui.root.add(rightPanel);
