#!/usr/bin/env Rscript
# =============================================================================
# ctmm Continuous-Time Movement Model Baseline for GPS Gap-Filling
# =============================================================================
# Benchmarks ctmm's Kriging-based trajectory prediction (predict.ctmm) against
# naive linear interpolation on ARTIFICIALLY introduced gaps of varying size,
# for one jaguar individual. This mirrors the evaluation protocol in
# Hirakawa et al. (2018) Appendix S1 (hold out a fraction of the trajectory,
# artificially create missing parts, interpolate, compare to ground truth
# with a shape metric) so results here are directly comparable to the
# MaxEnt IRL interpolation once that model is trained.
#
# Individual chosen: ID 13 (Jaguar_Taiama study, Pantanal, Brazil)
#   - 5,040 fixes at ~hourly resolution over 260 days (near-regular sampling
#     is rare in this dataset; see grid_analysis_report.csv) -> lets us
#     stratify synthetic gap duration cleanly without the analysis being
#     confounded by the individual's own irregular native sampling.
#   - Single stable home range: home_range_analysis.R found n_core_areas=1
#     and is_range_shift=FALSE for this individual, so one movement model
#     (OUF anisotropic) describes the whole trajectory -- no need to handle
#     range shifts or multi-modal home ranges for this baseline.
#   - OUF anisotropic model is well identified (dAICc to next-best model
#     ~388; see home_range_output/individual_rds/individual_13.rds).
#
# Usage:
#   Rscript ctmm_interpolation_baseline.R              # individual 13, defaults
#   Rscript ctmm_interpolation_baseline.R --id 26       # a different individual
#   Rscript ctmm_interpolation_baseline.R --id 20 --gap-bins 24,72,168,336,504,840,1200,1680 --n-reps 2
#       # custom gap bins (hours, given as lo,hi pairs) and replicate count --
#       # needed for individuals whose own position-autocorrelation timescale
#       # (tau_position) is on a completely different scale than individual 13's
#       # ~3.4 days (e.g. individual 20's ~73 days), so a fixed set of absolute
#       # gap sizes would not probe the same relative regime.
# =============================================================================

suppressPackageStartupMessages({
  library(ctmm)
  library(data.table)
})

# =============================================================================
# Configuration
# =============================================================================

BASE_DIR <- getwd()
OUT_DIR <- file.path(BASE_DIR, "ctmm_baseline_output")
dir.create(OUT_DIR, recursive = TRUE, showWarnings = FALSE)

args <- commandArgs(trailingOnly = TRUE)
IND_ID <- 13
if ("--id" %in% args) {
  idx <- which(args == "--id")
  if (idx < length(args)) IND_ID <- as.integer(args[idx + 1])
}

SEED <- 42
set.seed(SEED)

# Synthetic gap-duration bins (hours), chosen to span the range of gap sizes
# actually seen across the Morato et al. jaguar dataset (median inter-fix
# gap ranges from ~1 to ~8 h across individuals; p90/max gaps commonly reach
# multiple days -- see grid_analysis_report.csv gap_p90_hr / gap_max_hr).
# Override with --gap-bins lo1,hi1,lo2,hi2,... (any number of bins, named
# bin1, bin2, ... automatically) for individuals whose own movement timescale
# differs greatly from individual 13's.
GAP_BINS <- list(
  short   = c(2, 6),      # a few missed fixes
  medium  = c(12, 24),    # about a day
  long    = c(48, 96),    # 2-4 days
  extreme = c(168, 240)   # 7-10 days: mimics the largest realistic jaguar gaps
)
if ("--gap-bins" %in% args) {
  idx <- which(args == "--gap-bins")
  vals <- as.numeric(strsplit(args[idx + 1], ",")[[1]])
  stopifnot(length(vals) %% 2 == 0)
  GAP_BINS <- setNames(
    lapply(seq(1, length(vals), by = 2), function(i) vals[i:(i + 1)]),
    sprintf("bin%d_%g-%gh", seq_along(seq(1, length(vals), by = 2)), vals[seq(1, length(vals), by = 2)], vals[seq(2, length(vals), by = 2)])
  )
}

