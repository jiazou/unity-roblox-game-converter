"""
bridge_injector.py — Detect which Unity bridge modules are needed by transpiled
Luau scripts and inject them into the transpilation result.

Scans transpiled Luau source for ``require()`` calls and API usage patterns
that indicate a bridge module dependency.  Returns the set of bridge module
filenames that should be included in the .rbxl output.

No other pipeline module is imported here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Bridge module registry
# ---------------------------------------------------------------------------

# Each entry maps a bridge module filename to the patterns that indicate it's
# needed.  Patterns are checked against the transpiled Luau source of each
# script.  Both explicit require() calls and direct API usage are detected.

_BRIDGE_DIR = Path(__file__).resolve().parent.parent / "bridge"


@dataclass
class _BridgeSpec:
    """Describes how to detect that a bridge module is needed."""
    filename: str                # e.g. "Input.lua"
    module_name: str             # e.g. "Input" — the require target name
    # Regex patterns that, if found in Luau source, indicate this bridge is
    # needed.  Compiled at module load time for speed.
    patterns: list[re.Pattern[str]]


def _p(*args: str) -> list[re.Pattern[str]]:
    """Compile one or more regex patterns."""
    return [re.compile(p) for p in args]


# The bridge specs for the 6 modules that can be auto-detected.
# AnimatorBridge and TransformAnimator are already handled by
# animation_converter.py and are excluded here.
BRIDGE_SPECS: list[_BridgeSpec] = [
    _BridgeSpec(
        filename="Input.lua",
        module_name="Input",
        patterns=_p(
            r"""require\s*\(.*["']Input["']""",
            r"""\bInput\.GetKey(?:Down|Up)?\s*\(""",
            r"""\bInput\.GetAxis\s*\(""",
            r"""\bInput\.GetSwipe\s*\(""",
        ),
    ),
    _BridgeSpec(
        filename="Time.lua",
        module_name="Time",
        patterns=_p(
            r"""require\s*\(.*["']Time["']""",
            r"""\bTime\.deltaTime\b""",
            r"""\bTime\.time\b""",
            r"""\bTime\.timeScale\b""",
            r"""\bTime\.fixedDeltaTime\b""",
        ),
    ),
    _BridgeSpec(
        filename="Coroutine.lua",
        module_name="Coroutine",
        patterns=_p(
            r"""require\s*\(.*["']Coroutine["']""",
            r"""\bCoroutine\.Start\s*\(""",
            r"""\bCoroutine\.WaitForSeconds\s*\(""",
            r"""\bCoroutine\.WaitForEndOfFrame\s*\(""",
            r"""\bCoroutine\.Yield\s*\(""",
        ),
    ),
    _BridgeSpec(
        filename="Physics.lua",
        module_name="Physics",
        patterns=_p(
            r"""require\s*\(.*["']Physics["']""",
            r"""\bPhysics\.Raycast\s*\(""",
            r"""\bPhysics\.CheckSphere\s*\(""",
            r"""\bPhysics\.OverlapSphere\s*\(""",
        ),
    ),
    _BridgeSpec(
        filename="MonoBehaviour.lua",
        module_name="MonoBehaviour",
        patterns=_p(
            r"""require\s*\(.*["']MonoBehaviour["']""",
            r"""\bMonoBehaviour\.new\s*\(""",
        ),
    ),
    _BridgeSpec(
        filename="GameObjectUtil.lua",
        module_name="GameObjectUtil",
        patterns=_p(
            r"""require\s*\(.*["']GameObjectUtil["']""",
            r"""\bGameObjectUtil\.Instantiate(?:FromAsset)?\s*\(""",
            r"""\bGameObjectUtil\.Destroy\s*\(""",
            r"""\bGameObjectUtil\.Find(?:WithTag)?\s*\(""",
            r"""\bGameObjectUtil\.SetActive\s*\(""",
        ),
    ),
    _BridgeSpec(
        filename="StateMachine.lua",
        module_name="StateMachine",
        patterns=_p(
            r"""require\s*\(.*["']StateMachine["']""",
            r"""\bStateMachine\.new\s*\(""",
        ),
    ),
]


# ---------------------------------------------------------------------------
# Detection API
# ---------------------------------------------------------------------------

@dataclass
class BridgeInjectionResult:
    """Result of scanning scripts for bridge dependencies."""
    needed: list[str] = field(default_factory=list)     # filenames to inject
    already_present: list[str] = field(default_factory=list)  # already in scripts


def detect_needed_bridges(
    luau_sources: list[str],
    existing_script_names: set[str] | None = None,
) -> BridgeInjectionResult:
    """Scan transpiled Luau source code for bridge module dependencies.

    Args:
        luau_sources: List of Luau source code strings to scan.
        existing_script_names: Set of script filenames already in the
            transpilation result (to avoid duplicates).

    Returns:
        BridgeInjectionResult with the list of bridge filenames to inject.
    """
    existing = existing_script_names or set()
    result = BridgeInjectionResult()

    for spec in BRIDGE_SPECS:
        if spec.filename in existing:
            result.already_present.append(spec.filename)
            continue

        needed = False
        for source in luau_sources:
            for pattern in spec.patterns:
                if pattern.search(source):
                    needed = True
                    break
            if needed:
                break

        if needed:
            result.needed.append(spec.filename)

    return result


def inject_bridges(
    needed_filenames: list[str],
    bridge_dir: Path | None = None,
) -> list[tuple[str, str]]:
    """Read bridge module files and return (filename, source) pairs.

    Args:
        needed_filenames: List of bridge filenames to load (e.g. ["Input.lua"]).
        bridge_dir: Directory containing bridge modules. Defaults to
            the ``bridge/`` directory next to this package.

    Returns:
        List of (filename, luau_source) tuples for each bridge module found.
    """
    bdir = bridge_dir or _BRIDGE_DIR
    result: list[tuple[str, str]] = []

    for filename in needed_filenames:
        path = bdir / filename
        if path.exists():
            result.append((filename, path.read_text(encoding="utf-8")))

    return result
