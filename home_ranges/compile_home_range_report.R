#!/usr/bin/env Rscript
# Reads per-individual RDS checkpoints and writes a flat CSV summary.

BASE_DIR  <- dirname(sys.frame(1)$ofile %||% normalizePath("."))
RDS_DIR   <- file.path(BASE_DIR, "home_range_output", "individual_rds")
OUT_CSV   <- file.path(BASE_DIR, "../data", "home_range_analysis_report.csv")

`%||%` <- function(a, b) if (!is.null(a)) a else b

rds_files <- list.files(RDS_DIR, pattern = "^individual_\\d+\\.rds$", full.names = TRUE)
cat(sprintf("Found %d RDS files in %s\n", length(rds_files), RDS_DIR))

rows <- vector("list", length(rds_files))

for (i in seq_along(rds_files)) {
  f   <- rds_files[[i]]
  res <- tryCatch(readRDS(f), error = function(e) {
    cat(sprintf("  WARNING: could not read %s: %s\n", basename(f), e$message))
    NULL
  })

  if (is.null(res) || res$status != "success") {
    cat(sprintf("  SKIP: %s (status = %s)\n", basename(f),
                if (is.null(res)) "NULL" else res$status))
    next
  }

  rows[[i]] <- data.frame(
    id               = res$id,
    study_name       = res$study_name,
    sex              = res$sex,
    n_gps_points     = res$n_gps_points,
    trajectory_days  = as.numeric(res$trajectory_days),
    ctmm_model       = res$ctmm_model,
    area_95_km2      = res$area_95_km2,
    area_50_km2      = res$area_50_km2,
    n_core_areas     = res$n_core_areas,
    mcp_area_km2     = res$mcp_area_km2,
    is_range_shift   = res$is_range_shift,
    n_segments       = res$n_segments,
    stringsAsFactors = T
  )
}

rows <- Filter(Negate(is.null), rows)
cat(sprintf("Compiled %d successful individuals\n", length(rows)))

report <- do.call(rbind, rows)
report  <- report[order(report$id), ]

write.csv(report, OUT_CSV, row.names = FALSE)
cat(sprintf("Written: %s\n", OUT_CSV))
