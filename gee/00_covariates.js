/**
 * =============================================================================
 * Tier 2 habitat-state covariates -- shared module
 * =============================================================================
 * Paste this block ABOVE the app code in 01_biome_review_app.js and
 * 02_visualization_app.js, or save it as a Code Editor script and pull it in
 * with require() if you keep your scripts in a repository:
 *
 *     var cov = require('users/<you>/jaguar:00_covariates');
 *
 * WHAT THIS IS FOR
 *   RESOLVE describes the landscape's native state -- what would grow there
 *   absent land-use change. That is the slow-varying template the biome label
 *   captures. These layers describe the fast-varying condition the collared
 *   animal actually moved through, which the label deliberately does not.
 *   The two are complementary, not competing, so nothing here is allowed to
 *   change a biome suggestion; it only annotates and flags.
 *
 * TIME MATTERS
 *   Tracking runs 1999-2016. Every time-varying source below is indexed to the
 *   individual's own tracking years rather than to today, because "how much
 *   forest is there now" is not the question -- "how much forest was there
 *   while this animal was collared" is.
 * =============================================================================
 */

// ============================================================================
// SOURCES
// ============================================================================

/**
 * Geometry error margin in metres, used by every area, intersection and length
 * operation here. Declared in this module because the module owns the vector
 * road computation; the review app declares the same value for its own overlap
 * maths, and the two agreeing is intentional.
 */
var MAX_ERROR = ee.ErrorMargin(1);

var SRC = {
  // Canopy cover in 2000 plus year-of-loss, so cover can be rebuilt for any
  // year in the tracking window. The universal spine: global, 30 m, and the
  // only habitat-state source that covers all five range countries here.
  hansen: 'UMD/hansen/global_forest_change_2025_v1_13',

  // Net primary productivity. Thompson et al. (2021) found this the second
  // strongest driver of jaguar home range size in this very dataset.
  npp: 'MODIS/061/MOD17A3HGF',

  // Human modification, change-consistent series. Chosen over the static
  // CSP/HM/GlobalHumanModification precisely because it is a time series --
  // 1990-2020 in five-year steps, so it can be matched to tracking years.
  // Its Transportation and Built_up bands are kept alongside the GRIP4 road
  // density below rather than replaced by it: gHM is a modelled 300 m surface
  // that also sees tracks and settlement GRIP4's centrelines miss, and it is
  // the only transport signal available for the two studies GRIP4 covers
  // thinly. Between them they span the road-density and distance-to-settlement
  // covariates Thompson et al. and Rabinowitz & Zeller (2010) identified.
  ghm: 'TNC/HM/v3/300m_c',

  // Population, also multi-temporal. Rabinowitz & Zeller's expert panel ranked
  // human population density among six factors driving jaguar movement cost.
  pop: 'JRC/GHSL/P2023A/GHS_POP',

  // Surface water occurrence and seasonality. 56% of the fixes in this dataset
  // come from Pantanal-cluster studies and a further 6,911 from Mamiraua --
  // flood-pulse systems where de Brito et al. (2025) show movement regime
  // shifts within a single individual between seasons.
  water: 'JRC/GSW1_4/GlobalSurfaceWater',

  // Elevation and ruggedness, the third of Rabinowitz & Zeller's six factors.
  dem: 'USGS/SRTMGL1_003',

  // Protection status. Tested (and dropped) by Thompson et al., but retained
  // here because it conditions hunting pressure, which their model could not
  // observe directly.
  wdpa: 'WCMC/WDPA/current/polygons',

  // GRIP4 road centrelines (Meijer et al. 2018), via the awesome-gee-community
  // catalog. Vector, so road density is computed as clipped line length over
  // range area rather than sampled from a raster -- which is also why it is a
  // better road covariate than the gHM transport band it now supersedes.
  // Two regions are needed: Central-South-America covers Brazil, Paraguay,
  // Argentina and Costa Rica; North-America covers the Mexican studies.
  roadsSouth: 'projects/sat-io/open-datasets/GRIP4/Central-South-America',
  roadsNorth: 'projects/sat-io/open-datasets/GRIP4/North-America'
};

/**
 * GRIP4 road-type attribute, per the published layer documentation:
 * a STRING field named `Highway` taking one of five OpenStreetMap-style
 * classes, not the numeric GP_RTP code of the raw GRIP4 shapefiles.
 *
 * Thompson et al. modelled *primary* road density specifically, so the top
 * three classes are split out. Motorways, trunk roads and primary roads are
 * the paved, high-traffic network -- the one that actually functions as a
 * movement barrier and a source of vehicle mortality. Secondary and tertiary
 * roads are mostly unpaved in this range and behave more like access routes
 * than barriers, which is a different mechanism and belongs in total density.
 *
 * The mixed-case list is a deliberate hedge: the attribute is documented
 * lower-case, but ee.Filter.inList is exact, and a capitalisation mismatch
 * would silently return zero rather than error. See describeRoadAttributes().
 */
var GRIP_TYPE_PROPERTY = 'Highway';
var GRIP_PRIMARY_CLASSES = ['motorway', 'trunk', 'primary'];

function gripPrimaryFilter() {
  var wanted = [];
  GRIP_PRIMARY_CLASSES.forEach(function (v) {
    wanted.push(v);
    wanted.push(v.charAt(0).toUpperCase() + v.slice(1));
    wanted.push(v.toUpperCase());
  });
  return ee.Filter.inList(GRIP_TYPE_PROPERTY, wanted);
}

