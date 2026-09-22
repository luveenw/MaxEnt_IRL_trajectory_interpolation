#!/usr/bin/env Rscript
# =============================================================================
# Jaguar Home Range Analysis
# =============================================================================
# Computes AKDE home ranges (95% + 50%) and MCP for 117 jaguar individuals
# from the Morato et al. (2018) dataset using the ctmm R package.
# Performs temporal segmentation via segclust2d to detect range shifts.
# Exports results as GeoJSON + per-individual RDS checkpoints.
#
# Usage:
#   Rscript home_range_analysis.R                    # Full batch (117 individuals)
#   Rscript home_range_analysis.R --test             # Test batch (5 individuals)
#   Rscript home_range_analysis.R --ids 1,26,70      # Specific individuals
#   Rscript home_range_analysis.R --resume           # Resume from checkpoints
#   Rscript home_range_analysis.R --consolidate-only # Rebuild GeoJSON from checkpoints
# =============================================================================

suppressPackageStartupMessages({
  library(ctmm)
  library(sf)
  library(jsonlite)
  library(data.table)
  library(parallel)
})

# =============================================================================
# Configuration
# =============================================================================

BASE_DIR <- getwd()
DATA_DIR <- file.path(BASE_DIR, "data")
OUTPUT_DIR <- file.path(BASE_DIR, "home_range_output")
RDS_DIR <- file.path(OUTPUT_DIR, "individual_rds")
GPS_DIR <- file.path(OUTPUT_DIR, "individual_gps")
LOG_DIR <- file.path(OUTPUT_DIR, "logs")

# Create output directories
for (d in c(OUTPUT_DIR, RDS_DIR, GPS_DIR, LOG_DIR)) {
  dir.create(d, recursive = TRUE, showWarnings = FALSE)
}

# Test batch individual IDs (chosen to span different studies/range sizes)
TEST_IDS <- c(1, 26, 70, 85, 103)

# Number of parallel cores (leave 1 free for system)
N_CORES <- max(1, detectCores() - 1)

# =============================================================================
# Parse command-line arguments
# =============================================================================

args <- commandArgs(trailingOnly = TRUE)

run_mode <- "full"  # default
specific_ids <- NULL

if ("--test" %in% args) {
  run_mode <- "test"
  specific_ids <- TEST_IDS
  cat("=== TEST MODE: Processing", length(TEST_IDS), "individuals ===\n")
} else if ("--ids" %in% args) {
  idx <- which(args == "--ids")
  if (idx < length(args)) {
    specific_ids <- as.integer(strsplit(args[idx + 1], ",")[[1]])
    run_mode <- "specific"
    cat("=== SPECIFIC MODE: Processing individuals", paste(specific_ids, collapse = ", "), "===\n")
  }
} else if ("--resume" %in% args) {
  run_mode <- "resume"
  cat("=== RESUME MODE: Skipping individuals with existing checkpoints ===\n")
} else if ("--consolidate-only" %in% args) {
  run_mode <- "consolidate"
  cat("=== CONSOLIDATE MODE: Rebuilding home_ranges_raw.geojson from checkpoints ===\n")
}

# =============================================================================
# Data Loading
# =============================================================================

cat("\n--- Loading data ---\n")

# Load movement data
movement_file <- file.path(BASE_DIR, "jaguar_movement_data.csv")
cat("Reading movement data from:", movement_file, "\n")
mov <- fread(movement_file, stringsAsFactors = FALSE)
cat("  Loaded", nrow(mov), "GPS fixes for", length(unique(mov[["individual.local.identifier (ID)"]])), "individuals\n")

# Load additional information (sex assignments)
addinfo_file <- file.path(BASE_DIR, "Jaguar_additional_information_fixed.csv")
cat("Reading additional info from:", addinfo_file, "\n")
addinfo <- fread(addinfo_file, stringsAsFactors = FALSE)
sex_lookup <- addinfo[!is.na(Sex), .(ID, Sex)]
sex_lookup <- unique(sex_lookup)
cat("  Sex data for", nrow(sex_lookup), "individuals (", 
    sum(sex_lookup$Sex == "Male"), "M,", sum(sex_lookup$Sex == "Female"), "F)\n")

# Merge sex into movement data
mov[, individual_id := `individual.local.identifier (ID)`]
mov <- merge(mov, sex_lookup, by.x = "individual_id", by.y = "ID", all.x = TRUE)

