## USAGE:
## Open Python Console in QGIS (usually Ctrl+Alt+P) and paste this in and run it

import os
from qgis.core import QgsProject, QgsProcessingFeedback
import processing

# --- CONFIGURATION ---
LAYER_NAME = "jaguar_movement_data"  # The name of your imported CSV layer
ID_FIELD = "individual.local.identifier (ID)"      # Column identifying each animal
OUTPUT_DIR = "/home/luveen/Dropbox/Documents/Luveen Wadhwani/OneDrive/OneDrive Documents/Luveen-Obsidian/03 - Projects/Columbia/00 - Thesis/MaxEnt_IRL_trajectory_interpolation/data/mcps/"  # Must end with a slash
# ---------------------

layer = QgsProject.instance().mapLayersByName(LAYER_NAME)[0]
feedback = QgsProcessingFeedback()

# Step 1: Find all unique individual IDs in your dataset
unique_ids = layer.uniqueValues(layer.fields().indexFromName(ID_FIELD))
print(f"Found {len(unique_ids)} individuals: {unique_ids}")

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# Step 2: Loop over individuals to split layers and generate 95% MCPs
for ind_id in unique_ids:
    print(f"Processing MCP for Individual: {ind_id}")
    
    # Clean the ID string for file path safety
    safe_id = str(ind_id).replace(" ", "_").replace("/", "-")
    
    # Filter out points for this specific individual
    filter_expr = f'"{ID_FIELD}" = \'{ind_id}\''
    
    # Extract only this individual's points
    extracted = processing.run("native:extractbyexpression", {
        'INPUT': layer,
        'EXPRESSION': filter_expr,
        'OUTPUT': 'TEMPORARY_OUTPUT'
    })['OUTPUT']
    
    # Run the modern Minimum Bounding Geometry tool configured to "Convex Hull"
    mcp_output = os.path.join(OUTPUT_DIR, f"mcp_95_{safe_id}.gpkg")
    processing.run("qgis:minimumboundinggeometry", {
        'INPUT': extracted,
        'FIELD': ID_FIELD,
        'TYPE': 3,  # 3 = Convex Hull geometry type
        'OUTPUT': mcp_output
    })
    
    # Load the completed polygon back directly into your QGIS canvas
    QgsProject.instance().addMapLayer(QgsVectorLayer(mcp_output, f"MCP_95_{safe_id}", "ogr"))

print("All MCPs generated successfully!")