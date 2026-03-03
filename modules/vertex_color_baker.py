"""
vertex_color_baker.py — Bakes mesh vertex colors into albedo textures.

Roblox's SurfaceAppearance ignores vertex colors stored in mesh data.
Many Unity games (especially mobile) rely heavily on vertex-color
multiplication to add variation without extra texture lookups.

This module:
  1. Loads a mesh file (OBJ, PLY, GLTF/GLB — FBX when trimesh supports it)
  2. Extracts per-vertex RGBA colors and UV coordinates
  3. Rasterises vertex colors onto a UV-space texture
  4. Multiplies the rasterised colour map into the albedo texture

No other module is imported here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BakeResult:
    """Outcome of baking vertex colours for a single mesh."""
    mesh_path: Path
    output_path: Path | None = None
    baked: bool = False
    has_vertex_colors: bool = False
    error: str = ""


@dataclass
class VertexColorBakeResult:
    """Aggregate result for all meshes processed."""
    entries: list[BakeResult] = field(default_factory=list)
    total: int = 0
    baked: int = 0
    skipped: int = 0
    no_colors: int = 0
    warnings: list[str] = field(default_factory=list)


def _load_mesh_vertex_data(
    mesh_path: Path,
) -> tuple[Any, Any, Any, Any] | None:
    """
    Load mesh and extract vertices, faces, UVs, and vertex colors.

    Returns (vertices, faces, uv_coords, vertex_colors) or None on failure.
    Each array is a numpy ndarray:
      - vertices: (N, 3) float
      - faces: (F, 3) int
      - uv_coords: (N, 2) float — per-vertex UV0
      - vertex_colors: (N, 4) uint8 — RGBA per vertex
    """
    try:
        import trimesh  # type: ignore
        import numpy as np
    except ImportError:
        return None

    try:
        mesh = trimesh.load(str(mesh_path), force="mesh", process=False)
    except Exception:
        return None

    vertices = mesh.vertices
    faces = mesh.faces

    # Extract vertex colors
    visual = mesh.visual
    if hasattr(visual, "kind") and visual.kind == "vertex":
        colors = visual.vertex_colors
        if colors is None or len(colors) == 0:
            return None
    elif hasattr(visual, "vertex_colors"):
        colors = visual.vertex_colors
        if colors is None or len(colors) == 0:
            return None
    else:
        return None

    # Ensure RGBA uint8
    colors = np.array(colors, dtype=np.uint8)
    if colors.ndim != 2 or colors.shape[1] < 3:
        return None
    if colors.shape[1] == 3:
        # Add alpha channel
        alpha = np.full((colors.shape[0], 1), 255, dtype=np.uint8)
        colors = np.hstack([colors, alpha])

    # Check if all vertex colors are white (255,255,255) — skip baking
    if np.all(colors[:, :3] >= 250):
        return None

    # Extract UVs
    uv = None
    if hasattr(visual, "uv") and visual.uv is not None:
        uv = np.array(visual.uv, dtype=np.float32)
    elif hasattr(mesh, "visual") and hasattr(mesh.visual, "uv"):
        uv = np.array(mesh.visual.uv, dtype=np.float32)

    if uv is None or len(uv) != len(vertices):
        # Try texture visual
        if hasattr(visual, "to_texture") and callable(visual.to_texture):
            try:
                tex_visual = visual.to_texture()
                if hasattr(tex_visual, "uv") and tex_visual.uv is not None:
                    uv = np.array(tex_visual.uv, dtype=np.float32)
            except Exception:
                pass

    if uv is None or len(uv) != len(vertices):
        return None

    return vertices, faces, uv, colors


def _rasterise_vertex_colors(
    faces: Any,
    uv_coords: Any,
    vertex_colors: Any,
    resolution: int = 512,
) -> Any:
    """
    Rasterise per-vertex colors onto a UV-space texture.

    For each triangle, fill the UV-space region with interpolated
    vertex colors using barycentric coordinates.

    Returns an (H, W, 4) uint8 RGBA numpy array.
    """
    import numpy as np

    tex = np.zeros((resolution, resolution, 4), dtype=np.float32)
    weight = np.zeros((resolution, resolution), dtype=np.float32)

    for face in faces:
        i0, i1, i2 = face
        uv0 = uv_coords[i0]
        uv1 = uv_coords[i1]
        uv2 = uv_coords[i2]
        c0 = vertex_colors[i0].astype(np.float32)
        c1 = vertex_colors[i1].astype(np.float32)
        c2 = vertex_colors[i2].astype(np.float32)

        # Convert UV to pixel coords.  Clamp to [0, 1] rather than using
        # modulo, because 1.0 % 1.0 == 0.0 which collapses edges.
        def _uv_to_px(u: float, v: float) -> tuple[float, float]:
            u = max(0.0, min(1.0, float(u)))
            v = max(0.0, min(1.0, float(v)))
            return (u * (resolution - 1), (1.0 - v) * (resolution - 1))

        px0 = _uv_to_px(uv0[0], uv0[1])
        px1 = _uv_to_px(uv1[0], uv1[1])
        px2 = _uv_to_px(uv2[0], uv2[1])

        # Bounding box of the triangle in pixel space
        min_x = max(0, int(min(px0[0], px1[0], px2[0])))
        max_x = min(resolution - 1, int(max(px0[0], px1[0], px2[0])) + 1)
        min_y = max(0, int(min(px0[1], px1[1], px2[1])))
        max_y = min(resolution - 1, int(max(px0[1], px1[1], px2[1])) + 1)

        # Precompute denominator for barycentric coordinates
        denom = (
            (px1[1] - px2[1]) * (px0[0] - px2[0])
            + (px2[0] - px1[0]) * (px0[1] - px2[1])
        )
        if abs(denom) < 1e-10:
            continue

        inv_denom = 1.0 / denom

        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                # Barycentric coordinates
                w0 = (
                    (px1[1] - px2[1]) * (x - px2[0])
                    + (px2[0] - px1[0]) * (y - px2[1])
                ) * inv_denom
                w1 = (
                    (px2[1] - px0[1]) * (x - px2[0])
                    + (px0[0] - px2[0]) * (y - px2[1])
                ) * inv_denom
                w2 = 1.0 - w0 - w1

                if w0 >= -0.01 and w1 >= -0.01 and w2 >= -0.01:
                    # Clamp weights
                    w0 = max(0.0, w0)
                    w1 = max(0.0, w1)
                    w2 = max(0.0, w2)
                    wsum = w0 + w1 + w2
                    if wsum > 0:
                        w0 /= wsum
                        w1 /= wsum
                        w2 /= wsum
                    color = c0 * w0 + c1 * w1 + c2 * w2
                    tex[y, x] += color
                    weight[y, x] += 1.0

    # Average where multiple triangles overlap
    mask = weight > 0
    for c in range(4):
        tex[..., c][mask] /= weight[mask]

    # Fill uncovered pixels with the average of all covered pixels.
    # This avoids a scipy dependency while still producing reasonable results.
    if not np.all(mask):
        if mask.any():
            avg_color = np.zeros(4, dtype=np.float32)
            for c in range(4):
                avg_color[c] = tex[..., c][mask].mean()
            for c in range(4):
                tex[..., c][~mask] = avg_color[c]
        else:
            # No pixels covered at all — fill with white
            tex[..., :3] = 255.0
            tex[..., 3] = 255.0

    return np.clip(tex, 0, 255).astype(np.uint8)


def bake_vertex_colors_into_albedo(
    mesh_path: Path,
    albedo_path: Path,
    output_path: Path,
    resolution: int | None = None,
) -> BakeResult:
    """
    Bake vertex colours from a mesh into an albedo texture.

    The vertex colours are rasterised onto UV space and multiplied
    into the albedo texture.  If the mesh has no vertex colours or
    they are all white, the albedo is left unchanged.

    Args:
        mesh_path: Path to the mesh file (OBJ, PLY, GLB, etc.)
        albedo_path: Path to the albedo texture to multiply into.
        output_path: Where to write the resulting texture.
        resolution: Resolution for the vertex colour raster.
            Defaults to the albedo texture's width.

    Returns:
        BakeResult with outcome details.
    """
    result = BakeResult(mesh_path=mesh_path)

    data = _load_mesh_vertex_data(mesh_path)
    if data is None:
        result.has_vertex_colors = False
        return result

    vertices, faces, uv_coords, vertex_colors = data
    result.has_vertex_colors = True

    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        result.error = "Pillow or numpy not installed"
        return result

    try:
        albedo = Image.open(albedo_path).convert("RGB")
    except Exception as exc:
        result.error = f"Failed to open albedo: {exc}"
        return result

    res = resolution or albedo.width
    vc_texture = _rasterise_vertex_colors(faces, uv_coords, vertex_colors, res)

    # Resize VC texture to match albedo
    vc_img = Image.fromarray(vc_texture[..., :3])  # drop alpha, use RGB
    if vc_img.size != albedo.size:
        vc_img = vc_img.resize(albedo.size, Image.LANCZOS)

    # Multiply: result = albedo * (vc / 255)
    alb_arr = np.array(albedo, dtype=np.float32)
    vc_arr = np.array(vc_img, dtype=np.float32) / 255.0
    baked = np.clip(alb_arr * vc_arr, 0, 255).astype(np.uint8)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(baked).save(output_path, "PNG")
    result.output_path = output_path
    result.baked = True
    return result


def bake_vertex_colors_batch(
    mesh_albedo_pairs: list[tuple[Path, Path]],
    output_dir: Path,
    resolution: int | None = None,
) -> VertexColorBakeResult:
    """
    Batch-bake vertex colours for multiple mesh/albedo pairs.

    Args:
        mesh_albedo_pairs: List of (mesh_path, albedo_path) tuples.
        output_dir: Directory for output textures.
        resolution: Optional resolution override.

    Returns:
        VertexColorBakeResult with per-mesh outcomes.
    """
    result = VertexColorBakeResult()

    for mesh_path, albedo_path in mesh_albedo_pairs:
        result.total += 1
        out_name = f"{mesh_path.stem}_vc_baked.png"
        out_path = output_dir / out_name

        entry = bake_vertex_colors_into_albedo(
            mesh_path, albedo_path, out_path, resolution,
        )
        result.entries.append(entry)

        if entry.baked:
            result.baked += 1
        elif not entry.has_vertex_colors:
            result.no_colors += 1
        else:
            result.skipped += 1
            if entry.error:
                result.warnings.append(f"{mesh_path.name}: {entry.error}")

    return result