# Parse timestamps
mov[, timestamp_parsed := as.POSIXct(timestamp, format = "%m/%d/%y %H:%M", tz = "UTC")]
# Try alternate format for any that failed
na_ts <- is.na(mov$timestamp_parsed)
if (any(na_ts)) {
  mov[na_ts, timestamp_parsed := as.POSIXct(timestamp, format = "%m/%d/%Y %H:%M", tz = "UTC")]
}
cat("  Timestamp parsing: ", sum(!is.na(mov$timestamp_parsed)), "parsed,",
    sum(is.na(mov$timestamp_parsed)), "failed\n")

# Get unique individuals with metadata
individuals <- mov[, .(
  study_name = `study.name`[1],
  sex = Sex[1],
  n_points = .N,
  start_date = min(timestamp_parsed, na.rm = TRUE),
  end_date = max(timestamp_parsed, na.rm = TRUE),
  duration_days = as.numeric(difftime(max(timestamp_parsed, na.rm = TRUE),
                                       min(timestamp_parsed, na.rm = TRUE), units = "days")),
  mean_lon = mean(`location.long`, na.rm = TRUE),
  mean_lat = mean(`location.lat`, na.rm = TRUE)
), by = individual_id]

cat("\n  Individual summary:\n")
cat("    Total:", nrow(individuals), "\n")
cat("    Males:", sum(individuals$sex == "Male", na.rm = TRUE), "\n")
cat("    Females:", sum(individuals$sex == "Female", na.rm = TRUE), "\n")
cat("    Median tracking duration:", median(individuals$duration_days, na.rm = TRUE), "days\n")
cat("    Median GPS fixes:", median(individuals$n_points), "\n")

# =============================================================================
# Determine which individuals to process
# =============================================================================

all_ids <- sort(individuals$individual_id)

if (run_mode == "test") {
  process_ids <- intersect(TEST_IDS, all_ids)
} else if (run_mode == "specific") {
  process_ids <- intersect(specific_ids, all_ids)
} else if (run_mode == "resume") {
  # Skip individuals that already have RDS files
  existing <- gsub("individual_(\\d+)\\.rds", "\\1",
                   list.files(RDS_DIR, pattern = "individual_\\d+\\.rds"))
  existing_ids <- as.integer(existing)
  process_ids <- setdiff(all_ids, existing_ids)
  cat("  Skipping", length(existing_ids), "individuals with existing checkpoints\n")
  cat("  Remaining:", length(process_ids), "individuals\n")
} else {
  process_ids <- all_ids
}

if (length(process_ids) == 0) {
  cat("\nNo individuals to process. Use --resume to skip existing, or delete RDS files to reprocess.\n")
  quit(status = 0)
}

cat("\nWill process", length(process_ids), "individuals\n")

# =============================================================================
# Core Analysis Function: process_individual()
# =============================================================================

