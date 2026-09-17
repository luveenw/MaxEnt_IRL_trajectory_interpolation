/**
 * =============================================================================
 * Step 3 - Jaguar Home Range Explorer (read-only)
 * =============================================================================
 * Paste this whole file into the Google Earth Engine Code Editor and Run.
 *
 * WHAT IT DOES
 *   Browses the biome-assigned home ranges from Step 2 through three cascading
 *   multi-select filters -- biome type, then study, then individual. Draws the
 *   95% AKDE contours and 50% core areas of whatever is selected, colour-coded
 *   by biome, and can drop into a per-individual detail view showing the raw
 *   GPS fixes and each temporal segment in its own colour.
 *
 * PREREQUISITE
 *   Run the Step 2 review app, run its `biome_assignments_export_csv` task, then
 *   upload the resulting biome_assignments_export.csv as a GEE table asset:
 *
 *     Assets -> NEW -> CSV file
 *       Geometry: the `.geo` column (usually auto-detected)
 *       Asset ID: <ASSET_ROOT>/biome_assignments
 *
 *   The CSV is used rather than the GeoJSON because Earth Engine's table
 *   ingestion accepts Shapefile and CSV only.
 *
 * A NOTE ON HOVER
 *   The plan asked for hover-to-toggle detail. Earth Engine's ui.Map exposes
 *   onClick but has no hover event for vector features, so detail view is
 *   opened by clicking a contour on the map (or an individual in the list).
 * =============================================================================
 */

// ============================================================================
// CONFIG -- edit these lines
// ============================================================================

/** Must match the ASSET_ROOT used in 01_biome_review_app.js. */
var ASSET_ROOT = 'projects/REPLACE-WITH-YOUR-PROJECT/assets/jaguar_biome';

/** Asset holding the Step 2 export (uploaded from biome_assignments_export.csv). */
var ASSIGNMENTS_ASSET = ASSET_ROOT + '/biome_assignments';

/** Raw GPS fixes, created by upload_gee_assets.sh. */
var GPS_ASSET = ASSET_ROOT + '/gps_points';

/**
 * Tier 2 habitat covariates, one row per individual, from the review app's
 * `individual_covariates_csv` task. OPTIONAL -- set to '' and the explorer
 * simply omits the habitat panel and filter.
 *
 * Upload the downloaded CSV via Assets -> NEW -> CSV file with no geometry
 * column (it is a plain table), then point this at it.
 */
var COVARIATES_ASSET = ASSET_ROOT + '/individual_covariates';

/** Covariates offered in the habitat filter, in menu order. */
var FILTERABLE_COVARIATES = [
  'forest_pct_ge25', 'forest_cover_pct', 'forest_loss_pct_tracked',
  'road_density_km_km2', 'primary_road_density_km_km2',
  'livestock_large_tlu_km2', 'cattle_per_km2',
  'ghm_overall', 'npp_kgC_m2',
  'water_seasonal_pct', 'protected_pct', 'pop_per_cell',
  'mb_forest_pct', 'mb_forest_plantation_pct', 'mb_farming_pct'
];

// ============================================================================
// DATA
// ============================================================================

var assignments = ee.FeatureCollection(ASSIGNMENTS_ASSET);
var gpsPoints = ee.FeatureCollection(GPS_ASSET);
// Same terrestrial guard the review app assigns under, so the outlines drawn
// here are exactly the polygons that could have been chosen.
var ecoregions = terrestrialEcoregions();

var akde95 = assignments.filter(
  ee.Filter.and(ee.Filter.eq('contour_level', 95), ee.Filter.eq('segment_id', 0))
);
var akde50 = assignments.filter(
  ee.Filter.and(ee.Filter.eq('contour_level', 50), ee.Filter.eq('segment_id', 0))
);
var segments95 = assignments.filter(
  ee.Filter.and(ee.Filter.eq('contour_level', 95), ee.Filter.gt('segment_id', 0))
);
// Individuals with no AKDE contour are exported with contour_level = -1.
var hulls = assignments.filter(ee.Filter.eq('contour_level', -1));

// ============================================================================
// PALETTE
// ============================================================================