/**
 * One-off audit: print what the loaded GRIP4 assets actually call their
 * road-type field and which values it takes, over a sample region.
 *
 * Run this once before trusting primary_road_density_km_km2. If the printed
 * property list has no `Highway`, or its values are integers, change
 * GRIP_TYPE_PROPERTY and GRIP_PRIMARY_CLASSES to match.
 */
function describeRoadAttributes(geometry) {
  var roads = ee.FeatureCollection(SRC.roadsSouth).filterBounds(geometry);
  print('GRIP4 -- property names on the first feature:',
        ee.Feature(roads.first()).propertyNames().sort());
  print('GRIP4 -- distinct ' + GRIP_TYPE_PROPERTY + ' values in sample:',
        roads.limit(5000).aggregate_array(GRIP_TYPE_PROPERTY).distinct().sort());
  print('GRIP4 -- segments in sample / of which primary:',
        roads.size(), roads.filter(gripPrimaryFilter()).size());
}

/**
 * Annual gridded livestock (AGLW, Zenodo 10.5281/zenodo.17128483) -- 5 km,
 * heads/km2, one image per species per year, so it indexes to tracking years
 * the way every other time-varying source here does.
 *
 * Not a public catalog dataset; these are your own ingested assets, one image
 * per `<code>_<year><suffix>`, created by upload_aglw_assets.py. That script
 * strips the source `.tif` extension from the asset id, so `suffix` is blank;
 * set it to '.tif' if you ingested them some other way and kept it.
 *
 * WHY MULTIPLE SPECIES AND NOT JUST CATTLE. Jaguar-livestock conflict in this
 * range is overwhelmingly cattle, and retaliatory killing is a real mortality
 * pressure that shapes where animals will and will not go -- so cattle is the
 * layer that matters most, and it drives livestock_large_tlu_km2. The other
 * seven ride along because they are the same 144-file upload and they
 * separate two different things cattle alone conflates: large-bodied stock
 * that is worth a jaguar's while, and the smallholdings whose presence says
 * more about settlement than about prey.
 *
 * Densities are combined in Tropical Livestock Units (Jahnke 1982; FAO), a
 * 250 kg-liveweight equivalent, because summing heads would let a chicken
 * count as much as a bull. The split into large / small / poultry is a
 * jaguar-specific one rather than an agricultural one: only large-bodied
 * stock is routinely taken by jaguars and routinely triggers retaliation,
 * small stock is mostly a puma and ocelot conflict, and poultry is here as an
 * index of dispersed smallholder settlement rather than as prey.
 */
var LIVESTOCK = {
  root: 'projects/perceptive-ivy-780/assets/AGLW/',
  suffix: '',
  years: [1999, 2016],
  species: [
    // code     own field            group      TLU   enabled
    { code: 'Cattl', field: 'cattle_per_km2',  group: 'large',   tlu: 0.70,
      enabled: true },
    { code: 'Buffa', field: 'buffalo_per_km2', group: 'large',   tlu: 0.70,
      enabled: true },
    { code: 'Horse', field: 'horse_per_km2',   group: 'large',   tlu: 0.80,
      enabled: true },
    { code: 'Swine', field: null,              group: 'small',   tlu: 0.20,
      enabled: true },
    { code: 'Goats', field: null,              group: 'small',   tlu: 0.10,
      enabled: true },
    { code: 'Sheep', field: null,              group: 'small',   tlu: 0.10,
      enabled: true },
    { code: 'Chick', field: null,              group: 'poultry', tlu: 0.01,
      enabled: true },
    { code: 'Ducks', field: null,              group: 'poultry', tlu: 0.01,
      enabled: true }
  ]
};

// Years each source actually offers. Requests are clamped or snapped into
// these, so an individual tracked in 1999 does not silently ask MODIS for a
// year that predates the sensor.
var SRC_YEARS = {
  hansen: [2000, 2025],
  npp:    [2001, 2023],
  ghm:    [1990, 1995, 2000, 2005, 2010, 2015, 2020],
  pop:    [1975, 1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020]
};

/**
 * MapBiomas: regional land-use refinement. OPTIONAL -- blank the asset and
 * that region is skipped cleanly.
 *
 * TWO ACCESS PATTERNS, deliberately both supported:
 *
 *   type: 'imagecollection'  -- the official Earth Engine Data Catalog form.
 *       One image per year, single `classification` band, selected with
 *       ee.Filter.eq('year', y).
 *
 *   type: 'multiband'        -- the form the MapBiomas User Toolkit publishes,
 *       and the only form the non-Brazil regions come in. ONE image whose
 *       bands are classification_1985 ... classification_YYYY.
 *
 * Getting this wrong fails loudly rather than silently, because select() on a
 * missing band throws.
 *
 * Paths below are taken from the MapBiomas User Toolkit source
 * (github.com/mapbiomas-brazil/user-toolkit). Year ranges are the collection's
 * documented coverage -- if a select() ever fails on a missing band, the range
 * here is what needs correcting.
 *
 * Legends differ between collections, so everything is reduced to MapBiomas
 * Level 1 (see MB_LEVEL1 below) before any cross-region comparison.
 */
