# -*- coding: utf-8 -*-
"""
Shared constants, biome mapping, and helper functions for EDA.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ------------------------------------------------------------------ #
#  Column names
# ------------------------------------------------------------------ #
COL_ID = "individual.local.identifier (ID)"
COL_TS = "timestamp"
COL_LON = "location.long"
COL_LAT = "location.lat"
COL_STUDY = "study.name"
COL_COUNTRY = "country"
COL_BIOME = "biome"

# ------------------------------------------------------------------ #
#  Coordinate helpers
# ------------------------------------------------------------------ #
M_PER_DEG_LAT = 111_320.0
M_PER_DEG_LON_EQUATOR = 111_320.0


def m_per_deg_lon(lat_deg: float) -> float:
    return M_PER_DEG_LON_EQUATOR * np.cos(np.radians(lat_deg))


def step_lengths_m(lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    """Compute step lengths in metres from lon/lat arrays."""
    dlat = np.diff(lats) * M_PER_DEG_LAT
    dlon = np.diff(lons) * np.array([m_per_deg_lon(lat) for lat in lats[:-1]])
    return np.sqrt(dlat**2 + dlon**2)


def turning_angles(lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    """Compute turning angles in radians from lon/lat arrays."""
    dx = np.diff(lons)
    dy = np.diff(lats)
    bearings = np.arctan2(dx, dy)
    return np.diff(bearings)


# ------------------------------------------------------------------ #
#  Biome assignment
# ------------------------------------------------------------------ #
# Compound key: (study_name, country) -> biome
# Based on Morato et al. (2018), Morato et al. (2021), Movebank metadata
STUDY_BIOME_MAP: dict[tuple[str, str], str] = {
    ("Panthera_Pantanal-Jaguar-Project", "Brazil"): "Pantanal",
    ("Jaguar_Taiama", "Brazil"): "Pantanal",
    ("jaguar_Oncafari Project", "Brazil"): "Pantanal",
    ("Sao Bento", "Brazil"): "Pantanal",
    ("Pantanal", "Paraguay"): "Pantanal",
    ("Paraguayan Pantanal", "Paraguay"): "Pantanal",
    ("Jaguar Conservation in the Atlantic Forest", "Brazil"): "Atlantic Forest",
    ("Jaguars' Movement Pattern in a fragmente landscape", "Brazil"): "Atlantic Forest",
    ("IOP", "Brazil"): "Atlantic Forest",
    ("Atlantic forest", "Paraguay"): "Atlantic Forest",
    ("Jaguar Conservation in the Caatinga Biome", "Brazil"): "Caatinga",
    ("Humid Chaco", "Paraguay"): "Chaco",
    ("Dry Chaco", "Paraguay"): "Chaco",
    ("Jaguar Conservation in Argentina", "Argentina"): "Chaco",
    ("Jaguar Conservation in Argentina", "Brazil"): "Atlantic Forest",
    ("Rio Negro", "Brazil"): "Amazon/Transition",
    ("Jaguar_Mamiraua", "Brazil"): "Amazon/Transition",
    ("Costa Rica", "Costa Rica"): "Mesoamerican Forest",
    ("Greater Lacandona Ecosystem", "Mexico"): "Mesoamerican Forest",
    ("Jaguar Mex", "Mexico"): "Mesoamerican Forest",
    ("jaguar of sonora", "Mexico"): "Mesoamerican Forest",
}

# Canonical order for plotting
BIOME_ORDER = [
    "Pantanal", "Atlantic Forest", "Chaco",
    "Amazon/Transition", "Mesoamerican Forest", "Caatinga",
]

BIOME_COLORS = {
    "Pantanal": "#1E88E5",
    "Atlantic Forest": "#43A047",
    "Chaco": "#FB8C00",
    "Amazon/Transition": "#8E24AA",
    "Mesoamerican Forest": "#E53935",
    "Caatinga": "#FDD835",
}


def assign_biome(df: pd.DataFrame) -> pd.DataFrame:
    """Add a 'biome' column using the study-country compound key."""
    df[COL_BIOME] = df.apply(
        lambda row: STUDY_BIOME_MAP.get(
            (row[COL_STUDY], row[COL_COUNTRY]), "Unknown"
        ), axis=1,
    )
    return df


def load_data(csv_path: str) -> pd.DataFrame:
    """Load, parse, and add biome column to the jaguar CSV."""
    df = pd.read_csv(csv_path, low_memory=False, dtype={"tag.local.identifier": str})
    df.columns = df.columns.str.strip()
    df[COL_TS] = pd.to_datetime(df[COL_TS], format="mixed", dayfirst=False)
    df[COL_LON] = pd.to_numeric(df[COL_LON], errors="coerce")
    df[COL_LAT] = pd.to_numeric(df[COL_LAT], errors="coerce")
    df = df.dropna(subset=[COL_LON, COL_LAT, COL_TS])
    df = df.sort_values([COL_ID, COL_TS]).reset_index(drop=True)
    df = assign_biome(df)
    return df