N_REPLICATES_PER_BIN <- 4
if ("--n-reps" %in% args) {
  idx <- which(args == "--n-reps")
  N_REPLICATES_PER_BIN <- as.integer(args[idx + 1])
}
BUFFER_HOURS <- 12   # minimum spacing reserved around each gap so gaps don't crowd each other
MAX_TRIES <- 500

cat(sprintf("=== ctmm interpolation baseline: individual %d ===\n", IND_ID))

# =============================================================================
# Helper functions
# =============================================================================

# Great-circle (haversine) distance in meters. Used for ALL error metrics so
# that ctmm-based and linear-interpolation predictions are compared on
# identical footing, independent of any map projection choice.
haversine_m <- function(lon1, lat1, lon2, lat2) {
  R <- 6371008.8
  phi1 <- lat1 * pi / 180; phi2 <- lat2 * pi / 180
  dphi <- (lat2 - lat1) * pi / 180
  dlambda <- (lon2 - lon1) * pi / 180
  a <- sin(dphi / 2)^2 + cos(phi1) * cos(phi2) * sin(dlambda / 2)^2
  2 * R * asin(pmin(1, sqrt(a)))
}

# Modified Hausdorff Distance (Dubuisson & Jain 1994), as used for the
# accuracy metric in Hirakawa et al. (2018). Treats each path as an
# unordered set of points; robust to the two paths having different
# numbers of vertices (relevant once compared against the grid/time-step
# based MaxEnt IRL interpolation, which will not share timestamps with
# the GPS record).
mhd_m <- function(lon_a, lat_a, lon_b, lat_b) {
  na <- length(lon_a); nb <- length(lon_b)
  d <- matrix(NA_real_, na, nb)
  for (i in seq_len(na)) d[i, ] <- haversine_m(lon_a[i], lat_a[i], lon_b, lat_b)
  mean_min_ab <- mean(apply(d, 1, min))
  mean_min_ba <- mean(apply(d, 2, min))
  max(mean_min_ab, mean_min_ba)
}

# Straight-line interpolation between the two known fixes bracketing a gap,
# parameterized by elapsed time (the conventional "linear interpolation"
# baseline in the animal movement literature, e.g., Tancell et al. 2013,
# and the baseline Hirakawa et al. compared their IRL method against).
linear_interp <- function(t_target, t0, lon0, lat0, t1, lon1, lat1) {
  frac <- (t_target - t0) / (t1 - t0)
  data.frame(
    longitude = lon0 + frac * (lon1 - lon0),
    latitude  = lat0 + frac * (lat1 - lat0)
  )
}

# =============================================================================
# Data loading (mirrors home_range_analysis.R's data treatment)
# =============================================================================

cat("\n--- Loading data ---\n")
mov <- fread(file.path(BASE_DIR, "jaguar_movement_data.csv"), stringsAsFactors = FALSE)
mov[, individual_id := `individual.local.identifier (ID)`]
ind <- mov[individual_id == IND_ID]
if (nrow(ind) == 0) stop(sprintf("No records found for individual %d", IND_ID))

ind[, timestamp_parsed := as.POSIXct(timestamp, format = "%m/%d/%y %H:%M", tz = "UTC")]
na_ts <- is.na(ind$timestamp_parsed)
if (any(na_ts)) ind[na_ts, timestamp_parsed := as.POSIXct(timestamp, format = "%m/%d/%Y %H:%M", tz = "UTC")]

tel_df <- data.frame(
  `individual.local.identifier` = as.character(IND_ID),
  timestamp  = format(ind$timestamp_parsed, "%Y-%m-%d %H:%M:%S"),
  `location.long` = ind$`location.long`,
  `location.lat`  = ind$`location.lat`,
  check.names = FALSE
)
tel_df <- tel_df[complete.cases(tel_df), ]
tel_df <- tel_df[order(tel_df$timestamp), ]
tel_df <- tel_df[!duplicated(tel_df$timestamp), ]  # as.telemetry requires unique timestamps
tel_df$t_posix <- as.POSIXct(tel_df$timestamp, tz = "UTC", format = "%Y-%m-%d %H:%M:%S")
tel_df$t_num <- as.numeric(tel_df$t_posix)
n_total <- nrow(tel_df)