process_individual <- function(ind_id, mov_data, ind_meta) {
  
  tryCatch({
    
    cat(sprintf("\n[ID %d] Starting analysis...\n", ind_id))
    
    # ---- Extract this individual's data ----
    ind_data <- mov_data[individual_id == ind_id]
    meta <- ind_meta[individual_id == ind_id]
    
    cat(sprintf("[ID %d] %s | %s | %d points | %.0f days | Study: %s\n",
                ind_id, meta$sex, 
                format(meta$start_date, "%Y-%m-%d"),
                meta$n_points, meta$duration_days, meta$study_name))
    
    # ---- Prepare ctmm telemetry object ----
    # ctmm expects columns: individual.local.identifier, timestamp, location.long, location.lat
    tel_df <- data.frame(
      `individual.local.identifier` = as.character(ind_id),
      timestamp = format(ind_data$timestamp_parsed, "%Y-%m-%d %H:%M:%S"),
      `location.long` = ind_data$`location.long`,
      `location.lat` = ind_data$`location.lat`,
      check.names = FALSE
    )
    
    # Remove rows with NA coordinates or timestamps
    tel_df <- tel_df[complete.cases(tel_df), ]
    
    if (nrow(tel_df) < 20) {
      warning(sprintf("[ID %d] Too few valid GPS points (%d). Skipping.", ind_id, nrow(tel_df)))
      return(list(
        id = ind_id, status = "skipped",
        reason = paste("Too few valid GPS points:", nrow(tel_df))
      ))
    }
    
    # Convert to ctmm telemetry object
    tel <- as.telemetry(tel_df, timeformat = "%Y-%m-%d %H:%M:%S")
    cat(sprintf("[ID %d] Telemetry object: %d locations\n", ind_id, nrow(tel)))
    
    # ---- Variogram analysis ----
    cat(sprintf("[ID %d] Computing variogram...\n", ind_id))
    svf <- variogram(tel)
    
    # Initial model guess from variogram
    guess <- ctmm.guess(tel, interactive = FALSE)
    cat(sprintf("[ID %d] Initial guess: %s\n", ind_id, summary(guess)$name))
    
    # ---- Model selection ----
    cat(sprintf("[ID %d] Fitting movement models (ctmm.select)...\n", ind_id))
    fit <- ctmm.select(tel, guess, verbose = TRUE)
    
    # Best model is the first in the list
    best_model <- fit[[1]]
    model_name <- names(fit)[1]
    cat(sprintf("[ID %d] Best model: %s\n", ind_id, model_name))
    
    # ---- AKDE computation (95% and 50%) ----
    cat(sprintf("[ID %d] Computing AKDE...\n", ind_id))
    ud <- akde(tel, best_model)
    
    # Extract 95% and 50% contour areas
    area_summary <- summary(ud, units = FALSE)  # Get area in m^2
    area_95_km2 <- area_summary$CI["area (square meters)", "est"] / 1e6
    
    cat(sprintf("[ID %d] AKDE 95%% area: %.2f km²\n", ind_id, area_95_km2))
    
    # ---- Extract contour polygons ----
    # SpatialPolygonsDataFrame.UD returns 3 rows: low CI, estimate, high CI
    # We extract only the estimate (row 2) for the primary polygons
    
    # 95% contour
    sp_95 <- SpatialPolygonsDataFrame.UD(ud, level.UD = 0.95)
    sf_95_all <- st_as_sf(sp_95)
    sf_95_all <- st_transform(sf_95_all, crs = 4326)
    sf_95 <- sf_95_all[2, ]  # estimate only
    
    # 50% contour
    sp_50 <- SpatialPolygonsDataFrame.UD(ud, level.UD = 0.50)
    sf_50_all <- st_as_sf(sp_50)
    sf_50_all <- st_transform(sf_50_all, crs = 4326)
    sf_50 <- sf_50_all[2, ]  # estimate only
    
    # Compute areas in km² (single value now, not vector)
    area_95_precise <- as.numeric(st_area(sf_95)) / 1e6
    area_50_precise <- as.numeric(st_area(sf_50)) / 1e6
    
    cat(sprintf("[ID %d] AKDE areas: 95%% = %.2f km², 50%% = %.2f km²\n",
                ind_id, area_95_precise, area_50_precise))
    
    # ---- Check for multiple disconnected core areas ----
    # The 50% estimate polygon may be a MULTIPOLYGON with disjoint components
    # st_cast to POLYGON will split these into separate rows
    core_geom <- st_geometry(sf_50)
    if (st_geometry_type(core_geom) == "MULTIPOLYGON") {
      core_polygons <- st_cast(sf_50, "POLYGON", warn = FALSE)
      n_core_areas <- nrow(core_polygons)
    } else {
      core_polygons <- sf_50
      n_core_areas <- 1L
    }
    cat(sprintf("[ID %d] 50%% AKDE forms %d disconnected core area(s)\n", ind_id, n_core_areas))
    
    # ---- MCP computation ----
    cat(sprintf("[ID %d] Computing MCP...\n", ind_id))
    
    # Create sf point object for MCP
    gps_sf <- st_as_sf(ind_data, 
                        coords = c("location.long", "location.lat"),
                        crs = 4326)
    
    # Compute convex hull (MCP)
    mcp_polygon <- st_convex_hull(st_combine(gps_sf))
    
    # Project to equal area for accurate area calculation
    # Use local UTM zone based on centroid
    centroid_lon <- meta$mean_lon
    utm_zone <- floor((centroid_lon + 180) / 6) + 1
    hemisphere <- ifelse(meta$mean_lat >= 0, "north", "south")
    epsg <- ifelse(hemisphere == "north", 32600 + utm_zone, 32700 + utm_zone)
    
    mcp_projected <- st_transform(mcp_polygon, crs = epsg)
    mcp_area_km2 <- as.numeric(st_area(mcp_projected)) / 1e6
    
    cat(sprintf("[ID %d] MCP area: %.2f km²\n", ind_id, mcp_area_km2))
    
    # ---- Temporal segmentation (segclust2d) ----
    is_range_shift <- FALSE
    n_segments <- 1
    segment_results <- NULL
    segment_akde_list <- list()
    
    # Only attempt segmentation if trajectory is long enough
    if (meta$duration_days >= 60 && meta$n_points >= 100) {
      cat(sprintf("[ID %d] Running segclust2d segmentation...\n", ind_id))
      
      tryCatch({
        # segclust2d expects a data.frame with x, y, date columns
        # Project to UTM for distance-based segmentation
        gps_projected <- st_transform(gps_sf, crs = epsg)
        coords <- st_coordinates(gps_projected)
        
        seg_df <- data.frame(
          x = coords[, 1],
          y = coords[, 2],
          date = ind_data$timestamp_parsed[complete.cases(ind_data$`location.long`, ind_data$`location.lat`)]
        )
        seg_df <- seg_df[order(seg_df$date), ]
        seg_df <- seg_df[!duplicated(seg_df$date), ]  # Remove duplicate timestamps
        
        if (requireNamespace("segclust2d", quietly = TRUE)) {
          # Perform segmentation-clustering
          # Try up to 3 segments, 2-3 clusters
          # Note: 'type' parameter was removed in newer versions of segclust2d
          seg_result <- segclust2d::segclust(
            seg_df, 
            Kmax = 3,
            lmin = max(10, floor(nrow(seg_df) * 0.05)),  # Minimum segment length: 5% of data
            ncluster = c(2, 3),
            seg.var = c("x", "y")
          )
          
          # Get the best segmentation
          # augment() returns a data.frame with a 'state' column indicating segment membership
          best_seg <- segclust2d::augment(seg_result)
          n_segments <- length(unique(best_seg$state))
          is_range_shift <- n_segments > 1
          
          cat(sprintf("[ID %d] segclust2d detected %d segment(s)\n", ind_id, n_segments))
          
          if (is_range_shift) {
            segment_results <- best_seg
            
            # Compute per-segment AKDEs
            for (seg_idx in seq_len(n_segments)) {
              seg_rows <- which(best_seg$state == unique(best_seg$state)[seg_idx])
              
              if (length(seg_rows) < 30) {
                cat(sprintf("[ID %d] Segment %d has only %d points, skipping AKDE\n",
                            ind_id, seg_idx, length(seg_rows)))
                next
              }
              
              # Create segment telemetry object
              seg_tel_df <- tel_df[seg_rows, ]
              
              tryCatch({
                seg_tel <- as.telemetry(seg_tel_df, timeformat = "%Y-%m-%d %H:%M:%S")
                seg_guess <- ctmm.guess(seg_tel, interactive = FALSE)
                seg_fit <- ctmm.select(seg_tel, seg_guess, verbose = TRUE)
                seg_best <- seg_fit[[1]]
                seg_ud <- akde(seg_tel, seg_best)
                
                # Extract contours (estimate only, row 2)
                seg_sp_95 <- SpatialPolygonsDataFrame.UD(seg_ud, level.UD = 0.95)
                seg_sf_95 <- st_as_sf(seg_sp_95)
                seg_sf_95 <- st_transform(seg_sf_95, crs = 4326)
                seg_sf_95 <- seg_sf_95[2, ]  # estimate only
                
                seg_sp_50 <- SpatialPolygonsDataFrame.UD(seg_ud, level.UD = 0.50)
                seg_sf_50 <- st_as_sf(seg_sp_50)
                seg_sf_50 <- st_transform(seg_sf_50, crs = 4326)
                seg_sf_50 <- seg_sf_50[2, ]  # estimate only
                
                segment_akde_list[[seg_idx]] <- list(
                  segment_id = seg_idx,
                  sf_95 = seg_sf_95,
                  sf_50 = seg_sf_50,
                  area_95_km2 = as.numeric(st_area(seg_sf_95)) / 1e6,
                  area_50_km2 = as.numeric(st_area(seg_sf_50)) / 1e6,
                  n_points = length(seg_rows),
                  model_name = names(seg_fit)[1]
                )
                
                cat(sprintf("[ID %d] Segment %d AKDE 95%%: %.2f km²\n",
                            ind_id, seg_idx, segment_akde_list[[seg_idx]]$area_95_km2))
                
              }, error = function(e) {
                cat(sprintf("[ID %d] Segment %d AKDE failed: %s\n", ind_id, seg_idx, e$message))
              })
            }
          }
        } else {
          cat(sprintf("[ID %d] segclust2d not available, skipping segmentation\n", ind_id))
        }
        
      }, error = function(e) {
        cat(sprintf("[ID %d] Segmentation failed: %s\n", ind_id, e$message))
      })
    } else {
      cat(sprintf("[ID %d] Trajectory too short for segmentation (%.0f days, %d points)\n",
                  ind_id, meta$duration_days, meta$n_points))
    }
    
    # ---- Build result object ----
    result <- list(
      id = ind_id,
      status = "success",
      study_name = meta$study_name,
      sex = meta$sex,
      n_gps_points = meta$n_points,
      trajectory_days = as.numeric(meta$duration_days),
      
      # Model info
      ctmm_model = model_name,
      
      # Full-trajectory contours
      sf_95 = sf_95,
      sf_50 = sf_50,
      area_95_km2 = area_95_precise,
      area_50_km2 = area_50_precise,
      n_core_areas = n_core_areas,
      
      # MCP
      mcp_polygon = st_sf(geometry = st_sfc(mcp_polygon, crs = 4326)),
      mcp_area_km2 = mcp_area_km2,
      
      # Segmentation
      is_range_shift = is_range_shift,
      n_segments = n_segments,
      segment_results = segment_results,
      segment_akde_list = segment_akde_list,
      
      # ctmm objects for checkpointing
      telemetry = tel,
      variogram = svf,
      model_fits = fit,
      akde_ud = ud
    )
    
    # ---- Save RDS checkpoint ----
    rds_path <- file.path(RDS_DIR, sprintf("individual_%d.rds", ind_id))
    saveRDS(result, rds_path)
    cat(sprintf("[ID %d] Checkpoint saved: %s\n", ind_id, rds_path))
    
    # ---- Export per-individual GPS GeoJSON ----
    export_individual_gps_geojson(ind_id, ind_data, sf_50, core_polygons)
    
    cat(sprintf("[ID %d] COMPLETE | AKDE 95%%: %.1f km² | MCP: %.1f km² | Cores: %d | Segments: %d\n",
                ind_id, area_95_precise, mcp_area_km2, n_core_areas, n_segments))
    
    return(result)
    
  }, error = function(e) {
    cat(sprintf("[ID %d] FAILED: %s\n", ind_id, e$message))
    cat(sprintf("[ID %d] Traceback: %s\n", ind_id, paste(capture.output(traceback()), collapse = "\n")))
    return(list(id = ind_id, status = "error", reason = e$message))
  })
}

