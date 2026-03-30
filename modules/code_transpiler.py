"""
code_transpiler.py — Transpiles Unity C# MonoBehaviour scripts to Roblox Luau.

Uses Claude (via Anthropic API) to convert C# source to idiomatic Luau.
An API key is required — there is no offline fallback.

Tree-sitter is optionally used for structural analysis (script type
classification, pattern warnings) but not for code generation.

No other pipeline module is imported here (api_mappings is a data module).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from modules.api_mappings import API_CALL_MAP, LIFECYCLE_MAP, SERVICE_IMPORTS


TranspilationStrategy = Literal["ai", "skipped"]
RobloxScriptType = Literal["Script", "LocalScript", "ModuleScript"]


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
    script_type: RobloxScriptType = "Script"  # classified placement target


@dataclass
class TranspilationResult:
    """Aggregate result for all scripts in a Unity project."""
    scripts: list[TranspiledScript] = field(default_factory=list)
    total: int = 0
    succeeded: int = 0
    flagged: int = 0
    skipped: int = 0


# ---------------------------------------------------------------------------
# Structural C# analysis — detect patterns worth flagging
# ---------------------------------------------------------------------------

# Standard Unity base classes that are expected (not custom inheritance)
_UNITY_BASE_CLASSES: frozenset[str] = frozenset({
    "MonoBehaviour", "ScriptableObject", "Editor", "EditorWindow",
    "PropertyDrawer", "StateMachineBehaviour", "NetworkBehaviour",
})

# LINQ methods
_LINQ_METHODS = re.compile(
    r"\.\s*(?:Where|Select|SelectMany|FirstOrDefault|First|Last|LastOrDefault|"
    r"Any|All|Count|Sum|Average|Min|Max|Aggregate|OrderBy|OrderByDescending|"
    r"ThenBy|GroupBy|Distinct|Skip|Take|ToList|ToArray|ToDictionary|"
    r"OfType|Cast|Zip|Concat)\s*\("
)

# Networking attributes
_NETWORK_ATTRS = re.compile(
    r"\[\s*(?:Command|ClientRpc|ServerRpc|SyncVar|TargetRpc|"
    r"ClientCallback|Server|Client)\s*[(\]]"
)

# Complex generic types (beyond simple GetComponent<T>)
_COMPLEX_GENERICS = re.compile(
    r"(?:Dictionary|List|HashSet|Queue|Stack|IEnumerable|IReadOnlyList)"
    r"\s*<\s*\w+\s*(?:<[^>]+>|,\s*\w+(?:<[^>]+>)?)\s*>"
)


def _analyze_csharp_patterns(source: str) -> list[str]:
    """Detect C# patterns that the transpiler handles poorly or not at all.

    Returns a list of warning strings for patterns found.
    """
    warnings: list[str] = []

    # Custom inheritance — base class methods won't be included
    class_decl = re.findall(
        r"class\s+(\w+)\s*:\s*([\w.<>,\s]+?)(?:\s*\{|\s*where\b)", source
    )
    for class_name, bases in class_decl:
        base_list = [b.strip() for b in bases.split(",")]
        custom_bases = [
            b for b in base_list
            if b and b not in _UNITY_BASE_CLASSES
            and not b.startswith("I")  # interfaces (IDisposable, etc.)
        ]
        if custom_bases:
            warnings.append(
                f"'{class_name}' extends custom base class '{custom_bases[0]}' "
                f"— inherited methods are not included in transpilation"
            )

    # LINQ
    linq_matches = _LINQ_METHODS.findall(source)
    if linq_matches:
        count = len(linq_matches)
        warnings.append(
            f"LINQ detected ({count} call{'s' if count > 1 else ''}) "
            f"— rewrite as explicit loops in Luau"
        )

    # Networking attributes
    net_matches = _NETWORK_ATTRS.findall(source)
    if net_matches:
        count = len(net_matches)
        warnings.append(
            f"Networking attributes detected ({count}) "
            f"— convert to RemoteEvent/RemoteFunction manually"
        )

    # Complex generic types
    generic_matches = _COMPLEX_GENERICS.findall(source)
    if generic_matches:
        warnings.append(
            f"Complex generic types detected ({len(generic_matches)}) "
            f"— Luau uses untyped tables, verify data structure conversion"
        )

    # async/await (beyond simple coroutine patterns)
    if re.search(r"\basync\s+Task", source):
        warnings.append(
            "async Task methods detected — convert to coroutine (task.spawn) patterns"
        )

    return warnings


# ---------------------------------------------------------------------------
# Tree-sitter C# parser (optional — used for classification, not transpilation)
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
# Script type classification (client / server / shared)
# ---------------------------------------------------------------------------

# Unity APIs that indicate client-side execution (LocalScript in Roblox).
# These access player input, camera, screen, or GUI — services only
# available on the Roblox client.
_CLIENT_INDICATORS: set[str] = {
    # Input
    "Input.GetKey", "Input.GetKeyDown", "Input.GetKeyUp",
    "Input.GetMouseButton", "Input.GetMouseButtonDown",
    "Input.GetAxis", "Input.mousePosition", "Input.GetTouch",
    "Input.GetJoystickNames", "Input.anyKey", "Input.anyKeyDown",
    # Camera
    "Camera.main", "Camera.fieldOfView",
    "Camera.ScreenToWorldPoint", "Camera.WorldToScreenPoint",
    "Camera.ScreenPointToRay", "Camera.ViewportToWorldPoint",
    # Screen / display
    "Screen.width", "Screen.height", "Screen.orientation",
    # UI
    "Canvas", "Text.text", "Image.sprite", "Button.onClick",
    "RectTransform", "EventSystem", "Slider.value", "Toggle.isOn",
    "InputField.text", "Dropdown.value", "ScrollRect",
    # Cursor
    "Cursor.lockState", "Cursor.visible",
    # Lifecycle hooks that are client-only
    "OnMouseDown", "OnMouseEnter", "OnMouseExit", "OnGUI",
    "OnBecameVisible", "OnBecameInvisible",
}

# Unity APIs / attributes that indicate server-side execution.
_SERVER_INDICATORS: set[str] = {
    # Networking attributes
    "[Command]", "[SyncVar]", "[ClientRpc]", "[ServerRpc]",
    "[Server]", "[ServerCallback]",
    # Persistent data (server-side in Roblox)
    "PlayerPrefs.SetInt", "PlayerPrefs.GetInt",
    "PlayerPrefs.SetFloat", "PlayerPrefs.GetFloat",
    "PlayerPrefs.SetString", "PlayerPrefs.GetString",
    "PlayerPrefs.Save", "PlayerPrefs.DeleteKey",
    # Scene management
    "SceneManager.LoadScene", "SceneManager.GetActiveScene",
    # Server-side physics
    "Physics.Raycast", "Physics.OverlapSphere", "Physics.SphereCast",
}

# Lifecycle hooks that are inherently client-side in Roblox.
_CLIENT_LIFECYCLE: set[str] = {
    "LateUpdate",  # maps to RenderStepped, client-only
    "OnGUI",
    "OnMouseDown", "OnMouseEnter", "OnMouseExit",
}


def _classify_script_type(
    source: str,
    ast_info: CSharpClassInfo | None,
) -> RobloxScriptType:
    """
    Classify a C# script as LocalScript, Script, or ModuleScript based on
    which Unity APIs it uses and its structural characteristics.

    Heuristic (in priority order):
      1. No MonoBehaviour/NetworkBehaviour base AND no lifecycle hooks → ModuleScript
      2. Has NetworkBehaviour base or networking attributes → Script (server)
      3. Uses server-only APIs (PlayerPrefs/DataStore) with NO client APIs → Script
      4. Default → ModuleScript (required by bootstrap)

    Unity has no server/client split, so ported single-player games default to
    ModuleScript. The auto-generated bootstrap LocalScript requires and drives
    these modules. Only explicitly server-side scripts (networking, persistence)
    become Scripts in ServerScriptService.
    """
    _BEHAVIOUR_BASES = {"MonoBehaviour", "NetworkBehaviour", "StateMachineBehaviour"}
    _NETWORK_BASES = {"NetworkBehaviour"}
    _NETWORK_ATTRS = {"[Command]", "[SyncVar]", "[ClientRpc]", "[ServerRpc]",
                      "[Server]", "[ServerCallback]"}

    if ast_info:
        # Pure utility / data class — no MonoBehaviour, no lifecycle hooks
        if ast_info.base_class not in _BEHAVIOUR_BASES and not ast_info.lifecycle_hooks:
            if ast_info.class_name:
                return "ModuleScript"

        # NetworkBehaviour → genuinely server-side
        if ast_info.base_class in _NETWORK_BASES:
            return "Script"

    # Check for networking attributes in source (strong server signal)
    for attr in _NETWORK_ATTRS:
        if attr in source:
            return "Script"

    # Check for server-only persistence patterns with NO client patterns
    server_score = 0
    client_score = 0
    for pattern in _SERVER_INDICATORS:
        if pattern in source:
            server_score += 1
    for pattern in _CLIENT_INDICATORS:
        if pattern.startswith("[") or pattern.startswith("On"):
            continue
        if pattern in source:
            client_score += 1
    if server_score > 0 and client_score == 0:
        return "Script"

    # Everything else is a ModuleScript — the bootstrap will require and drive it.
    # Unity has no server/client split; ported games run as modules on the client.
    return "ModuleScript"


# ---------------------------------------------------------------------------
# Project context — cross-file awareness for transpilation
# ---------------------------------------------------------------------------

_MAX_FULL_CONTEXT_TOKENS = 80_000  # threshold for full-context vs manifest


def _build_project_context(
    assets_dir: Path,
) -> tuple[str, dict[str, str]]:
    """Return (concatenated_source, {stem: relative_path}) for all C# files."""
    parts: list[str] = []
    file_map: dict[str, str] = {}
    for cs_path in sorted(assets_dir.rglob("*.cs")):
        relative_parts = cs_path.relative_to(assets_dir).parts
        if _is_editor_or_test_path(relative_parts):
            continue
        rel = str(cs_path.relative_to(assets_dir))
        file_map[cs_path.stem] = rel
        source = cs_path.read_text(encoding="utf-8-sig", errors="replace")
        parts.append(f"--- File: {rel} (module name: {cs_path.stem}) ---\n{source}")
    return "\n\n".join(parts), file_map


