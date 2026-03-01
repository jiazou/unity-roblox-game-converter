"""
code_transpiler.py — Transpiles Unity C# MonoBehaviour scripts to Roblox Luau.

Two strategies are available:
  1. AI-assisted (Claude via Anthropic API): Sends the full C# source to Claude
     and receives idiomatic Luau. Handles complex logic well but costs tokens.
  2. Rule-based: Applies regex/AST transformations for common patterns
     (variable declarations, basic control flow, Unity lifecycle hooks).
     Fast and free, but limited in coverage.

The chosen strategy is controlled by config.USE_AI_TRANSPILATION.
No other module is imported here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


TranspilationStrategy = Literal["ai", "rule_based", "skipped"]


@dataclass
class TranspiledScript:
    """Result of transpiling a single C# script."""
    source_path: Path              # Original .cs file
    output_filename: str           # Target filename (e.g. "PlayerController.lua")
    csharp_source: str             # Original C# source text
    luau_source: str               # Resulting Luau source text
    strategy: TranspilationStrategy
    confidence: float              # 0.0–1.0; <threshold → flagged for review
    warnings: list[str] = field(default_factory=list)
    flagged_for_review: bool = False


@dataclass
class TranspilationResult:
    """Aggregate result for all scripts in a Unity project."""
    scripts: list[TranspiledScript] = field(default_factory=list)
    total: int = 0
    succeeded: int = 0
    flagged: int = 0
    skipped: int = 0


# ---------------------------------------------------------------------------
# Rule-based transpilation helpers
# ---------------------------------------------------------------------------

_RULE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Variable declarations: int/float/bool/string → local
    (re.compile(r"\b(int|float|double|bool|string)\s+(\w+)\s*="), r"local \2 ="),
    # Debug.Log → print
    (re.compile(r"\bDebug\.Log\("), "print("),
    # void → (no return type in Luau)
    (re.compile(r"\bvoid\s+(\w+)\s*\("), r"local function \1("),
    # Unity lifecycle stubs
    (re.compile(r"\bStart\s*\(\s*\)"), "function script.Parent.AncestryChanged"),
    (re.compile(r"\bUpdate\s*\(\s*\)"), "game:GetService('RunService').Heartbeat:Connect(function()"),
    # this. → self.
    (re.compile(r"\bthis\."), "self."),
    # C# single-line comment style is same as Luau (--) so no change needed
]


def _rule_based_transpile(csharp: str) -> tuple[str, float, list[str]]:
    """
    Apply regex substitutions to convert common C# patterns to Luau.

    Returns:
        (luau_source, confidence, warnings)
    """
    luau = csharp
    warnings: list[str] = []

    for pattern, replacement in _RULE_PATTERNS:
        luau = pattern.sub(replacement, luau)

    # Strip using directives (no equivalent in Luau)
    luau = re.sub(r"^using\s+[\w.]+;\s*\n", "", luau, flags=re.MULTILINE)

    # Strip namespace / class wrappers (simplified)
    luau = re.sub(r"\bnamespace\s+\w[\w.]*\s*\{", "", luau)
    luau = re.sub(r"\bpublic\s+class\s+\w+\s*(?::\s*\w+)?\s*\{", "", luau)

    # Rough confidence: ratio of lines changed
    original_lines = csharp.splitlines()
    new_lines = luau.splitlines()
    changed = sum(a != b for a, b in zip(original_lines, new_lines))
    confidence = min(1.0, changed / max(len(original_lines), 1) * 1.5)

    if "class " in luau:
        warnings.append("Residual 'class' keyword detected — manual cleanup needed.")
    if "{" in luau or "}" in luau:
        warnings.append("Curly braces remain — Luau uses 'end' blocks, not braces.")

    return luau, confidence, warnings


def _ai_transpile(
    csharp: str,
    api_key: str,
    model: str,
    max_tokens: int,
) -> tuple[str, float, list[str]]:
    """
    Send C# source to Claude and receive Luau output.

    Returns:
        (luau_source, confidence, warnings)
    """
    try:
        import anthropic  # type: ignore

        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            "Convert the following Unity C# MonoBehaviour script to idiomatic Roblox Luau.\n"
            "Output ONLY the Luau code, no explanations.\n\n"
            f"```csharp\n{csharp}\n```"
        )
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        luau = message.content[0].text.strip()
        # Strip markdown fences if present
        luau = re.sub(r"^```(?:lua|luau)?\n?", "", luau)
        luau = re.sub(r"\n?```$", "", luau)
        return luau, 0.9, []

    except Exception as exc:  # noqa: BLE001
        return (
            f"-- AI transpilation failed: {exc}\n-- Original C# preserved below:\n"
            + "\n".join(f"-- {line}" for line in csharp.splitlines()),
            0.0,
            [f"AI transpilation error: {exc}"],
        )


def transpile_scripts(
    unity_project_path: str | Path,
    use_ai: bool = False,
    api_key: str = "",
    model: str = "claude-opus-4-5",
    max_tokens: int = 4096,
    confidence_threshold: float = 0.7,
) -> TranspilationResult:
    """
    Find all C# scripts in *unity_project_path*/Assets and transpile them to Luau.

    Args:
        unity_project_path: Root directory of the Unity project.
        use_ai: If True, use Claude for transpilation; otherwise rule-based.
        api_key: Anthropic API key (required when use_ai=True).
        model: Claude model name.
        max_tokens: Max tokens per Claude request.
        confidence_threshold: Scripts below this score are flagged for review.

    Returns:
        TranspilationResult with one TranspiledScript per .cs file found.
    """
    root = Path(unity_project_path).resolve()
    assets_dir = root / "Assets"
    if not assets_dir.is_dir():
        raise FileNotFoundError(f"Assets directory not found: {assets_dir}")

    result = TranspilationResult()

    for cs_path in assets_dir.rglob("*.cs"):
        csharp_source = cs_path.read_text(encoding="utf-8", errors="replace")
        result.total += 1

        if use_ai and api_key:
            luau, confidence, warnings = _ai_transpile(csharp_source, api_key, model, max_tokens)
            strategy: TranspilationStrategy = "ai"
        else:
            luau, confidence, warnings = _rule_based_transpile(csharp_source)
            strategy = "rule_based"

        flagged = confidence < confidence_threshold
        ts = TranspiledScript(
            source_path=cs_path,
            output_filename=cs_path.stem + ".lua",
            csharp_source=csharp_source,
            luau_source=luau,
            strategy=strategy,
            confidence=confidence,
            warnings=warnings,
            flagged_for_review=flagged,
        )
        result.scripts.append(ts)

        if flagged:
            result.flagged += 1
        else:
            result.succeeded += 1

    return result
