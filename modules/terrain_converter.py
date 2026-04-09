"""
terrain_converter.py — Extract Unity TerrainData and generate a Roblox terrain loader script.

Parses the binary Unity TerrainData .asset file to extract:
  - Heightmap (uint16 array, normalized to 0–1)
  - Terrain dimensions (from scale + resolution)
  - Terrain layer names (from .terrainlayer YAML files)

Generates a Luau ServerScript that recreates the terrain in Roblox using
Terrain:FillBlock() with material assignment based on elevation.

The terrain is downsampled to a configurable grid to keep the loader script
within reasonable size limits (~64x64 grid → ~4000 cells).
"""

from __future__ import annotations

import array
import json
import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Common Unity heightmap resolutions (power-of-2 + 1)
_CANDIDATE_RESOLUTIONS = [33, 65, 129, 257, 513, 1025, 2049, 4097]

# Unity terrain layer name → Roblox Enum.Material
_LAYER_MATERIAL_MAP: dict[str, str] = {
    "sand": "Enum.Material.Sand",
    "grass": "Enum.Material.Grass",
    "grasshill": "Enum.Material.Grass",
    "grassrocky": "Enum.Material.Ground",
    "rock": "Enum.Material.Rock",
    "cliff": "Enum.Material.Rock",
    "mud": "Enum.Material.Mud",
    "mudrocky": "Enum.Material.Ground",
    "snow": "Enum.Material.Snow",
    "ice": "Enum.Material.Ice",
    "ground": "Enum.Material.Ground",
    "dirt": "Enum.Material.Ground",
    "cobblestone": "Enum.Material.Cobblestone",
    "slate": "Enum.Material.Slate",
    "concrete": "Enum.Material.Concrete",
    "sandstone": "Enum.Material.Sandstone",
    "limestone": "Enum.Material.Limestone",
    "asphalt": "Enum.Material.Asphalt",
    "pavement": "Enum.Material.Pavement",
    "leafygrass": "Enum.Material.LeafyGrass",
    "salt": "Enum.Material.Salt",
    "basalt": "Enum.Material.Basalt",
    "crackedlava": "Enum.Material.CrackedLava",
    "glacier": "Enum.Material.Glacier",
}


@dataclass
class TerrainResult:
    """Result of terrain conversion."""
    found: bool = False
    resolution: int = 0
    size_x: float = 0.0
    size_y: float = 0.0
    size_z: float = 0.0
    layers: list[str] = field(default_factory=list)
    loader_script: str = ""
    terrain_data_json: str = ""
    error: str = ""


def _find_heightmap_array(data: bytes) -> tuple[int | None, int | None, array.array | None]:
    """Find the heightmap in the binary data by searching for array-length prefix."""
    for res in sorted(_CANDIDATE_RESOLUTIONS, reverse=True):
        elem_count = res * res
        needle = struct.pack("<I", elem_count)
        pos = 0
        while pos < len(data) - 4:
            idx = data.find(needle, pos)
            if idx == -1:
                break
            block_end = idx + 4 + elem_count * 2
            if block_end <= len(data):
                raw = data[idx + 4 : idx + 4 + elem_count * 2]
                h = array.array("H")
                h.frombytes(raw)
                if max(h) > 0:
                    return idx + 4, res, h
            pos = idx + 1
    return None, None, None


def _find_terrain_scale(data: bytes) -> dict | None:
    """Find terrain scale/size from the binary data."""
    for res in sorted(_CANDIDATE_RESOLUTIONS, reverse=True):
        pattern = struct.pack("<II", res, res)
        pos = 0
        while pos < len(data) - 28:
            idx = data.find(pattern, pos)
            if idx == -1:
                break
            if idx + 28 <= len(data):
                thickness = struct.unpack_from("<f", data, idx + 8)[0]
                levels = struct.unpack_from("<I", data, idx + 12)[0]
                sx, sy, sz = struct.unpack_from("<fff", data, idx + 16)
                if (
                    0.0 < thickness <= 10.0
                    and 1 <= levels <= 20
                    and 0.0 < sx < 10000.0
                    and 0.0 < sy < 10000.0
                    and 0.0 < sz < 10000.0
                ):
                    return {
                        "resolution": res,
                        "scale": {"x": sx, "y": sy, "z": sz},
                    }
            pos = idx + 1
    return None