cat(sprintf("  %d valid, uniquely-timestamped fixes spanning %.1f days\n",
            n_total, as.numeric(difftime(max(tel_df$t_posix), min(tel_df$t_posix), units = "days"))))

# =============================================================================
# Select synthetic gap windows
# =============================================================================

cat("\n--- Selecting synthetic gap windows ---\n")

select_gap_windows <- function(t_num, bins, n_per_bin, buffer_hours, max_tries) {
  n <- length(t_num)
  reserved <- rep(FALSE, n)   # index positions already claimed by a gap or its buffer
  # keep a margin at each end so every gap has a real bracketing fix on both sides
  edge_margin <- 3
  reserved[1:edge_margin] <- TRUE
  reserved[(n - edge_margin + 1):n] <- TRUE

  windows <- list()
  for (bin_name in names(bins)) {
    rng <- bins[[bin_name]]
    placed <- 0
    tries <- 0
    while (placed < n_per_bin && tries < max_tries) {
      tries <- tries + 1
      dur_s <- runif(1, rng[1] * 3600, rng[2] * 3600)
      start_idx <- sample((edge_margin + 1):(n - edge_margin - 1), 1)
      start_t <- t_num[start_idx]
      end_t <- start_t + dur_s

      idx_in <- which(t_num > start_t & t_num < end_t)
      if (length(idx_in) < 1) next
      lo <- min(idx_in) - 1L; hi <- max(idx_in) + 1L   # bracketing fixes, kept in training data
      if (lo < 1 || hi > n) next

      buf_lo <- max(1, lo - ceiling(buffer_hours * 3600 / median(diff(t_num))))
      buf_hi <- min(n, hi + ceiling(buffer_hours * 3600 / median(diff(t_num))))
      if (any(reserved[buf_lo:buf_hi])) next

      reserved[buf_lo:buf_hi] <- TRUE
      windows[[length(windows) + 1]] <- list(
        bin = bin_name, idx = idx_in, bracket_lo = lo, bracket_hi = hi,
        start_t = start_t, end_t = end_t, dur_hr = dur_s / 3600
      )
      placed <- placed + 1
    }
    if (placed < n_per_bin) {
      warning(sprintf("Only placed %d/%d gaps for bin '%s'", placed, n_per_bin, bin_name))
    }
  }
  windows
}

windows <- select_gap_windows(tel_df$t_num, GAP_BINS, N_REPLICATES_PER_BIN, BUFFER_HOURS, MAX_TRIES)
cat(sprintf("  Placed %d gap windows across %d bins\n", length(windows), length(GAP_BINS)))
for (w in windows) {
  cat(sprintf("    [%-8s] %5.1f h, %2d removed fixes, bracketed by rows %d..%d\n",
              w$bin, w$dur_hr, length(w$idx), w$bracket_lo, w$bracket_hi))
}

gap_idx_all <- sort(unique(unlist(lapply(windows, `[[`, "idx"))))
train_df <- tel_df[-gap_idx_all, ]
cat(sprintf("  Training set: %d fixes (%.1f%% of total) after removing all gap fixes\n",
            nrow(train_df), 100 * nrow(train_df) / n_total))

# =============================================================================
# Fit ctmm movement model on the gap-removed ("training") data
# =============================================================================
# Fitting once on data with every synthetic gap already excised (rather than
# refitting per-gap) mirrors Hirakawa et al.'s single held-out test split
# (Appendix S1): the model never sees the fixes it is later asked to predict.

