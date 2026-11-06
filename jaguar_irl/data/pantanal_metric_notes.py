"""Source-backed interpretation of the report's per-animal count balance."""

METRIC_SOURCES = [
    {"title": "NIST Dataplot: population and sample coefficients of variation",
     "url": "https://www.itl.nist.gov/div898/software/dataplot/refman1/auxillar/coefvate.htm"},
    {"title": "Jain, Chiu & Hawe (1984): A Quantitative Measure of Fairness and Discrimination, DEC TR-301",
     "url": "https://www.cs.wustl.edu/~jain/papers/ftp/fairness.pdf"},
    {"title": "Hönig, Zhao & Mullins (2022): DAdaQuant, ICML/PMLR 162, 8852–8866, §4.2",
     "url": "https://proceedings.mlr.press/v162/honig22a/honig22a.pdf"},
    {"title": "Jeong & Kim (2022): A Cluster-Driven Adaptive Training Approach for Federated Learning, Sensors 22, 7061, §5.3.2",
     "url": "https://www.mdpi.com/1424-8220/22/18/7061"},
    {"title": "Chen & Hooker (2023): A guide to formulating fairness in an optimization model, §4.1",
     "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC10081824/"},
]

METRIC_NOTES_HTML = """
<section id="point-count-metrics">
<h2>Why point CV and Jain's index?</h2>
<p>Here nᵢ is the retained fix count for jaguar i, and k is the number of included
individuals. These metrics describe how evenly the selected observations are
distributed across animals. Counts have a meaningful zero and a positive mean,
so relative dispersion is interpretable. Equal contributions are an explicit
cohort-design preference; actual training influence also depends on the model's
loss aggregation and weighting.</p>
<p><strong>Point CV:</strong> CV = σ / μ, where μ = Σnᵢ / k and
σ = √[Σ(nᵢ − μ)² / k]. We use the population divisor k because we describe the
complete selected group, rather than estimate variation in a larger population.
CV = 0 means equal counts; CV = 0.04 means the standard deviation is 4% of the
mean. Lower is more balanced. The
<a href="https://www.itl.nist.gov/div898/software/dataplot/refman1/auxillar/coefvate.htm">NIST definition</a>
distinguishes this population CV from the sample version using k − 1.</p>
<p><strong>Jain's index:</strong> J = (Σnᵢ)² / [k Σnᵢ²]. It equals 1 for equal
counts and decreases with imbalance. Multiplying every animal's count by the
same factor leaves both CV and Jain unchanged, making them useful complements
to total fixes. The original
<a href="https://www.cs.wustl.edu/~jain/papers/ftp/fairness.pdf">Jain, Chiu &amp; Hawe (1984)</a>
measure concerns resource-allocation fairness; using it for jaguar observation
counts is our adaptation.</p>
<p><strong>Related count-based case studies:</strong>
<a href="https://proceedings.mlr.press/v162/honig22a/honig22a.pdf">Hönig, Zhao &amp; Mullins (2022), DAdaQuant, §4.2</a>,
use CV of client dataset sample counts to characterize quantity imbalance in
federated learning. Their application concerns communication compression, rather
than choosing equal dataset sizes.
<a href="https://www.mdpi.com/1424-8220/22/18/7061">Jeong &amp; Kim (2022), CATA-Fed, §5.3.2 and Fig. 13a</a>,
use Jain's index on client-selection counts to assess equality of training
opportunities. These establish relevant uses of count-balance measures; neither
study validates a jaguar sampling threshold or an improvement in IRL prediction.</p>
<p><strong>Two views of the same property:</strong> for these counts and the
population standard deviation, <code>J = 1 / (1 + CV²)</code>, exactly.
<a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC10081824/">Chen &amp; Hooker (2023), §4.1</a>,
also give this relationship. The two values are mathematically redundant.
Only Jain enters the ranking score,
<code>total fixes × J = total fixes / (1 + CV²)</code>; CV is an interpretation aid,
not a second penalty. Both are shown alongside the individual bars and histogram
so the underlying counts remain inspectable.</p>
<p><strong>Interpretation:</strong> balanced counts do not establish independent
fixes, comparable habitat coverage, effective sample size, or predictive accuracy.
Equally small and equally large datasets both have CV = 0 and J = 1; total fixes
and animal counts must be considered alongside balance. The minimum week-coverage
screen already constrains count variation, so Jain values near 1 are expected.
Validate model performance with animal-level train/test grouping.</p>
</section>
"""