// One colour per RESOLVE biome. This covers all fourteen that survive the
// terrestrial guard -- confirmed against the asset's own distinct BIOME_NAME
// list -- so the grey fallback below is unreachable, and grey on the map means
// a genuine data problem rather than a palette gap.
//
// The last three never appear in this dataset, which spans Sonora to Misiones.
// They are here so that stays a fact about the data and not an assumption
// baked into the palette.
var BIOME_COLORS = {
  'Tropical & Subtropical Moist Broadleaf Forests': '1B7837',
  'Tropical & Subtropical Dry Broadleaf Forests': '92C46D',
  'Tropical & Subtropical Coniferous Forests': '2E8B7A',
  'Tropical & Subtropical Grasslands, Savannas & Shrublands': 'E8B33B',
  'Flooded Grasslands & Savannas': '3D9AD1',
  'Montane Grasslands & Shrublands': 'B07AA1',
  'Deserts & Xeric Shrublands': 'D9762B',
  'Mediterranean Forests, Woodlands & Scrub': 'C44E52',
  'Temperate Grasslands, Savannas & Shrublands': 'C7A76C',
  'Temperate Broadleaf & Mixed Forests': '4C7A3F',
  'Mangroves': '7B4EA3',
  'Boreal Forests/Taiga': '3B5F52',
  'Temperate Conifer Forests': '6E9B8A',
  'Tundra': 'A8B8C4'
};
var FALLBACK_COLOR = '888888';

// Distinct colours for temporal segments within one individual.
var SEGMENT_COLORS = ['E6194B', '3CB44B', '4363D8', 'F58231', '911EB4',
                      '46F0F0', 'F032E6', 'BCF60C'];

function biomeColor(name) {
  return BIOME_COLORS[name] || FALLBACK_COLOR;
}

/** First element of a pipe-delimited biome_type string. */
function primaryBiome(biomeType) {
  if (!biomeType) { return ''; }
  return String(biomeType).split('|')[0];
}

// ============================================================================
// STYLE CONSTANTS
// ============================================================================

var S = {
  left: { width: '320px', padding: '8px', backgroundColor: '#fafafa' },
  right: { width: '330px', padding: '8px', backgroundColor: '#fafafa' },
  h1: { fontSize: '15px', fontWeight: 'bold', margin: '4px 8px 2px 8px' },
  h2: { fontSize: '13px', fontWeight: 'bold', margin: '10px 8px 2px 8px' },
  note: { fontSize: '11px', color: '#666', margin: '0 8px 6px 8px' },
  meta: { fontSize: '12px', margin: '1px 8px' },
  cb: { fontSize: '11px', margin: '0px 0px 0px 4px', padding: '0px' }
};

// ============================================================================
// STATE
// ============================================================================

var catalog = [];            // one entry per individual, from the assignments asset
var selectedBiomes = {};     // biome name -> true
var selectedStudies = {};    // study name -> true
var selectedIds = {};        // individual_id -> true
var detailIds = {};          // individual_id -> true (detail view on)
var covariates = {};         // individual_id -> Tier 2 record, if loaded
var habitatField = null;     // covariate currently constraining the map
var habitatMin = null;       // inclusive lower bound, or null for no bound

// ============================================================================
// UI SKELETON
// ============================================================================

var map = ui.Map();
map.setOptions('HYBRID');
map.setCenter(-58, -16, 4);

var leftPanel = ui.Panel({ style: S.left });
var rightPanel = ui.Panel({ style: S.right });

var biomePanel = ui.Panel({ style: { height: '170px', margin: '0px' } });
var studyPanel = ui.Panel({ style: { height: '150px', margin: '0px' } });
var idPanel = ui.Panel({ style: { height: '190px', margin: '0px' } });
var detailPanel = ui.Panel({ style: { margin: '0px' } });
var legendPanel = ui.Panel({ style: { margin: '0px' } });

var statusLabel = ui.Label('Loading assignments...', S.note);
var habitatStatus = ui.Label('Loading habitat covariates...', S.note);
var habitatPanel = ui.Panel({ style: { margin: '0px' } });

// ---- layer toggles -------------------------------------------------------

var showEcoregions = ui.Checkbox({
  label: 'RESOLVE ecoregion outlines', value: false,
  onChange: refreshMap, style: { fontSize: '12px', margin: '2px 8px' }
});
var show95 = ui.Checkbox({
  label: '95% AKDE home range', value: true,
  onChange: refreshMap, style: { fontSize: '12px', margin: '2px 8px' }
});
var show50 = ui.Checkbox({
  label: '50% AKDE core area', value: true,
  onChange: refreshMap, style: { fontSize: '12px', margin: '2px 8px' }
});
var showSegments = ui.Checkbox({
  label: 'Temporal segments (range shifts)', value: false,
  onChange: refreshMap, style: { fontSize: '12px', margin: '2px 8px' }
});