# =============================================================================
# GeoJSON Export Functions
# =============================================================================

export_individual_gps_geojson <- function(ind_id, ind_data, sf_50, core_polygons) {
  # Export per-individual GeoJSON with GPS points + core area polygons
  
  tryCatch({
    # GPS points
    gps_clean <- ind_data[!is.na(`location.long`) & !is.na(`location.lat`)]
    gps_sf <- st_as_sf(gps_clean,
                        coords = c("location.long", "location.lat"),
                        crs = 4326)
    gps_sf$feature_type <- "gps_point"
    gps_sf$timestamp_str <- as.character(gps_clean$timestamp_parsed)
    gps_sf$individual_id <- ind_id
    
    # Keep only relevant columns
    gps_export <- gps_sf[, c("feature_type", "individual_id", "timestamp_str", "geometry")]
    
    # Core area polygons
    core_export <- core_polygons
    core_export$feature_type <- "core_area"
    core_export$individual_id <- ind_id
    core_export$timestamp_str <- NA_character_
    
    # Keep only matching columns 
    core_cols <- intersect(names(gps_export), names(core_export))
    core_cols <- c(core_cols, "geometry")
    core_cols <- unique(core_cols)
    
    # Combine (need to handle column mismatch carefully)
    gps_for_bind <- gps_export[, c("feature_type", "individual_id", "timestamp_str")]
    core_for_bind <- st_sf(
      feature_type = rep("core_area", nrow(core_export)),
      individual_id = rep(ind_id, nrow(core_export)),
      timestamp_str = rep(NA_character_, nrow(core_export)),
      geometry = st_geometry(core_export)
    )
    
    combined <- rbind(gps_for_bind, core_for_bind)
    
    out_path <- file.path(GPS_DIR, sprintf("individual_%d.geojson", ind_id))
    st_write(combined, out_path, driver = "GeoJSON", delete_dsn = TRUE, quiet = TRUE)
    cat(sprintf("[ID %d] GPS GeoJSON exported: %s (%d points + %d core polygons)\n",
                ind_id, out_path, nrow(gps_for_bind), nrow(core_for_bind)))
    
  }, error = function(e) {
    cat(sprintf("[ID %d] GPS GeoJSON export failed: %s\n", ind_id, e$message))
  })
}

