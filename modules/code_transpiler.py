"""
code_transpiler.py — Transpiles Unity C# MonoBehaviour scripts to Roblox Luau.

Two strategies are available:
  1. AI-assisted (Claude via Anthropic API): Sends the full C# source to Claude
     and receives idiomatic Luau. Handles complex logic well but costs tokens.
  2. Rule-based: Uses tree-sitter AST parsing (with regex fallback) and a
     comprehensive API mapping table for structured transformations.

The chosen strategy is controlled by config.USE_AI_TRANSPILATION.
No other pipeline module is imported here (api_mappings is a data module).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from modules.api_mappings import API_CALL_MAP, LIFECYCLE_MAP, SERVICE_IMPORTS, TYPE_MAP


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
# Tree-sitter C# parser (optional — falls back to regex if unavailable)
# ---------------------------------------------------------------------------

_TS_AVAILABLE = False
_ts_parser: Any = None
_ts_language: Any = None

try:
    import tree_sitter_c_sharp as tscsharp  # type: ignore
    from tree_sitter import Language, Parser  # type: ignore

    _ts_language = Language(tscsharp.language())
    _ts_parser = Parser(_ts_language)
    _TS_AVAILABLE = True
except Exception:  # noqa: BLE001 — graceful fallback
    pass


@dataclass
class CSharpClassInfo:
    """Structural information extracted from a C# class via AST."""
    class_name: str = ""
    base_class: str = ""
    fields: list[tuple[str, str, str]] = field(default_factory=list)     # (type, name, default)
    methods: list[tuple[str, str, list[str]]] = field(default_factory=list)  # (return_type, name, param_names)
    lifecycle_hooks: list[str] = field(default_factory=list)  # Start, Update, etc.
    unity_apis_used: list[str] = field(default_factory=list)  # API calls detected
    services_needed: set[str] = field(default_factory=set)    # Roblox services to import


def _extract_text(node: Any, source_bytes: bytes) -> str:
    """Extract source text for a tree-sitter node."""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _parse_csharp_ast(source: str) -> CSharpClassInfo | None:
    """
    Parse C# source using tree-sitter and extract structural information.

    Returns None if tree-sitter is not available.
    """
    if not _TS_AVAILABLE or _ts_parser is None:
        return None

    info = CSharpClassInfo()
    source_bytes = source.encode("utf-8")
    tree = _ts_parser.parse(source_bytes)
    root = tree.root_node

    def _walk(node: Any) -> None:
        # Class declarations
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                info.class_name = _extract_text(name_node, source_bytes)
            # Base class
            bases = node.child_by_field_name("bases")
            if bases:
                for child in bases.children:
                    if child.type == "identifier" or child.type == "qualified_name":
                        info.base_class = _extract_text(child, source_bytes)
                        break

        # Field declarations
        elif node.type == "field_declaration":
            type_node = node.child_by_field_name("type") or (
                node.children[0] if node.children else None
            )
            field_type = _extract_text(type_node, source_bytes) if type_node else ""
            for child in node.children:
                if child.type == "variable_declaration":
                    ftype_node = child.child_by_field_name("type")
                    if ftype_node:
                        field_type = _extract_text(ftype_node, source_bytes)
                    for decl in child.children:
                        if decl.type == "variable_declarator":
                            name_node = decl.child_by_field_name("name")
                            init_node = decl.child_by_field_name("value")
                            fname = _extract_text(name_node, source_bytes) if name_node else ""
                            fdefault = _extract_text(init_node, source_bytes) if init_node else ""
                            if fname:
                                info.fields.append((field_type, fname, fdefault))

        # Method declarations
        elif node.type == "method_declaration":
            ret_node = node.child_by_field_name("type") or (
                node.children[0] if node.children else None
            )
            name_node = node.child_by_field_name("name")
            ret_type = _extract_text(ret_node, source_bytes) if ret_node else "void"
            method_name = _extract_text(name_node, source_bytes) if name_node else ""

            params: list[str] = []
            params_node = node.child_by_field_name("parameters")
            if params_node:
                for param in params_node.children:
                    if param.type == "parameter":
                        pname_node = param.child_by_field_name("name")
                        if pname_node:
                            params.append(_extract_text(pname_node, source_bytes))

            if method_name:
                info.methods.append((ret_type, method_name, params))
                if method_name in LIFECYCLE_MAP:
                    info.lifecycle_hooks.append(method_name)

        # Detect Unity API calls via member access / invocations
        elif node.type == "member_access_expression":
            text = _extract_text(node, source_bytes)
            for api_key in API_CALL_MAP:
                if api_key in text:
                    info.unity_apis_used.append(api_key)
                    # Determine which Roblox services are needed
                    roblox_equiv = API_CALL_MAP[api_key]
                    for svc in SERVICE_IMPORTS:
                        if svc in roblox_equiv:
                            info.services_needed.add(svc)

        for child in node.children:
            _walk(child)

    _walk(root)

    # Lifecycle hooks also determine services needed
    for hook in info.lifecycle_hooks:
        roblox = LIFECYCLE_MAP.get(hook, "")
        for svc in SERVICE_IMPORTS:
            if svc in roblox:
                info.services_needed.add(svc)

    return info


