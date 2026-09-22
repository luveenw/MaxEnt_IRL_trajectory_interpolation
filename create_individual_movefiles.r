# Split the jaguar movement CSV into one file per individual, so each can be
# loaded as a separate, independently-toggleable layer in QGIS (Add Delimited
# Text Layer, using location.long / location.lat as the X/Y fields).

data <- read.csv("/home/luveen/Dropbox/Documents/Luveen Wadhwani/OneDrive/OneDrive Documents/Luveen-Obsidian/03 - Projects/Columbia/00 - Thesis/MaxEnt_IRL_trajectory_interpolation/jaguar_movement_data.csv")

# read.csv() mangles "individual.local.identifier (ID)" into
# "individual.local.identifier..ID." via make.names().
names(data)[names(data) == "individual.local.identifier..ID."] <- "individual.local.identifier"

output_dir <- "/home/luveen/Dropbox/Documents/Luveen Wadhwani/OneDrive/OneDrive Documents/Luveen-Obsidian/03 - Projects/Columbia/00 - Thesis/MaxEnt_IRL_trajectory_interpolation/data/individual_tracks/"

if (!dir.exists(output_dir)) {
  dir.create(output_dir, recursive = TRUE)
}

individual_ids <- sort(unique(as.character(data$individual.local.identifier)))

for (i in seq_along(individual_ids)) {
  ind_id <- individual_ids[i]
  cat(sprintf("[%d/%d] Writing individual %s...\n", i, length(individual_ids), ind_id))
  
  ind_data <- data[as.character(data$individual.local.identifier) == ind_id, ]
  
  out_path <- file.path(output_dir, paste0("individual_", ind_id, ".csv"))
  write.csv(ind_data, out_path, row.names = FALSE)
}

cat(sprintf("Done. Wrote %d individual files to %s\n", length(individual_ids), output_dir))