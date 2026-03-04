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

# Canonical extension→kind mapping: single source of truth for both
# asset_extractor and guid_resolver.
ASSET_EXT_TO_KIND: dict[str, str] = {
    # Textures
    ".png": "texture", ".jpg": "texture", ".jpeg": "texture",
    ".tga": "texture", ".bmp": "texture", ".exr": "texture",
    ".hdr": "texture", ".psd": "texture",
    # Meshes
    ".fbx": "mesh", ".obj": "mesh", ".dae": "mesh", ".blend": "mesh",
    # Audio
    ".wav": "audio", ".mp3": "audio", ".ogg": "audio",
    # Materials / animations / shaders
    ".mat": "material",
    ".anim": "animation", ".controller": "animation",
    ".shader": "shader", ".cginc": "shader", ".hlsl": "shader",
    # Scene / prefab / script
    ".prefab": "prefab",
    ".unity": "scene",
    ".cs": "script",
    # Other
    ".asset": "unknown",
}

SUPPORTED_ASSET_EXTENSIONS: frozenset[str] = frozenset(ASSET_EXT_TO_KIND.keys())
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
EMIT_PACKAGES: bool = False                 # generate .rbxm per prefab
PACKAGES_SUBDIR: str = "packages"           # subdirectory under output_dir

# ---------------------------------------------------------------------------
# Roblox Open Cloud upload (portal upload)
# ---------------------------------------------------------------------------

ROBLOX_API_KEY: str = os.environ.get("ROBLOX_API_KEY", "")
ROBLOX_UNIVERSE_ID: int | None = None
ROBLOX_PLACE_ID: int | None = None
ROBLOX_CREATOR_ID: int | None = None       # user or group ID for asset ownership
ROBLOX_CREATOR_TYPE: str = "User"          # "User" or "Group"

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