# ---------------------------------------------------------------------------
# Rule-based transpilation (regex + API mappings)
# ---------------------------------------------------------------------------

# Build regex patterns from the API mapping table (sorted longest-first for
# correct precedence when patterns overlap)
_API_REGEX_PATTERNS: list[tuple[re.Pattern, str]] = []
for _api_key in sorted(API_CALL_MAP.keys(), key=len, reverse=True):
    _escaped = re.escape(_api_key)
    _API_REGEX_PATTERNS.append(
        (re.compile(r"\b" + _escaped), API_CALL_MAP[_api_key])
    )

_RULE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Variable declarations: int/float/bool/string → local
    (re.compile(r"\b(int|float|double|bool|string)\s+(\w+)\s*="), r"local \2 ="),
    # Debug.Log → print (keep for backward compat, also in API map)
    (re.compile(r"\bDebug\.Log\("), "print("),
    # void → (no return type in Luau)
    (re.compile(r"\bvoid\s+(\w+)\s*\("), r"local function \1("),
    # Unity lifecycle stubs
    (re.compile(r"\bStart\s*\(\s*\)"), "function script.Parent.AncestryChanged"),
    (re.compile(r"\bUpdate\s*\(\s*\)"), "game:GetService('RunService').Heartbeat:Connect(function()"),
    # this. → self.
    (re.compile(r"\bthis\."), "self."),
]


def _apply_api_mappings(source: str) -> tuple[str, int]:
    """
    Apply the comprehensive API mapping table to source code.

    Returns (transformed_source, number_of_substitutions).
    """
    total_subs = 0
    result = source
    for pattern, replacement in _API_REGEX_PATTERNS:
        result, n = pattern.subn(replacement, result)
        total_subs += n
    return result, total_subs