// ============================================================================
// CATALOG LOADING
// ============================================================================

akde95.merge(hulls)
  .select(['individual_id', 'study_name', 'sex', 'area_km2', 'n_gps_points',
           'trajectory_days', 'ctmm_model', 'is_range_shift', 'n_core_areas',
           'biome_type', 'ecoregion_name', 'n_biomes', 'assignment_status',
           'assignment_method', 'usage_weight', 'area_weight',
           'n_fixes_inside', 'rejected_ecoregion_name', 'rejected_usage_weight',
           'rank_mode', 'review_flags'], null, false)
  .sort('individual_id')
  .evaluate(function (fc, err) {
    if (err) {
      statusLabel.setValue('Failed to load ' + ASSIGNMENTS_ASSET + ': ' + err);
      return;
    }

    catalog = fc.features.map(function (f) { return f.properties; });

    // Every biome that appears anywhere in any individual's pipe-delimited list
    // becomes a filter option, not just the primary one.
    var biomes = {};
    catalog.forEach(function (c) {
      String(c.biome_type || '').split('|').forEach(function (b) {
        if (b) { biomes[b] = true; }
      });
    });

    Object.keys(biomes).sort().forEach(function (b) { selectedBiomes[b] = true; });

    renderBiomeFilter(Object.keys(biomes).sort());
    renderStudyFilter();
    renderIdFilter();
    renderLegend();
    refreshMap();
    loadCovariates();
  });

/**
 * Pull the Tier 2 table, if one is configured.
 *
 * Failure here is deliberately non-fatal: the biome explorer is complete
 * without habitat covariates, and a missing optional asset should not take
 * the whole app down.
 */
function loadCovariates() {
  if (!COVARIATES_ASSET) {
    habitatStatus.setValue('No covariate asset configured.');
    return;
  }

  ee.FeatureCollection(COVARIATES_ASSET).evaluate(function (fc, err) {
    if (err || !fc || !fc.features) {
      habitatStatus.setValue(
        'Covariates unavailable — check COVARIATES_ASSET. Everything else works.');
      return;
    }

    fc.features.forEach(function (f) {
      var props = f.properties || {};
      if (props.individual_id === undefined) { return; }
      covariates[Number(props.individual_id)] = props;
    });

    var n = Object.keys(covariates).length;
    habitatStatus.setValue('Habitat covariates loaded for ' + n + ' individuals.');
    renderHabitatFilter();
    renderDetailPanel();
  });
}

// ============================================================================
// CASCADING FILTERS
// ============================================================================

/** Individuals whose biome list intersects the checked biomes. */
function biomeMatched() {
  return catalog.filter(function (c) {
    var list = String(c.biome_type || '').split('|');
    for (var i = 0; i < list.length; i++) {
      if (selectedBiomes[list[i]]) { return true; }
    }
    return false;
  });
}

/** Individuals passing the biome filter AND the study filter. */
function studyMatched() {
  return biomeMatched().filter(function (c) {
    return selectedStudies[c.study_name] === true;
  });
}

/** True when an individual clears the active habitat-covariate threshold. */
function passesHabitat(c) {
  if (!habitatField || habitatMin === null) { return true; }
  var record = covariates[c.individual_id];
  // Individuals with no covariate row are kept rather than silently dropped;
  // absence of evidence is not evidence of a low value.
  if (!record) { return true; }
  var value = record[habitatField];
  if (value === null || value === undefined) { return true; }
  return Number(value) >= habitatMin;
}

/** Individuals passing every filter -- what actually gets drawn. */
function visibleIndividuals() {
  return studyMatched().filter(function (c) {
    return selectedIds[c.individual_id] === true && passesHabitat(c);
  });
}

/** Observed range of one covariate across everything loaded. */
function covariateRange(field) {
  var lo = null, hi = null;
  for (var id in covariates) {
    var v = covariates[id][field];
    if (v === null || v === undefined) { continue; }
    v = Number(v);
    if (lo === null || v < lo) { lo = v; }
    if (hi === null || v > hi) { hi = v; }
  }
  if (lo === null) { return null; }
  return { min: lo, max: hi };
}