var MAPBIOMAS = {
  // Brazil. The official Earth Engine Data Catalog publishes this as an
  // ImageCollection; the toolkit's equivalent is Collection 10.1 as a
  // multiband image:
  //   'projects/mapbiomas-public/assets/brazil/lulc/collection10_1/mapbiomas_brazil_collection10_1_coverage_v1'
  // Either works -- the catalog form is kept because it is the documented,
  // officially supported one.
  brazil: {
    asset: 'projects/mapbiomas-public/assets/brazil/lulc/v1',
    type: 'imagecollection',
    yearProperty: 'year',
    years: [1985, 2024]
  },

  // Pan-Amazonia Collection 6 (2024). Supersedes the RAISG-hosted Collection 5
  // and extends coverage by a year. Used for Mamiraua.
  amazonia: {
    asset: 'projects/mapbiomas-public/assets/amazon/lulc/collection6/' +
           'mapbiomas_collection60_integration_v1',
    type: 'multiband',
    years: [1985, 2023]
  },

  // Paraguay Collection 2 -- national, so it covers all five Paraguayan
  // studies in one legend: Dry Chaco, Humid Chaco, Atlantic forest, Pantanal
  // and Paraguayan Pantanal. Preferred over splitting the country between the
  // Chaco and Atlantic Forest collections, which left the Paraguayan Pantanal
  // in doubt (it sits north of the Gran Chaco boundary).
  paraguay: {
    asset: 'projects/mapbiomas-public/assets/paraguay/collection2/' +
           'mapbiomas_paraguay_collection2_integration_v1',
    type: 'multiband',
    years: [1985, 2023]
  },

  // Argentina Collection 1. Note the series starts in 1998, not 1985; the
  // year clamp handles that, and all Argentine tracking here postdates it.
  argentina: {
    asset: 'projects/mapbiomas-public/assets/argentina/collection1/' +
           'mapbiomas_argentina_collection1_integration_v1',
    type: 'multiband',
    years: [1998, 2022]
  },

  // Peru Collection 3. Not used by any source individual -- it exists so the
  // Madre de Dios TARGET site can be described in the same terms as the source
  // animals, which is the whole point of the transfer question.
  peru: {
    asset: 'projects/mapbiomas-public/assets/peru/collection3/' +
           'mapbiomas_peru_collection3_integration_v1',
    type: 'multiband',
    years: [1985, 2024]
  },

  // Regional alternatives, configured but unused by STUDY_REGION below.
  // Switch a study to these if you would rather have a regional legend than a
  // national one.
  chaco: {
    asset: 'projects/mapbiomas-public/assets/chaco/lulc/collection5/' +
           'mapbiomas_chaco_collection5_integration_v2',
    type: 'multiband',
    years: [1985, 2023]
  },
  atlantic: {
    asset: 'projects/mapbiomas_af_trinacional/public/collection3/' +
           'mapbiomas_atlantic_forest_collection30_integration_v1',
    type: 'multiband',
    years: [1985, 2022]
  }
};

/** Which MapBiomas collection covers each study in this dataset. */
var STUDY_REGION = {
  // Brazil (94,071 fixes, 69.8%)
  'Jaguar_Taiama': 'brazil',
  'jaguar_Oncafari Project': 'brazil',
  'Sao Bento': 'brazil',
  'Panthera_Pantanal-Jaguar-Project': 'brazil',
  'Rio Negro': 'brazil',
  'IOP': 'brazil',
  'Jaguar Conservation in the Caatinga Biome': 'brazil',
  'Jaguar Conservation in the Atlantic Forest': 'brazil',
  "Jaguars' Movement Pattern in a fragmente landscape": 'brazil',

  // Deliberately pan-Amazonia rather than Brazil: Mamiraua is the closest
  // study to the Madre de Dios target site, and putting both in a comparable
  // legend is what makes the comparison mean anything.
  'Jaguar_Mamiraua': 'amazonia',

  // Paraguay (21,760 fixes, 16.2%) -- one national collection for all five
  // studies, including the Paraguayan Pantanal.
  'Humid Chaco': 'paraguay',
  'Dry Chaco': 'paraguay',
  'Pantanal': 'paraguay',
  'Paraguayan Pantanal': 'paraguay',
  'Atlantic forest': 'paraguay',

  // Argentina (8,469 fixes, 6.3%)
  'Jaguar Conservation in Argentina': 'argentina',

  // No MapBiomas initiative covers Central America or Mexico (10,390 fixes,
  // 7.7%). These fall back to Hansen alone -- which is exactly why Hansen is
  // the spine and MapBiomas is a refinement.
  'Costa Rica': null,
  'Greater Lacandona Ecosystem': null,
  'Jaguar Mex': null,
  'jaguar of sonora': null
};

/**
 * MapBiomas collection describing the TARGET site, for comparing a candidate
 * source individual against Madre de Dios on the same legend.
 */
var TARGET_REGION = 'peru';

/**
 * MapBiomas Level 1 groupings.
 *
 * Taken from the User Toolkit's own `className` dictionary and
 * `transitionsCodes` groupings (mapbiomas-user-toolkit-lulc.js v1.35.0), which
 * are authoritative. Three things here are easy to get wrong:
 *
 *  - The Chaco-specific classes (42-45 pastizal/lenosas, 57-58 cultivo) exist
 *    only in the Chaco and Paraguay legends. Omitting them would leave most of
 *    the natural grassland and shrubland in the Paraguayan studies -- 16% of
 *    the fixes in this dataset -- assigned to no group at all, silently
 *    deflating every fraction for those animals.
 *
 *  - Forest plantation (9) is its own group in MapBiomas, not part of forest,
 *    and is kept separate here. A eucalyptus stand is structurally forest but
 *    is not jaguar habitat in the way native forest is, so folding it in would
 *    overstate habitat quality exactly where plantations are expanding.
 *
 *  - Class 6 is flooded/floodable forest, which matters for the Pantanal and
 *    Mamiraua individuals; class 27 and 0 are "not observed" and belong to no
 *    group, so they are excluded rather than defaulted anywhere.
 */