load_all_checkpoints <- function(in_memory = NULL) {
  # Gather every successful per-individual result available on disk, then
  # overlay anything still held in memory from the current run.
  #
  # Reading from RDS_DIR rather than from the current run's `results` is what
  # makes consolidation complete: a --resume run only carries the individuals it
  # actually reprocessed, so consolidating from memory alone silently drops
  # every individual that was finished in an earlier invocation.

  rds_files <- list.files(RDS_DIR, pattern = "^individual_\\d+\\.rds$",
                          full.names = TRUE)
  cat(sprintf("  Reading %d checkpoint(s) from %s\n", length(rds_files), RDS_DIR))

  by_id <- list()

  for (f in rds_files) {
    res <- tryCatch(readRDS(f), error = function(e) {
      cat(sprintf("  WARNING: could not read %s: %s\n", basename(f), e$message))
      NULL
    })
    if (is.null(res) || is.null(res$status) || res$status != "success") next
    by_id[[as.character(res$id)]] <- res
  }

  # In-memory results win for IDs processed in this run (they are identical to
  # what was just written, but this keeps the output correct even if a
  # checkpoint write failed).
  if (!is.null(in_memory)) {
    for (res in in_memory) {
      if (is.null(res$status) || res$status != "success") next
      by_id[[as.character(res$id)]] <- res
    }
  }

  ids <- sort(as.integer(names(by_id)))
  cat(sprintf("  %d successful individual(s): %s\n", length(ids),
              paste(ids, collapse = ", ")))

  by_id[as.character(ids)]
}

