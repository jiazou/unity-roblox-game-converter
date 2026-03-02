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
# LLM cache options
# ---------------------------------------------------------------------------

LLM_CACHE_ENABLED: bool = True
LLM_CACHE_DIR: Path = Path(os.environ.get("LLM_CACHE_DIR", ".cache/llm"))
LLM_CACHE_TTL_SECONDS: float = 7 * 24 * 3600  # 7 days

# ---------------------------------------------------------------------------
# Retry options (for LLM and Roblox API calls)
# ---------------------------------------------------------------------------

RETRY_MAX_ATTEMPTS: int = 4
RETRY_BASE_DELAY: float = 2.0
RETRY_MAX_DELAY: float = 60.0
RETRY_BACKOFF_FACTOR: float = 2.0

# ---------------------------------------------------------------------------
# Roblox output options
# ---------------------------------------------------------------------------

RBXL_OUTPUT_FILENAME: str = "converted_place.rbxl"
ROBLOX_XML_NAMESPACE: str = "roblox.com"

# ---------------------------------------------------------------------------
# Roblox Open Cloud upload (portal upload)
# ---------------------------------------------------------------------------

ROBLOX_API_KEY: str = os.environ.get("ROBLOX_API_KEY", "")
ROBLOX_UNIVERSE_ID: int | None = None
ROBLOX_PLACE_ID: int | None = None

# ---------------------------------------------------------------------------
# Mesh decimation (conservative defaults)
# ---------------------------------------------------------------------------

MESH_DECIMATION_ENABLED: bool = True
MESH_ROBLOX_MAX_FACES: int = 10_000        # hard MeshPart limit
MESH_TARGET_FACES: int = 8_000             # leave headroom below the cap
MESH_QUALITY_FLOOR: float = 0.6           # never reduce below 60% of original

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