var MB_LEVEL1 = {
  // 1-8 forest per transitionsCodes; 49 is wooded sandbank vegetation.
  forest:             [1, 2, 3, 4, 5, 6, 7, 8, 49],

  // Kept apart from native forest on purpose -- see note above.
  forest_plantation:  [9],

  // 10-13 natural non-forest; 32 salt flat; 42-45 Chaco pastizal and scattered
  // woody; 50 herbaceous sandbank; 63 steppe.
  natural_non_forest: [10, 11, 12, 13, 32, 42, 43, 44, 45, 50, 63],

  // 14-21, 28 agriculture and pasture; 35-36, 39-41, 46-48 crops;
  // 57-58 Chaco cultivo simple/multiple; 62 cotton.
  farming:            [14, 15, 16, 17, 18, 19, 20, 21, 28, 35, 36, 39, 40, 41,
                       46, 47, 48, 57, 58, 62],

  // 22-25, 29-30 non-vegetated; 34 glacier; 61 salares; 68 other natural
  // non-vegetated.
  non_vegetated:      [22, 23, 24, 25, 29, 30, 34, 61, 68],

  // 26, 31, 33 water; 37-38 artificial water body and reservoirs.
  water:              [26, 31, 33, 37, 38]
};

// ============================================================================
// YEAR SELECTION
// ============================================================================

/** Clamp a year into a [min, max] range. Client-side. */
function clampYear(year, range) {
  return Math.max(range[0], Math.min(range[1], year));
}

/** Snap a year to the nearest value in a discrete list. Client-side. */
function snapYear(year, years) {
  var best = years[0];
  var bestGap = Math.abs(year - best);
  years.forEach(function (y) {
    var gap = Math.abs(year - y);
    if (gap < bestGap) { best = y; bestGap = gap; }
  });
  return best;
}

/**
 * One image from a collection for a given calendar year.
 * Uses filterDate, which relies on system:time_start. If a collection ever
 * lacks it, this is the single function to change.
 */
function imageForYear(assetId, year, band) {
  var start = ee.Date.fromYMD(year, 1, 1);
  var image = ee.Image(
    ee.ImageCollection(assetId).filterDate(start, start.advance(1, 'year')).first()
  );
  return band ? image.select(band) : image;
}

// ============================================================================
// LAYER BUILDERS
// ============================================================================

/**
 * Canopy cover as it stood in `year`: the 2000 baseline with everything lost
 * on or before that year zeroed out. This reconstruction is the whole reason
 * Hansen is preferred over a modern one-shot land cover product.
 */
function forestCoverAtYear(year) {
  var hansen = ee.Image(SRC.hansen);
  var y = clampYear(year, SRC_YEARS.hansen);
  var lossCode = y - 2000;

  var cover = hansen.select('treecover2000');
  if (lossCode > 0) {
    var lost = hansen.select('lossyear').gt(0)
                 .and(hansen.select('lossyear').lte(lossCode));
    cover = cover.where(lost, 0);
  }
  return cover.rename('forest_cover_pct');
}

/** Fraction of the range meeting a canopy-closure threshold in `year`. */
function forestFractionAtYear(year, thresholdPct) {
  return forestCoverAtYear(year).gte(thresholdPct)
    .multiply(100).rename('forest_pct_ge' + thresholdPct);
}

/** Fraction of the range that lost forest between two years, inclusive. */
function forestLossBetween(yearStart, yearEnd) {
  var hansen = ee.Image(SRC.hansen);
  var a = clampYear(yearStart, SRC_YEARS.hansen) - 2000;
  var b = clampYear(yearEnd, SRC_YEARS.hansen) - 2000;
  var lossyear = hansen.select('lossyear');
  return lossyear.gt(0)
    .and(lossyear.gte(Math.max(a, 1)))
    .and(lossyear.lte(Math.max(b, 1)))
    .multiply(100).rename('forest_loss_pct_tracked');
}

function nppAtYear(year) {
  var y = clampYear(year, SRC_YEARS.npp);
  return imageForYear(SRC.npp, y, 'Npp').multiply(0.0001).rename('npp_kgC_m2');
}

/** All nine gHM threat bands for the nearest available year. */
function ghmAtYear(year) {
  var y = snapYear(year, SRC_YEARS.ghm);
  return imageForYear(SRC.ghm, y).select(
    ['All_threats_combined', 'Transportation_and_service_corridors',
     'Built_up', 'Agriculture', 'Human_accessibility', 'Biological_resource_use'],
    ['ghm_overall', 'ghm_transport', 'ghm_builtup',
     'ghm_agriculture', 'ghm_accessibility', 'ghm_resource_use']
  );
}

function popAtYear(year) {
  var y = snapYear(year, SRC_YEARS.pop);
  return imageForYear(SRC.pop, y).rename('pop_per_cell');
}

/**
 * Surface water. `occurrence` is the long-run share of observations that were
 * water; `seasonality` counts months of water per year. Together they separate
 * permanent river from flood-pulse floodplain, which is the distinction that
 * matters for Pantanal and Mamiraua individuals.
 */
function waterBands() {
  var gsw = ee.Image(SRC.water);
  return gsw.select('occurrence').unmask(0).rename('water_occurrence_pct')
    .addBands(
      gsw.select('seasonality').unmask(0).gte(1).and(gsw.select('seasonality').lte(11))
        .multiply(100).rename('water_seasonal_pct')
    );
}