build_consolidated_geojson <- function(results = NULL) {
  # Build a single GeoJSON FeatureCollection from every individual on disk
  
  cat("\n--- Consolidating results into home_ranges_raw.geojson ---\n")
  
  results <- load_all_checkpoints(results)
  
  all_features <- list()
  feature_idx <- 0
  
  for (res in results) {
    if (res$status != "success") next
    
    ind_id <- res$id
    
    # ---- Full-trajectory AKDE 95% ----
    feat <- res$sf_95
    feat$individual_id <- ind_id
    feat$study_name <- res$study_name
    feat$sex <- res$sex
    feat$segment_id <- 0L
    feat$contour_level <- 95L
    feat$area_km2 <- res$area_95_km2
    feat$method <- "AKDE"
    feat$is_range_shift <- res$is_range_shift
    feat$n_core_areas <- res$n_core_areas
    feat$ctmm_model <- res$ctmm_model
    feat$n_gps_points <- res$n_gps_points
    feat$trajectory_days <- res$trajectory_days
    
    feature_idx <- feature_idx + 1
    all_features[[feature_idx]] <- feat[, c("individual_id", "study_name", "sex",
                                             "segment_id", "contour_level", "area_km2",
                                             "method", "is_range_shift", "n_core_areas",
                                             "ctmm_model", "n_gps_points", "trajectory_days")]
    
    # ---- Full-trajectory AKDE 50% ----
    feat50 <- res$sf_50
    feat50$individual_id <- ind_id
    feat50$study_name <- res$study_name
    feat50$sex <- res$sex
    feat50$segment_id <- 0L
    feat50$contour_level <- 50L
    feat50$area_km2 <- res$area_50_km2
    feat50$method <- "AKDE"
    feat50$is_range_shift <- res$is_range_shift
    feat50$n_core_areas <- res$n_core_areas
    feat50$ctmm_model <- res$ctmm_model
    feat50$n_gps_points <- res$n_gps_points
    feat50$trajectory_days <- res$trajectory_days
    
    feature_idx <- feature_idx + 1
    all_features[[feature_idx]] <- feat50[, c("individual_id", "study_name", "sex",
                                               "segment_id", "contour_level", "area_km2",
                                               "method", "is_range_shift", "n_core_areas",
                                               "ctmm_model", "n_gps_points", "trajectory_days")]
    
    # ---- MCP ----
    mcp_feat <- res$mcp_polygon
    mcp_feat$individual_id <- ind_id
    mcp_feat$study_name <- res$study_name
    mcp_feat$sex <- res$sex
    mcp_feat$segment_id <- 0L
    mcp_feat$contour_level <- 100L  # MCP is effectively 100%
    mcp_feat$area_km2 <- res$mcp_area_km2
    mcp_feat$method <- "MCP"
    mcp_feat$is_range_shift <- res$is_range_shift
    mcp_feat$n_core_areas <- res$n_core_areas
    mcp_feat$ctmm_model <- res$ctmm_model
    mcp_feat$n_gps_points <- res$n_gps_points
    mcp_feat$trajectory_days <- res$trajectory_days
    
    feature_idx <- feature_idx + 1
    all_features[[feature_idx]] <- mcp_feat[, c("individual_id", "study_name", "sex",
                                                  "segment_id", "contour_level", "area_km2",
                                                  "method", "is_range_shift", "n_core_areas",
                                                  "ctmm_model", "n_gps_points", "trajectory_days")]
    
    # ---- Per-segment AKDEs (if range shift detected) ----
    if (res$is_range_shift && length(res$segment_akde_list) > 0) {
      for (seg in res$segment_akde_list) {
        if (is.null(seg)) next
        
        # 95% segment contour
        seg_feat_95 <- seg$sf_95
        seg_feat_95$individual_id <- ind_id
        seg_feat_95$study_name <- res$study_name
        seg_feat_95$sex <- res$sex
        seg_feat_95$segment_id <- as.integer(seg$segment_id)
        seg_feat_95$contour_level <- 95L
        seg_feat_95$area_km2 <- seg$area_95_km2
        seg_feat_95$method <- "AKDE"
        seg_feat_95$is_range_shift <- TRUE
        seg_feat_95$n_core_areas <- NA_integer_
        seg_feat_95$ctmm_model <- seg$model_name
        seg_feat_95$n_gps_points <- as.integer(seg$n_points)
        seg_feat_95$trajectory_days <- NA_real_
        
        feature_idx <- feature_idx + 1
        all_features[[feature_idx]] <- seg_feat_95[, c("individual_id", "study_name", "sex",
                                                         "segment_id", "contour_level", "area_km2",
                                                         "method", "is_range_shift", "n_core_areas",
                                                         "ctmm_model", "n_gps_points", "trajectory_days")]
        
        # 50% segment contour
        seg_feat_50 <- seg$sf_50
        seg_feat_50$individual_id <- ind_id
        seg_feat_50$study_name <- res$study_name
        seg_feat_50$sex <- res$sex
        seg_feat_50$segment_id <- as.integer(seg$segment_id)
        seg_feat_50$contour_level <- 50L
        seg_feat_50$area_km2 <- seg$area_50_km2
        seg_feat_50$method <- "AKDE"
        seg_feat_50$is_range_shift <- TRUE
        seg_feat_50$n_core_areas <- NA_integer_
        seg_feat_50$ctmm_model <- seg$model_name
        seg_feat_50$n_gps_points <- as.integer(seg$n_points)
        seg_feat_50$trajectory_days <- NA_real_
        
        feature_idx <- feature_idx + 1
        all_features[[feature_idx]] <- seg_feat_50[, c("individual_id", "study_name", "sex",
                                                         "segment_id", "contour_level", "area_km2",
                                                         "method", "is_range_shift", "n_core_areas",
                                                         "ctmm_model", "n_gps_points", "trajectory_days")]
      }
    }
  }
  
  if (length(all_features) == 0) {
    cat("ERROR: No successful results to consolidate.\n")
    return(NULL)
  }
  
  # Combine all features
  cat(sprintf("Combining %d features...\n", length(all_features)))
  combined <- do.call(rbind, all_features)
  
  # Export
  out_path <- file.path(OUTPUT_DIR, "home_ranges_raw.geojson")
  st_write(combined, out_path, driver = "GeoJSON", delete_dsn = TRUE, quiet = TRUE)
  cat(sprintf("Exported: %s (%d features)\n", out_path, nrow(combined)))
  
  return(combined)
}

