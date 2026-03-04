# Plan: Get Sprites and Audio Working in the .rbxl

## Problem Summary

Three major gaps prevent sprites and audio from working:

1. **UI classification bug**: All 282 UI elements become `Frame` — no `TextLabel`, `ImageLabel`, `TextButton`, etc. The `_detect_ui_class()` only checks `component_type` strings, but the scene parser classifies everything as `MonoBehaviour`.

2. **No sprite asset pipeline**: 5 sprite files (including a 54-sprite spritesheet) are referenced but never extracted, sliced, or included in the build. Even if classification were fixed, the `rbxassetid://<unity-guid>` URLs are invalid.

3. **Audio SoundId placeholders**: Sound XML is correct structurally but SoundId is `-- TODO: upload <path>`. Audio files exist on disk but aren't copied to the build output.

## Implementation Plan

### Phase 1: Fix UI element classification (ui_translator.py)

Update `_detect_ui_class()` to detect MonoBehaviour-based UI components using the same script GUID approach as `_is_image_component()`:

- `fe87c0e1cc204ed48ad3b37840f39efc` → Image → ImageLabel/ImageButton
- `5f7201a12d95ffc40944...` → Text → TextLabel
- Button GUID → detect and map to TextButton/ImageButton

Also update `_extract_text_properties()` and `_extract_image_properties()` to handle MonoBehaviour components (check script GUID, not just component_type string).

**Result**: UI elements get correct class names. Text shows up. Image elements identified.

### Phase 2: Sprite extraction — slicing the spritesheet (new: sprite_extractor)

Create a sprite extraction step that:

1. Reads the `.meta` files for sprite textures to get `spriteSheet.sprites[].rect` data
2. Uses PIL/Pillow to slice individual sprites from the atlas (UISpritesheet.png → 54 individual PNGs)
3. For single sprites (Logo.png, Unity.png), just copies them as-is
4. Outputs sliced sprites to `<build_dir>/sprites/` with names matching the sprite name from the meta
5. Builds a mapping: `(guid, fileID) → sprite_file_path`

**Result**: Individual sprite PNGs available in the build output.

### Phase 3: Wire sprite paths into the UI elements (ui_translator.py + rbxl_writer.py)

1. Pass the sprite mapping from Phase 2 into `translate_ui_hierarchy()`
2. In `_extract_image_properties()`, resolve `m_Sprite` guid+fileID to a local sprite file path using the mapping
3. In `_make_ui_element()` in rbxl_writer, write the sprite path as an `Image` Content property (local file reference for now — upload would be Phase 5)

**Result**: ImageLabel elements reference actual sprite files.

### Phase 4: Copy audio files to build output (conversion_helpers.py + rbxl_writer.py)

1. During the Processing phase, copy referenced audio files (.ogg/.wav/.mp3) to `<build_dir>/audio/`
2. Update `_make_sound()` in rbxl_writer to reference the local audio file path instead of `-- TODO: upload <path>`
3. Build a mapping: `audio_guid → copied_audio_path`

**Result**: Sound elements reference actual audio files in the build output.

### Phase 5 (Optional/Future): Upload assets and rewrite .rbxl

This requires a valid Roblox API key and involves:
1. Upload sprites via existing `_upload_image_asset()` (as Decal type)
2. Add `_upload_audio_asset()` (same API, `assetType: "Audio"`)
3. Add a post-upload rewriting step that replaces local file paths in the .rbxl XML with `rbxassetid://<id>` URLs
4. Re-upload the place file with the patched .rbxl

**This is the only phase that requires network access.** Phases 1-4 make the build output self-contained with local files that can be manually imported into Roblox Studio.

## Files Modified

- `modules/ui_translator.py` — Phases 1, 3
- `modules/rbxl_writer.py` — Phases 3, 4
- `modules/conversion_helpers.py` — Phase 4 (audio copy)
- New: sprite extraction logic (Phase 2) — either in `modules/asset_extractor.py` or a new `modules/sprite_extractor.py`
- `converter.py` / `convert_interactive.py` — wire new steps into pipeline

## Scope for this session

Phases 1-4 (everything except Roblox Cloud upload). This gets text rendering, sprite images as local files, and audio as local files all working in the .rbxl build output.