/**
 * Filter the map by habitat state.
 *
 * This is the control that actually serves the transfer question: the biome
 * label says what a landscape natively was, and this says what condition it
 * was in, so "native moist forest AND still ≥60% canopy during tracking" is
 * expressible where either axis alone could not express it.
 */
function renderHabitatFilter() {
  habitatPanel.clear();

  if (Object.keys(covariates).length === 0) { return; }

  var items = [{ label: 'No habitat filter', value: '' }];
  FILTERABLE_COVARIATES.forEach(function (f) {
    if (covariateRange(f)) { items.push({ label: f, value: f }); }
  });

  var slider = null;
  var readout = ui.Label('', S.note);

  var fieldSelect = ui.Select({
    items: items,
    value: habitatField || '',
    onChange: function (v) {
      habitatField = v || null;
      habitatMin = null;
      renderHabitatFilter();
      refreshMap();
    },
    style: { width: '290px', margin: '2px 8px' }
  });

  habitatPanel.add(fieldSelect);

  if (habitatField) {
    var range = covariateRange(habitatField);
    var step = (range.max - range.min) / 100 || 0.01;

    slider = ui.Slider({
      min: range.min,
      max: range.max,
      value: habitatMin === null ? range.min : habitatMin,
      step: step,
      onChange: function (v) {
        habitatMin = v;
        readout.setValue('Showing individuals with ' + habitatField +
                         ' ≥ ' + (Math.round(v * 1000) / 1000));
        refreshMap();
      },
      style: { width: '280px', margin: '2px 8px' }
    });

    habitatPanel.add(slider);
    habitatPanel.add(readout);
    readout.setValue('Drag to set a minimum for ' + habitatField + '.');
  }
}

function renderBiomeFilter(biomeNames) {
  biomePanel.clear();

  biomeNames.forEach(function (b) {
    var swatch = ui.Label({
      value: '█',
      style: { color: '#' + biomeColor(b), fontSize: '13px',
               margin: '0px 0px 0px 6px', padding: '0px' }
    });
    var cb = ui.Checkbox({
      label: b,
      value: selectedBiomes[b] === true,
      onChange: function (v) {
        if (v) { selectedBiomes[b] = true; } else { delete selectedBiomes[b]; }
        // Narrowing biomes can orphan studies and individuals, so rebuild the
        // dependent filters rather than leaving stale selections behind.
        renderStudyFilter();
        renderIdFilter();
        refreshMap();
      },
      style: S.cb
    });
    biomePanel.add(ui.Panel({
      widgets: [swatch, cb],
      layout: ui.Panel.Layout.flow('horizontal'),
      style: { margin: '0px', padding: '0px' }
    }));
  });
}

function renderStudyFilter() {
  studyPanel.clear();

  var studies = {};
  biomeMatched().forEach(function (c) { studies[c.study_name] = true; });
  var names = Object.keys(studies).sort();

  // Default newly-available studies to checked so narrowing a biome does not
  // silently blank the map.
  names.forEach(function (n) {
    if (selectedStudies[n] === undefined) { selectedStudies[n] = true; }
  });

  names.forEach(function (n) {
    var count = biomeMatched().filter(function (c) {
      return c.study_name === n;
    }).length;

    studyPanel.add(ui.Checkbox({
      label: n + ' (' + count + ')',
      value: selectedStudies[n] === true,
      onChange: function (v) {
        if (v) { selectedStudies[n] = true; } else { delete selectedStudies[n]; }
        renderIdFilter();
        refreshMap();
      },
      style: S.cb
    }));
  });

  if (names.length === 0) {
    studyPanel.add(ui.Label('No studies match the biome filter.', S.note));
  }
}

