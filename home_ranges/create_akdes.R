library(ctmm)
library(sf)

# Load your exported CSV telemetry dataset
data <- read.csv("/home/luveen/Dropbox/Documents/Luveen Wadhwani/OneDrive/OneDrive Documents/Luveen-Obsidian/03 - Projects/Columbia/00 - Thesis/MaxEnt_IRL_trajectory_interpolation/jaguar_movement_data.csv")

# read.csv() mangles "individual.local.identifier (ID)" into
# "individual.local.identifier..ID." via make.names(). Rename it to match what
# as.telemetry() recognizes.
names(data)[names(data) == "individual.local.identifier..ID."] <- "individual.local.identifier"

# Some individuals' rows are concatenated out of chronological order in the
# source file (e.g. a later re-collaring's older data appearing after a newer
# tag's data) -- this caused "Times might be out of order" warnings. Sort by
# individual and timestamp before conversion. Confirm this format string
# ("M/D/YY H:MM") matches the whole file, not just the sample checked here.
data$.sort_time <- as.POSIXct(data$timestamp, format = "%m/%d/%y %H:%M", tz = "UTC")
data <- data[order(data$individual.local.identifier, data$.sort_time), ]
data$.sort_time <- NULL

# as.telemetry() prefers individual.local.identifier over tag.local.identifier
# when both are present, so it already splits/merges by individual -- a
# re-collared individual's rows from both tags land in the same telemetry
# object. No tag-to-individual lookup or tbind() merge step needed for
# BUILDING the telemetry objects themselves.
telemetry.data <- as.telemetry(data)

# We DO still want the tag ID(s) behind each individual for the shapefile
# attributes (some individuals have 1 tag, some -- re-collared -- have 2).
# Build a lookup: individual.local.identifier -> collapsed tag ID string.
tag_lookup <- tapply(
  as.character(data$tag.local.identifier),
  as.character(data$individual.local.identifier),
  function(x) paste(sort(unique(x)), collapse = "; ")
)

# Directory to save calculated shapes
output_dir <- "/home/luveen/Dropbox/Documents/Luveen Wadhwani/OneDrive/OneDrive Documents/Luveen-Obsidian/03 - Projects/Columbia/00 - Thesis/MaxEnt_IRL_trajectory_interpolation/data/akdes/"

individual_ids <- names(telemetry.data)

# Process each individual dynamically
create_akdes = function() {
  # st_write() does not create missing directories -- do it explicitly, or every
  # write fails with "No such file or directory".
  if (!dir.exists(output_dir)) {
    dir.create(output_dir, recursive = TRUE)
  }

  for (i in seq_along(individual_ids)) {
    name <- individual_ids[i]
    cat(sprintf("[%d/%d] Processing individual %s...\n", i, length(individual_ids), name))
    
    ind_data <- telemetry.data[[name]]
    
    # 1. Automatically fit the best movement model (accounting for autocorrelation)
    GUESS <- ctmm.guess(ind_data, interactive = FALSE)
    FIT <- ctmm.select(ind_data, GUESS, trace = FALSE)
    
    # 2. Calculate the Autocorrelated Kernel Density Estimate
    UD_akde <- akde(ind_data, FIT)
    
    # 3. Extract the 95% Utilization Distribution contour directly as an sf object.
    # (SpatialPolygonsDataFrame() is a plain sp constructor, not a generic, so it
    # does NOT dispatch to ctmm's SpatialPolygonsDataFrame.UD() method -- as.sf()
    # is the documented, correct way to get UD contours out as sf polygons.)
    sf_contour <- as.sf(UD_akde, level.UD = 0.95)
    
    # Explicitly transform the contour to the CRS used by the underlying data
    sf_contour <- st_transform(sf_contour, crs = 4326)

        # Attach individual and tag identifiers for grouping/filtering in QGIS
    sf_contour$individual_id <- name
    sf_contour$tag_ids <- tag_lookup[[name]]
    
    # 4. Export as a Shapefile to display seamlessly inside QGIS
    st_write(sf_contour, paste0(output_dir, "akde_95_", name, ".shp"))
  }
}

create_akdes()