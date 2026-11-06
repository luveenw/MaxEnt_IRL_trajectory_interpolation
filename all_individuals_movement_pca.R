#!/usr/bin/env Rscript
# =============================================================================
# Deliverable 1: Movement-Covariate PCA
# =============================================================================
# Individual-level PCA on movement-derived covariates (not landscape
# covariates -- see the MaxEnt IRL deliverable for those). Plan as finalized
# in project memory (areas/movement-pca-covariates.md):
#   - Individual-level (one row per jaguar)
#   - No BCPA-based behavioral segmentation -- simple derived Vp only
#   - No resampling -- valid time-delta band per step pair + native fix
#     interval as an explicit covariate, checked for confounding
#   - Sinuosity vs. straightness gated by the NSD Resident/Disperser
#     heuristic (ported from eda_nsd.py)
#   - Home-range size pulled directly from individual_akde_rds/ (not a
#     separately-maintained summary CSV, to avoid drift from the
#     regenerated, non-segmented AKDEs)
#   - Cluster membership attached as annotation only, never used to filter
#
# Usage:
#   Rscript movement_pca.R
# =============================================================================

suppressPackageStartupMessages({
  library(data.table)
  library(sf)
})

# trajr is used only for sinuosity/straightness (Benhamou 2004); everything
# else is computed directly to avoid depending on exact API details of a
# larger package this script hasn't been tested against live.
HAS_TRAJR <- requireNamespace("trajr", quietly = TRUE)
if (!HAS_TRAJR) cat("NOTE: trajr not installed - run install.packages('trajr') for sinuosity/straightness.\n")

HAS_FACTOEXTRA <- requireNamespace("factoextra", quietly = TRUE)
HAS_FACTOMINER <- requireNamespace("FactoMineR", quietly = TRUE)
if (!HAS_FACTOEXTRA || !HAS_FACTOMINER) {
  cat("NOTE: install.packages(c('FactoMineR','factoextra')) for the full PCA + plots.\n")
}

# =============================================================================
# Configuration
# =============================================================================
BASE_DIR <- getwd()
MOVEMENT_FILE <- file.path(BASE_DIR, "jaguar_movement_data.csv")
RDS_DIR_NEW <- file.path(BASE_DIR, "home_ranges/home_range_output/individual_akde_rds")
RDS_DIR_OLD <- file.path(BASE_DIR, "home_ranges/home_range_output/individual_rds")
OUT_DIR <- file.path(BASE_DIR, "movement_pca_output")
dir.create(OUT_DIR, showWarnings = FALSE, recursive = TRUE)

# Cluster file: prefer the AKDE-derived one if it exists yet, fall back to
# the earlier MCP-based screen otherwise. Purely an annotation join -- never
# used to filter or weight the PCA itself.
CLUSTER_FILE <- if (file.exists("akde_overlap_clusters.csv")) {
  "akde_overlap_clusters.csv"
} else if (file.exists("overlap_clusters.csv")) {
  "overlap_clusters.csv"
} else {
  NA_character_
}

MAX_VALID_DT_HOURS <- 48  # drop consecutive-fix pairs with larger gaps as tracking artifacts, not real steps

# =============================================================================
# Load raw movement data
# =============================================================================
cat("--- Loading movement data ---\n")
mov <- fread(MOVEMENT_FILE, stringsAsFactors = FALSE)
setnames(mov, "individual.local.identifier (ID)", "id", skip_absent = TRUE)
setnames(mov, "location.long", "lon", skip_absent = TRUE)
setnames(mov, "location.lat", "lat", skip_absent = TRUE)
mov[, timestamp := as.POSIXct(timestamp, format = "%m/%d/%y %H:%M", tz = "UTC")]
na_ts <- is.na(mov$timestamp)
if (any(na_ts)) mov[na_ts, timestamp := as.POSIXct(timestamp, format = "%m/%d/%Y %H:%M", tz = "UTC")]
mov <- mov[!is.na(lon) & !is.na(lat) & !is.na(timestamp)]
setorder(mov, id, timestamp)
cat(sprintf("  %d fixes, %d individuals\n", nrow(mov), uniqueN(mov$id)))

m_per_deg_lat <- 111320
m_per_deg_lon <- function(lat) 111320 * cos(lat * pi / 180)