function renderIdFilter() {
  idPanel.clear();

  var candidates = studyMatched();
  candidates.forEach(function (c) {
    if (selectedIds[c.individual_id] === undefined) {
      selectedIds[c.individual_id] = true;
    }
  });

  candidates.forEach(function (c) {
    var swatch = ui.Label({
      value: '█',
      style: { color: '#' + biomeColor(primaryBiome(c.biome_type)),
               fontSize: '13px', margin: '0px 0px 0px 6px', padding: '0px' }
    });
    var cb = ui.Checkbox({
      // Guarded: a null sex would otherwise throw and blank the whole list.
      label: 'ID ' + c.individual_id + ' · ' + String(c.sex || '?').charAt(0),
      value: selectedIds[c.individual_id] === true,
      onChange: function (v) {
        if (v) {
          selectedIds[c.individual_id] = true;
        } else {
          delete selectedIds[c.individual_id];
        }
        refreshMap();
      },
      style: S.cb
    });
    var detail = ui.Button({
      label: detailIds[c.individual_id] ? 'hide' : 'detail',
      onClick: function () { toggleDetail(c.individual_id); },
      style: { margin: '0px 0px 0px 4px', padding: '0px', fontSize: '10px' }
    });

    idPanel.add(ui.Panel({
      widgets: [swatch, cb, detail],
      layout: ui.Panel.Layout.flow('horizontal'),
      style: { margin: '0px', padding: '0px' }
    }));
  });

  if (candidates.length === 0) {
    idPanel.add(ui.Label('No individuals match these filters.', S.note));
  }
}

// ---- bulk filter buttons -------------------------------------------------

function bulkButton(label, fn) {
  return ui.Button({
    label: label, onClick: fn,
    style: { margin: '1px 4px', padding: '0px', fontSize: '10px' }
  });
}

function setAllIds(value) {
  studyMatched().forEach(function (c) {
    if (value) {
      selectedIds[c.individual_id] = true;
    } else {
      delete selectedIds[c.individual_id];
    }
  });
  renderIdFilter();
  refreshMap();
}

// ============================================================================
// DETAIL VIEW
// ============================================================================

function toggleDetail(id) {
  if (detailIds[id]) { delete detailIds[id]; } else { detailIds[id] = true; }
  renderIdFilter();
  renderDetailPanel();
  refreshMap();
}

function renderDetailPanel() {
  detailPanel.clear();

  var ids = Object.keys(detailIds);
  if (ids.length === 0) {
    detailPanel.add(ui.Label(
      'Click "detail" beside an individual, or click a contour on the map, ' +
      'to load its raw GPS fixes.', S.note));
    return;
  }

  ids.forEach(function (idStr) {
    var id = Number(idStr);
    var entry = null;
    for (var i = 0; i < catalog.length; i++) {
      if (catalog[i].individual_id === id) { entry = catalog[i]; break; }
    }
    if (!entry) { return; }

    detailPanel.add(ui.Label(
      'ID ' + id + ' · ' + entry.study_name, S.h2));
    detailPanel.add(ui.Label('Sex: ' + entry.sex, S.meta));
    detailPanel.add(ui.Label(
      'Fixes: ' + entry.n_gps_points +
      (entry.trajectory_days >= 0
        ? '  ·  ' + Math.round(entry.trajectory_days) + ' d' : ''), S.meta));
    if (entry.area_km2 >= 0) {
      detailPanel.add(ui.Label(
        '95% AKDE: ' + Math.round(entry.area_km2 * 10) / 10 + ' km²  ·  cores: ' +
        entry.n_core_areas, S.meta));
      detailPanel.add(ui.Label('Model: ' + entry.ctmm_model, S.meta));
    } else {
      detailPanel.add(ui.Label(
        'No AKDE contour — biome assigned from raw fixes.', S.meta));
    }
    // The four assignment lists are positionally paired, so render them as
    // rows rather than four separate pipe-delimited strings the reader has to
    // line up by eye.
    var ecos = String(entry.ecoregion_name || '').split('|');
    var biomes = String(entry.biome_type || '').split('|');
    var usage = String(entry.usage_weight || '').split('|');
    var area = String(entry.area_weight || '').split('|');

    detailPanel.add(ui.Label('Assignment', S.h2));
    ecos.forEach(function (eco, i) {
      if (!eco) { return; }
      detailPanel.add(ui.Label(eco, {
        fontSize: '11px', fontWeight: 'bold', margin: '2px 8px 0px 8px'
      }));
      detailPanel.add(ui.Label(biomes[i] || '—', {
        fontSize: '10px', color: '#666', margin: '0px 8px 0px 16px'
      }));
      detailPanel.add(ui.Label(
        'use ' + (usage[i] === undefined ? '?' : usage[i]) + '%' +
        '   ·   area ' + (area[i] === undefined ? '?' :
                          (Number(area[i]) < 0 ? 'n/a' : area[i] + '%')), {
        fontSize: '10px', color: '#888', margin: '0px 8px 2px 16px'
      }));
    });

    if (entry.rejected_ecoregion_name) {
      detailPanel.add(ui.Label(
        'Offered and not taken: ' + entry.rejected_ecoregion_name +
        ' (' + entry.rejected_usage_weight + '% use)', S.note));
    }

    detailPanel.add(ui.Label(
      'Assignment: ' + entry.assignment_status + ' · ' +
      entry.assignment_method +
      (entry.rank_mode ? ' · ranked by ' + entry.rank_mode : ''), S.meta));

    if (entry.review_flags) {
      detailPanel.add(ui.Label('Flags: ' + entry.review_flags, {
        fontSize: '10px', color: '#b00', margin: '2px 8px'
      }));
    }

    var record = covariates[id];
    if (record) {
      detailPanel.add(ui.Label('Habitat during tracking', S.h2));
      detailPanel.add(ui.Label(
        'Years ' + record.year_start + '–' + record.year_end +
        ' · from ' + record.covariate_geometry, S.note));

      FILTERABLE_COVARIATES.forEach(function (field) {
        var v = record[field];
        if (v === null || v === undefined) { return; }
        v = Number(v);
        detailPanel.add(ui.Label(
          field + ': ' + (Math.abs(v) >= 100 ? Math.round(v)
                                             : Math.round(v * 1000) / 1000), {
          fontSize: '10px', color: '#555', margin: '0px 8px 0px 12px'
        }));
      });
    }
    detailPanel.add(ui.Button({
      label: 'Zoom to ID ' + id,
      onClick: function () {
        map.centerObject(
          assignments.filter(ee.Filter.eq('individual_id', id)), 10);
      },
      style: { margin: '2px 8px', fontSize: '11px' }
    }));
  });
}