cat("\n--- Fitting ctmm movement model on training data ---\n")
train_tel <- as.telemetry(train_df[, c("individual.local.identifier", "timestamp",
                                        "location.long", "location.lat")],
                           timeformat = "%Y-%m-%d %H:%M:%S")
svf <- variogram(train_tel)
guess <- ctmm.guess(train_tel, interactive = FALSE)
fit_list <- ctmm.select(train_tel, guess, verbose = TRUE)
FIT <- fit_list[[1]]
cat(sprintf("  Best model: %s\n", names(fit_list)[1]))
print(summary(FIT)$CI)

# =============================================================================
# Interpolate each gap with ctmm and with linear interpolation
# =============================================================================

cat("\n--- Interpolating gaps ---\n")

per_point_results <- list()
per_gap_results <- list()

for (gi in seq_along(windows)) {
  w <- windows[[gi]]
  truth <- tel_df[w$idx, ]
  target_t <- truth$t_num

  # ---- ctmm (Kriging) interpolation ----
  pred <- predict(FIT, data = train_tel, t = target_t, complete = TRUE)
  pred <- pred[match(target_t, pred$t), ]  # ensure row order matches truth

  ctmm_err_m <- haversine_m(truth$location.long, truth$location.lat,
                             pred$longitude, pred$latitude)
  ctmm_sd_m <- sqrt(pmax(0, (pred$COV.x.x + pred$COV.y.y) / 2))  # approx. 1-sigma radial uncertainty

  # ---- Linear interpolation baseline ----
  b_lo <- tel_df[w$bracket_lo, ]; b_hi <- tel_df[w$bracket_hi, ]
  lin <- linear_interp(target_t, b_lo$t_num, b_lo$location.long, b_lo$location.lat,
                        b_hi$t_num, b_hi$location.long, b_hi$location.lat)
  lin_err_m <- haversine_m(truth$location.long, truth$location.lat,
                            lin$longitude, lin$latitude)

  per_point_results[[gi]] <- data.frame(
    gap_id = gi, bin = w$bin, dur_hr = w$dur_hr, t = target_t,
    true_lon = truth$location.long, true_lat = truth$location.lat,
    ctmm_lon = pred$longitude, ctmm_lat = pred$latitude, ctmm_err_m = ctmm_err_m, ctmm_sd_m = ctmm_sd_m,
    lin_lon = lin$longitude, lin_lat = lin$latitude, lin_err_m = lin_err_m
  )

  mhd_ctmm <- mhd_m(pred$longitude, pred$latitude, truth$location.long, truth$location.lat)
  mhd_lin  <- mhd_m(lin$longitude, lin$latitude, truth$location.long, truth$location.lat)

  per_gap_results[[gi]] <- data.frame(
    gap_id = gi, bin = w$bin, dur_hr = w$dur_hr, n_points = length(w$idx),
    ctmm_mean_err_m = mean(ctmm_err_m), ctmm_median_err_m = median(ctmm_err_m),
    ctmm_mean_sd_m = mean(ctmm_sd_m), mhd_ctmm_m = mhd_ctmm,
    lin_mean_err_m = mean(lin_err_m), lin_median_err_m = median(lin_err_m),
    mhd_lin_m = mhd_lin,
    pct_improvement = 100 * (mean(lin_err_m) - mean(ctmm_err_m)) / mean(lin_err_m)
  )

  cat(sprintf("  [gap %2d, %-8s, %5.1f h] ctmm mean err = %7.1f m | linear mean err = %7.1f m | improvement = %5.1f%%\n",
              gi, w$bin, w$dur_hr, mean(ctmm_err_m), mean(lin_err_m),
              per_gap_results[[gi]]$pct_improvement))
}

per_point_df <- do.call(rbind, per_point_results)
per_gap_df <- do.call(rbind, per_gap_results)

# =============================================================================
# Summarize by gap-duration bin
# =============================================================================

