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
# AST-driven Luau emitter (replaces regex pipeline when tree-sitter available)
# ---------------------------------------------------------------------------

class _LuauEmitter:
    """Walk a tree-sitter C# AST and emit Luau source code.

    Unlike the regex pipeline, this is context-aware: string literals and
    comments are never transformed, control-flow blocks produce correct
    ``end`` placement, and expressions like ``Instantiate(prefab)`` are
    structurally rewritten rather than naively text-substituted.
    """

    def __init__(
        self,
        source: str,
        serialized_refs: dict[str, str] | None = None,
    ) -> None:
        self.source = source
        self.source_bytes = source.encode("utf-8")
        self.refs = serialized_refs or {}
        self.services: set[str] = set()
        self.warnings: list[str] = []
        self.indent = 0
        self.api_subs = 0
        # Pre-sort API keys longest-first for correct precedence
        self._sorted_api_keys = sorted(API_CALL_MAP.keys(), key=len, reverse=True)

    # -- helpers ----------------------------------------------------------

    def _text(self, node: Any) -> str:
        return self.source_bytes[node.start_byte:node.end_byte].decode(
            "utf-8", errors="replace"
        )

    def _ind(self) -> str:
        return "    " * self.indent

    def _track_service(self, text: str) -> None:
        for svc in SERVICE_IMPORTS:
            if svc in text:
                self.services.add(svc)

    def _is_string_context(self, node: Any) -> bool:
        """True if *node* (or a parent) is a string literal."""
        cur = node
        while cur:
            if cur.type in ("string_literal", "interpolated_string_expression"):
                return True
            cur = cur.parent
        return False

    def _named_children(self, node: Any) -> list[Any]:
        return [c for c in node.children if c.is_named]

    # -- main dispatch ----------------------------------------------------

    def emit(self, node: Any) -> str:
        handler = getattr(self, f"_emit_{node.type}", None)
        if handler:
            return handler(node)
        # Leaf tokens that aren't explicitly handled → raw text
        if node.child_count == 0:
            return self._text(node)
        # Container with no handler → emit named children
        parts = [self.emit(c) for c in self._named_children(node)]
        return "\n".join(p for p in parts if p.strip())

    # -- structure --------------------------------------------------------

    def _emit_compilation_unit(self, node: Any) -> str:
        parts: list[str] = []
        for child in node.children:
            if child.type == "using_directive":
                continue
            result = self.emit(child)
            if result and result.strip():
                parts.append(result)
        return "\n\n".join(parts)

    def _emit_global_statement(self, node: Any) -> str:
        parts = [self.emit(c) for c in self._named_children(node)]
        return "\n".join(p for p in parts if p.strip())

    def _emit_using_directive(self, _node: Any) -> str:
        return ""

    def _emit_namespace_declaration(self, node: Any) -> str:
        body = node.child_by_field_name("body")
        return self._emit_declaration_list_inner(body) if body else ""

    def _emit_class_declaration(self, node: Any) -> str:
        body = node.child_by_field_name("body")
        return self._emit_declaration_list_inner(body) if body else ""

    def _emit_declaration_list(self, node: Any) -> str:
        return self._emit_declaration_list_inner(node)

    def _emit_declaration_list_inner(self, node: Any) -> str:
        parts: list[str] = []
        for child in node.children:
            if child.type in ("{", "}"):
                continue
            if not child.is_named:
                continue
            result = self.emit(child)
            if result and result.strip():
                parts.append(result)
        return "\n\n".join(parts)

    # -- declarations -----------------------------------------------------

    def _emit_field_declaration(self, node: Any) -> str:
        # Check for [SerializeField] attribute
        has_serialize = False
        for child in node.children:
            if child.type == "attribute_list":
                if "SerializeField" in self._text(child):
                    has_serialize = True

        var_decl = next(
            (c for c in node.children if c.type == "variable_declaration"), None
        )
        if var_decl is None:
            return ""

        declarator = next(
            (c for c in var_decl.children if c.type == "variable_declarator"), None
        )
        if declarator is None:
            return ""

        name_node = declarator.child_by_field_name("name")
        field_name = self._text(name_node) if name_node else ""

        if has_serialize and field_name in self.refs:
            ref_value = self.refs[field_name]
            if ref_value.startswith("audio:"):
                audio_filename = ref_value[len("audio:"):]
                self.services.add("SoundService")
                return (
                    f'{self._ind()}local {field_name} = Instance.new("Sound")\n'
                    f'{self._ind()}{field_name}.Name = "{field_name}"\n'
                    f'{self._ind()}{field_name}.SoundId = "-- TODO: upload {audio_filename}"'
                )
            self.services.add("ServerStorage")
            return (
                f'{self._ind()}local {field_name} = '
                f'ServerStorage:WaitForChild("{ref_value}")'
            )

        # Normal field → local declaration
        value = self._get_declarator_value(declarator)
        if value is not None:
            return f"{self._ind()}local {field_name} = {value}"
        return f"{self._ind()}local {field_name} = nil"

    def _emit_method_declaration(self, node: Any) -> str:
        name_node = node.child_by_field_name("name")
        name = self._text(name_node) if name_node else ""
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        # Lifecycle hooks
        if name in LIFECYCLE_MAP:
            return self._emit_lifecycle(name, body_node)

        # Check if this is a coroutine (returns IEnumerator)
        ret_node = node.child_by_field_name("type") or (
            node.children[0] if node.children else None
        )
        ret_type = self._text(ret_node) if ret_node else ""
        is_coroutine = ret_type == "IEnumerator"

        # Regular method
        params = self._emit_param_names(params_node)
        body = self._emit_block_body(body_node) if body_node else ""
        if is_coroutine:
            # Coroutine → wrap body in task.spawn
            self.warnings.append(f"Coroutine '{name}' converted to task.spawn — verify timing")
            return (
                f"{self._ind()}local function {name}({params})\n"
                f"{self._ind()}    task.spawn(function()\n"
                f"{body}\n"
                f"{self._ind()}    end)\n"
                f"{self._ind()}end"
            )
        return (
            f"{self._ind()}local function {name}({params})\n"
            f"{body}\n"
            f"{self._ind()}end"
        )

    def _emit_lifecycle(self, name: str, body_node: Any) -> str:
        roblox = LIFECYCLE_MAP.get(name, "")
        self._track_service(roblox)
        body = self._emit_block_body(body_node) if body_node else ""

        if name in ("Start", "Awake"):
            # Emit as top-level code
            comment = f"{self._ind()}-- {name}\n" if body.strip() else ""
            return f"{comment}{body}" if body.strip() else f"{self._ind()}-- {name}: (empty)"

        if "Connect" in roblox:
            return (
                f"{self._ind()}{roblox}\n"
                f"{body}\n"
                f"{self._ind()}end)"
            )
        return f"{self._ind()}{roblox}\n{body}"

    def _emit_local_function_statement(self, node: Any) -> str:
        name_node = node.child_by_field_name("name")
        name = self._text(name_node) if name_node else ""
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        # Check for lifecycle hooks even in top-level function statements
        if name in LIFECYCLE_MAP:
            return self._emit_lifecycle(name, body_node)

        params = self._emit_param_names(params_node)
        body = self._emit_block_body(body_node) if body_node else ""
        return (
            f"{self._ind()}local function {name}({params})\n"
            f"{body}\n"
            f"{self._ind()}end"
        )

    def _emit_property_declaration(self, node: Any) -> str:
        name_node = node.child_by_field_name("name")
        name = self._text(name_node) if name_node else "UnknownProp"
        accessors_node = node.child_by_field_name("accessors")

        parts: list[str] = []
        if accessors_node:
            for acc in accessors_node.children:
                if acc.type == "accessor_declaration":
                    acc_name_node = acc.child_by_field_name("name")
                    acc_name = self._text(acc_name_node) if acc_name_node else ""
                    acc_body = next(
                        (c for c in acc.children if c.type == "block"), None
                    )
                    if acc_name == "get" and acc_body:
                        body = self._emit_block_body(acc_body)
                        parts.append(
                            f"{self._ind()}local function get{name}()\n"
                            f"{body}\n"
                            f"{self._ind()}end"
                        )
                    elif acc_name == "set" and acc_body:
                        body = self._emit_block_body(acc_body)
                        parts.append(
                            f"{self._ind()}local function set{name}(value)\n"
                            f"{body}\n"
                            f"{self._ind()}end"
                        )
        return "\n\n".join(parts) if parts else f"{self._ind()}-- property {name} (auto-property)"

    def _emit_constructor_declaration(self, _node: Any) -> str:
        return f"{self._ind()}-- constructor (not applicable in Luau)"

    # -- statements -------------------------------------------------------

    def _emit_block(self, node: Any) -> str:
        return self._emit_block_body(node)

    def _emit_block_body(self, block_node: Any) -> str:
        self.indent += 1
        parts: list[str] = []
        for child in block_node.children:
            if child.type in ("{", "}"):
                continue
            if not child.is_named:
                continue
            result = self.emit(child)
            if result is not None:
                parts.append(result)
        self.indent -= 1
        return "\n".join(parts)

    def _emit_expression_statement(self, node: Any) -> str:
        for child in node.children:
            if child.is_named:
                expr = self.emit(child)
                return f"{self._ind()}{expr}"
        return ""

    def _emit_local_declaration_statement(self, node: Any) -> str:
        for child in node.children:
            if child.type == "variable_declaration":
                return self._emit_variable_decl_stmt(child)
        return ""

    def _emit_variable_decl_stmt(self, node: Any) -> str:
        results: list[str] = []
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                name = self._text(name_node) if name_node else ""
                value = self._get_declarator_value(child)
                if value is not None:
                    results.append(f"{self._ind()}local {name} = {value}")
                else:
                    results.append(f"{self._ind()}local {name}")
        return "\n".join(results)

    def _emit_return_statement(self, node: Any) -> str:
        expr_nodes = [c for c in node.children if c.is_named]
        if expr_nodes:
            return f"{self._ind()}return {self.emit(expr_nodes[0])}"
        return f"{self._ind()}return"

    def _emit_if_statement(self, node: Any, is_elseif: bool = False) -> str:
        cond_node = node.child_by_field_name("condition")
        cons_node = node.child_by_field_name("consequence")
        alt_node = node.child_by_field_name("alternative")

        cond = self.emit(cond_node) if cond_node else "true"
        keyword = "elseif" if is_elseif else "if"
        result = f"{self._ind()}{keyword} {cond} then\n"

        if cons_node:
            result += self._emit_block_body(cons_node)

        if alt_node:
            if alt_node.type == "if_statement":
                result += "\n" + self._emit_if_statement(alt_node, is_elseif=True)
                return result  # The nested if_statement handles its own 'end'
            else:
                # else block
                result += f"\n{self._ind()}else\n"
                result += self._emit_block_body(alt_node)

        if not is_elseif or alt_node is None or alt_node.type != "if_statement":
            result += f"\n{self._ind()}end"
        return result

    def _emit_for_statement(self, node: Any) -> str:
        init = node.child_by_field_name("initializer")
        cond = node.child_by_field_name("condition")
        update = node.child_by_field_name("update")
        body = node.child_by_field_name("body")

        # Detect simple counting loop: for (int i = start; i < end; i++)
        if (
            init
            and cond
            and update
            and init.type == "variable_declaration"
            and cond.type == "binary_expression"
            and update.type == "postfix_unary_expression"
        ):
            declarator = next(
                (c for c in init.children if c.type == "variable_declarator"),
                None,
            )
            if declarator:
                var_name = self._text(declarator.child_by_field_name("name"))
                start_val = self._get_declarator_value(declarator) or "0"
                op_node = cond.child_by_field_name("operator")
                right_node = cond.child_by_field_name("right")
                op = self._text(op_node) if op_node else ""
                end_val = self.emit(right_node) if right_node else ""

                if op == "<":
                    end_expr = f"{end_val} - 1"
                elif op == "<=":
                    end_expr = end_val
                else:
                    end_expr = end_val

                body_text = self._emit_block_body(body) if body else ""
                return (
                    f"{self._ind()}for {var_name} = {start_val}, {end_expr} do\n"
                    f"{body_text}\n"
                    f"{self._ind()}end"
                )

        # Fallback: while loop
        init_text = self._emit_variable_decl_stmt(init) if init and init.type == "variable_declaration" else ""
        cond_text = self.emit(cond) if cond else "true"
        update_text = self.emit(update) if update else ""
        body_text = self._emit_block_body(body) if body else ""
        lines = []
        if init_text:
            lines.append(init_text)
        lines.append(f"{self._ind()}while {cond_text} do")
        if body_text:
            lines.append(body_text)
        if update_text:
            lines.append(f"{self._ind()}    {update_text}")
        lines.append(f"{self._ind()}end")
        return "\n".join(lines)

    def _emit_foreach_statement(self, node: Any) -> str:
        var_node = node.child_by_field_name("left")
        collection_node = node.child_by_field_name("right")
        body = node.child_by_field_name("body")

        var_name = self._text(var_node) if var_node else "v"
        collection = self.emit(collection_node) if collection_node else "items"
        body_text = self._emit_block_body(body) if body else ""
        return (
            f"{self._ind()}for _, {var_name} in {collection} do\n"
            f"{body_text}\n"
            f"{self._ind()}end"
        )

    def _emit_while_statement(self, node: Any) -> str:
        cond_node = node.child_by_field_name("condition")
        body = node.child_by_field_name("body")
        cond = self.emit(cond_node) if cond_node else "true"
        body_text = self._emit_block_body(body) if body else ""
        return (
            f"{self._ind()}while {cond} do\n"
            f"{body_text}\n"
            f"{self._ind()}end"
        )

    # -- expressions ------------------------------------------------------

    def _emit_invocation_expression(self, node: Any) -> str:
        func_node = node.child_by_field_name("function")
        args_node = node.child_by_field_name("arguments")

        if func_node is None:
            return self._text(node)

        func_text = self._text(func_node)

        # -- Special functions ---
        if func_text == "Instantiate":
            return self._emit_instantiate(args_node)
        if func_text in ("Destroy", "DestroyImmediate"):
            return self._emit_destroy(args_node)

        # GetComponent<T>() and variants
        if func_node.type == "generic_name":
            ident = next(
                (c for c in func_node.children if c.type == "identifier"), None
            )
            if ident and self._text(ident) in (
                "GetComponent", "GetComponentInChildren", "GetComponentInParent",
                "GetComponents", "GetComponentsInChildren",
            ):
                return self._emit_get_component(func_node)

        # member_access_expression: check for special method patterns
        if func_node.type == "member_access_expression":
            name_node = func_node.child_by_field_name("name")
            expr_node = func_node.child_by_field_name("expression")
            method_name = self._text(name_node) if name_node else ""

            # Handle generic method on member: obj.GetComponent<T>()
            if name_node and name_node.type == "generic_name":
                generic_ident = next(
                    (c for c in name_node.children if c.type == "identifier"), None
                )
                if generic_ident and self._text(generic_ident) in (
                    "GetComponent", "GetComponentInChildren", "GetComponentInParent",
                ):
                    obj = self.emit(expr_node) if expr_node else ""
                    comp = self._emit_get_component(name_node)
                    return f"{obj}{comp}"

            obj = self.emit(expr_node) if expr_node else ""
            args = self._emit_args(args_node)

            # .SetActive(val) → .Visible = val
            if method_name == "SetActive":
                return f"{obj}.Visible = {args}"
            # .Add(item) → table.insert(obj, item)
            if method_name == "Add":
                return f"table.insert({obj}, {args})"
            # .Remove(item) → table.remove(obj, item)
            if method_name == "Remove":
                return f"table.remove({obj}, {args})"
            # .Contains(item) → table.find(obj, item)
            if method_name == "Contains":
                return f"table.find({obj}, {args})"
            # .ToString() → tostring(obj)
            if method_name == "ToString":
                return f"tostring({obj})"

            # Check full function text against API map
            mapped = self._check_api_map(func_text)
            if mapped is not None:
                return f"{mapped}({args})"

            return f"{obj}.{method_name}({args})"

        # Check bare identifier against API map (e.g. StartCoroutine)
        mapped = self._check_api_map(func_text)
        if mapped is not None:
            args = self._emit_args(args_node)
            return f"{mapped}({args})"

        func = self.emit(func_node)
        args = self._emit_args(args_node)
        return f"{func}({args})"

    def _emit_instantiate(self, args_node: Any) -> str:
        """Restructure ``Instantiate(prefab[, pos, rot])`` → ``prefab:Clone()``."""
        arg_nodes = [c for c in args_node.children if c.type == "argument"] if args_node else []
        if not arg_nodes:
            return "nil --[[ Instantiate: missing argument ]]"
        prefab = self.emit(self._named_children(arg_nodes[0])[0]) if self._named_children(arg_nodes[0]) else self._text(arg_nodes[0])
        if len(arg_nodes) > 1:
            extras = [self.emit(self._named_children(a)[0]) for a in arg_nodes[1:] if self._named_children(a)]
            return f"{prefab}:Clone() --[[ TODO: set CFrame from {', '.join(extras)} ]]"
        return f"{prefab}:Clone()"

    def _emit_destroy(self, args_node: Any) -> str:
        arg_nodes = [c for c in args_node.children if c.type == "argument"] if args_node else []
        if not arg_nodes:
            return ":Destroy()"
        obj = self.emit(self._named_children(arg_nodes[0])[0]) if self._named_children(arg_nodes[0]) else self._text(arg_nodes[0])
        return f"{obj}:Destroy()"

    def _emit_get_component(self, func_node: Any) -> str:
        """Convert ``GetComponent<T>()`` → ``:FindFirstChildOfClass("RobloxT")``."""
        ident = next(
            (c for c in func_node.children if c.type == "identifier"), None
        )
        method_name = self._text(ident) if ident else "GetComponent"
        roblox_method = API_CALL_MAP.get(method_name, ":FindFirstChildOfClass")

        type_args = next(
            (c for c in func_node.children if c.type == "type_argument_list"),
            None,
        )
        if type_args:
            type_idents = [c for c in type_args.children if c.type in ("identifier", "predefined_type")]
            if type_idents:
                csharp_type = self._text(type_idents[0])
                roblox_type = TYPE_MAP.get(csharp_type, csharp_type)
                return f'{roblox_method}("{roblox_type}")'
        return f"{roblox_method}()"

    def _emit_member_access_expression(self, node: Any) -> str:
        raw = self._text(node)
        expr_node = node.child_by_field_name("expression")
        name_node = node.child_by_field_name("name")
        name = self._text(name_node) if name_node else ""

        # Check full raw text against API map
        mapped = self._check_api_map(raw)
        if mapped is not None:
            return mapped

        obj = self.emit(expr_node) if expr_node else ""

        # .Length / .Count → #obj
        if name in ("Length", "Count"):
            return f"#{obj}"

        return f"{obj}.{name}"

    def _emit_object_creation_expression(self, node: Any) -> str:
        type_node = node.child_by_field_name("type")
        args_node = node.child_by_field_name("arguments")
        type_text = self._text(type_node) if type_node else ""
        args = self._emit_args(args_node) if args_node else ""

        # new Vector3(...) → Vector3.new(...)
        type_map = {
            "Vector3": "Vector3.new",
            "Vector2": "Vector2.new",
            "Color": "Color3.new",
            "Color32": "Color3.new",
        }
        if type_text in type_map:
            return f"{type_map[type_text]}({args})"
        # new List<T>() / new Dictionary<K,V>() → {}
        if type_node and type_node.type == "generic_name":
            ident = next((c for c in type_node.children if c.type == "identifier"), None)
            if ident and self._text(ident) in ("List", "Dictionary", "HashSet"):
                return "{}"
        # new SomeType() → nil with comment
        if not args:
            return f"nil --[[ new {type_text}() ]]"
        return f"nil --[[ new {type_text}({args}) ]]"

    def _emit_assignment_expression(self, node: Any) -> str:
        left_node = node.child_by_field_name("left")
        op_node = node.child_by_field_name("operator")
        right_node = node.child_by_field_name("right")
        left = self.emit(left_node)
        right = self.emit(right_node)
        op = self._text(op_node) if op_node else "="

        # Event subscription: obj.Event += Handler → obj.Event:Connect(Handler)
        if op == "+=" and self._looks_like_event_target(left_node):
            return f"{left}:Connect({right})"
        # Event unsubscription: obj.Event -= Handler → comment (no direct Roblox equiv)
        if op == "-=" and self._looks_like_event_target(left_node):
            return f"-- {left} -= {right} (TODO: Disconnect)"

        return f"{left} {op} {right}"

    def _looks_like_event_target(self, node: Any) -> bool:
        """Heuristic: is this a likely C# event (member access ending in
        an event-like name such as onClick, OnClick, Collided, etc.)?"""
        if node is None:
            return False
        text = self._text(node)

        # Known Unity event member names (exact matches on the member name)
        _KNOWN_EVENTS = {
            "onClick", "OnClick", "onValueChanged", "OnValueChanged",
            "onEndEdit", "OnEndEdit", "onSubmit", "OnSubmit",
            "onSelect", "OnSelect", "onDeselect", "OnDeselect",
            "AddListener", "RemoveListener",
            "Touched", "TouchEnded",
            "MouseClick", "MouseHoverEnter", "MouseHoverLeave",
            "InputBegan", "InputEnded", "InputChanged",
            "AncestryChanged", "ChildAdded", "ChildRemoved",
            "Destroying", "DescendantAdded", "DescendantRemoving",
        }

        if node.type == "member_access_expression":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = self._text(name_node)
                # Exact match against known events
                if name in _KNOWN_EVENTS:
                    return True
                # Pattern-based: starts with "On" (but not "One", "Only", etc.)
                if name.startswith("On") and len(name) > 2 and name[2].isupper():
                    return True
                # Ends with common event suffixes
                if name.endswith(("Event", "Changed", "Completed",
                                  "Started", "Ended", "Triggered",
                                  "Clicked", "Pressed", "Released")):
                    return True

        # Fallback: check the full text for known event patterns
        for evt in _KNOWN_EVENTS:
            if text.endswith(evt):
                return True
        return False

    def _emit_binary_expression(self, node: Any) -> str:
        left_node = node.child_by_field_name("left")
        op_node = node.child_by_field_name("operator")
        right_node = node.child_by_field_name("right")

        left = self.emit(left_node)
        right = self.emit(right_node)
        op = self._text(op_node) if op_node else "+"

        # Operator conversions
        if op == "!=":
            op = "~="
        elif op == "&&":
            op = "and"
        elif op == "||":
            op = "or"
        elif op == "+":
            # String concatenation: if either side is a string literal
            if self._is_string_typed(left_node) or self._is_string_typed(right_node):
                op = ".."

        return f"{left} {op} {right}"

    def _emit_prefix_unary_expression(self, node: Any) -> str:
        op = ""
        operand = None
        for child in node.children:
            if child.is_named:
                operand = child
            else:
                op = self._text(child)
        expr = self.emit(operand) if operand else ""
        if op == "!":
            return f"not {expr}"
        return f"{op}{expr}"

    def _emit_postfix_unary_expression(self, node: Any) -> str:
        operand = None
        op = ""
        for child in node.children:
            if child.is_named:
                operand = child
            elif child.type in ("++", "--"):
                op = self._text(child)
        expr = self.emit(operand) if operand else ""
        if op == "++":
            return f"{expr} += 1"
        if op == "--":
            return f"{expr} -= 1"
        return f"{expr}{op}"

    def _emit_conditional_expression(self, node: Any) -> str:
        cond = self.emit(node.child_by_field_name("condition"))
        cons = self.emit(node.child_by_field_name("consequence"))
        alt = self.emit(node.child_by_field_name("alternative"))
        return f"if {cond} then {cons} else {alt}"

    def _emit_parenthesized_expression(self, node: Any) -> str:
        inner = next((c for c in node.children if c.is_named), None)
        return f"({self.emit(inner)})" if inner else "()"

    def _emit_element_access_expression(self, node: Any) -> str:
        # obj[index] — emit as-is (Luau uses 1-based, but keep for now)
        expr = node.children[0] if node.children else None
        bracket_args = node.child_by_field_name("arguments") or next(
            (c for c in node.children if c.type == "bracketed_argument_list"), None
        )
        obj = self.emit(expr) if expr else ""
        if bracket_args:
            indices = [self.emit(c) for c in bracket_args.children if c.is_named]
            return f"{obj}[{', '.join(indices)}]"
        return self._text(node)

    def _emit_cast_expression(self, node: Any) -> str:
        # (Type)expr → just expr (strip the cast)
        # The value is the last named child
        named = self._named_children(node)
        if len(named) >= 2:
            return self.emit(named[-1])
        return self._text(node)

    # -- literals ---------------------------------------------------------

    def _emit_this_expression(self, _node: Any) -> str:
        return "self"

    def _emit_this(self, _node: Any) -> str:
        # tree-sitter-c-sharp uses node type "this" (not "this_expression")
        return "self"

    def _emit_identifier(self, node: Any) -> str:
        text = self._text(node)
        if text == "this":
            return "self"
        return text

    def _emit_string_literal(self, node: Any) -> str:
        # Preserve string literals unchanged — key AST advantage
        return self._text(node)

    def _emit_verbatim_string_literal(self, node: Any) -> str:
        return self._text(node)

    def _emit_interpolated_string_expression(self, node: Any) -> str:
        # $"hello {x}" → string.format("hello %s", tostring(x))
        format_parts: list[str] = []
        format_args: list[str] = []
        for child in node.children:
            if child.type == "interpolated_string_text":
                # Literal text portion — escape any existing % for string.format
                format_parts.append(self._text(child).replace("%", "%%"))
            elif child.type == "interpolation":
                # {expression} portion
                expr_nodes = [c for c in child.children if c.is_named]
                if expr_nodes:
                    format_parts.append("%s")
                    format_args.append(f"tostring({self.emit(expr_nodes[0])})")
                else:
                    format_parts.append("%s")
                    format_args.append("nil")
            # Skip $, ", { } tokens
        format_str = "".join(format_parts)
        if format_args:
            return f'string.format("{format_str}", {", ".join(format_args)})'
        return f'"{format_str}"'

    def _emit_character_literal(self, node: Any) -> str:
        return self._text(node)

    def _emit_integer_literal(self, node: Any) -> str:
        return self._text(node)

    def _emit_real_literal(self, node: Any) -> str:
        text = self._text(node)
        # Strip f/d/m suffixes
        if text.endswith(("f", "F", "d", "D", "m", "M")):
            text = text[:-1]
        return text

    def _emit_boolean_literal(self, node: Any) -> str:
        text = self._text(node)
        return text.lower()

    def _emit_null_literal(self, _node: Any) -> str:
        return "nil"

    def _emit_comment(self, node: Any) -> str:
        text = self._text(node)
        # Convert // comment → -- comment
        if text.startswith("//"):
            return f"{self._ind()}--{text[2:]}"
        # Convert /* ... */ → --[[ ... ]]
        if text.startswith("/*"):
            inner = text[2:-2] if text.endswith("*/") else text[2:]
            return f"{self._ind()}--[[ {inner.strip()} ]]"
        return f"{self._ind()}{text}"

    # -- other node types -------------------------------------------------

    def _emit_attribute_list(self, _node: Any) -> str:
        # Attributes are handled in field_declaration context
        return ""

    def _emit_modifier(self, _node: Any) -> str:
        return ""

    def _emit_predefined_type(self, _node: Any) -> str:
        return ""

    def _emit_implicit_type(self, _node: Any) -> str:
        return ""

    def _emit_variable_declaration(self, node: Any) -> str:
        return self._emit_variable_decl_stmt(node)

    def _emit_argument(self, node: Any) -> str:
        named = self._named_children(node)
        return self.emit(named[0]) if named else self._text(node)

    def _emit_base_list(self, _node: Any) -> str:
        return ""

    def _emit_qualified_name(self, node: Any) -> str:
        return self._text(node)

    def _emit_generic_name(self, node: Any) -> str:
        return self._text(node)

    def _emit_type_argument_list(self, node: Any) -> str:
        return self._text(node)

    def _emit_array_type(self, _node: Any) -> str:
        return ""

    def _emit_nullable_type(self, _node: Any) -> str:
        return ""

    def _emit_break_statement(self, _node: Any) -> str:
        return f"{self._ind()}break"

    def _emit_continue_statement(self, _node: Any) -> str:
        return f"{self._ind()}continue"

    def _emit_yield_statement(self, node: Any) -> str:
        # yield return null → task.wait()
        # yield return new WaitForSeconds(n) → task.wait(n)
        # yield return expr → task.wait() -- expr
        expr_nodes = [c for c in node.children if c.is_named]
        if not expr_nodes:
            self.services.add("RunService")
            return f"{self._ind()}task.wait()"
        expr_node = expr_nodes[0]
        expr_text = self._text(expr_node)
        if expr_text == "null":
            return f"{self._ind()}task.wait()"
        # new WaitForSeconds(n)
        if expr_node.type == "object_creation_expression":
            type_node = expr_node.child_by_field_name("type")
            type_text = self._text(type_node) if type_node else ""
            if type_text == "WaitForSeconds":
                args_node = expr_node.child_by_field_name("arguments")
                args = self._emit_args(args_node) if args_node else ""
                return f"{self._ind()}task.wait({args})"
            if type_text in ("WaitForEndOfFrame", "WaitForFixedUpdate"):
                return f"{self._ind()}task.wait()"
        return f"{self._ind()}task.wait() --[[ yield {expr_text} ]]"

    def _emit_throw_statement(self, node: Any) -> str:
        expr = next((c for c in node.children if c.is_named), None)
        if expr:
            return f"{self._ind()}error({self.emit(expr)})"
        return f"{self._ind()}error()"

    def _emit_try_statement(self, node: Any) -> str:
        # Approximate: extract try body, wrap in pcall-style comment
        parts: list[str] = []
        for child in node.children:
            if child.type == "block":
                parts.append(f"{self._ind()}-- try")
                parts.append(self._emit_block_body(child))
            elif child.type == "catch_clause":
                body = next((c for c in child.children if c.type == "block"), None)
                if body:
                    parts.append(f"{self._ind()}-- catch")
                    parts.append(self._emit_block_body(body))
            elif child.type == "finally_clause":
                body = next((c for c in child.children if c.type == "block"), None)
                if body:
                    parts.append(f"{self._ind()}-- finally")
                    parts.append(self._emit_block_body(body))
        return "\n".join(parts)

    def _emit_switch_statement(self, node: Any) -> str:
        cond_node = node.child_by_field_name("value") or next(
            (c for c in node.children if c.is_named and c.type not in ("switch_body",)), None
        )
        body = node.child_by_field_name("body") or next(
            (c for c in node.children if c.type == "switch_body"), None
        )
        cond = self.emit(cond_node) if cond_node else "value"
        parts = [f"{self._ind()}-- switch {cond}"]
        if body:
            for section in body.children:
                if section.type == "switch_section":
                    labels = [c for c in section.children if "label" in c.type]
                    stmts = [c for c in section.children if c.is_named and "label" not in c.type]
                    for label in labels:
                        parts.append(f"{self._ind()}-- {self._text(label).strip()}")
                    for stmt in stmts:
                        parts.append(self.emit(stmt))
        return "\n".join(parts)

    def _emit_do_statement(self, node: Any) -> str:
        cond_node = node.child_by_field_name("condition")
        body = node.child_by_field_name("body") or next(
            (c for c in node.children if c.type == "block"), None
        )
        cond = self.emit(cond_node) if cond_node else "true"
        body_text = self._emit_block_body(body) if body else ""
        return (
            f"{self._ind()}repeat\n"
            f"{body_text}\n"
            f"{self._ind()}until not ({cond})"
        )

    def _emit_lambda_expression(self, node: Any) -> str:
        # (args) => expr  or  (args) => { body }
        params_node = node.child_by_field_name("parameters") or next(
            (c for c in node.children if c.type == "parameter_list"), None
        )
        body_node = node.child_by_field_name("body") or next(
            (c for c in node.children if c.type in ("block", "expression_statement")), None
        )
        params = self._emit_param_names(params_node) if params_node else ""
        # Single-parameter lambda without parens
        if params_node is None:
            for child in node.children:
                if child.type == "identifier":
                    params = self._text(child)
                    break
        if body_node and body_node.type == "block":
            body = self._emit_block_body(body_node)
            return (
                f"function({params})\n"
                f"{body}\n"
                f"{self._ind()}end"
            )
        elif body_node:
            expr = self.emit(body_node)
            return f"function({params}) return {expr} end"
        return f"function({params}) end"

    def _emit_anonymous_method_expression(self, node: Any) -> str:
        # delegate(args) { body } → function(args) ... end
        params_node = next(
            (c for c in node.children if c.type == "parameter_list"), None
        )
        body_node = next(
            (c for c in node.children if c.type == "block"), None
        )
        params = self._emit_param_names(params_node) if params_node else ""
        if body_node:
            body = self._emit_block_body(body_node)
            return (
                f"function({params})\n"
                f"{body}\n"
                f"{self._ind()}end"
            )
        return f"function({params}) end"

    # -- helpers ----------------------------------------------------------

    def _emit_args(self, args_node: Any) -> str:
        if args_node is None:
            return ""
        parts = []
        for child in args_node.children:
            if child.type == "argument":
                parts.append(self._emit_argument(child))
        return ", ".join(parts)

    def _emit_param_names(self, params_node: Any) -> str:
        if params_node is None:
            return ""
        names = []
        for child in params_node.children:
            if child.type == "parameter":
                name_node = child.child_by_field_name("name")
                if name_node:
                    names.append(self._text(name_node))
        return ", ".join(names)

    def _get_declarator_value(self, declarator: Any) -> str | None:
        """Extract the initializer expression from a variable_declarator."""
        found_eq = False
        for child in declarator.children:
            if child.type == "=" or self._text(child) == "=":
                found_eq = True
            elif found_eq:
                return self.emit(child)
        # Also check for equals_value_clause wrapper
        for child in declarator.children:
            if child.type == "equals_value_clause":
                for inner in child.children:
                    if inner.is_named:
                        return self.emit(inner)
        return None

    def _check_api_map(self, raw_text: str) -> str | None:
        """Check if *raw_text* matches an API_CALL_MAP key."""
        for api_key in self._sorted_api_keys:
            if raw_text == api_key:
                replacement = API_CALL_MAP[api_key]
                self.api_subs += 1
                self._track_service(replacement)
                return replacement
        return None

    def _is_string_typed(self, node: Any) -> bool:
        """Heuristic: is this expression clearly a string?"""
        if node is None:
            return False
        if node.type == "string_literal":
            return True
        if node.type == "invocation_expression":
            func = node.child_by_field_name("function")
            if func and func.type == "member_access_expression":
                name_node = func.child_by_field_name("name")
                if name_node and self._text(name_node) == "ToString":
                    return True
        if node.type == "binary_expression":
            op = node.child_by_field_name("operator")
            if op and self._text(op) == "+":
                return (
                    self._is_string_typed(node.child_by_field_name("left"))
                    or self._is_string_typed(node.child_by_field_name("right"))
                )
        return False


