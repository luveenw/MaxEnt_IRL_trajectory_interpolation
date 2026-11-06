# Jaguar literature: range crossings and trajectory coverage

## What does the cited literature mean by range crossings, and does it prescribe 30–50?

### Takeaway
Silva et al. (2022) define an effective home-range sample size as roughly observation duration divided by the *time to cross the linear extent of the home range*. This is a property of an individual telemetry record, not the number of GPS fixes, grid cells, or segmented paths. The paper recommends a duration many times the crossing time, but gives no universal 30–50 cutoff. 

### Cited Findings
- Silva et al. define home range as the area repeatedly used for normal activities, and range-crossing time τ as the average time to cross its linear extent. — [Silva et al. 2022, introduction](https://besjournals.onlinelibrary.wiley.com/doi/full/10.1111/2041-210X.13786)
- The effective sample size relevant to home-range estimation is approximately `T/τ`, where `T` is observation duration. More frequent fixes increase the raw count, but do not increase effective sample size proportionately. — [Silva et al. 2022, §2](https://besjournals.onlinelibrary.wiley.com/doi/full/10.1111/2041-210X.13786)
- Silva et al. advise sampling for “many times” the mean range-crossing time if the objective is home-range area estimation; their practical guidance cautions especially against changing bias-correcting defaults for effective sample sizes below 20. They do not specify 30–50 as a prerequisite. — [Silva et al. 2022, discussion](https://besjournals.onlinelibrary.wiley.com/doi/full/10.1111/2041-210X.13786)
- The paper illustrates small effective size using a jaguar record cut to three months: 363 fixes but effective sample size about 3.1. — [Silva et al. 2022, Fig. 3 caption](https://besjournals.onlinelibrary.wiley.com/doi/full/10.1111/2041-210X.13786)

### Inferences
- A 30–50 crossing goal can be chosen as a conservative study-specific precision target, but it is not a requirement attributable to Silva et al. Pooling all fixes and splitting them into more paths cannot create more range crossings.

### Gaps
- The Silva paper does not give a jaguar-specific crossing threshold for trajectory segmentation or for inverse reinforcement learning.

## What did de la Torre and Rivero observe, and what did they require for home-range analysis?

### Takeaway
They checked range residency using individual variograms, estimated AKDE home ranges for four jaguars, and excluded the fifth because its variogram did not level off. Their four reported records imply roughly 28–83 crossing times, not a uniform 30–50 threshold.

### Cited Findings
- Five jaguars were collared; the authors obtained 1,134 GPS fixes in total, with low fix success attributed partly to forest canopy. The collars were programmed for a fix every 4.8 hours and release after 12–14 months. — [de la Torre & Rivero 2019, pp. 221–223](https://doi.org/10.1007/978-3-030-03463-4_13); [full chapter PDF](https://r.jordan.im/download/conservation/torre2019.pdf)
- Their residency criterion was a variogram reaching an asymptote, expected at roughly the range-crossing time; a jaguar without this asymptote was not assumed to be range resident. — [de la Torre & Rivero 2019, p. 223](https://r.jordan.im/download/conservation/torre2019.pdf)
- Table 13.1 reports `days/fixes` and `crossing time (days)`: JF05 331/88 and 9.9; JF15 350/395 and 4.6; JM04 367/578 and 4.4; JM11 133/72 and 4.7. By Silva's approximation `T/τ`, these are about 33, 76, 83, and 28 range-crossing times respectively. The quotient is an approximation derived from the table, not a separately reported observed event count. — [de la Torre & Rivero 2019, Table 13.1, p. 222](https://r.jordan.im/download/conservation/torre2019.pdf); [Silva et al. 2022, §2](https://besjournals.onlinelibrary.wiley.com/doi/full/10.1111/2041-210X.13786)
- The fifth jaguar JF12 yielded little data after being shot 20 days after capture, and its variogram did not reach an asymptote; the authors calculated home ranges for the other four only. — [de la Torre & Rivero 2019, pp. 222, 228](https://r.jordan.im/download/conservation/torre2019.pdf)
- The authors also emphasize within-range recursion and intensity of use, and fit biased random bridge distributions for two well-observed individuals. They distinguish repeatedly visited sites from places visited once but occupied for a long time. — [de la Torre & Rivero 2019, pp. 224–225](https://r.jordan.im/download/conservation/torre2019.pdf)
- They note that crossing time varied among individuals. — [de la Torre & Rivero 2019, p. 233](https://r.jordan.im/download/conservation/torre2019.pdf)

### Inferences
- For a jaguar telemetry dataset, diagnose residency and spatial representativeness on each animal's full, timestamped record before cutting it into IRL trajectories. A short segment may be a valid movement path yet have insufficient information to estimate that animal's entire home range; conversely the full record can establish residency while constituent paths remain short. Preserve animal identity and timestamps across segments.
- A crossing-time count is a home-range-estimation quality measure, not a number of required IRL trajectories or a rule that each trajectory must cross the range. It should not be used to force equal-length paths or infer stationary range use from a transient/dispersing record.

### Gaps
- The chapter does not state a universal minimum crossing count, and it does not test IRL trajectory segmentation. Its four fitted jaguars came from a small study area; the authors themselves caution that 2–5 tracked animals probably do not represent the population. — [de la Torre & Rivero 2019, p. 235](https://r.jordan.im/download/conservation/torre2019.pdf)
