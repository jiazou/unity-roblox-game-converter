"""
config.py — Global configuration for the Unity → Roblox converter.

Holds file paths, API keys, feature flags, and tunable options.
All modules read from this file; none of them modify it.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

UNITY_PROJECT_PATH: Path = Path(os.environ.get("UNITY_PROJECT_PATH", "./unity_project"))
OUTPUT_DIR: Path = Path(os.environ.get("OUTPUT_DIR", "./output"))
TEMP_DIR: Path = Path(os.environ.get("TEMP_DIR", "./tmp"))

# ---------------------------------------------------------------------------
# Anthropic (Claude) API
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "sk-ant-PLACEHOLDER")
ANTHROPIC_MODEL: str = "claude-opus-4-5"
ANTHROPIC_MAX_TOKENS: int = 4096

# ---------------------------------------------------------------------------
# Asset extraction options
# ---------------------------------------------------------------------------

SUPPORTED_ASSET_EXTENSIONS: list[str] = [
    ".png", ".jpg", ".jpeg", ".tga", ".bmp",
    ".fbx", ".obj", ".dae",
    ".wav", ".mp3", ".ogg",
    ".mat",
    ".anim",
]
COPY_ASSETS: bool = True

# ---------------------------------------------------------------------------
# Scene / prefab parsing
# ---------------------------------------------------------------------------

UNITY_SCENE_EXT: str = ".unity"
UNITY_PREFAB_EXT: str = ".prefab"
MAX_SCENE_DEPTH: int = 64

# ---------------------------------------------------------------------------
# Code transpilation options
# ---------------------------------------------------------------------------

USE_AI_TRANSPILATION: bool = True
TRANSPILATION_CONFIDENCE_THRESHOLD: float = 0.7

# ---------------------------------------------------------------------------
# Roblox output options
# ---------------------------------------------------------------------------

RBXL_OUTPUT_FILENAME: str = "converted_place.rbxl"
ROBLOX_XML_NAMESPACE: str = "roblox.com"

# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

REPORT_FILENAME: str = "conversion_report.json"
REPORT_VERBOSE: bool = True

# ---------------------------------------------------------------------------
# Material mapper options
# ---------------------------------------------------------------------------

TEXTURE_MAX_RESOLUTION: int = 4096          # Roblox allows up to 4096x4096
TEXTURE_OUTPUT_FORMAT: str = "png"
GENERATE_UNIFORM_TEXTURES: bool = True    # 4x4 PNGs for scalar values
PRE_TILE_MAX_FACTOR: int = 4             # max tiling before logging to UNCONVERTED
FLIP_NORMAL_GREEN_CHANNEL: bool = False  # set True for DirectX-format normal maps
UNCONVERTED_FILENAME: str = "UNCONVERTED.md"