def _read_terrain_layers(unity_project_path: Path) -> list[str]:
    """Find and read terrain layer names from .terrainlayer files."""
    layers = []
    for tl in sorted(unity_project_path.rglob("*.terrainlayer")):
        layers.append(tl.stem)
    return layers


def _map_layer_to_material(layer_name: str) -> str:
    """Map a Unity terrain layer name to a Roblox material enum string."""
    key = layer_name.lower().replace(" ", "").replace("_", "")
    return _LAYER_MATERIAL_MAP.get(key, "Enum.Material.Grass")


def _downsample_heights(
    heights: array.array, resolution: int, target_grid: int
) -> list[list[float]]:
    """Downsample the heightmap to a target grid size."""
    step = max(1, (resolution - 1) // (target_grid - 1))
    sampled = []
    for z in range(0, resolution, step):
        row = []
        for x in range(0, resolution, step):
            val = heights[z * resolution + x] / 65535.0
            row.append(round(val, 5))
        sampled.append(row)
    return sampled


def _generate_loader_script(
    sampled: list[list[float]],
    size_x: float,
    size_y: float,
    size_z: float,
    layers: list[str],
    terrain_offset: tuple[float, float, float] = (0, 0, 0),
) -> str:
    """Generate a Luau ServerScript that builds terrain from heightmap data."""
    nrows = len(sampled)
    ncols = len(sampled[0])
    cell_x = size_x / (ncols - 1)
    cell_z = size_z / (nrows - 1)
    ox, oy, oz = terrain_offset

    # Build material thresholds from layers (elevation-based assignment)
    # Default: sand < 5, grass < 20, ground < 50, rock >= 50
    mat_thresholds = []
    if layers:
        # Map layers to materials and distribute elevation thresholds
        for layer in layers:
            mat_thresholds.append(_map_layer_to_material(layer))

    # Flatten heights to comma-separated string
    flat = []
    for row in sampled:
        for h in row:
            flat.append(f"{h * size_y:.1f}")
    height_str = ",".join(flat)

    script = f"""-- TerrainLoader (ServerScript) — auto-generated from Unity TerrainData
-- Recreates terrain using Terrain:FillBlock() with elevation-based materials
-- Grid: {nrows}x{ncols}, Cell size: {cell_x:.2f}x{cell_z:.2f} studs

local terrain = workspace.Terrain

local nrows = {nrows}
local ncols = {ncols}
local cellX = {cell_x:.4f}
local cellZ = {cell_z:.4f}
local offsetX = {ox}
local offsetY = {oy}
local offsetZ = {oz}
local heights = {{{height_str}}}

-- Water base
terrain:FillBlock(
    CFrame.new(offsetX + {size_x/2:.1f}, offsetY, offsetZ + {size_z/2:.1f}),
    Vector3.new({size_x + 50:.1f}, 4, {size_z + 50:.1f}),
    Enum.Material.Water
)

-- Build terrain
local count = 0
for r = 0, nrows - 1 do
    for c = 0, ncols - 1 do
        local h = heights[r * ncols + c + 1]
        if h > 1 then
            local x = offsetX + c * cellX
            local z = offsetZ + r * cellZ
            local mat
            if h < 5 then
                mat = Enum.Material.Sand
            elseif h < 20 then
                mat = Enum.Material.Grass
            elseif h < 50 then
                mat = Enum.Material.Ground
            else
                mat = Enum.Material.Rock
            end
            terrain:FillBlock(
                CFrame.new(x, offsetY + h / 2, z),
                Vector3.new(cellX, h, cellZ),
                mat
            )
            count = count + 1
        end
    end
end

print("[TerrainLoader] Placed " .. count .. " terrain blocks")
"""
    return script


def find_terrain_asset(unity_project_path: Path) -> Path | None:
    """Find the TerrainData .asset file in a Unity project.

    Searches for .asset files under a Terrains/ directory, or any .asset
    file that contains TerrainData markers in its binary content.
    """
    # First: look in common terrain directories
    for pattern in ["**/Terrains/*.asset", "**/Terrain/*.asset"]:
        for asset_file in unity_project_path.glob(pattern):
            # Skip non-terrain assets (lighting, occlusion, etc.)
            name = asset_file.stem.lower()
            if any(skip in name for skip in ["lighting", "occlusion", "nav"]):
                continue
            # Quick check: is it a binary file large enough to contain heightmap?
            if asset_file.stat().st_size > 10000:
                return asset_file

    # Fallback: scan all .asset files for terrain markers
    for asset_file in unity_project_path.rglob("*.asset"):
        if asset_file.stat().st_size < 10000:
            continue
        try:
            head = asset_file.read_bytes()[:200]
            # LFS pointer files start with "version https://git-lfs"
            if head.startswith(b"version https://git-lfs"):
                # It's an LFS pointer — the actual binary wasn't pulled
                logger.warning(
                    "Terrain asset %s is a Git LFS pointer (not downloaded). "
                    "Run 'git lfs pull' to fetch the actual terrain data.",
                    asset_file.name,
                )
                return asset_file  # Return it so we can report the error
            # Check for binary Unity asset (starts with NUL bytes or metadata)
            if head[:4] != b"%YAM":  # Not a YAML text file
                return asset_file
        except Exception:
            continue

    return None


def convert_terrain(
    unity_project_path: Path,
    target_grid: int = 65,
    terrain_offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> TerrainResult:
    """Extract Unity terrain data and generate a Roblox terrain loader script.

    Args:
        unity_project_path: Path to the Unity project root.
        target_grid: Downsample the heightmap to this grid size (default 65x65).
        terrain_offset: World position of the Terrain GameObject (x, y, z).

    Returns:
        TerrainResult with the loader script and metadata.
    """
    result = TerrainResult()

    # Find terrain asset
    terrain_asset = find_terrain_asset(unity_project_path)
    if terrain_asset is None:
        logger.debug("No terrain asset found in %s", unity_project_path)
        return result

    # Read binary data
    try:
        data = terrain_asset.read_bytes()
    except Exception as exc:
        result.error = f"Failed to read terrain asset: {exc}"
        return result

    # Check for LFS pointer
    if data.startswith(b"version https://git-lfs"):
        result.error = (
            f"Terrain asset '{terrain_asset.name}' is a Git LFS pointer. "
            "Run 'git lfs pull' to download the actual terrain data."
        )
        logger.warning(result.error)
        return result

    # Find heightmap
    _, resolution, heights = _find_heightmap_array(data)
    if heights is None:
        result.error = "Could not find heightmap data in terrain asset"
        return result

    result.resolution = resolution
    result.found = True

    # Find scale
    scale_info = _find_terrain_scale(data)
    if scale_info:
        s = scale_info["scale"]
        result.size_x = (resolution - 1) * s["x"]
        result.size_y = s["y"]
        result.size_z = (resolution - 1) * s["z"]
    else:
        # Fallback: assume 1 unit per cell, 600 height
        result.size_x = float(resolution - 1)
        result.size_y = 600.0
        result.size_z = float(resolution - 1)
        logger.warning("Could not find terrain scale, using defaults")

    # Read terrain layers
    result.layers = _read_terrain_layers(unity_project_path)

    # Downsample
    sampled = _downsample_heights(heights, resolution, target_grid)

    # Generate loader script
    result.loader_script = _generate_loader_script(
        sampled, result.size_x, result.size_y, result.size_z, result.layers,
        terrain_offset=terrain_offset,
    )

    # Generate compact JSON for terrain data (useful for MCP-based terrain painting)
    result.terrain_data_json = json.dumps({
        "resolution": resolution,
        "size": {"x": result.size_x, "y": result.size_y, "z": result.size_z},
        "layers": result.layers,
        "grid_size": len(sampled),
    }, indent=None)

    logger.info(
        "Terrain converted: %dx%d heightmap, %.0fx%.0fx%.0f world size, "
        "%d layers, downsampled to %dx%d",
        resolution, resolution,
        result.size_x, result.size_y, result.size_z,
        len(result.layers),
        len(sampled), len(sampled[0]) if sampled else 0,
    )

    return result