def _rule_based_transpile(csharp: str) -> tuple[str, float, list[str]]:
    """
    Apply regex substitutions and API mappings to convert C# patterns to Luau.

    When tree-sitter is available, AST info is used to generate service imports
    and improve confidence scoring.

    Returns:
        (luau_source, confidence, warnings)
    """
    luau = csharp
    warnings: list[str] = []

    # Try AST-based analysis for structural insight
    ast_info = _parse_csharp_ast(csharp)

    # Apply basic structural transformations
    for pattern, replacement in _RULE_PATTERNS:
        luau = pattern.sub(replacement, luau)

    # Apply comprehensive API mappings
    luau, api_subs = _apply_api_mappings(luau)

    # Strip using directives (no equivalent in Luau)
    luau = re.sub(r"^using\s+[\w.]+;\s*\n", "", luau, flags=re.MULTILINE)

    # Strip namespace / class wrappers (simplified)
    luau = re.sub(r"\bnamespace\s+\w[\w.]*\s*\{", "", luau)
    luau = re.sub(r"\bpublic\s+class\s+\w+\s*(?::\s*\w+)?\s*\{", "", luau)

    # Strip access modifiers
    luau = re.sub(r"\b(public|private|protected|internal|static)\s+", "", luau)

    # Convert C# type casts to comments
    luau = re.sub(r"\((?:int|float|double|string|bool)\)\s*", "", luau)

    # Convert != to ~= (Luau inequality operator)
    luau = re.sub(r"!=", "~=", luau)

    # Convert && to and, || to or, ! to not
    luau = re.sub(r"&&", " and ", luau)
    luau = re.sub(r"\|\|", " or ", luau)
    luau = re.sub(r"!(\w)", r"not \1", luau)

    # Convert null to nil
    luau = re.sub(r"\bnull\b", "nil", luau)

    # Convert true/false (same in Luau, but ensure lowercase)
    luau = re.sub(r"\bTrue\b", "true", luau)
    luau = re.sub(r"\bFalse\b", "false", luau)

    # Convert string concatenation + to ..
    luau = re.sub(r'"\s*\+\s*', '" .. ', luau)
    luau = re.sub(r'\s*\+\s*"', ' .. "', luau)

    # Convert for(int i = 0; i < n; i++) to for i = 0, n-1 do
    luau = re.sub(
        r"for\s*\(\s*(?:int\s+)?(\w+)\s*=\s*(\d+)\s*;\s*\1\s*<\s*(\w+)\s*;\s*\1\+\+\s*\)",
        r"for \1 = \2, \3 - 1 do",
        luau,
    )

    # Convert foreach (Type item in collection) to for _, item in collection do
    luau = re.sub(
        r"foreach\s*\(\s*\w+\s+(\w+)\s+in\s+(\w+)\s*\)",
        r"for _, \1 in \2 do",
        luau,
    )

    # Add Roblox service imports at the top if AST detected usage
    service_header = ""
    if ast_info and ast_info.services_needed:
        lines = []
        for svc in sorted(ast_info.services_needed):
            if svc in SERVICE_IMPORTS:
                lines.append(SERVICE_IMPORTS[svc])
        if lines:
            service_header = "\n".join(lines) + "\n\n"

    if service_header:
        luau = service_header + luau

    # Confidence scoring — improved with AST data
    original_lines = csharp.splitlines()
    new_lines = luau.splitlines()
    changed = sum(a != b for a, b in zip(original_lines, new_lines))
    base_confidence = min(1.0, changed / max(len(original_lines), 1) * 1.5)

    # Boost confidence if AST was available and we detected real structure
    if ast_info:
        if ast_info.class_name:
            base_confidence = min(1.0, base_confidence + 0.1)
        if ast_info.lifecycle_hooks:
            base_confidence = min(1.0, base_confidence + 0.1)
        if api_subs > 0:
            base_confidence = min(1.0, base_confidence + 0.05 * min(api_subs, 5))

    confidence = base_confidence

    if "class " in luau:
        warnings.append("Residual 'class' keyword detected — manual cleanup needed.")
    if "{" in luau or "}" in luau:
        warnings.append("Curly braces remain — Luau uses 'end' blocks, not braces.")

    if ast_info and ast_info.unity_apis_used:
        unmapped = [
            api for api in ast_info.unity_apis_used
            if API_CALL_MAP.get(api, "").startswith("--")
        ]
        if unmapped:
            warnings.append(
                f"APIs requiring manual work: {', '.join(unmapped[:5])}"
                + (f" (+{len(unmapped)-5} more)" if len(unmapped) > 5 else "")
            )

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

    for cs_path in sorted(assets_dir.rglob("*.cs")):
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
