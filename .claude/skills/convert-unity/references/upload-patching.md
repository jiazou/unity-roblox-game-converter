# Upload Patching Details

## Assembly Phase Internals

The assembly phase:
- Converts scene nodes to Roblox Parts/MeshParts
- Generates prefab packages and embeds them in ReplicatedStorage/Templates (enabled by default). This is critical for runtime-driven games where environment content (tracks, obstacles, pickups) is spawned by code rather than placed in the scene. Without this, only the scene's static objects (UI, camera, sky) would be included.
- Builds a `mesh_texture_map` linking mesh IDs to texture filenames for the upload patcher

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
replacement.Parent = placeholder.Parent
placeholder:Destroy()
```

This applies to both scene objects (placed in Workspace at conversion time) and prefab templates (stored in ReplicatedStorage for runtime spawning). Any MeshPart that needs a visible mesh must ultimately be a clone of a MeshPart loaded via InsertService.

## Upload Patching Strategies

The upload command handles everything automatically:
1. Uploads textures, sprites, and audio (polls async operations for asset IDs)
2. Patches the .rbxl with `rbxassetid://` URLs using four strategies:
   - Replaces `rbxassetid://` placeholders and `-- TODO: upload` comments
   - Replaces local filesystem paths by matching filenames
   - Replaces bare texture filenames in SurfaceAppearance ColorMap values (e.g. `BrickWall_color.png` → `rbxassetid://12345`)
   - Injects new SurfaceAppearance on MeshParts by scanning Unity project for mesh→material relationships
3. Converts XML to binary .rbxl format
4. Uploads the place file

## Structured Error Types

- `"error_type": "place_not_published"` — the user must open Roblox Studio, open the place, and publish an initial version before the API can accept uploads.