def _build_project_manifest(
    assets_dir: Path,
) -> str:
    """Build a compressed class/method manifest for projects too large for full context."""
    lines: list[str] = []
    for cs_path in sorted(assets_dir.rglob("*.cs")):
        relative_parts = cs_path.relative_to(assets_dir).parts
        if _is_editor_or_test_path(relative_parts):
            continue
        source = cs_path.read_text(encoding="utf-8-sig", errors="replace")
        ast_info = _parse_csharp_ast(source)

        # Extract class declarations via regex as fallback
        classes = re.findall(
            r"(?:public\s+)?(?:abstract\s+)?(?:static\s+)?class\s+(\w+)"
            r"(?:\s*:\s*([\w,\s<>]+))?",
            source,
        )
        enums = re.findall(r"(?:public\s+)?enum\s+(\w+)", source)
        structs = re.findall(r"(?:public\s+)?struct\s+(\w+)", source)

        exports: list[str] = []
        for cname, bases in classes:
            base_str = f" : {bases.strip()}" if bases else ""
            exports.append(f"{cname}{base_str}")
        exports.extend(f"{e} (enum)" for e in enums)
        exports.extend(f"{s} (struct)" for s in structs)

        # Public methods
        methods = re.findall(
            r"public\s+(?:static\s+)?(?:virtual\s+)?(?:override\s+)?(?:abstract\s+)?"
            r"[\w<>\[\]]+\s+(\w+)\s*\(",
            source,
        )
        # Singleton pattern
        has_singleton = bool(re.search(r"static\s+\w+\s+(?:s_Instance|instance|_instance)", source))

        module_name = cs_path.stem
        export_str = ", ".join(exports) if exports else "(no classes)"
        lines.append(f"{module_name}.lua — exports: {export_str}")
        if has_singleton:
            lines.append("  [singleton]")
        if methods:
            lines.append(f"  methods: {', '.join(dict.fromkeys(methods))}")
        if ast_info and ast_info.lifecycle_hooks:
            lines.append(f"  lifecycle: {', '.join(ast_info.lifecycle_hooks)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Post-processing: strip invalid Luau patterns
# ---------------------------------------------------------------------------

_PROPERTY_CALL = re.compile(r"^.*=\s*property\s*\(.*\)\s*$", re.MULTILINE)


def _strip_property_calls(luau: str) -> str:
    """Remove property() calls — Luau has no property() function.

    The AI sometimes emits C#-style property descriptors like:
        Foo.bar = property(Foo.getBar, Foo.setBar)
    These must be stripped; callers should use direct field access instead.
    """
    return _PROPERTY_CALL.sub("", luau)


# ---------------------------------------------------------------------------
# AI transpilation (Claude via Anthropic API)
# ---------------------------------------------------------------------------

def _ai_transpile(
    csharp: str,
    api_key: str,
    model: str,
    max_tokens: int,
    *,
    project_context: str | None = None,
    target_filename: str = "",
) -> tuple[str, float, list[str]]:
    """Send C# source to Claude and return (luau_source, confidence, warnings)."""
    try:
        import anthropic  # type: ignore

        client = anthropic.Anthropic(api_key=api_key)

        if project_context:
            prompt = (
                "You are converting a Unity C# project to Roblox Luau. "
                "Below is the project source for cross-file reference. "
                f"Convert ONLY the target file ({target_filename}), but use the "
                "other files to resolve class references, inheritance, and shared types.\n\n"
                "RULES:\n"
                "- All converted modules live in ReplicatedStorage.\n"
                "- To reference another module: "
                'require(game:GetService("ReplicatedStorage"):WaitForChild("ModuleName"))\n'
                "- ModuleName is the C# filename without extension "
                "(e.g., PlayerData.cs becomes \"PlayerData\").\n"
                "- If a C# file defines multiple classes/enums, export ALL of them "
                "in the return table: return { Class1 = Class1, Class2 = Class2, ... }\n"
                "- Singleton pattern (static instance) → module-level state.\n"
                "- Unity GetComponent<T>() → explicit references passed via config/init.\n"
                "- MonoBehaviour public/serialized fields are set by the Unity Inspector, "
                "not by code. Constructors MUST start with `config = config or {}` and "
                "default every field: `self.x = config.x or defaultValue`. Never assume "
                "config fields are non-nil — the caller may wire references after construction.\n"
                "- C# properties with get/set → emit getter/setter methods and wire them "
                "through __index/__newindex metamethods on the class table. Do NOT use "
                "direct field access or class-level aliases (MyClass.prop = MyClass.getProp) "
                "— those resolve to the function, not the return value.\n"
                "- GameObject.SetActive(bool) → GameObjectUtil.SetActive(instance, bool). "
                "Never emit obj.Parent = nil to hide objects — it detaches from the scene tree "
                "and causes nil-parent cascading failures.\n"
                "- Unity bridge modules are available in ReplicatedStorage. Use require() to "
                "import them when the C# source uses the corresponding Unity API:\n"
                '  * Input (GetKey/GetKeyDown/GetKeyUp/GetAxis) → require(...:WaitForChild("Input"))\n'
                '  * Time (deltaTime/time/timeScale) → require(...:WaitForChild("Time"))\n'
                '  * Coroutine (StartCoroutine/WaitForSeconds) → require(...:WaitForChild("Coroutine"))\n'
                '  * Physics (Raycast/CheckSphere/OverlapSphere) → require(...:WaitForChild("Physics"))\n'
                '  * MonoBehaviour (lifecycle: Start/Update/Awake/OnEnable) → require(...:WaitForChild("MonoBehaviour"))\n'
                '  * GameObjectUtil (Instantiate/Destroy/Find/SetActive) → require(...:WaitForChild("GameObjectUtil"))\n'
                '  * StateMachine (state machine pattern with Enter/Exit/Tick) → require(...:WaitForChild("StateMachine"))\n'
                "  Use the module API exactly as named (e.g. Input.GetKey, Physics.Raycast, "
                "Coroutine.Start, Time.deltaTime, GameObjectUtil.Destroy). "
                "The require target is ReplicatedStorage.\n"
                "- BinaryWriter/BinaryReader serialization → use Lua table fields. "
                "Roblox persists data via DataStore (JSON), not binary streams. "
                "Replace writer.Write(x)/reader.Read() with table.field = x / x = table.field.\n"
                "- If the script references an Animator (GetComponent<Animator>(), "
                "Animator.SetBool/SetFloat/SetTrigger/Play), assume an `animatorBridge` "
                "field is available on self (passed via config). Map Animator API calls to "
                "animatorBridge:SetBool/SetFloat/SetTrigger/Play accordingly.\n"
                "- Output ONLY the Luau code for the target file, no explanations.\n\n"
                f"=== PROJECT SOURCE ===\n{project_context}\n\n"
                f"=== TARGET FILE TO CONVERT: {target_filename} ===\n"
                f"```csharp\n{csharp}\n```"
            )
        else:
            prompt = (
                "Convert the following Unity C# MonoBehaviour script to idiomatic Roblox Luau.\n"
                "Output ONLY the Luau code, no explanations.\n\n"
                f"```csharp\n{csharp}\n```"
            )

        # Retry with doubled max_tokens on truncation (up to one retry)
        current_max = max_tokens
        for attempt in range(2):
            message = client.messages.create(
                model=model,
                max_tokens=current_max,
                messages=[{"role": "user", "content": prompt}],
            )
            if message.stop_reason != "max_tokens" or attempt == 1:
                break
            current_max = min(current_max * 2, 65536)

        luau = message.content[0].text.strip()
        luau = re.sub(r"^```(?:lua|luau)?\n?", "", luau)
        luau = re.sub(r"\n?```$", "", luau)
        luau = _strip_property_calls(luau)
        warnings: list[str] = []
        confidence = 0.9
        if message.stop_reason == "max_tokens":
            warnings.append("Output truncated after retry — script may be incomplete.")
            confidence = 0.3
        return luau, confidence, warnings

    except Exception as exc:  # noqa: BLE001
        return (
            f"-- AI transpilation failed: {exc}\n-- Original C# preserved below:\n"
            + "\n".join(f"-- {line}" for line in csharp.splitlines()),
            0.0,
            [f"AI transpilation error: {exc}"],
        )


# ---------------------------------------------------------------------------
# Post-transpilation require resolution
# ---------------------------------------------------------------------------

_REQUIRE_PATTERN = re.compile(
    r'require\s*\(\s*'
    r'(?:game:GetService\(["\']ReplicatedStorage["\']\)|ReplicatedStorage)'
    r'\s*(?::WaitForChild\s*\(\s*["\'](\w+)["\']\s*\)'
    r'|\.(\w+))'
    r'\s*\)',
)

_REQUIRE_ANY = re.compile(r'require\s*\([^)]*?["\'](\w+)["\'][^)]*\)')


def _resolve_requires(scripts: list[TranspiledScript]) -> list[str]:
    """Validate require() calls target modules that exist in the output."""
    known_modules = {ts.output_filename.replace(".lua", "") for ts in scripts}
    warnings: list[str] = []

    for ts in scripts:
        # Find all require targets in this script
        for match in _REQUIRE_ANY.finditer(ts.luau_source):
            target = match.group(1)
            # Skip Roblox built-in services
            if target in (
                "ReplicatedStorage", "ServerStorage", "ServerScriptService",
                "Players", "RunService", "UserInputService", "TweenService",
                "Workspace", "SoundService", "StarterGui", "Lighting",
                "CollectionService", "HttpService", "DataStoreService",
                "MarketplaceService", "TextService", "PathfindingService",
            ):
                continue
            if target not in known_modules:
                warnings.append(
                    f"{ts.output_filename}: require(\"{target}\") — "
                    f"module not found in project"
                )

    return warnings


_SKIP_DIRS = frozenset({"Editor", "Tests", "Test", "EditorTests", "TestFramework"})


def _is_editor_or_test_path(path_parts: tuple[str, ...]) -> bool:
    """True if the path contains an Editor or Test directory."""
    return bool(_SKIP_DIRS.intersection(path_parts))


def _is_valid_cached_luau(text: str) -> bool:
    """Return True if a cached Luau script looks complete (not truncated)."""
    stripped = text.rstrip()
    if not stripped:
        return False
    lines = stripped.splitlines()
    for line in reversed(lines[-15:]):
        if line.strip().startswith("return"):
            return True
    if stripped.endswith("end"):
        return True
    if lines[-1].strip().endswith(")"):
        return True
    return False


def transpile_scripts(
    unity_project_path: str | Path,
    *,
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 16384,
    confidence_threshold: float = 0.7,
    serialized_refs: dict[Path, dict[str, str]] | None = None,
    transpile_cache_dir: str | Path | None = None,
) -> TranspilationResult:
    """Transpile all C# scripts under Assets/ to Luau via Claude."""
    root = Path(unity_project_path).resolve()
    assets_dir = root / "Assets"
    if not assets_dir.is_dir():
        raise FileNotFoundError(f"Assets directory not found: {assets_dir}")

    cache_dir = Path(transpile_cache_dir) if transpile_cache_dir else None

    full_context, file_map = _build_project_context(assets_dir)
    token_estimate = len(full_context) / 4
    if token_estimate < _MAX_FULL_CONTEXT_TOKENS:
        project_context = full_context
    else:
        project_context = (
            "=== PROJECT MODULE MANIFEST (project too large for full source) ===\n"
            + _build_project_manifest(assets_dir)
        )

    result = TranspilationResult()

    for cs_path in sorted(assets_dir.rglob("*.cs")):
        relative_parts = cs_path.relative_to(assets_dir).parts
        if _is_editor_or_test_path(relative_parts):
            continue

        csharp_source = cs_path.read_text(encoding="utf-8-sig", errors="replace")
        result.total += 1

        ast_info = _parse_csharp_ast(csharp_source)

        cached_lua = None
        if cache_dir:
            cached_path = cache_dir / (cs_path.stem + ".lua")
            if cached_path.is_file():
                cached_text = cached_path.read_text(encoding="utf-8", errors="replace")
                if _is_valid_cached_luau(cached_text):
                    cached_lua = cached_text

        if cached_lua is not None:
            luau = cached_lua
            confidence = 0.9
            warnings: list[str] = []
            strategy: TranspilationStrategy = "ai"
        else:
            luau, confidence, warnings = _ai_transpile(
                csharp_source, api_key, model, max_tokens,
                project_context=project_context,
                target_filename=cs_path.name,
            )
            strategy = "ai"

        warnings.extend(_analyze_csharp_patterns(csharp_source))
        script_type = _classify_script_type(csharp_source, ast_info)

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
            script_type=script_type,
        )
        result.scripts.append(ts)

        if flagged:
            result.flagged += 1
        else:
            result.succeeded += 1

    require_warnings = _resolve_requires(result.scripts)
    if require_warnings:
        for ts in result.scripts:
            prefix = ts.output_filename + ":"
            ts.warnings.extend(w for w in require_warnings if w.startswith(prefix))

    return result