function terrainBands() {
  var dem = ee.Image(SRC.dem).select('elevation');
  return dem.rename('elevation_m')
    .addBands(
      // Terrain ruggedness as the local standard deviation of elevation --
      // cheaper than a true TRI and adequate at home-range scale.
      dem.reduceNeighborhood({
        reducer: ee.Reducer.stdDev(),
        kernel: ee.Kernel.square(3)
      }).rename('terrain_ruggedness_m')
    );
}

/**
 * Percent of the range inside a WDPA protected area.
 *
 * Takes the geometry so the WDPA collection can be filtered to it first --
 * painting the global protected-areas layer once per individual would dominate
 * the runtime of the whole pass.
 */
function protectedFraction(geometry) {
  var nearby = ee.FeatureCollection(SRC.wdpa).filterBounds(geometry);
  return ee.Image(0).byte().paint(nearby, 1)
    .multiply(100).rename('protected_pct');
}

/**
 * Road density over one range, in km of road per km2.
 *
 * GRIP4 is vector, so this clips each road line to the range and sums lengths
 * rather than averaging a coarse density raster. At home-range scale that
 * matters: the published GRIP raster is 5 arcminutes (~8 km), which is larger
 * than some of the female home ranges in this dataset.
 */
function roadDensityStats(geometry) {
  var roads = ee.FeatureCollection(SRC.roadsSouth)
    .merge(ee.FeatureCollection(SRC.roadsNorth))
    .filterBounds(geometry);

  var areaKm2 = geometry.area(MAX_ERROR).divide(1e6);

  var lengthOf = function (collection) {
    var clipped = collection.map(function (f) {
      return f.set('len_km', f.geometry()
        .intersection(geometry, MAX_ERROR)
        .length(MAX_ERROR).divide(1000));
    });
    // aggregate_sum returns null on an empty collection, which would poison
    // the whole dictionary, so an empty result is an explicit zero.
    return ee.Number(ee.Algorithms.If(
      clipped.size().gt(0), clipped.aggregate_sum('len_km'), 0));
  };

  var primary = roads.filter(gripPrimaryFilter());

  // n_primary_road_segments is the diagnostic for a wrong attribute name: if
  // it is 0 for every individual while n_road_segments is not, the filter is
  // matching nothing and the primary density is a false zero, not a real one.
  return ee.Dictionary({
    road_density_km_km2: lengthOf(roads).divide(areaKm2),
    primary_road_density_km_km2: lengthOf(primary).divide(areaKm2),
    n_road_segments: roads.size(),
    n_primary_road_segments: primary.size()
  });
}

/**
 * Livestock density bands for one year, or null when nothing is configured.
 *
 * Emits the large-bodied species individually (they are the ones a reviewer
 * will want to see) plus three TLU aggregates.
 *
 * AGLW ships matched per-pixel uncertainty rasters, and the authors ask that
 * they be consulted for long-term trends and regional inference. They are
 * deliberately NOT ingested here: their stated weak spots are the 1960s-1990s
 * and data-sparse regions, and this study reads only 1999-2016. That is a
 * judgement, not a certainty -- the Gran Chaco interior is thinner ground
 * than the Brazilian south -- so if a reviewer presses on livestock, the
 * uncertainty layers are a separate Zenodo download and this function is
 * where they would attach.
 *
 * The NaN guard matters: AGLW marks ocean with float NaN and sets no NoData
 * tag, so an unguarded coastal home range would reduce to NaN and poison the
 * whole covariate dictionary. `gte(0)` is false for NaN, which masks it, and
 * unmask(0) then reads it as the absence of livestock that it is.
 */
function livestockBands(year) {
  var enabled = LIVESTOCK.species.filter(function (sp) { return sp.enabled; });
  if (!LIVESTOCK.root || enabled.length === 0) { return null; }

  var y = clampYear(year, LIVESTOCK.years);

  var named = null;
  var largeTlu = ee.Image(0);
  var smallTlu = ee.Image(0);
  var poultry = ee.Image(0);

  enabled.forEach(function (sp) {
    var dens = ee.Image(LIVESTOCK.root + sp.code + '_' + y + LIVESTOCK.suffix)
      .select(0).toFloat();
    dens = dens.updateMask(dens.gte(0)).unmask(0);

    var tlu = dens.multiply(sp.tlu);
    if (sp.group === 'large') {
      largeTlu = largeTlu.add(tlu);
    } else if (sp.group === 'small') {
      smallTlu = smallTlu.add(tlu);
    } else {
      poultry = poultry.add(dens);
    }

    if (sp.field) {
      var band = dens.rename(sp.field);
      named = named ? named.addBands(band) : band;
    }
  });

  var out = largeTlu.rename('livestock_large_tlu_km2')
    .addBands(smallTlu.rename('livestock_small_tlu_km2'))
    .addBands(poultry.rename('poultry_per_km2'));

  return (named ? out.addBands(named) : out).toFloat();
}

/** Whether the cattle series is loaded -- the flag text depends on it. */
function cattleAvailable() {
  return LIVESTOCK.species.some(function (sp) {
    return sp.code === 'Cattl' && sp.enabled;
  });
}

/**
 * A single multi-band image carrying every non-MapBiomas covariate, so each
 * individual costs one reduceRegion rather than eight.
 */
