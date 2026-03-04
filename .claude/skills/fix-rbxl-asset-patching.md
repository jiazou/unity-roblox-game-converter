# Skill: Fix RBXL Asset ID Patching

## Goal

Replace the fragile `str.replace()` calls in `modules/roblox_uploader.py`
with XML-aware replacement so that asset URL patching does not corrupt
embedded Luau scripts or XML comments.

## Context

After uploading assets to Roblox Cloud, `_patch_rbxl_asset_ids()` rewrites
placeholder `rbxassetid://` URLs in the `.rbxl` file with real asset IDs.
It currently reads the file as raw text and calls `str.replace()`, which
replaces ALL occurrences — including inside `<ProtectedString>` elements
that contain Luau source code.

## Fixes Required

### 1. Parse the RBXL as XML, replace only in URL properties

**File**: `roblox_uploader.py:311-321`
**Current**: `content.replace(f"rbxassetid://{local_name}", rbx_url)`
**Fix**: Parse the `.rbxl` with `xml.etree.ElementTree`.  Walk elements and
only replace `rbxassetid://` URLs in `<url>` and `<Content>` elements (these
are the Roblox property types that hold asset references).  Do NOT touch
`<ProtectedString>` elements (script source) or `<string>` elements.

### 2. Distinguish HTTP error codes in upload failures

**File**: `roblox_uploader.py:389-449`
**Current**: All exceptions caught as generic `Exception`, HTTP codes lost.
**Fix**: Catch `urllib.error.HTTPError` separately, log the `.code` and
`.reason`, and distinguish 401 (auth), 403 (permission), 429 (rate limit)
from 500 (server error) for better error messages.

## Verification

```bash
python -m pytest tests/test_roblox_uploader.py tests/test_roblox_uploader_detailed.py -v
```

Add tests for:
- RBXL with a Luau script containing `rbxassetid://texture_name` as a string
  literal — should NOT be patched
- RBXL with a Content property containing `rbxassetid://texture_name` — should
  be patched
- Normal patching behavior unchanged

## References

- `.rbxl` XML schema: Content/url elements hold asset references
- `docs/FRAGILITY_AUDIT.md` — P1b section