# =============================================================================
# Per-individual movement-metric computation
# =============================================================================
compute_individual_metrics <- function(id, df) {
  df <- df[order(timestamp)]
  n <- nrow(df)
  if (n < 5) return(NULL)

  lon <- df$lon; lat <- df$lat; t <- df$timestamp

  dt_h <- as.numeric(diff(t), units = "hours")
  dlat_m <- diff(lat) * m_per_deg_lat
  dlon_m <- diff(lon) * m_per_deg_lon(lat[-n])
  step_m <- sqrt(dlat_m^2 + dlon_m^2)
  bearing <- atan2(dlon_m, dlat_m)
  turn_rad <- c(NA, diff(bearing))
  turn_rad <- ifelse(turn_rad > pi, turn_rad - 2*pi, ifelse(turn_rad < -pi, turn_rad + 2*pi, turn_rad))

  valid <- dt_h > 0 & dt_h <= MAX_VALID_DT_HOURS
  step_v <- step_m[valid]; dt_v <- dt_h[valid]; turn_v <- turn_rad[valid]
  speed_v <- step_v / dt_v                       # m/h
  Vp_v <- speed_v * cos(turn_v)                  # persistence velocity (Gurarie et al. 2009)

  if (length(step_v) < 3) return(NULL)

  # ---- NSD-based Resident/Disperser classification (ported from eda_nsd.py) ----
  lat_mean <- mean(lat)
  dx <- (lon - lon[1]) * m_per_deg_lon(lat_mean)
  dy <- (lat - lat[1]) * m_per_deg_lat
  nsd_km2 <- (dx^2 + dy^2) / 1e6
  max_nsd <- max(nsd_km2)
  final_nsd <- if (n >= 10) median(tail(nsd_km2, 10)) else median(nsd_km2)
  nsd_class <- if (max_nsd < 1) "Sedentary" else if (final_nsd > 0.5 * max_nsd) "Disperser" else "Resident"

  # ---- Sinuosity (Resident) or straightness index (Disperser), via trajr ----
  tort_metric <- NA_real_; tort_type <- NA_character_
  if (HAS_TRAJR) {
    tryCatch({
      coords <- data.frame(x = (lon - lon[1]) * m_per_deg_lon(lat_mean),
                            y = (lat - lat[1]) * m_per_deg_lat,
                            time = as.numeric(t))
      traj <- trajr::TrajFromCoords(coords, xCol = "x", yCol = "y", timeCol = "time", timeUnits = "s")
      if (nsd_class == "Disperser") {
        tort_metric <- trajr::TrajStraightness(traj); tort_type <- "straightness"
      } else {
        tort_metric <- trajr::TrajSinuosity2(traj); tort_type <- "sinuosity"
      }
    }, error = function(e) cat(sprintf("[ID %s] trajr failed: %s\n", id, e$message)))
  }

  # ---- Intensity of use needs home-range area; filled in after RDS join ----
  data.frame(
    id = id,
    n_fixes_used = length(step_v),
    median_step_m = median(step_v),
    median_turn_abs_rad = median(abs(turn_v), na.rm = TRUE),
    median_speed_m_h = median(speed_v),
    median_Vp = median(Vp_v),
    native_median_dt_h = median(dt_h[dt_h > 0], na.rm = TRUE),
    nsd_class = nsd_class,
    tortuosity_metric = tort_metric,
    tortuosity_type = tort_type,
    total_distance_m = sum(step_v)
  )
}

cat("--- Computing per-individual movement metrics ---\n")
metrics_list <- mov[, .(data = list(.SD)), by = id]
results <- lapply(seq_len(nrow(metrics_list)), function(i) {
  compute_individual_metrics(metrics_list$id[i], metrics_list$data[[i]])
})
metrics <- rbindlist(results[!sapply(results, is.null)])
cat(sprintf("  %d individuals with usable movement metrics\n", nrow(metrics)))

# =============================================================================
# Pull home-range area + n_core_areas directly from the AKDE RDS files
# =============================================================================
cat("--- Reading home-range areas from individual_akde_rds/ (falling back to individual_rds/ if not yet regenerated) ---\n")
get_hr <- function(id) {
  path_new <- file.path(RDS_DIR_NEW, sprintf("individual_%d.rds", id))
  path_old <- file.path(RDS_DIR_OLD, sprintf("individual_%d.rds", id))
  path <- if (file.exists(path_new)) path_new else path_old
  source_used <- if (file.exists(path_new)) "new" else if (file.exists(path_old)) "old" else "missing"
  if (!file.exists(path)) return(data.frame(id = id, area_95_km2 = NA_real_, n_core_areas = NA_integer_, hr_source = source_used))
  r <- readRDS(path)
  if (r$status != "success") return(data.frame(id = id, area_95_km2 = NA_real_, n_core_areas = NA_integer_, hr_source = source_used))
  # area_95_km2, area_50_km2, mcp_area_km2, and n_core_areas are computed
  # before the (now-removed) segmentation block ever runs, so these fields
  # are valid in the old individual_rds/ files too -- the segclust2d bug
  # only affected is_range_shift/n_segments/segment_akde_list, not these.
  data.frame(id = id, area_95_km2 = r$area_95_km2, n_core_areas = r$n_core_areas, hr_source = source_used)
}
hr <- rbindlist(lapply(metrics$id, get_hr))

cat("\n--- Home-range source report (by individual ID) ---\n")
new_ids <- sort(hr$id[hr$hr_source == "new"])
old_ids <- sort(hr$id[hr$hr_source == "old"])
missing_ids <- sort(hr$id[hr$hr_source == "missing"])

cat(sprintf("NEW source (individual_akde_rds/), n=%d:\n  %s\n",
            length(new_ids), if (length(new_ids)) paste(new_ids, collapse = ", ") else "(none)"))