function covariateImage(yearStart, yearEnd, yearMid, geometry) {
  var image = forestCoverAtYear(yearMid)
    .addBands(forestFractionAtYear(yearMid, 25))
    .addBands(forestFractionAtYear(yearMid, 50))
    .addBands(forestLossBetween(yearStart, yearEnd))
    .addBands(nppAtYear(yearMid))
    .addBands(ghmAtYear(yearMid))
    .addBands(popAtYear(yearMid))
    .addBands(waterBands())
    .addBands(terrainBands())
    .addBands(protectedFraction(geometry));

  var livestock = livestockBands(yearMid);
  if (livestock) { image = image.addBands(livestock); }
  return image.toFloat();
}

/** The single-year classification image for a MapBiomas config. */
function mapbiomasClassification(config, year) {
  var y = clampYear(year, config.years);

  if (config.type === 'multiband') {
    // Toolkit form: one image, one band per year.
    return ee.Image(config.asset).select(['classification_' + y]);
  }

  // Catalog form: one image per year in a collection.
  return ee.Image(
    ee.ImageCollection(config.asset)
      .filter(ee.Filter.eq(config.yearProperty || 'year', y))
      .first()
  ).select(0);
}

/** MapBiomas Level 1 area fractions, or null when the region has no asset. */
function mapbiomasLevel1(studyName, year) {
  var region = STUDY_REGION[studyName];
  if (!region) { return null; }

  var config = MAPBIOMAS[region];
  if (!config || !config.asset) { return null; }

  var classified = mapbiomasClassification(config, year);

  var bands = null;
  for (var group in MB_LEVEL1) {
    var mask = classified.remap(MB_LEVEL1[group],
                                MB_LEVEL1[group].map(function () { return 1; }), 0)
      .multiply(100).rename('mb_' + group + '_pct');
    bands = bands ? bands.addBands(mask) : mask;
  }
  return bands.toFloat();
}

// ============================================================================
// ECOREGION GUARD
// ============================================================================

/**
 * RESOLVE 2017 fills the gaps between terrestrial ecoregions with two
 * non-ecoregion classes -- large lakes and rock/ice -- which carry a
 * placeholder BIOME_NAME rather than a real one. A 95% AKDE contour drawn
 * around a Pantanal or Mamiraua animal will overlap those polygons, and if
 * they are left in the candidate list the app offers the reviewer a "biome"
 * that describes no vegetation at all and dilutes the weights of the real
 * ones.
 *
 * The guard is deliberately built from a null check plus a numeric-code
 * exclusion rather than a hard-coded list of biome names: name strings drift
 * between RESOLVE releases, BIOME_NUM does not.
 *
 * Mangroves (BIOME_NUM 14) is a real terrestrial biome and is KEPT. Coastal
 * and estuarine jaguars are a genuine part of this species' range, and
 * dropping mangrove would misclassify them, not clean them up.
 */
var NON_TERRESTRIAL_BIOME_NUMS = [98, 99];
var RESOLVE_ASSET = 'RESOLVE/ECOREGIONS/2017';

function terrestrialEcoregions() {
  return ee.FeatureCollection(RESOLVE_ASSET)
    .filter(ee.Filter.notNull(['BIOME_NAME', 'BIOME_NUM', 'ECO_ID']))
    .filter(ee.Filter.inList('BIOME_NUM', NON_TERRESTRIAL_BIOME_NUMS).not())
    .filter(ee.Filter.neq('BIOME_NAME', 'N/A'));
}

/**
 * One-off audit: print what BIOME_NAME actually contains and what the guard
 * removes. Run once, confirm the dropped count is small and consists only of
 * lakes and rock/ice, then trust the guard.
 */
function describeBiomes() {
  var all = ee.FeatureCollection(RESOLVE_ASSET);
  var kept = terrestrialEcoregions();
  print('RESOLVE 2017 -- BIOME_NAME, all features:',
        all.aggregate_array('BIOME_NAME').distinct().sort());
  print('RESOLVE 2017 -- BIOME_NAME, non-null only:',
        all.filter(ee.Filter.notNull(['BIOME_NAME']))
           .aggregate_array('BIOME_NAME').distinct().sort());
  print('RESOLVE 2017 -- BIOME_NUM surviving the guard:',
        kept.aggregate_array('BIOME_NUM').distinct().sort());
  print('RESOLVE 2017 -- features total / kept / dropped:',
        all.size(), kept.size(), all.size().subtract(kept.size()));
}

// ============================================================================
// REDUCTION
// ============================================================================

/**
 * Mean of every covariate band over one home-range polygon.
 *
 * Scale is deliberately coarser than Hansen's native 30 m: these are
 * home-range means over areas up to a few thousand km2, where the extra
 * precision changes nothing and the extra pixels cost seconds of interactive
 * latency. Raise it for the batch export if you want native resolution.
 */
function reduceCovariates(geometry, studyName, yearStart, yearEnd, yearMid, scale) {
  var image = covariateImage(yearStart, yearEnd, yearMid, geometry);
  var mb = mapbiomasLevel1(studyName, yearMid);
  if (mb) { image = image.addBands(mb); }

  // Road density is a vector computation, so it cannot ride along as a band
  // and is merged into the same dictionary afterwards.
  return image.reduceRegion({
    reducer: ee.Reducer.mean(),
    geometry: geometry,
    scale: scale || 120,
    maxPixels: 1e9,
    bestEffort: true,
    tileScale: 4
  }).combine(roadDensityStats(geometry), true);
}

// ============================================================================
// FLAGS
// ============================================================================