def _compute_confidence(
    original: str,
    output: str,
    warnings: list[str],
    *,
    api_subs: int = 0,
    ast_driven: bool = False,
) -> float:
    """Compute a transpilation confidence score using multiple signals.

    Signals considered:
      - Ratio of lines changed (baseline — more changes = more transformation)
      - AST vs. regex path (AST is inherently more reliable)
      - Number of API substitutions made (more = better coverage)
      - Presence of residual C# artifacts (braces, class keyword = problems)
      - Placeholder comments left behind (-- TODO, -- comment mappings)
      - Warning count (more warnings = lower confidence)
      - Trivial/empty scripts (nothing to convert)
    """
    orig_lines = original.splitlines()
    out_lines = output.splitlines()
    non_blank = [l for l in orig_lines if l.strip()]
    code_lines = [l for l in non_blank if not l.strip().startswith("//")]

    # Trivial / near-empty scripts: low confidence (flag for review)
    if len(code_lines) <= 1:
        return 0.3

    # Base: ratio of lines that changed
    changed = sum(a != b for a, b in zip(orig_lines, out_lines))
    base = min(1.0, changed / max(len(orig_lines), 1) * 1.5)

    # Bonuses
    if ast_driven:
        base = min(1.0, base + 0.15)
    if api_subs > 0:
        base = min(1.0, base + 0.05 * min(api_subs, 5))

    # Penalties: residual C# artifacts indicate incomplete conversion
    remaining_braces = output.count("{") + output.count("}")
    if remaining_braces > 0:
        base -= min(0.2, remaining_braces * 0.02)
    if re.search(r"\bclass\s+\w+", output):
        base -= 0.1
    # Placeholder comments from API_CALL_MAP (lines starting with "-- ")
    placeholder_count = sum(
        1 for line in out_lines
        if line.strip().startswith("-- ") and (
            "TODO" in line or "no direct" in line or "manual" in line.lower()
            or "use " in line.lower()
        )
    )
    if placeholder_count > 0:
        base -= min(0.15, placeholder_count * 0.03)
    # Warning penalty
    if warnings:
        base -= min(0.1, len(warnings) * 0.02)

    return max(0.0, min(1.0, base))


