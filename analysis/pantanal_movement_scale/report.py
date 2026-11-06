"""Render the movement-scale audit as one portable HTML report (embedded figures)."""
import base64
import csv
import html
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT/'results'


def records(name):
    with (OUT/name).open() as stream:
        return list(csv.DictReader(stream))


def table(headers, rows):
    return '<div class="table"><table><thead><tr>'+''.join(f'<th>{html.escape(x)}</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{html.escape(str(x))}</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def fig(name, caption):
    data=base64.b64encode((OUT/name).read_bytes()).decode()
    return f'<figure><img src="data:image/png;base64,{data}" alt="{html.escape(caption)}"><figcaption>{caption}</figcaption></figure>'


def number(row, key, decimals=0):
    return f'{float(row[key]):,.{decimals}f}'


def download(name, mime='text/csv'):
    data=base64.b64encode((OUT/name).read_bytes()).decode()
    return f'<li><a download="{name}" href="data:{mime};base64,{data}">{name}</a></li>'


metrics=records('season_metrics.csv')
allrows=[r for r in metrics if r['scope']=='all_retained']
balanced=records('animal_balanced_metrics.csv')
primary=table(['Season','Animals / bursts','Steps','Median [IQR], m','95th percentile, m','Mean, m','Median / P95 speed, km/h'],[
    [r['season'].title(),f"{r['animals']} / {r['bursts']}",number(r,'steps'),
     f"{number(r,'distance_m_median')} [{number(r,'distance_m_p25')}–{number(r,'distance_m_p75')}]",
     number(r,'distance_m_p95'),number(r,'distance_m_mean'),
     f"{number(r,'speed_kmh_median',3)} / {number(r,'speed_kmh_p95',3)}"] for r in allrows])
grid=table(['Season','Steps <500 m','Same cell: 100 m','Same cell: 200 m','Same cell: 250 m','Same cell: 500 m','Same cell: 1 km','Nonadjacent cells: 500 m'],[
    [r['season'].title()]+[number(r,k,1)+'%' for k in ['pct_distance_lt_500m','pct_same_cell_100m','pct_same_cell_200m','pct_same_cell_250m','pct_same_cell_500m','pct_same_cell_1000m','pct_nonadjacent_500m']] for r in allrows])
gaps=table(['Season','Regular steps / animals','Regular median, m','Longer steps / animals','Longer median, m'],[
    [s.title(), f"{a['steps']} / {a['animals']}",number(a,'distance_m_median'),f"{b['steps']} / {b['animals']}",number(b,'distance_m_median')]
    for s in ['winter','spring','summer','autumn']
    for a in [next(r for r in metrics if r['season']==s and r['scope']=='regular_1p5_to_2p5h')]
    for b in [next(r for r in metrics if r['season']==s and r['scope']=='longer_gt2p5_to4p25h')]])
weights=table(['Season','Median of animal medians, m','Equal-animal share <500 m','Equal-animal same-cell share','Current candidate animals / routes'],[
    [r['season'].title(),number(r,'median_animal_distance_median_m'),number(r,'equal_animal_pct_below500m',1)+'%',number(r,'equal_animal_pct_same_cell500m',1)+'%',f"{r['candidate_animals']} / {r['candidate_routes']}"] for r in balanced])
body='''<header><p class="eyebrow">PANTANAL · MOVEMENT-SCALE AUDIT · 3 NOVEMBER 2026</p>
<h1>How much movement does a 500 m grid preserve?</h1>
<p class="lead">A defensible first grid for broad route selection, but a coarse representation of the typical retained displacement.</p></header>
<div class="finding"><strong>Measured result:</strong>
<ul>
<li><strong>500 m:</strong> 72–80% of retained inter-fix displacements are below 500 m; 59.6–68.8% of consecutive retained-fix pairs occupy the same cell.</li>
<li><strong>250 m:</strong> same-cell share is 52.2–62.1%, a reduction of 6.7–7.7 percentage points relative to 500 m.</li>
<li><strong>200 m:</strong> same-cell share is 49.9–56.8%, a reduction of 9.7–12.0 percentage points relative to 500 m.</li>
<li><strong>100 m:</strong> same-cell share is 41.8–48.7%, a reduction of 17.8–20.0 percentage points relative to 500 m.</li>
</ul>
<p class="small">Ranges span the four seasons, using the same retained observations and per-group grid origins.</p>
</div>
<h2>Scope and measurement</h2>
<p>We analyzed <strong>43,244 selected fixes, 2,669 technical bursts and 40,575 observed steps</strong> in the current seasonal selection checkpoint. Each burst has at least three fixes, a nominal two-hour sampling target, and gaps no longer than 4.25 hours. All retained seasonal evidence is included, across years and before optimizer exclusions. Alternative spatial groups are deduplicated using the canonical seasonal collections; no steps connect separate bursts, tags or seasons.</p>
<p>Distance is the WGS84 geodesic between two consecutive retained fixes. “Speed” is that displacement divided by the actual elapsed hours, in km/h. It is an <strong>interval-averaged displacement rate</strong>, not walking/running speed or the distance along the animal’s unobserved path. Tortuous movement between fixes can be missed; location error can inflate small distances.<sup><a href="#ref1">1</a></sup> No speed filter or behavioral-state classification was applied.</p>
<p class="small">Seasons: Winter May 15–August 14; Spring August 15–November 14; Summer November 15–March 21; Autumn March 22–May 14. No overlapping buffer; timestamps used as recorded. These pooled descriptive distributions are conditional on selection, not estimates for all 56 animals’ complete movement histories.</p>
<h2>Results: short displacements dominate every season</h2>
'''+primary+'''
<p>All four distance and speed distributions are strongly right-skewed: many very small displacements coexist with an extended upper tail. Means are 9–14 times the distance medians, so an average alone would obscure the typical observation. Between 55% and 65% of steps are under 100 m.</p>
<ul><li><strong>Winter:</strong> median 29 m and IQR 10–363 m; 79.0% below 500 m. Most intervals show little net displacement, but the upper 5% exceed 1.68 km. The speed median is 0.013 km/h, versus 0.699 km/h at the 95th percentile.</li>
<li><strong>Spring:</strong> the broadest pooled distribution, with median 64 m, IQR 11–602 m and a 2.30 km 95th percentile. It has the lowest below-500 m fraction (72.1%) and the highest median displacement rate (0.026 km/h). Its longer-gap and animal composition differs substantially from the other seasons.</li>
<li><strong>Summer:</strong> the largest sample, with 17,337 steps, resembles Winter: median 31 m, IQR 10–361 m and 79.2% below 500 m. A 1.65 km 95th percentile still leaves substantial movement across multiple cells.</li>
<li><strong>Autumn:</strong> the smallest median (25 m), IQR 10–329 m and largest sub-500 m share (80.1%). The 95th percentile is 1.56 km. This is consistent with more concentrated net displacements in the retained sample, without establishing a seasonal behavioral mechanism.</li></ul>
<p>Figure 1 compares the retained displacement distribution with each tested cell width. The colored dashed lines mark 100, 200, 250 and 500 m. Each line’s matching legend label gives the season-specific percentage of consecutive retained-fix pairs assigned to the same cell at that resolution. The denominator is observed within-burst steps, rather than individual points.</p>
'''+fig('distributions.png','Figure 1. Each panel pools all retained steps for one season. The solid curve is the empirical cumulative displacement distribution. Red and bright blue dashed lines mark the seasonal mean and median observed displacement, respectively. Muted blue, orange, green and purple lines mark the 100, 200, 250 and 500 m cell widths. Their legend percentages come from assigning both endpoints to cells on grids that share each group’s upper-left origin. Read the curve height at each width as the share of steps at or below that distance. The legend gives the share of endpoint pairs in the same cell. Axes are linear near zero and logarithmic above 10 m.')+'''
'''+fig('duration_distributions.png','Figure 2. Each row shows one season. The left column shows regular-gap displacement histograms in 75 m bins. The middle column shows cumulative displacement for longer gaps. The right column shows cumulative speed across all retained steps on an axis that is linear near zero and logarithmic above 0.005 km/h. Red and blue dashed lines show the mean and median displacement across all retained steps for that season in both distance panels. Gray dashed lines mark 500 m. Distance panels show up to 3 km, with the full distributions used for percentages and summary statistics.')+'''
<h2>Sampling intervals and animals matter</h2>
'''+gaps+'''
<p>“Regular” means the selector’s 1.5–2.5-hour band; “longer” means &gt;2.5–4.25 hours. Longer intervals make up 25.9%, 41.6%, 20.6% and 20.3% of Winter, Spring, Summer and Autumn steps, respectively. They include native three-/four-hour sampling and missing-fix gaps; this analysis does not identify each gap’s cause. Within the regular band, seasonal medians are only 20–29 m and 81–83% of steps are below 500 m. Dividing distance by elapsed time does not remove all sampling-scale effects, because intervening turns and returns remain unobserved.<sup><a href="#ref1">1</a></sup></p>
'''+weights+'''
<p>To check uneven sampling, we calculated each animal’s distribution separately, then gave each animal equal weight in the below-threshold percentages. These remain high: 63.6–72.6% below 500 m. The median of animal medians is 37–162 m, compared with 25–64 m for pooled steps. Thus, heavily sampled animals emphasize small movements, but do not create the overall finding. This check is not the same as the trainer’s animal-weighted trajectory-likelihood objective.</p>
<p>Different animals, years, sites, sexes and acquisition schedules contribute to each season. Even the regular-gap subsets contain different animals. The seasonal contrasts therefore do <strong>not</strong> establish a flood, temperature or reproductive effect. Jaguar research documents substantial individual, sex and regional variation in movement;<sup><a href="#ref2">2</a></sup> paired animal comparisons and appropriate repeated-measures models would be needed for seasonal inference. We have not treated the 40,575 autocorrelated steps as independent biological replicates or calculated significance tests.</p>
<h2>What gridding removes—and what it invents between anchors</h2>
'''+grid+fig('grid_sensitivity.png','Figure 3. Left: each dot is one animal’s median retained displacement in that season; black bars are medians across animals, and the dashed line is 500 m. Right: observed endpoint pairs assigned to the same cell at each resolution. The 500 m classification matches the saved exporter point links exactly. Counterfactual 100 m, 200 m, 250 m and 1 km grids share each group’s upper-left origin; grid-phase sensitivity and new exports were not evaluated.')+'''
<p><strong>Additional 200 m scenario:</strong> same-cell shares are 55.6% in Winter, 49.9% in Spring, 56.2% in Summer and 56.8% in Autumn. This is 9.7–12.0 percentage points below the corresponding 500 m shares. At fixed extent, 200 m requires 6.25 times as many cells as 500 m, compared with 25 times for 100 m. It is an intermediate candidate for a measured resolution/performance comparison; these counts do not establish a preferred production resolution.</p>
<p><strong>Additional 100 m scenario:</strong> the same-cell share is 47.9% in Winter, 41.8% in Spring, 47.3% in Summer and 48.7% in Autumn. Relative to 500 m, these are reductions of 18.8, 17.8, 18.6 and 20.0 percentage points; relative to 250 m, the reductions are 11.8, 10.4, 11.0 and 13.4 points. This is a substantial additional change in endpoint representation, although roughly two in five to one in two observed steps still have endpoints in the same cell.</p>
<p>The 100 m and 200 m scenarios reassign the <em>same retained observed endpoints</em> to smaller cells. Distances, speeds, sampling rules, burst identities and denominators are unchanged. It does not retrain the model or recompute optimizer eligibility at either resolution; the optimizer-candidate summaries still refer to the original 500 m exports. All scenarios use the same per-group upper-left origins. Some compared partitions (for example, 100 m versus 250 m, or 200 m versus 500 m) are not nested subdivisions of one another, so their percentage-point difference is a net rate comparison.</p>
<p><strong>Below 500 m is not synonymous with same cell.</strong> A short step can cross a nearby boundary, whereas two points in the same square can be almost 707 m apart. A cell center represents locations up to 354 m away. These are geometric limits, not GPS-error estimates.</p>
<p>The current exporter collapses consecutive same-cell observations; it retains provenance but does not represent their elapsed residence time in the model’s spatial-move clock. Conversely, 13.4–20.1% of observed steps end in nonadjacent cells. Their intermediate grid positions are constructed by the exporter’s straight raster connection, not observed telemetry. A cardinal model move is 500 m and a diagonal move about 707 m, but neither has a fixed real-time duration.</p>
<p>Even within current optimizer-candidate routes, 56.7–67.6% of observed endpoint pairs are same-cell pairs. The effect is not confined to completely stationary routes rejected before training. Candidate counts above reflect the existing exports; Autumn’s optional G324 map-budget exception is <em>not</em> applied to those counts. All temporally retained G324 evidence is included in the main distributions.</p>
<h2>Ecological interpretation and outlook</h2>
<p>The near-zero concentration is compatible with resting, feeding at a localized resource, restricted movement or departures followed by returns. It cannot identify any of those behaviors from endpoints alone. Distances near 10 m may also contain a substantial location-error contribution; no device-specific accuracy calibration was available in this audit. Accordingly, a 25–64 m pooled median is not a biological justification for choosing a 25–64 m grid.</p>
<p>Alvarenga et al. explicitly used 500 m environmental rasters as a compromise among landscape representation, study extent and fix intervals. Their habitat-response scales were much broader (4–32 km), and their path-selection analysis was a different model.<sup><a href="#ref3">3</a></sup> Those results support a broad-scale habitat context, but cannot validate our discretized IRL actions or interpolation accuracy. Narrow riparian strips, small forest patches and flood-channel crossings can still be blurred within a 500 m cell.</p>
<p><strong>Recommendation:</strong> retain 500 m as the initial Spring baseline for learning broad route preferences. Describe it explicitly as a coarse spatial-move model; do not interpret it as a model of fine-scale behavior, dwell time or two-hour movement speed. The strong same-cell concentration is a material limitation for reconstructing detailed trajectories.</p>
<p>Next, compare 500 m with 250 m and 100 m on a manageable subset using the same whole-animal holdout and withholding scheme. Rebuild aligned covariates and exports for the comparison; simply upsampling a coarse feature map creates no new environmental information. Measure held-out positional/path error in meters, informative-route retention, same-cell compression, inferred connectors, runtime and memory. A 250 m grid gives about four times as many cells at fixed extent and may also lengthen grid routes; measure the actual training cost before expanding it. A 1 km grid would increase compression to roughly 68–75%, so these movement data do not support coarsening further.</p>
<p><strong>Should we switch to 100 m?</strong> These results justify testing it, but do not establish that it is the best production grid. At fixed extent, 100 m has 25 times as many cells as 500 m (6.25 times as many as 250 m), and finer routes can require more model steps as well. These are geometric counts, not measured runtime multipliers. Finer cells also need covariates with useful variation at that scale; copying a broad or strongly smoothed predictor onto more cells does not add habitat information. Use held-out reconstruction performance and resource measurements to decide whether the added detail is worthwhile. Minimizing same-cell share alone is not an ecological objective: genuine localized activity and measurement noise should not automatically become extra movement actions.</p>
<p>Reducing cell size alone will not recover residence time or missing within-interval paths. Those require a separate model-design decision. The proposed resolution comparison remains a scientific testing plan, not a validated testing implementation.</p>
<div class="finding"><strong>Quality-control follow-up:</strong> ID 114 contributes 222 of the 278 steps exceeding 5 km. The maximum is 19.23 km in three hours (6.41 km/h), on 25 August 2008; all of the 12 largest displacement rates belong to this animal. Inspect original coordinates, collar metadata and neighboring fixes before interpreting these as biological travel or allowing constructed connectors to dominate inference. These are review flags, not proven errors or automatic exclusion criteria. Omitting ID 114 in a sensitivity calculation changes pooled medians to 28, 58, 30 and 25 m, and same-cell shares to 67.3%, 60.7%, 66.4% and 68.9%: the grid conclusion persists.</div>
<details><summary>Reproducibility, metrics and verification</summary>
<p>Checkpoint: <code>selection_5bf188474d229bb43e3efde0</code>. The analysis uses selector points linked to source coordinates, canonical collection ownership, saved grids and the four exports named in <code>analysis/pantanal_seasonal_selection/exports.json</code>. It preserves historical identifiers containing <code>bout</code>; the units are technical bursts.</p>
<pre>python3 -m analysis.pantanal_movement_scale.analyze
python3 -m analysis.pantanal_movement_scale.report</pre>
<p>Run from the repository root with NumPy, pyproj and Matplotlib. The analysis accepts <code>--checkpoint</code>, <code>--exports-index</code> and <code>--output</code>; the report renderer uses the default <code>results/</code> directory. It overwrites its own diagnostic products only. Checkpoints, exports, rasters and training inputs are unchanged.</p>
<p>Software checks verify unique canonical evidence, no cross-burst/tag steps, ≥3 fixes per burst, all gaps within 1.5–4.25 hours, exact agreement of all 40,575 observed edges with independent two-hour exports, and identical 500 m same-cell classifications. Projected versus geodesic distances differ by at most 7.69 m over the entire sample; thresholds use geodesic distance and cells use the actual projected grid. These are implementation checks, not scientific validation.</p>
<p>The downloadable tables below are embedded in this report. <code>season_metrics.csv</code> includes all-retained, regular-gap, longer-gap, optimizer-candidate and without-ID114 sensitivity results; quantiles, means, maxima and threshold shares are explicit in the column names. <code>animal_metrics.csv</code> describes each animal–season. Full event-level <code>steps.csv</code> and figure PNG/SVG files are additionally saved alongside the report in the repository’s <code>analysis/pantanal_movement_scale/results/</code> directory.</p><ul>
'''+''.join(download(name) for name in ['season_metrics.csv','animal_metrics.csv','animal_balanced_metrics.csv','largest_speeds.csv'])+download('provenance.json','application/json')+'''
</ul></details>
<h2>References</h2>
<ol class="refs"><li id="ref1">Noonan et al. (2019). <a href="https://doi.org/10.1186/s40462-019-0177-1">Scale-insensitive estimation of speed and distance traveled from animal tracking data.</a> Movement Ecology 7, 35. Sampling scale, tortuosity and measurement error affect displacement-based speed estimates.</li>
<li id="ref2">Morato et al. (2016). <a href="https://doi.org/10.1371/journal.pone.0168176">Space Use and Movement of a Neotropical Top Predator: The Endangered Jaguar.</a> PLOS ONE 11, e0168176. Continuous-time movement estimates and individual/sex/regional heterogeneity; these estimates are not directly interchangeable with the interval rates here.</li>
<li id="ref3">Alvarenga et al. (2021). <a href="https://www.fs.usda.gov/rm/pubs_journals/2021/rmrs_2021_alvarenga_g001.pdf">Multi-scale path-level analysis of jaguar habitat use in the Pantanal ecosystem.</a> Biological Conservation 253, 108900. Methods §2.3 explains 500 m raster grain; broad habitat-response scales concern predictor neighborhoods, not the IRL action grid.</li></ol>
'''
css='''body{font:16px/1.6 system-ui,sans-serif;color:#263943;background:#fff;margin:0 auto;padding:40px 26px;max-width:1120px}h1{font-size:36px;line-height:1.2;margin:10px 0}h2{font-size:23px;margin-top:36px}a{color:#32677e}p{max-width:1000px}.eyebrow{font-size:12px;letter-spacing:1.4px;color:#60747c}.lead{font-size:21px;color:#526970}.finding{background:#edf3f3;border-left:4px solid #668c96;padding:18px 22px;margin:24px 0}.table{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th{text-align:left;background:#edf2f3}td,th{padding:11px 10px;border-bottom:1px solid #dce4e5}td{font-variant-numeric:tabular-nums}figure{margin:28px 0}img{width:100%;height:auto}figcaption,.small,.refs{font-size:13px;color:#53656e}li{margin:9px 0}details{background:#f5f7f7;padding:18px;margin:28px 0}summary{cursor:pointer;font-weight:700}code,pre{font-size:12px;overflow-wrap:anywhere}pre{background:white;padding:14px;overflow:auto}@media print{body{padding:0;font-size:10pt}h1{font-size:25pt}h2{font-size:16pt}figure,table,.finding{break-inside:avoid}details{display:block}.table{overflow:visible}a{color:inherit}}'''
(OUT/'pantanal_movement_scale_report.html').write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Pantanal movement scale and the 500 m grid</title><style>'+css+'</style></head><body>'+body+'</body></html>')
print(OUT/'pantanal_movement_scale_report.html')
