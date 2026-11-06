// ESA CCI via documented Conservation International / Trends.Earth mirror.
// Access pilot only. 2005 is not a production representative-year choice.
// Citation and validation: mirror_provenance.json, mirror_comparison.json.
var source = ee.Image('users/geflanddegradation/toolbox_datasets/lcov_esacc_1992_2022');
var lc = source.select('y2005');
// Preserve original thematic classes; never average class codes.
var valid = lc.mask().gt(0).and(lc.neq(0)).and(lc.neq(9999)).and(lc.neq(-32768));
lc = lc.updateMask(valid);
var aoi = ee.Geometry.Rectangle([-58.31388888887916,-20.6555555555644,
                                -55.89999999999008,-16.761111111119646], 'EPSG:4326', false);
Map.centerObject(aoi, 7);
Map.addLayer(lc.clip(aoi), {min:10,max:220}, 'ESA CCI original classes, 2005');
Map.addLayer(lc.eq(120).or(lc.eq(121)).or(lc.eq(122)).selfMask().clip(aoi),
             {palette:['b39b27']}, 'Shrubland candidate 120/121/122');
print('Available year bands', source.bandNames());
print('Native source projection', lc.projection());
// No export or ingestion task is created.