def _has_parse_errors(root: Any) -> bool:
    """Check if the tree-sitter parse tree contains ERROR nodes."""
    if root.type == "ERROR":
        return True
    for child in root.children:
        if _has_parse_errors(child):
            return True
    return False


def _ast_transpile_luau(
    source: str,
    serialized_refs: dict[str, str] | None = None,
) -> tuple[str, float, list[str]] | None:
    """
    Attempt AST-driven transpilation.  Returns ``None`` if the source cannot
    be cleanly parsed (has ERROR nodes), signalling the caller to fall back
    to the regex pipeline.
    """
    if not _TS_AVAILABLE or _ts_parser is None:
        return None

    tree = _ts_parser.parse(source.encode("utf-8"))
    if _has_parse_errors(tree.root_node):
        return None

    emitter = _LuauEmitter(source, serialized_refs)
    luau = emitter.emit(tree.root_node)

    # Clean up multiple blank lines
    luau = re.sub(r"\n{3,}", "\n\n", luau)

    # Add service import header
    if emitter.services:
        lines = []
        for svc in sorted(emitter.services):
            if svc in SERVICE_IMPORTS:
                lines.append(SERVICE_IMPORTS[svc])
        if lines:
            luau = "\n".join(lines) + "\n\n" + luau

    confidence = _compute_confidence(
        source, luau, emitter.warnings,
        api_subs=emitter.api_subs, ast_driven=True,
    )

    return luau, confidence, emitter.warnings


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
      2. Uses client-only APIs (Input, Camera, GUI, etc.) → LocalScript
      3. Uses server-only APIs (networking attrs, PlayerPrefs, Physics) → Script
      4. Has only client-side lifecycle hooks → LocalScript
      5. Default → Script (server)
    """
    client_score = 0
    server_score = 0

    if ast_info:
        # Pure utility / data class — no MonoBehaviour, no lifecycle hooks
        _BEHAVIOUR_BASES = {"MonoBehaviour", "NetworkBehaviour", "StateMachineBehaviour"}
        if ast_info.base_class not in _BEHAVIOUR_BASES and not ast_info.lifecycle_hooks:
            if ast_info.class_name:
                return "ModuleScript"

        # Score based on detected API usage
        for api in ast_info.unity_apis_used:
            if api in _CLIENT_INDICATORS:
                client_score += 1
            if api in _SERVER_INDICATORS:
                server_score += 1

        # Client-only lifecycle hooks get stronger weight (2 points each)
        for hook in ast_info.lifecycle_hooks:
            if hook in _CLIENT_LIFECYCLE:
                client_score += 2

    # Fallback: regex scan for patterns AST might miss
    for pattern in _CLIENT_INDICATORS:
        if pattern.startswith("[") or pattern.startswith("On"):
            continue  # skip attribute/lifecycle patterns for regex
        if pattern in source:
            client_score += 1
    for pattern in _SERVER_INDICATORS:
        if pattern in source:
            server_score += 1

    # Client wins on tie (client-side patterns are more specific signals)
    if client_score > 0 and client_score >= server_score:
        return "LocalScript"

    # Only classify as Script if there's actual evidence of server work,
    # or if the script has lifecycle hooks (it does something at runtime)
    if server_score > 0:
        return "Script"

    # Has lifecycle hooks but no strong client/server signal → default server
    if ast_info and ast_info.lifecycle_hooks:
        return "Script"

    # No signals at all but has a MonoBehaviour base → Script
    if ast_info and ast_info.base_class in _BEHAVIOUR_BASES:
        return "Script"

    return "Script"


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
    # SetActive → Visible assignment (handles any variable, e.g. tutorialBlocker.SetActive(false))
    (re.compile(r"(\w[\w.]*)\.SetActive\(([^)]*)\)"), r"\1.Visible = \2"),
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


def _rule_based_transpile(
    csharp: str,
    serialized_refs: dict[str, str] | None = None,
) -> tuple[str, float, list[str]]:
    """
    Convert C# source to Luau using AST-driven emission (preferred) with
    regex fallback.

    When tree-sitter is available and the source parses without errors, the
    AST emitter walks the syntax tree to produce structurally correct Luau.
    Otherwise, the legacy regex pipeline handles the conversion.

    Args:
        csharp: Original C# source text.
        serialized_refs: Optional field_name → prefab_name mapping from
            MonoBehaviour YAML.  When provided, ``[SerializeField]`` fields
            referencing prefabs are converted to ``ServerStorage:WaitForChild()``
            calls instead of being stripped.

    Returns:
        (luau_source, confidence, warnings)
    """
    # --- AST path (preferred) ---
    ast_result = _ast_transpile_luau(csharp, serialized_refs)
    if ast_result is not None:
        return ast_result

    # --- Regex fallback (for snippets / missing tree-sitter) ---
    luau = csharp
    warnings: list[str] = []
    need_server_storage = False

    # Try AST-based analysis for structural insight
    ast_info = _parse_csharp_ast(csharp)

    # Handle [SerializeField] declarations before general transforms.
    # When we have serialized_refs (from MonoBehaviour YAML), replace field
    # declarations that reference prefabs with ServerStorage:WaitForChild().
    need_sound_service = False

    if serialized_refs:
        def _replace_serialize_field(m: re.Match) -> str:
            nonlocal need_server_storage, need_sound_service
            field_name = m.group("fname")
            if field_name in serialized_refs:
                ref_value = serialized_refs[field_name]
                if ref_value.startswith("audio:"):
                    # AudioClip reference → preloaded Sound object
                    audio_filename = ref_value[len("audio:"):]
                    need_sound_service = True
                    return (
                        f'local {field_name} = Instance.new("Sound")\n'
                        f'{field_name}.Name = "{field_name}"\n'
                        f'{field_name}.SoundId = "-- TODO: upload {audio_filename}"'
                    )
                else:
                    # Prefab reference → ServerStorage:WaitForChild()
                    need_server_storage = True
                    return f'local {field_name} = ServerStorage:WaitForChild("{ref_value}")'
            # Field not in our ref map — strip the attribute, keep the declaration
            return m.group("decl")

        # Match: [SerializeField] <modifiers> <Type> <name> <optional init> ;
        luau = re.sub(
            r"\[SerializeField\]\s*"
            r"(?P<decl>"
            r"(?:(?:public|private|protected|internal|static|readonly)\s+)*"
            r"\w+(?:<[^>]*>)?\s+"
            r"(?P<fname>\w+)"
            r"(?:\s*=[^;]*)?"
            r"\s*;)",
            _replace_serialize_field,
            luau,
        )
    else:
        # No ref data — just strip [SerializeField] attributes
        luau = re.sub(r"\[SerializeField\]\s*", "", luau)

    # Apply basic structural transformations
    for pattern, replacement in _RULE_PATTERNS:
        luau = pattern.sub(replacement, luau)

    # Apply comprehensive API mappings
    luau, api_subs = _apply_api_mappings(luau)

    # Convert C# generic method calls to Luau string-argument form
    # e.g. :FindFirstChildOfClass<AudioSource>() → :FindFirstChildOfClass("Sound")
    def _replace_generic_type(m: re.Match) -> str:
        method = m.group(1)
        csharp_type = m.group(2)
        roblox_type = TYPE_MAP.get(csharp_type, csharp_type)
        return f'{method}("{roblox_type}")'

    luau = re.sub(
        r"(:\w+)<(\w+)>\(\)",
        _replace_generic_type,
        luau,
    )

    # Strip using directives (no equivalent in Luau)
    luau = re.sub(r"^using\s+[\w.]+;\s*\n", "", luau, flags=re.MULTILINE)

    # Strip namespace wrapper and its closing brace
    luau = re.sub(r"\bnamespace\s+\w[\w.]*\s*\{?\s*\n?", "", luau)

    # Strip class declarations (with optional inheritance) and their opening brace
    luau = re.sub(
        r"\b(?:public\s+|private\s+|internal\s+|abstract\s+|sealed\s+|partial\s+)*"
        r"class\s+\w+\s*(?::\s*[\w.,\s<>]+)?\s*\{?\s*\n?",
        "", luau,
    )

    # Strip access modifiers
    luau = re.sub(r"\b(public|private|protected|internal|static|sealed|abstract|partial|virtual|override|readonly|const)\s+", "", luau)

    # Strip return type annotations from methods (e.g., "int Foo(" → "local function Foo(")
    luau = re.sub(
        r"\b(?:int|float|double|bool|string|void|var|Vector[23]|Color|GameObject|Transform|Quaternion|List<[^>]*>|IEnumerator|AudioClip|AudioSource)\s+(\w+)\s*\(",
        r"local function \1(",
        luau,
    )

    # Strip type annotations from variable declarations (e.g., "List<int> items = " → "local items = ")
    luau = re.sub(
        r"\b(?:var|List<[^>]*>|Dictionary<[^>]*>|int\[\]|float\[\]|string\[\]|bool\[\]|GameObject\[\]|Transform\[\]|Vector[23]\[\]|AudioClip\[\]|AudioClip|AudioSource)\s+(\w+)\s*=",
        r"local \1 =",
        luau,
    )

    # Strip standalone AudioClip/AudioSource field declarations without initializer
    # e.g. "public AudioClip coinSound;" → "local coinSound = nil"
    luau = re.sub(
        r"\b(?:AudioClip|AudioSource)\s+(\w+)\s*;",
        r"local \1 = nil",
        luau,
    )

    # Convert C# type casts to nothing
    luau = re.sub(r"\((?:int|float|double|string|bool)\)\s*", "", luau)

    # Convert C# new keyword for common types
    luau = re.sub(r"\bnew\s+Vector3\(", "Vector3.new(", luau)
    luau = re.sub(r"\bnew\s+Vector2\(", "Vector2.new(", luau)
    luau = re.sub(r"\bnew\s+Color\(", "Color3.new(", luau)
    luau = re.sub(r"\bnew\s+List<[^>]*>\(\)", "{}", luau)
    luau = re.sub(r"\bnew\s+Dictionary<[^>]*>\(\)", "{}", luau)
    luau = re.sub(r"\bnew\s+\w+\(\)", "nil --[[ new object ]]", luau)

    # Convert != to ~= (Luau inequality operator)
    luau = re.sub(r"!=", "~=", luau)

    # Convert && to and, || to or, ! to not (with word boundary)
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
    # Note: (?:int|local) because _RULE_PATTERNS may already convert "int" to "local"
    luau = re.sub(
        r"for\s*\(\s*(?:(?:int|local)\s+)?(\w+)\s*=\s*(\d+)\s*;\s*\1\s*<\s*(\w+)\s*;\s*\1\+\+\s*\)",
        r"for \1 = \2, \3 - 1 do",
        luau,
    )

    # Convert for(int i = 0; i <= n; i++) to for i = 0, n do
    luau = re.sub(
        r"for\s*\(\s*(?:(?:int|local)\s+)?(\w+)\s*=\s*(\d+)\s*;\s*\1\s*<=\s*(\w+)\s*;\s*\1\+\+\s*\)",
        r"for \1 = \2, \3 do",
        luau,
    )

    # Convert foreach (Type item in collection) to for _, item in collection do
    luau = re.sub(
        r"foreach\s*\(\s*\w+\s+(\w+)\s+in\s+(\w+)\s*\)",
        r"for _, \1 in \2 do",
        luau,
    )

    # Convert while (condition) { to while condition do
    luau = re.sub(r"\bwhile\s*\(([^)]+)\)\s*\{", r"while \1 do", luau)

    # Convert } else if (condition) { to elseif condition then  (MUST be before standalone if)
    luau = re.sub(r"\}\s*else\s+if\s*\(([^)]+)\)\s*\{", r"elseif \1 then", luau)

    # Convert } else { to else  (MUST be before standalone if)
    luau = re.sub(r"\}\s*else\s*\{", "else", luau)

    # Convert if (condition) { to if condition then
    luau = re.sub(r"\bif\s*\(([^)]+)\)\s*\{", r"if \1 then", luau)

    # Convert remaining closing braces to end (heuristic: standalone } on a line)
    luau = re.sub(r"^\s*\}\s*$", "end", luau, flags=re.MULTILINE)

    # Strip semicolons at end of lines (Luau doesn't need them)
    luau = re.sub(r";\s*$", "", luau, flags=re.MULTILINE)

    # Convert ternary operator: condition ? a : b → if condition then a else b
    luau = re.sub(
        r"(\w+)\s*\?\s*([^:]+)\s*:\s*([^;\n]+)",
        r"if \1 then \2 else \3",
        luau,
    )

    # Convert .Length / .Count to # operator
    luau = re.sub(r"(\w+)\.Length\b", r"#\1", luau)
    luau = re.sub(r"(\w+)\.Count\b", r"#\1", luau)

    # Convert .Add() to table.insert()
    luau = re.sub(r"(\w+)\.Add\(([^)]+)\)", r"table.insert(\1, \2)", luau)

    # Convert .Remove() to table.remove()
    luau = re.sub(r"(\w+)\.Remove\(([^)]+)\)", r"table.remove(\1, \2)", luau)

    # Convert .Contains() to table.find()
    luau = re.sub(r"(\w+)\.Contains\(([^)]+)\)", r"table.find(\1, \2)", luau)

    # Convert .ToString() to tostring()
    luau = re.sub(r"(\w+)\.ToString\(\)", r"tostring(\1)", luau)

    # Coroutine: yield return null → task.wait()
    luau = re.sub(r"\byield\s+return\s+null\b", "task.wait()", luau)
    # Coroutine: yield return new WaitForSeconds(n) → task.wait(n)
    luau = re.sub(
        r"\byield\s+return\s+new\s+WaitForSeconds\(([^)]+)\)",
        r"task.wait(\1)",
        luau,
    )
    # Coroutine: yield return new WaitForEndOfFrame/WaitForFixedUpdate() → task.wait()
    luau = re.sub(
        r"\byield\s+return\s+new\s+WaitFor(?:EndOfFrame|FixedUpdate)\(\)",
        "task.wait()",
        luau,
    )

    # Event subscription: obj.OnClick += handler → obj.OnClick:Connect(handler)
    luau = re.sub(
        r"(\w[\w.]*\.(?:On\w+|on\w+|\w+Event|\w+Changed))\s*\+=\s*([^;\n]+)",
        r"\1:Connect(\2)",
        luau,
    )

    # C# string interpolation: $"text {expr}" → string.format("text %s", tostring(expr))
    def _convert_interpolated_string(m: re.Match) -> str:
        content = m.group(1)
        fmt_parts: list[str] = []
        args: list[str] = []
        i = 0
        while i < len(content):
            if content[i] == "{":
                # Find matching }
                depth = 1
                j = i + 1
                while j < len(content) and depth > 0:
                    if content[j] == "{":
                        depth += 1
                    elif content[j] == "}":
                        depth -= 1
                    j += 1
                expr = content[i + 1 : j - 1]
                fmt_parts.append("%s")
                args.append(f"tostring({expr})")
                i = j
            else:
                # Escape existing % for string.format
                if content[i] == "%":
                    fmt_parts.append("%%")
                else:
                    fmt_parts.append(content[i])
                i += 1
        fmt_str = "".join(fmt_parts)
        if args:
            return f'string.format("{fmt_str}", {", ".join(args)})'
        return f'"{fmt_str}"'

    luau = re.sub(r'\$"([^"]*)"', _convert_interpolated_string, luau)

    # Convert Mathf calls to math calls
    luau = re.sub(r"\bMathf\.Abs\b", "math.abs", luau)
    luau = re.sub(r"\bMathf\.Sin\b", "math.sin", luau)
    luau = re.sub(r"\bMathf\.Cos\b", "math.cos", luau)
    luau = re.sub(r"\bMathf\.Sqrt\b", "math.sqrt", luau)
    luau = re.sub(r"\bMathf\.Floor\b", "math.floor", luau)
    luau = re.sub(r"\bMathf\.Ceil\b", "math.ceil", luau)
    luau = re.sub(r"\bMathf\.Min\b", "math.min", luau)
    luau = re.sub(r"\bMathf\.Max\b", "math.max", luau)
    luau = re.sub(r"\bMathf\.Clamp\(([^,]+),\s*([^,]+),\s*([^)]+)\)", r"math.clamp(\1, \2, \3)", luau)
    luau = re.sub(r"\bMathf\.Lerp\(([^,]+),\s*([^,]+),\s*([^)]+)\)", r"(\1 + (\2 - \1) * \3)", luau)
    luau = re.sub(r"\bMathf\.PI\b", "math.pi", luau)
    luau = re.sub(r"\bMathf\.Infinity\b", "math.huge", luau)

    # Convert Time.deltaTime to common Roblox pattern
    luau = re.sub(r"\bTime\.deltaTime\b", "dt", luau)

    # Clean up multiple blank lines
    luau = re.sub(r"\n{3,}", "\n\n", luau)

    # Add Roblox service imports at the top if AST detected usage
    service_header = ""
    services_needed: set[str] = set()
    if ast_info and ast_info.services_needed:
        services_needed |= ast_info.services_needed
    if need_server_storage:
        services_needed.add("ServerStorage")
    if need_sound_service:
        services_needed.add("SoundService")
    if services_needed:
        lines = []
        for svc in sorted(services_needed):
            if svc in SERVICE_IMPORTS:
                lines.append(SERVICE_IMPORTS[svc])
        if lines:
            service_header = "\n".join(lines) + "\n\n"

    if service_header:
        luau = service_header + luau

    # Detect residual C# artifacts and add warnings
    if re.search(r"\bclass\s+\w+", luau):
        warnings.append("Residual 'class' keyword detected — manual cleanup needed.")
    remaining_braces = luau.count("{") + luau.count("}")
    if remaining_braces > 0:
        warnings.append(f"Curly braces remain ({remaining_braces}) — may need manual conversion to 'end' blocks.")

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

    confidence = _compute_confidence(
        csharp, luau, warnings,
        api_subs=api_subs, ast_driven=False,
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
    serialized_refs: dict[Path, dict[str, str]] | None = None,
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
        serialized_refs: Optional mapping from ``{script_cs_path: {field_name:
            prefab_name}}``, extracted from MonoBehaviour scene/prefab YAML.
            When provided, ``[SerializeField]`` fields referencing prefabs are
            converted to ``ServerStorage:WaitForChild("PrefabName")`` calls.

    Returns:
        TranspilationResult with one TranspiledScript per .cs file found.
    """
    root = Path(unity_project_path).resolve()
    assets_dir = root / "Assets"
    if not assets_dir.is_dir():
        raise FileNotFoundError(f"Assets directory not found: {assets_dir}")

    result = TranspilationResult()

    for cs_path in sorted(assets_dir.rglob("*.cs")):
        csharp_source = cs_path.read_text(encoding="utf-8-sig", errors="replace")
        result.total += 1

        # AST analysis for classification (needed regardless of transpilation strategy)
        ast_info = _parse_csharp_ast(csharp_source)

        # Look up serialized field refs for this specific script
        script_refs = serialized_refs.get(cs_path.resolve()) if serialized_refs else None

        if use_ai and api_key:
            luau, confidence, warnings = _ai_transpile(csharp_source, api_key, model, max_tokens)
            strategy: TranspilationStrategy = "ai"
        else:
            # Tiered fallback: AST (best) → AI (if key available) → regex (last resort)
            ast_result = _ast_transpile_luau(csharp_source, script_refs)
            if ast_result is not None:
                luau, confidence, warnings = ast_result
                strategy = "rule_based"
            elif api_key:
                # AST failed (no tree-sitter or parse errors) but we have an API key —
                # use AI rather than the fragile regex pipeline
                luau, confidence, warnings = _ai_transpile(
                    csharp_source, api_key, model, max_tokens,
                )
                strategy = "ai"
            else:
                # No AST, no API key — regex is all we have
                luau, confidence, warnings = _rule_based_transpile(
                    csharp_source, script_refs,
                )
                strategy = "rule_based"

        # Classify script type based on Unity API usage
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

    return result
