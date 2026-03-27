# Upload Patching Details

## Assembly Phase Internals

The assembly phase:
- Converts scene nodes to Roblox Parts/MeshParts
- Generates prefab packages and embeds them in ReplicatedStorage/Templates (enabled by default). This is critical for runtime-driven games where environment content (tracks, obstacles, pickups) is spawned by code rather than placed in the scene. Without this, only the scene's static objects (UI, camera, sky) would be included.
- Builds a `mesh_texture_map` linking mesh IDs to texture filenames for the upload patcher
- **Vertex-color fallback**: For MeshParts with no texture and no material color, extracts the average vertex color from the FBX binary and sets `Color3`. Many stylized Unity assets (roads, buildings, sky, poles) use per-vertex colors instead of textures. Roblox ignores vertex colors, so this flat-color approximation prevents them from rendering as default gray. Implemented in `conversion_helpers.py:extract_fbx_dominant_color()`.

### Local-to-World Transform Computation (Critical)

Unity stores all transforms as **local-space** (relative to parent). Roblox Parts use **world-space CFrame** (absolute position and orientation). The converter MUST compute world transforms when flattening Unity's hierarchy into Roblox Parts.

The formula applied recursively through the scene tree:
```
world_position = parent_world_position + parent_world_rotation * local_position
world_rotation = parent_world_rotation * local_rotation
```

Without this, every child object ends up at its local offset from the world origin (0,0,0) instead of from its parent — causing all nested objects to collapse to the origin. This is implemented in `conversion_helpers.py` via `_compute_world_transform()`, `_quat_multiply()`, and `_quat_rotate()`, with parent transforms passed recursively through `node_to_part()`.

Root-level scene nodes use the default parent of position=(0,0,0) and identity rotation=(0,0,0,1).

### Content Property XML Format

Roblox .rbxl XML requires Content-type properties (MeshId, TextureId, SoundId, ColorMap) to use a `<url>` sub-element:
```xml
<Content name="MeshId">
  <url>rbxassetid://12345</url>
</Content>
```
Writing the value directly as text content (`<Content name="MeshId">rbxassetid://12345</Content>`) causes Roblox Studio to ignore the value, resulting in missing textures/meshes.

### Mesh Loading at Runtime (Critical Platform Constraint)

**`MeshId` is read-only at runtime.** Roblox does not allow scripts to set the `MeshId` property on a MeshPart — attempting it produces `"The current thread cannot write 'MeshId' (lacking capability NotAccessible)"`. This means you **cannot** create an empty MeshPart in the .rbxl and fill in its MeshId later from a script.

**How mesh assets work in Roblox:**
- FBX files uploaded via Open Cloud become **Model assets** (not raw meshes)
- `InsertService:LoadAsset(assetId)` returns a Model containing MeshParts with their MeshId already set
- To get a mesh into the scene at runtime, you must **clone** the MeshPart from the loaded Model

**The MeshLoader pattern:**
1. Upload FBX files as Model assets → get asset IDs
2. At runtime, `InsertService:LoadAsset()` each asset → extract the first MeshPart descendant
3. Store the extracted MeshPart in ServerStorage as a template
4. For scene placement: **clone the template and replace** placeholder Parts, copying CFrame/Name/Parent from the placeholder. Do NOT try to set MeshId on existing parts.

```lua
-- WRONG: MeshId is read-only at runtime
part.MeshId = sourceMeshPart.MeshId  -- ERROR: NotAccessible

-- RIGHT: Clone the loaded MeshPart and replace the placeholder
local replacement = sourceMeshPart:Clone()
replacement.Name = placeholder.Name
replacement.CFrame = placeholder.CFrame
replacement.Anchored = true
-- Transfer children (SurfaceAppearance, etc.) from placeholder to clone
for _, child in ipairs(placeholder:GetChildren()) do
    child.Parent = replacement
end
replacement.Parent = placeholder.Parent
placeholder:Destroy()
```

**Critical details:**
- **Scan both Workspace AND ReplicatedStorage.** Scene objects live in Workspace, but prefab templates for runtime spawning live in ReplicatedStorage/Templates. If the MeshLoader only scans Workspace, all runtime-cloned content will have placeholder geometry instead of real meshes.
- **Transfer children from placeholder to clone.** The `.rbxl` stores SurfaceAppearance (texture references) as children of placeholder MeshParts. InsertService-loaded meshes have geometry but no SurfaceAppearance. Before destroying the placeholder, reparent all its children to the replacement. Without this, meshes render as untextured default-colored shapes.
- **Batch InsertService calls.** Firing all `InsertService:LoadAsset()` calls simultaneously overwhelms Roblox's asset servers, causing `SslConnectFail` on most requests. Load in batches of ~10 with retries (3 attempts, increasing delay).

### Asset Type for Texture Uploads

Roblox Open Cloud distinguishes between `Decal` and `Image` asset types. **SurfaceAppearance properties (ColorMap, NormalMap, MetalnessMap, RoughnessMap) require `Image` assets.** Uploading a texture as `Decal` and using the asset ID in a SurfaceAppearance produces: `Error: Asset type does not match requested type`. Use `Decal` only for UI sprites and legacy Decal instances.

### Binary Serialization of Content Properties

The XML→binary conversion (`rbxl_binary_writer.py`) must read Content property values from the `<url>` child element, not from `el.text`. When the XML uses the correct `<Content><url>value</url></Content>` format, `el.text` is `None` — the value lives in the child. If the binary writer reads `el.text` directly, all Content properties (MeshId, ColorMap, SoundId) are written as empty strings, producing a binary file with no asset references despite the XML being correct.

### Creator ID Extraction

The Roblox Open Cloud Assets API requires a valid `creator.userId` in the upload request. This must match the API key's owner. The uploader auto-extracts the owner ID from the API key's JWT payload (`ownerID` claim). Using a wrong or stale creator ID produces `404: Creator User XXXXX is not found` on every asset upload.

## Upload Patching Strategies

The upload command handles everything automatically:
1. Uploads textures as `Image` assets and sprites as `Decal` assets (polls async operations for asset IDs)
2. Patches the .rbxl with `rbxassetid://` URLs using four strategies:
   - Replaces `rbxassetid://` placeholders and `-- TODO: upload` comments
   - Replaces local filesystem paths by matching filenames
   - Replaces bare texture filenames in SurfaceAppearance ColorMap values (e.g. `BrickWall_color.png` → `rbxassetid://12345`)
   - Injects new SurfaceAppearance on MeshParts by scanning Unity project for mesh→material relationships
3. Converts XML to binary .rbxl format
4. Uploads the place file

## Structured Error Types

- `"error_type": "place_not_published"` — the user must open Roblox Studio, open the place, and publish an initial version before the API can accept uploads.
