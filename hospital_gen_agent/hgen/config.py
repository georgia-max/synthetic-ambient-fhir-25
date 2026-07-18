"""Shared configuration: absolute paths, model ids, and world constants."""
from pathlib import Path

# Absolute paths (config.py lives at <REPO>/hospital_gen_agent/hgen/config.py).
REPO = Path(__file__).resolve().parents[2]
HG = REPO / "hospital_gen_agent"
DATASET = REPO / "dataset" / "synthetic-ambient-fhir-25.jsonl"
STORAGE = HG / "storage"
WEB = HG / "web"

# LLM backend (Claude only).
MODEL_SONNET = "claude-sonnet-5"  # frequent, cheap cognition calls
MODEL_OPUS = "claude-opus-4-8"    # low-frequency, high-value reflection

# Time + world.
DATETIME_FMT = "%B %d, %Y, %H:%M:%S"
SEC_PER_STEP = 30
WORLD_NAME = "General Hospital"
MAZE_NAME = "hospital"