/**
 * Derived warnings, computed client-side once covariates are back.
 *
 * These deliberately do NOT alter the biome suggestion. The biome axis answers
 * "what was this landscape natively", the covariates answer "what state was it
 * in" -- letting the second rewrite the first would collapse the distinction
 * the two-tier design exists to preserve. Flags only tell the reviewer where
 * the two disagree enough to be worth a look.
 */
var FOREST_BIOMES = [
  'Tropical & Subtropical Moist Broadleaf Forests',
  'Tropical & Subtropical Dry Broadleaf Forests',
  'Tropical & Subtropical Coniferous Forests',
  'Temperate Broadleaf & Mixed Forests',
  'Mangroves'
];

function deriveFlags(overlaps, selected, covariates) {
  var flags = [];
  if (!overlaps || overlaps.length === 0) { return flags; }

  var top = overlaps[0];

  // Assignment is genuinely split rather than dominated by one ecoregion.
  if (top.usage_weight < 50) {
    flags.push({
      key: 'ambiguous_assignment',
      level: 'warn',
      text: 'No ecoregion holds a majority of fixes (top is ' +
            Math.round(top.usage_weight) + '%).'
    });
  }

  // Area and use disagree about which ecoregion matters most -- the classic
  // signature of a range whose outer contour sprawls into a biome the animal
  // barely entered.
  var byArea = overlaps.slice().sort(function (a, b) {
    return b.area_weight - a.area_weight;
  });
  if (byArea.length > 1 && byArea[0].eco_id !== top.eco_id) {
    flags.push({
      key: 'weight_divergence',
      level: 'warn',
      text: 'Ranked by area the top ecoregion is ' + byArea[0].eco_name +
            ', but by fixes it is ' + top.eco_name + '.'
    });
  }

  // Weights are computed over terrestrial ecoregions only, so a shortfall in
  // either total is range that fell in a lake or rock/ice polygon, outside
  // RESOLVE's coverage, or into candidates too small to list. Fixes matter
  // more than area here: a missing sliver of area is geometric noise, but a
  // fix that lands in no terrestrial ecoregion is a real point the assignment
  // cannot speak for.
  var usageSum = 0, areaSum = 0, haveArea = false;
  overlaps.forEach(function (o) {
    usageSum += o.usage_weight;
    if (o.area_weight >= 0) { areaSum += o.area_weight; haveArea = true; }
  });

  if (usageSum < 99) {
    flags.push({
      key: 'fixes_outside_terrestrial',
      level: 'warn',
      text: Math.round((100 - usageSum) * 10) / 10 + '% of fixes fall in no ' +
            'terrestrial ecoregion (open water, rock & ice, or outside ' +
            'RESOLVE coverage) and contribute to no candidate.'
    });
  } else if (haveArea && areaSum < 95) {
    flags.push({
      key: 'area_outside_terrestrial',
      level: 'info',
      text: Math.round(100 - areaSum) + '% of the 95% contour is not in any ' +
            'listed terrestrial ecoregion. The animal barely used it — ' +
            'weights are renormalised over what is listed.'
    });
  }

  // Time-weighted use and raw fix share disagree, which means the collar's
  // sampling rate was not constant across the ground the animal covered. The
  // time weight is the one to trust -- this flag exists because a large gap
  // is worth knowing about before confirming, not because the number is wrong.
  if (top.fix_share_pct !== undefined &&
      Math.abs(top.usage_weight - top.fix_share_pct) > 5) {
    flags.push({
      key: 'sampling_schedule_bias',
      level: 'info',
      text: 'Top ecoregion holds ' + Math.round(top.usage_weight) +
            '% of tracked time but ' + Math.round(top.fix_share_pct) +
            '% of fixes — the fix schedule changed across this range.'
    });
  }

  if (!covariates) { return flags; }

  // Native label says forest; the landscape during tracking was not.
  var selectedBiomes = selected.map(function (o) { return o.biome_name; });
  var claimsForest = selectedBiomes.some(function (b) {
    return FOREST_BIOMES.indexOf(b) !== -1;
  });
  var forested = covariates.forest_pct_ge25;
  if (claimsForest && forested !== null && forested !== undefined && forested < 30) {
    flags.push({
      key: 'label_state_mismatch',
      level: 'warn',
      text: 'Native biome is forest, but only ' + Math.round(forested) +
            '% of the range had ≥25% canopy during tracking. Expected for a ' +
            'degraded landscape -- keep the label, but note it for transfer.'
    });
  }

  if (covariates.ghm_overall !== null && covariates.ghm_overall > 0.4) {
    flags.push({
      key: 'high_human_modification',
      level: 'warn',
      text: 'Human modification is high (gHM ' +
            (Math.round(covariates.ghm_overall * 100) / 100) + ').'
    });
  }

  if (covariates.water_seasonal_pct !== null && covariates.water_seasonal_pct > 5) {
    flags.push({
      key: 'flood_pulse',
      level: 'info',
      text: Math.round(covariates.water_seasonal_pct) + '% of the range is ' +
            'seasonal water. Movement regime likely shifts between seasons.'
    });
  }

  // Livestock pressure, and whether the livestock map can be believed here.
  var largeStock = covariates.livestock_large_tlu_km2;
  if (largeStock !== null && largeStock !== undefined && largeStock > 5) {
    flags.push({
      key: 'livestock_conflict',
      level: 'info',
      text: Math.round(largeStock * 10) / 10 + ' TLU/km² of large stock' +
            (cattleAvailable() ? '' : ' (buffalo and horses only — the cattle ' +
             'series is not loaded, so this is an undercount)') +
            '. Retaliatory-killing risk is a plausible movement constraint.'
    });
  }

  if (covariates.forest_loss_pct_tracked !== null &&
      covariates.forest_loss_pct_tracked > 2) {
    flags.push({
      key: 'active_deforestation',
      level: 'warn',
      text: Math.round(covariates.forest_loss_pct_tracked * 10) / 10 +
            '% of the range was cleared during the tracking window.'
    });
  }

  return flags;
}