cat(sprintf("OLD source (individual_rds/, pre-simplification -- fine for area_95_km2/n_core_areas), n=%d:\n  %s\n",
            length(old_ids), if (length(old_ids)) paste(old_ids, collapse = ", ") else "(none)"))
cat(sprintf("MISSING (no RDS in either directory -- will be DROPPED from the PCA), n=%d:\n  %s\n",
            length(missing_ids), if (length(missing_ids)) paste(missing_ids, collapse = ", ") else "(none)"))
cat("\n")
metrics <- merge(metrics, hr, by = "id", all.x = TRUE)
metrics[, intensity_of_use := total_distance_m / 1000 / (area_95_km2^2)]  # km / km^4, comparable across individuals

# =============================================================================
# Attach cluster membership as annotation only
# =============================================================================
if (!is.na(CLUSTER_FILE)) {
  cat(sprintf("--- Attaching cluster membership from %s (annotation only) ---\n", CLUSTER_FILE))
  clusters <- fread(CLUSTER_FILE)
  metrics <- merge(metrics, clusters[, .(id, cluster_id)], by = "id", all.x = TRUE)
} else {
  cat("--- No cluster file found yet; proceeding without cluster annotation ---\n")
  metrics[, cluster_id := NA_integer_]
}

fwrite(metrics, file.path(OUT_DIR, "movement_covariates.csv"))
cat(sprintf("Wrote %s (%d individuals x %d columns)\n",
            file.path(OUT_DIR, "movement_covariates.csv"), nrow(metrics), ncol(metrics)))

# =============================================================================
# PCA
# =============================================================================
pca_cols <- c("median_step_m", "median_turn_abs_rad", "median_speed_m_h", "median_Vp",
              "tortuosity_metric", "intensity_of_use", "area_95_km2", "native_median_dt_h")

pca_data <- metrics[complete.cases(metrics[, ..pca_cols]), ]
cat(sprintf("--- Running PCA on %d individuals with complete covariates ---\n", nrow(pca_data)))

pca_matrix <- as.matrix(pca_data[, ..pca_cols])
rownames(pca_matrix) <- pca_data$id

if (HAS_FACTOMINER) {
  res_pca <- FactoMineR::PCA(pca_matrix, scale.unit = TRUE, graph = FALSE)
  saveRDS(res_pca, file.path(OUT_DIR, "pca_result.rds"))

  loadings <- as.data.frame(res_pca$var$coord)
  fwrite(loadings, file.path(OUT_DIR, "pca_loadings.csv"), row.names = TRUE)

  scores <- as.data.frame(res_pca$ind$coord)
  scores$id <- pca_data$id
  scores$cluster_id <- pca_data$cluster_id
  scores$nsd_class <- pca_data$nsd_class
  fwrite(scores, file.path(OUT_DIR, "pca_scores.csv"))

  cat("\n--- Variance explained ---\n")
  print(res_pca$eig[, 2])

  cat("\n--- Loading of native_median_dt_h on each PC (confound check) ---\n")
  print(loadings["native_median_dt_h", ])
  interval_loading_pc1 <- abs(loadings["native_median_dt_h", "Dim.1"])
  if (interval_loading_pc1 > 0.5) {
    cat(sprintf("\nWARNING: native fix interval loads at %.2f on PC1 (|loading|>0.5) -- likely confounded.\n", interval_loading_pc1))
    cat("Re-run with residual-partialled covariates (regress each on log(native_median_dt_h) first) before interpreting PC1.\n")
  } else {
    cat(sprintf("\nnative fix interval loading on PC1 = %.2f -- not dominant, but check other PCs too.\n", interval_loading_pc1))
  }

  if (HAS_FACTOEXTRA) {
    library(factoextra)
    p1 <- fviz_pca_biplot(res_pca, repel = TRUE,
                           col.ind = if (any(!is.na(pca_data$cluster_id))) factor(pca_data$cluster_id) else "black",
                           title = "Movement Covariate PCA - Biplot")
    ggplot2::ggsave(file.path(OUT_DIR, "pca_biplot.png"), p1, width = 10, height = 8)

    p2 <- fviz_eig(res_pca, addlabels = TRUE, title = "Scree Plot")
    ggplot2::ggsave(file.path(OUT_DIR, "pca_scree.png"), p2, width = 8, height = 6)

    p3 <- fviz_pca_var(res_pca, col.var = "contrib", title = "Variable Contributions")
    ggplot2::ggsave(file.path(OUT_DIR, "pca_variables.png"), p3, width = 8, height = 8)

    cat(sprintf("Plots written to %s/\n", OUT_DIR))
  }
} else {
  cat("FactoMineR not installed -- falling back to base prcomp() for a quick look.\n")
  res_pca <- prcomp(pca_matrix, scale. = TRUE)
  print(summary(res_pca))
  saveRDS(res_pca, file.path(OUT_DIR, "pca_result_base.rds"))
}

cat("\n=== Done ===\n")
cat(sprintf("Output directory: %s\n", OUT_DIR))