# =============================================================================
# Print summary report
# =============================================================================

print_summary <- function(results, elapsed_mins = NULL) {
  cat("\n")
  cat("=" |> rep(70) |> paste(collapse = ""))
  cat("\n  SUMMARY REPORT\n")
  cat("=" |> rep(70) |> paste(collapse = ""))
  cat("\n\n")
  
  if (!is.null(elapsed_mins)) {
    cat(sprintf("Total Execution Time: %.1f minutes\n", as.numeric(elapsed_mins)))
  }
  
  statuses <- sapply(results, function(r) r$status)
  cat(sprintf("Total processed: %d\n", length(results)))
  cat(sprintf("  Successful: %d\n", sum(statuses == "success")))
  cat(sprintf("  Skipped: %d\n", sum(statuses == "skipped")))
  cat(sprintf("  Errors: %d\n", sum(statuses == "error")))
  
  success_results <- results[statuses == "success"]
  
  if (length(success_results) > 0) {
    cat("\n--- Home Range Areas (km²) ---\n")
    akde_areas <- sapply(success_results, function(r) r$area_95_km2)
    mcp_areas <- sapply(success_results, function(r) r$mcp_area_km2)
    sexes <- sapply(success_results, function(r) r$sex)
    
    cat(sprintf("  AKDE 95%%: median = %.1f, mean = %.1f, range = [%.1f, %.1f]\n",
                median(akde_areas), mean(akde_areas), min(akde_areas), max(akde_areas)))
    cat(sprintf("  MCP:      median = %.1f, mean = %.1f, range = [%.1f, %.1f]\n",
                median(mcp_areas), mean(mcp_areas), min(mcp_areas), max(mcp_areas)))
    
    cat("\n--- By Sex ---\n")
    for (s in c("Male", "Female")) {
      mask <- sexes == s
      if (any(mask)) {
        cat(sprintf("  %s (n=%d): AKDE 95%% median = %.1f km², MCP median = %.1f km²\n",
                    s, sum(mask), median(akde_areas[mask]), median(mcp_areas[mask])))
      }
    }
    
    cat("\n--- Range Shifts ---\n")
    shifts <- sapply(success_results, function(r) r$is_range_shift)
    cat(sprintf("  Individuals with detected range shifts: %d / %d\n",
                sum(shifts), length(shifts)))
    if (any(shifts)) {
      shift_ids <- sapply(success_results[shifts], function(r) r$id)
      cat(sprintf("  IDs: %s\n", paste(shift_ids, collapse = ", ")))
    }
    
    cat("\n--- Multi-Core Areas ---\n")
    multi_core <- sapply(success_results, function(r) r$n_core_areas > 1)
    cat(sprintf("  Individuals with multiple core areas: %d / %d\n",
                sum(multi_core), length(multi_core)))
    if (any(multi_core)) {
      mc_ids <- sapply(success_results[multi_core], function(r) r$id)
      mc_n <- sapply(success_results[multi_core], function(r) r$n_core_areas)
      for (i in seq_along(mc_ids)) {
        cat(sprintf("    ID %d: %d core areas\n", mc_ids[i], mc_n[i]))
      }
    }
    
    # Per-individual table
    cat("\n--- Per-Individual Results ---\n")
    cat(sprintf("%-6s %-8s %-30s %10s %10s %6s %6s %8s\n",
                "ID", "Sex", "Study", "AKDE95", "MCP", "Cores", "Segs", "Model"))
    cat(rep("-", 90) |> paste(collapse = ""))
    cat("\n")
    for (r in success_results) {
      cat(sprintf("%-6d %-8s %-30s %10.1f %10.1f %6d %6d %8s\n",
                  r$id, r$sex, substr(r$study_name, 1, 30),
                  r$area_95_km2, r$mcp_area_km2,
                  r$n_core_areas, r$n_segments, r$ctmm_model))
    }
  }
  
  # Errors
  error_results <- results[statuses == "error"]
  if (length(error_results) > 0) {
    cat("\n--- Errors ---\n")
    for (r in error_results) {
      cat(sprintf("  ID %d: %s\n", r$id, r$reason))
    }
  }
}