// Field order used everywhere downstream, so the export, the review panel and
// the explorer all agree on what a covariate record contains.
var COVARIATE_FIELDS = [
  'forest_cover_pct', 'forest_pct_ge25', 'forest_pct_ge50',
  'forest_loss_pct_tracked', 'npp_kgC_m2',
  'road_density_km_km2', 'primary_road_density_km_km2',
  'n_road_segments', 'n_primary_road_segments',
  'cattle_per_km2', 'buffalo_per_km2', 'horse_per_km2',
  'livestock_large_tlu_km2', 'livestock_small_tlu_km2', 'poultry_per_km2',
  'ghm_overall', 'ghm_transport', 'ghm_builtup', 'ghm_agriculture',
  'ghm_accessibility', 'ghm_resource_use',
  'pop_per_cell', 'water_occurrence_pct', 'water_seasonal_pct',
  'elevation_m', 'terrain_ruggedness_m', 'protected_pct',
  'mb_forest_pct', 'mb_forest_plantation_pct', 'mb_natural_non_forest_pct',
  'mb_farming_pct', 'mb_non_vegetated_pct', 'mb_water_pct'
];

var COVARIATE_LABELS = {
  forest_cover_pct:        'Mean canopy cover',
  forest_pct_ge25:         'Range with ≥25% canopy',
  forest_pct_ge50:         'Range with ≥50% canopy',
  forest_loss_pct_tracked: 'Cleared during tracking',
  npp_kgC_m2:              'Net primary productivity',
  road_density_km_km2:     'Road density (GRIP4)',
  primary_road_density_km_km2: '— primary roads only',
  n_road_segments:         'Road segments intersecting',
  n_primary_road_segments: '— of which primary',
  cattle_per_km2:          'Cattle density',
  buffalo_per_km2:         'Buffalo density',
  horse_per_km2:           'Horse density',
  livestock_large_tlu_km2: 'Large stock (cattle/buffalo/horse)',
  livestock_small_tlu_km2: 'Small stock (pig/goat/sheep)',
  poultry_per_km2:         'Poultry density',
  ghm_overall:             'Human modification (all)',
  ghm_transport:           '— transport corridors',
  ghm_builtup:             '— built-up',
  ghm_agriculture:         '— agriculture',
  ghm_accessibility:       '— accessibility',
  ghm_resource_use:        '— resource use',
  pop_per_cell:            'Population per cell',
  water_occurrence_pct:    'Surface water occurrence',
  water_seasonal_pct:      'Seasonal water',
  elevation_m:             'Elevation',
  terrain_ruggedness_m:    'Terrain ruggedness',
  protected_pct:           'Inside protected areas',
  mb_forest_pct:           'MapBiomas native forest',
  mb_forest_plantation_pct: 'MapBiomas forest plantation',
  mb_natural_non_forest_pct: 'MapBiomas natural non-forest',
  mb_farming_pct:          'MapBiomas farming',
  mb_non_vegetated_pct:    'MapBiomas non-vegetated',
  mb_water_pct:            'MapBiomas water'
};

var COVARIATE_UNITS = {
  forest_cover_pct: '%', forest_pct_ge25: '%', forest_pct_ge50: '%',
  forest_loss_pct_tracked: '%', npp_kgC_m2: ' kgC/m²',
  road_density_km_km2: ' km/km²', primary_road_density_km_km2: ' km/km²',
  n_road_segments: '', n_primary_road_segments: '',
  cattle_per_km2: ' head/km²', buffalo_per_km2: ' head/km²',
  horse_per_km2: ' head/km²', poultry_per_km2: ' head/km²',
  livestock_large_tlu_km2: ' TLU/km²', livestock_small_tlu_km2: ' TLU/km²',
  pop_per_cell: '', water_occurrence_pct: '%', water_seasonal_pct: '%',
  elevation_m: ' m', terrain_ruggedness_m: ' m', protected_pct: '%',
  mb_forest_pct: '%', mb_forest_plantation_pct: '%',
  mb_natural_non_forest_pct: '%', mb_farming_pct: '%',
  mb_non_vegetated_pct: '%', mb_water_pct: '%'
};

exports.SRC = SRC;
exports.LIVESTOCK = LIVESTOCK;
exports.cattleAvailable = cattleAvailable;
exports.terrestrialEcoregions = terrestrialEcoregions;
exports.describeBiomes = describeBiomes;
exports.describeRoadAttributes = describeRoadAttributes;
exports.MAPBIOMAS = MAPBIOMAS;
exports.STUDY_REGION = STUDY_REGION;
exports.covariateImage = covariateImage;
exports.mapbiomasLevel1 = mapbiomasLevel1;
exports.reduceCovariates = reduceCovariates;
exports.deriveFlags = deriveFlags;
exports.COVARIATE_FIELDS = COVARIATE_FIELDS;
exports.COVARIATE_LABELS = COVARIATE_LABELS;
exports.COVARIATE_UNITS = COVARIATE_UNITS;
exports.forestCoverAtYear = forestCoverAtYear;