// ============================================================================
// MAP RENDERING
// ============================================================================

function refreshMap() {
  map.layers().reset();

  if (showEcoregions.getValue()) {
    map.addLayer(
      ecoregions.style({ color: 'FFFFFFAA', fillColor: '00000000', width: 1 }),
      {}, 'RESOLVE ecoregions');
  }

  var visible = visibleIndividuals();
  var ids = visible.map(function (c) { return c.individual_id; });

  statusLabel.setValue(
    'Showing ' + visible.length + ' of ' + catalog.length + ' individuals');

  if (ids.length === 0) { renderDetailPanel(); return; }

  var idFilter = ee.Filter.inList('individual_id', ids);

  // Group individuals by primary biome so each biome renders as one layer.
  // Drawing 115 separate layers would make the map unusable.
  var byBiome = {};
  visible.forEach(function (c) {
    var b = primaryBiome(c.biome_type) || 'Unassigned';
    if (!byBiome[b]) { byBiome[b] = []; }
    byBiome[b].push(c.individual_id);
  });

  if (show50.getValue()) {
    Object.keys(byBiome).forEach(function (b) {
      var color = biomeColor(b);
      map.addLayer(
        akde50.filter(ee.Filter.inList('individual_id', byBiome[b]))
          .style({ color: color + 'FF', fillColor: color + '99', width: 1 }),
        {}, '50% core · ' + b, true);
    });
  }

  if (show95.getValue()) {
    Object.keys(byBiome).forEach(function (b) {
      var color = biomeColor(b);
      map.addLayer(
        akde95.filter(ee.Filter.inList('individual_id', byBiome[b]))
          .style({ color: color + 'FF', fillColor: color + '33', width: 2 }),
        {}, '95% AKDE · ' + b, true);
    });

    // Point-only individuals get their convex hull drawn dashed-thin instead.
    map.addLayer(
      hulls.filter(idFilter)
        .style({ color: 'FFFFFFCC', fillColor: 'FFFFFF22', width: 1 }),
      {}, 'GPS hull (no AKDE)', true);
  }

  if (showSegments.getValue()) {
    // segment_id is 1-based; colour each segment distinctly across all shown
    // individuals so range-shift structure is visible at a glance.
    SEGMENT_COLORS.forEach(function (color, i) {
      var segId = i + 1;
      map.addLayer(
        segments95.filter(ee.Filter.and(idFilter,
                                        ee.Filter.eq('segment_id', segId)))
          .style({ color: color + 'FF', fillColor: color + '33', width: 2 }),
        {}, 'Segment ' + segId, true);
    });
  }

  // Detail view: raw fixes for each individual toggled on.
  Object.keys(detailIds).forEach(function (idStr) {
    var id = Number(idStr);
    map.addLayer(
      gpsPoints.filter(ee.Filter.eq('individual_id', id))
        .style({ color: 'FFFFFFDD', pointSize: 2 }),
      {}, 'GPS fixes · ID ' + id, true);
  });

  renderDetailPanel();
}