# =============================================================================
# Main Execution
# =============================================================================

if (run_mode == "consolidate") {
  # Skip analysis entirely; rebuild the consolidated GeoJSON from checkpoints.
  build_consolidated_geojson(NULL)
  cat("\n=== Done (consolidate-only) ===\n")
  quit(status = 0)
}

cat(sprintf("\n=== Processing %d individuals using %d cores ===\n",
            length(process_ids), N_CORES))

start_time <- Sys.time()

if (run_mode == "test" || length(process_ids) <= 3) {
  # Sequential for test mode (easier to debug)
  results <- lapply(process_ids, function(id) {
    process_individual(id, mov, individuals)
  })
} else {
  # Parallel for full batch
  cat(sprintf("Starting parallel execution with %d cores...\n", N_CORES))
  results <- mclapply(process_ids, function(id) {
    process_individual(id, mov, individuals)
  }, mc.cores = N_CORES)
}

elapsed <- difftime(Sys.time(), start_time, units = "mins")
cat(sprintf("\n=== Completed in %.1f minutes ===\n", as.numeric(elapsed)))

# Print summary
print_summary(results, elapsed)

# Consolidate GeoJSON
consolidated <- build_consolidated_geojson(results)

cat("\n=== Done ===\n")
cat(sprintf("Output directory: %s\n", OUTPUT_DIR))
cat(sprintf("  home_ranges_raw.geojson: %s\n", file.path(OUTPUT_DIR, "home_ranges_raw.geojson")))
cat(sprintf("  Per-individual RDS: %s/\n", RDS_DIR))
cat(sprintf("  Per-individual GPS: %s/\n", GPS_DIR))