cat("\n=== Summary by gap-duration bin ===\n")
# Paired Wilcoxon signed-rank test per bin (ctmm vs. linear mean error on the
# same gaps) -- the appropriate paired analogue of the Mann-Whitney U test
# Hirakawa et al. used (their comparison was also effectively paired, same
# held-out trajectories scored under both methods).
bin_summary <- do.call(rbind, lapply(split(per_gap_df, per_gap_df$bin), function(d) {
  wt <- if (nrow(d) >= 4) tryCatch(wilcox.test(d$ctmm_mean_err_m, d$lin_mean_err_m, paired = TRUE),
                                     error = function(e) NULL) else NULL
  data.frame(
    bin = d$bin[1], n_gaps = nrow(d), mean_dur_hr = mean(d$dur_hr),
    ctmm_mean_err_m = mean(d$ctmm_mean_err_m), lin_mean_err_m = mean(d$lin_mean_err_m),
    ctmm_mean_mhd_m = mean(d$mhd_ctmm_m), lin_mean_mhd_m = mean(d$mhd_lin_m),
    mean_pct_improvement = mean(d$pct_improvement),
    wilcoxon_p = if (is.null(wt)) NA_real_ else wt$p.value
  )
}))
bin_order <- names(GAP_BINS)
bin_summary <- bin_summary[match(bin_order, bin_summary$bin), ]
print(bin_summary, row.names = FALSE)

overall_wt <- wilcox.test(per_gap_df$ctmm_mean_err_m, per_gap_df$lin_mean_err_m, paired = TRUE)
cat(sprintf("\nOverall paired Wilcoxon signed-rank test (all %d gaps, ctmm vs. linear mean error): p = %.4f\n",
            nrow(per_gap_df), overall_wt$p.value))

# =============================================================================
# Save outputs
# =============================================================================

out_prefix <- file.path(OUT_DIR, sprintf("individual_%03d", IND_ID))
fwrite(per_point_df, paste0(out_prefix, "_per_point.csv"))
fwrite(per_gap_df, paste0(out_prefix, "_per_gap.csv"))
fwrite(bin_summary, paste0(out_prefix, "_bin_summary.csv"))
cat(sprintf("\nSaved: %s_{per_point,per_gap,bin_summary}.csv\n", out_prefix))

# ---- Diagnostic plot: one representative gap per bin ----
png(paste0(out_prefix, "_diagnostic.png"), width = 1400, height = 1400, res = 150)
par(mfrow = c(2, 2), mar = c(3, 3, 2, 1))
for (bin_name in bin_order) {
  bin_gaps <- which(sapply(windows, `[[`, "bin") == bin_name)
  if (length(bin_gaps) == 0) next
  gi <- bin_gaps[1]
  w <- windows[[gi]]
  ctx_idx <- max(1, w$bracket_lo - 20):min(n_total, w$bracket_hi + 20)
  plot(tel_df$location.long[ctx_idx], tel_df$location.lat[ctx_idx], type = "b",
       col = "gray70", pch = 16, cex = 0.5, xlab = "lon", ylab = "lat",
       main = sprintf("%s gap (%.0f h, n=%d)", bin_name, w$dur_hr, length(w$idx)))
  truth <- tel_df[w$idx, ]
  pp <- per_point_df[per_point_df$gap_id == gi, ]
  lines(truth$location.long, truth$location.lat, col = "black", lwd = 2)
  points(truth$location.long, truth$location.lat, col = "black", pch = 16)
  lines(pp$ctmm_lon, pp$ctmm_lat, col = "blue", lwd = 2, lty = 2)
  points(pp$ctmm_lon, pp$ctmm_lat, col = "blue", pch = 17)
  lines(pp$lin_lon, pp$lin_lat, col = "orange", lwd = 2, lty = 3)
  points(pp$lin_lon, pp$lin_lat, col = "orange", pch = 4)
  legend("topleft", legend = c("context", "true", "ctmm", "linear"),
         col = c("gray70", "black", "blue", "orange"), pch = c(16, 16, 17, 4), cex = 0.7, bty = "n")
}
dev.off()
cat(sprintf("Saved: %s_diagnostic.png\n", out_prefix))

cat("\n=== Done ===\n")