// ---- click-to-detail on the map -----------------------------------------

map.onClick(function (coords) {
  var pt = ee.Geometry.Point([coords.lon, coords.lat]);
  var hit = akde95.merge(hulls).filterBounds(pt)
    .select(['individual_id'], null, false);

  hit.aggregate_array('individual_id').evaluate(function (arr, err) {
    if (err || !arr || arr.length === 0) { return; }
    // Only toggle individuals the current filters actually show.
    var shown = {};
    visibleIndividuals().forEach(function (c) { shown[c.individual_id] = true; });
    arr.forEach(function (id) { if (shown[id]) { toggleDetail(id); } });
  });
});

// ============================================================================
// LEGEND
// ============================================================================

function renderLegend() {
  legendPanel.clear();

  var present = {};
  catalog.forEach(function (c) {
    String(c.biome_type || '').split('|').forEach(function (b) {
      if (b) { present[b] = true; }
    });
  });

  Object.keys(present).sort().forEach(function (b) {
    legendPanel.add(ui.Panel({
      widgets: [
        ui.Label('█', { color: '#' + biomeColor(b), fontSize: '13px',
                        margin: '0px 4px 0px 8px', padding: '0px' }),
        ui.Label(b, { fontSize: '10px', margin: '0px', padding: '0px' })
      ],
      layout: ui.Panel.Layout.flow('horizontal'),
      style: { margin: '0px', padding: '0px' }
    }));
  });

  legendPanel.add(ui.Label('Contour styling', S.h2));
  legendPanel.add(ui.Label(
    '95% AKDE: thick outline, light fill\n' +
    '50% core: thin outline, solid fill\n' +
    'GPS hull (white): individual with no AKDE\n' +
    'Segments: one colour per segment index',
    { fontSize: '10px', color: '#555', margin: '0px 8px', whiteSpace: 'pre' }));
}

// ============================================================================
// ASSEMBLY
// ============================================================================

leftPanel.add(ui.Label('Jaguar Home Range Explorer', S.h1));
leftPanel.add(statusLabel);

leftPanel.add(ui.Label('Biome type', S.h2));
leftPanel.add(biomePanel);

leftPanel.add(ui.Label('Study', S.h2));
leftPanel.add(studyPanel);

leftPanel.add(ui.Label('Habitat state', S.h2));
leftPanel.add(habitatStatus);
leftPanel.add(habitatPanel);

leftPanel.add(ui.Label('Individual', S.h2));
leftPanel.add(ui.Panel({
  widgets: [
    bulkButton('select all', function () { setAllIds(true); }),
    bulkButton('clear all', function () { setAllIds(false); }),
    bulkButton('hide all detail', function () {
      detailIds = {}; renderIdFilter(); refreshMap();
    }),
    bulkButton('show all detail', function () {
      // Bounded on purpose: every detail layer is a separate tile request, and
      // rendering 115 of them at once locks up the Code Editor.
      var shown = visibleIndividuals();
      if (shown.length > 12) {
        statusLabel.setValue(
          'Detail view is capped at 12 individuals — ' + shown.length +
          ' are selected. Narrow the filters first.');
        return;
      }
      shown.forEach(function (c) { detailIds[c.individual_id] = true; });
      renderIdFilter(); refreshMap();
    })
  ],
  layout: ui.Panel.Layout.flow('horizontal'),
  style: { margin: '0px', padding: '0px' }
}));
leftPanel.add(idPanel);

rightPanel.add(ui.Label('Layers', S.h1));
rightPanel.add(showEcoregions);
rightPanel.add(show95);
rightPanel.add(show50);
rightPanel.add(showSegments);
rightPanel.add(ui.Label('Detail view', S.h1));
rightPanel.add(detailPanel);
rightPanel.add(ui.Label('Legend', S.h1));
rightPanel.add(legendPanel);

ui.root.clear();
ui.root.setLayout(ui.Panel.Layout.flow('horizontal'));
ui.root.add(leftPanel);
ui.root.add(map);
ui.root.add(rightPanel);
