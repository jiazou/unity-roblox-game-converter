# Upload Patching Details

## Assembly Phase Internals

The assembly phase:
- Converts scene nodes to Roblox Parts/MeshParts
- Generates prefab packages and embeds them in ServerStorage (enabled by default). This is critical for runtime-driven games where environment content (tracks, obstacles, pickups) is spawned by code rather than placed in the scene. Without this, only the scene's static objects (UI, camera, sky) would be included.
- Builds a `mesh_texture_map` linking mesh IDs to texture filenames for the upload patcher

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
