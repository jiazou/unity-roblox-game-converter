"""Fine-grained unit tests for modules/code_transpiler.py.

Tests individual regex rule transformations, confidence scoring,
warning generation, and complex C# patterns.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.code_transpiler import (
    TranspilationResult,
    TranspiledScript,
    transpile_scripts,
    _rule_based_transpile,
)


class TestRuleBasedTranspilePatterns:
    """Test each regex rule individually."""

    def test_int_variable(self) -> None:
        luau, _, _ = _rule_based_transpile("int x = 5;")
        assert "local x =" in luau

    def test_float_variable(self) -> None:
        luau, _, _ = _rule_based_transpile("float speed = 3.5f;")
        assert "local speed =" in luau

    def test_double_variable(self) -> None:
        luau, _, _ = _rule_based_transpile("double dist = 10.0;")
        assert "local dist =" in luau

    def test_bool_variable(self) -> None:
        luau, _, _ = _rule_based_transpile("bool active = true;")
        assert "local active =" in luau

    def test_string_variable(self) -> None:
        luau, _, _ = _rule_based_transpile('string name = "player";')
        assert "local name =" in luau

    def test_debug_log_to_print(self) -> None:
        luau, _, _ = _rule_based_transpile('Debug.Log("hello");')
        assert 'print("hello")' in luau
        assert "Debug.Log" not in luau

    def test_void_method_to_local_function(self) -> None:
        luau, _, _ = _rule_based_transpile("void DoSomething()")
        assert "local function DoSomething(" in luau

    def test_this_to_self(self) -> None:
        luau, _, _ = _rule_based_transpile("this.speed = 5;")
        assert "self.speed" in luau
        assert "this." not in luau

    def test_using_directives_stripped(self) -> None:
        code = "using UnityEngine;\nusing System.Collections;\n\nvoid Start() {}"
        luau, _, _ = _rule_based_transpile(code)
        assert "using UnityEngine" not in luau
        assert "using System" not in luau

    def test_namespace_stripped(self) -> None:
        code = "namespace Foo.Bar {\n    // stuff\n}"
        luau, _, _ = _rule_based_transpile(code)
        assert "namespace" not in luau

    def test_class_wrapper_stripped(self) -> None:
        code = "public class Player : MonoBehaviour {\n    // stuff\n}"
        luau, _, _ = _rule_based_transpile(code)
        assert "public class" not in luau

    def test_start_lifecycle(self) -> None:
        luau, _, _ = _rule_based_transpile("void Start()")
        # Start maps to top-level code (AST) or AncestryChanged (regex fallback)
        assert "Start" in luau or "AncestryChanged" in luau

    def test_update_lifecycle(self) -> None:
        luau, _, _ = _rule_based_transpile("void Update()")
        assert "Heartbeat" in luau

    def test_set_active_simple(self) -> None:
        luau, _, _ = _rule_based_transpile("tutorialBlocker.SetActive(false)")
        assert "tutorialBlocker.Visible = false" in luau
        assert "SetActive" not in luau

    def test_set_active_with_expression(self) -> None:
        luau, _, _ = _rule_based_transpile(
            "tutorialBlocker.SetActive(not PlayerData.instance.tutorialDone)"
        )
        assert "tutorialBlocker.Visible = not PlayerData.instance.tutorialDone" in luau

    def test_set_active_on_gameobject(self) -> None:
        luau, _, _ = _rule_based_transpile("gameObject.SetActive(true)")
        assert "gameObject.Visible = true" in luau

    def test_set_active_on_dotted_path(self) -> None:
        luau, _, _ = _rule_based_transpile("foo.gameObject.SetActive(true)")
        assert "foo.gameObject.Visible = true" in luau


class TestRuleBasedConfidence:
    """Test confidence scoring logic."""

    def test_no_changes_zero_confidence(self) -> None:
        """Unrecognized code → no rules match → 0 confidence."""
        _, confidence, _ = _rule_based_transpile("-- already luau\nlocal x = 5\n")
        assert confidence == 0.0

    def test_many_changes_higher_confidence(self) -> None:
        code = (
            "using UnityEngine;\n"
            "public class Foo : MonoBehaviour {\n"
            "    float speed = 5.0f;\n"
            "    int count = 0;\n"
            "    void Start() {\n"
            "        Debug.Log(\"init\");\n"
            "    }\n"
            "}\n"
        )
        _, confidence, _ = _rule_based_transpile(code)
        assert confidence > 0.0

    def test_confidence_capped_at_1(self) -> None:
        # Generate a script where every line gets changed
        lines = [f"int var{i} = {i};" for i in range(20)]
        code = "\n".join(lines)
        _, confidence, _ = _rule_based_transpile(code)
        assert confidence <= 1.0


class TestRuleBasedWarnings:
    """Test warning generation."""

    def test_simple_class_stripped_no_warning(self) -> None:
        """A standard class declaration should now be stripped without warning."""
        code = "class InnerClass {\n    int x = 0;\n}"
        luau, _, warnings = _rule_based_transpile(code)
        class_warnings = [w for w in warnings if "class" in w.lower()]
        assert len(class_warnings) == 0

    def test_residual_braces_warning(self) -> None:
        # AST path produces clean output without braces; regex path may
        # leave braces that trigger a warning.  Either is acceptable.
        code = "void Foo() {\n    int x = 0;\n}"
        luau, _, warnings = _rule_based_transpile(code)
        if "{" in luau or "}" in luau:
            brace_warnings = [w for w in warnings if "brace" in w.lower()]
            assert len(brace_warnings) > 0

    def test_clean_output_no_warnings(self) -> None:
        """Plain text with no C# features should produce no warnings."""
        code = "-- luau comment\nlocal x = 5\n"
        _, _, warnings = _rule_based_transpile(code)
        assert warnings == []


class TestTranspileScriptsIntegration:
    """Integration tests for transpile_scripts with real file I/O."""

    def test_subdirectory_scripts(self, tmp_path: Path) -> None:
        """Scripts in subdirectories of Assets/ should be found."""
        project = tmp_path / "SubDir"
        subdir = project / "Assets" / "Scripts" / "Player"
        subdir.mkdir(parents=True)
        (subdir / "Move.cs").write_text(
            "void Update() { Debug.Log(\"move\"); }", encoding="utf-8"
        )
        result = transpile_scripts(project)
        assert result.total == 1
        assert result.scripts[0].output_filename == "Move.lua"

    def test_confidence_threshold_all_pass(self, tmp_path: Path) -> None:
        project = tmp_path / "Conf"
        (project / "Assets").mkdir(parents=True)
        (project / "Assets" / "A.cs").write_text(
            "using UnityEngine;\nfloat x = 1;\nDebug.Log(x);\n", encoding="utf-8"
        )
        result = transpile_scripts(project, use_ai=False, confidence_threshold=0.0)
        assert result.flagged == 0
        assert result.succeeded == 1

    def test_confidence_threshold_strict(self, tmp_path: Path) -> None:
        project = tmp_path / "Strict"
        (project / "Assets").mkdir(parents=True)
        # Very simple script → low change ratio → low confidence
        (project / "Assets" / "Simple.cs").write_text(
            "// just a comment\n", encoding="utf-8"
        )
        result = transpile_scripts(project, use_ai=False, confidence_threshold=0.99)
        assert result.flagged >= 1

    def test_preserves_original_source(self, tmp_path: Path) -> None:
        project = tmp_path / "Pres"
        (project / "Assets").mkdir(parents=True)
        original = "using UnityEngine;\nvoid Start() { Debug.Log(\"hi\"); }\n"
        (project / "Assets" / "Keep.cs").write_text(original, encoding="utf-8")
        result = transpile_scripts(project)
        ts = result.scripts[0]
        assert ts.csharp_source == original

    def test_complex_csharp_patterns(self, tmp_path: Path) -> None:
        """Test that complex C# doesn't crash the transpiler."""
        project = tmp_path / "Complex"
        (project / "Assets").mkdir(parents=True)
        code = (
            "using UnityEngine;\n"
            "using System.Collections.Generic;\n"
            "\n"
            "namespace Game.Player {\n"
            "    public class Controller : MonoBehaviour {\n"
            "        [SerializeField] float speed = 5.0f;\n"
            "        private List<int> scores = new List<int>();\n"
            "\n"
            "        void Start() {\n"
            "            this.speed = 10.0f;\n"
            "            Debug.Log(\"Starting\");\n"
            "        }\n"
            "\n"
            "        void Update() {\n"
            "            float dt = Time.deltaTime;\n"
            "            this.transform.position += Vector3.forward * speed * dt;\n"
            "        }\n"
            "\n"
            "        void OnCollisionEnter(Collision collision) {\n"
            "            Debug.Log(\"Hit: \" + collision.gameObject.name);\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        (project / "Assets" / "Controller.cs").write_text(code, encoding="utf-8")
        result = transpile_scripts(project, use_ai=False)
        assert result.total == 1
        ts = result.scripts[0]
        # Should not crash; verify key transformations applied
        assert "using UnityEngine" not in ts.luau_source
        assert "self.speed" in ts.luau_source
        assert "print(" in ts.luau_source

    def test_skipped_count_zero_for_rule_based(self, tmp_path: Path) -> None:
        """Rule-based transpilation should never skip scripts."""
        project = tmp_path / "NoSkip"
        (project / "Assets").mkdir(parents=True)
        (project / "Assets" / "X.cs").write_text("int a = 1;", encoding="utf-8")
        result = transpile_scripts(project, use_ai=False)
        assert result.skipped == 0

    def test_output_filenames_unique(self, tmp_path: Path) -> None:
        """Each script should produce a unique output filename."""
        project = tmp_path / "Unique"
        (project / "Assets").mkdir(parents=True)
        for name in ("Alpha", "Beta", "Gamma"):
            (project / "Assets" / f"{name}.cs").write_text(
                f"void Start() {{ Debug.Log(\"{name}\"); }}", encoding="utf-8"
            )
        result = transpile_scripts(project)
        filenames = [ts.output_filename for ts in result.scripts]
        assert len(filenames) == len(set(filenames))


# ── New transpiler improvements ──────────────────────────────────────


class TestImprovedTranspilerRules:
    """Test the improved rule-based transpiler features."""

    def test_if_else_converted(self) -> None:
        code = "if (x > 5) {\n    print(x);\n} else {\n    print(0);\n}"
        luau, _, _ = _rule_based_transpile(code)
        assert "if x > 5 then" in luau
        assert "else" in luau
        assert "end" in luau
        assert "{" not in luau

    def test_while_loop_converted(self) -> None:
        code = "while (running) {\n    DoWork();\n}"
        luau, _, _ = _rule_based_transpile(code)
        assert "while running do" in luau
        assert "end" in luau

    def test_elseif_converted(self) -> None:
        code = "if (a) {\n    f();\n} else if (b) {\n    g();\n}"
        luau, _, _ = _rule_based_transpile(code)
        assert "if a then" in luau
        assert "elseif b then" in luau

    def test_semicolons_stripped(self) -> None:
        code = "int x = 5;\nint y = 10;"
        luau, _, _ = _rule_based_transpile(code)
        assert ";" not in luau

    def test_mathf_calls_converted(self) -> None:
        code = "float a = Mathf.Abs(-5);\nfloat b = Mathf.PI;"
        luau, _, _ = _rule_based_transpile(code)
        assert "math.abs" in luau
        assert "math.pi" in luau

    def test_length_to_hash(self) -> None:
        code = "int n = items.Length;"
        luau, _, _ = _rule_based_transpile(code)
        assert "#items" in luau

    def test_list_add_to_table_insert(self) -> None:
        code = "myList.Add(item);"
        luau, _, _ = _rule_based_transpile(code)
        assert "table.insert(myList, item)" in luau

    def test_new_vector3_converted(self) -> None:
        code = "var pos = new Vector3(1, 2, 3);"
        luau, _, _ = _rule_based_transpile(code)
        assert "Vector3.new(1, 2, 3)" in luau

    def test_tostring_converted(self) -> None:
        code = "string s = x.ToString();"
        luau, _, _ = _rule_based_transpile(code)
        assert "tostring(x)" in luau

    def test_for_loop_less_equal(self) -> None:
        code = "for(int i = 0; i <= count; i++)"
        luau, _, _ = _rule_based_transpile(code)
        assert "for i = 0, count do" in luau

    def test_new_list_to_table(self) -> None:
        code = "var items = new List<int>();"
        luau, _, _ = _rule_based_transpile(code)
        assert "{}" in luau


# ── SerializeField → ServerStorage:WaitForChild wiring ────────────────


class TestSerializedFieldRefs:
    """Test [SerializeField] replacement with serialized_refs from scene YAML."""

    def test_serialize_field_replaced_with_wait_for_child(self) -> None:
        code = "[SerializeField] private GameObject enemyPrefab;\n"
        refs = {"enemyPrefab": "Enemy"}
        luau, _, _ = _rule_based_transpile(code, serialized_refs=refs)
        assert 'ServerStorage:WaitForChild("Enemy")' in luau
        assert "local enemyPrefab" in luau
        assert "[SerializeField]" not in luau

    def test_server_storage_service_imported(self) -> None:
        code = (
            "using UnityEngine;\n"
            "public class Spawner : MonoBehaviour {\n"
            "    [SerializeField] private GameObject bulletPrefab;\n"
            "}\n"
        )
        refs = {"bulletPrefab": "Bullet"}
        luau, _, _ = _rule_based_transpile(code, serialized_refs=refs)
        assert 'game:GetService("ServerStorage")' in luau

    def test_non_ref_serialize_field_stripped(self) -> None:
        """[SerializeField] on fields NOT in the ref map just strip the attribute."""
        code = "[SerializeField] private float speed = 5.0f;\n"
        refs = {"enemyPrefab": "Enemy"}  # speed is not in refs
        luau, _, _ = _rule_based_transpile(code, serialized_refs=refs)
        assert "[SerializeField]" not in luau
        assert "speed" in luau
        assert "WaitForChild" not in luau

    def test_multiple_serialize_fields(self) -> None:
        code = (
            "[SerializeField] private GameObject enemy;\n"
            "[SerializeField] private float speed = 5.0f;\n"
            "[SerializeField] private GameObject coin;\n"
        )
        refs = {"enemy": "EnemyZombie", "coin": "GoldCoin"}
        luau, _, _ = _rule_based_transpile(code, serialized_refs=refs)
        assert 'ServerStorage:WaitForChild("EnemyZombie")' in luau
        assert 'ServerStorage:WaitForChild("GoldCoin")' in luau
        assert "local enemy" in luau
        assert "local coin" in luau
        # Speed should not be replaced with WaitForChild
        assert luau.count("WaitForChild") == 2

    def test_no_refs_strips_attribute(self) -> None:
        """When serialized_refs is None, [SerializeField] is just stripped."""
        code = "[SerializeField] private GameObject thing;\n"
        luau, _, _ = _rule_based_transpile(code, serialized_refs=None)
        assert "[SerializeField]" not in luau

    def test_transpile_scripts_passes_refs(self, tmp_path: Path) -> None:
        """transpile_scripts() passes serialized_refs through to the transpiler."""
        project = tmp_path / "RefProject"
        (project / "Assets" / "Scripts").mkdir(parents=True)
        cs_path = project / "Assets" / "Scripts" / "Spawner.cs"
        cs_path.write_text(
            "using UnityEngine;\n"
            "public class Spawner : MonoBehaviour {\n"
            "    [SerializeField] private GameObject enemy;\n"
            "    void Start() { Debug.Log(\"go\"); }\n"
            "}\n",
            encoding="utf-8",
        )
        refs = {cs_path.resolve(): {"enemy": "EnemyBot"}}
        result = transpile_scripts(project, use_ai=False, serialized_refs=refs)
        assert result.total == 1
        assert 'WaitForChild("EnemyBot")' in result.scripts[0].luau_source


# ── AST-driven transpiler improvement tests ────────────────────────────


class TestASTTranspilerImprovements:
    """Tests for behaviours the AST emitter handles better than regex.

    These use well-formed C# source (full classes or complete statements)
    so that the AST path is always taken.
    """

    def test_instantiate_produces_clone(self, tmp_path: Path) -> None:
        """Instantiate(prefab) should produce prefab:Clone(), not .Clone(prefab)."""
        project = tmp_path / "InstClone"
        (project / "Assets").mkdir(parents=True)
        code = (
            "using UnityEngine;\n"
            "public class Spawner : MonoBehaviour {\n"
            "    public GameObject prefab;\n"
            "    void Start() {\n"
            "        var obj = Instantiate(prefab);\n"
            "    }\n"
            "}\n"
        )
        (project / "Assets" / "Spawner.cs").write_text(code, encoding="utf-8")
        result = transpile_scripts(project, use_ai=False)
        luau = result.scripts[0].luau_source
        # AST emitter restructures to obj method call (not broken .Clone(prefab))
        assert "prefab:Clone()" in luau
        assert ".Clone(prefab)" not in luau

    def test_destroy_produces_method_call(self, tmp_path: Path) -> None:
        """Destroy(obj) should produce obj:Destroy(), not .Destroy(obj)."""
        project = tmp_path / "DestroyObj"
        (project / "Assets").mkdir(parents=True)
        code = (
            "using UnityEngine;\n"
            "public class Cleanup : MonoBehaviour {\n"
            "    void Start() {\n"
            "        GameObject obj = null;\n"
            "        Destroy(obj);\n"
            "    }\n"
            "}\n"
        )
        (project / "Assets" / "Cleanup.cs").write_text(code, encoding="utf-8")
        result = transpile_scripts(project, use_ai=False)
        luau = result.scripts[0].luau_source
        assert "obj:Destroy()" in luau

    def test_string_literals_not_transformed(self, tmp_path: Path) -> None:
        """Strings containing C# keywords must not be mangled."""
        project = tmp_path / "SafeStr"
        (project / "Assets").mkdir(parents=True)
        code = (
            "using UnityEngine;\n"
            "public class Msg : MonoBehaviour {\n"
            '    void Start() { Debug.Log("int x = null"); }\n'
            "}\n"
        )
        (project / "Assets" / "Msg.cs").write_text(code, encoding="utf-8")
        result = transpile_scripts(project, use_ai=False)
        luau = result.scripts[0].luau_source
        # The string content must be preserved exactly
        assert '"int x = null"' in luau

    def test_no_braces_in_control_flow(self, tmp_path: Path) -> None:
        """if/else/while/for should produce then/do...end, not leftover braces."""
        project = tmp_path / "NoBraces"
        (project / "Assets").mkdir(parents=True)
        code = (
            "using UnityEngine;\n"
            "public class Flow : MonoBehaviour {\n"
            "    void Start() {\n"
            "        int x = 5;\n"
            "        if (x > 0) {\n"
            "            Debug.Log(\"pos\");\n"
            "        } else {\n"
            "            Debug.Log(\"neg\");\n"
            "        }\n"
            "        while (x > 0) {\n"
            "            x--;\n"
            "        }\n"
            "        for (int i = 0; i < 10; i++) {\n"
            "            Debug.Log(i.ToString());\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        (project / "Assets" / "Flow.cs").write_text(code, encoding="utf-8")
        result = transpile_scripts(project, use_ai=False)
        luau = result.scripts[0].luau_source
        assert "{" not in luau
        assert "}" not in luau
        assert "then" in luau
        assert "else" in luau
        assert "end" in luau
        assert "while" in luau
        assert "for" in luau

    def test_get_component_generic_converted(self, tmp_path: Path) -> None:
        """GetComponent<AudioSource>() → :FindFirstChildOfClass(\"Sound\")."""
        project = tmp_path / "GetComp"
        (project / "Assets").mkdir(parents=True)
        code = (
            "using UnityEngine;\n"
            "public class Audio : MonoBehaviour {\n"
            "    void Start() {\n"
            "        var s = GetComponent<AudioSource>();\n"
            "    }\n"
            "}\n"
        )
        (project / "Assets" / "Audio.cs").write_text(code, encoding="utf-8")
        result = transpile_scripts(project, use_ai=False)
        luau = result.scripts[0].luau_source
        assert ':FindFirstChildOfClass("Sound")' in luau

    def test_null_becomes_nil(self, tmp_path: Path) -> None:
        project = tmp_path / "NullNil"
        (project / "Assets").mkdir(parents=True)
        code = (
            "using UnityEngine;\n"
            "public class Chk : MonoBehaviour {\n"
            "    void Start() {\n"
            "        GameObject x = null;\n"
            "        if (x != null) { Debug.Log(\"found\"); }\n"
            "    }\n"
            "}\n"
        )
        (project / "Assets" / "Chk.cs").write_text(code, encoding="utf-8")
        result = transpile_scripts(project, use_ai=False)
        luau = result.scripts[0].luau_source
        assert "nil" in luau
        assert "null" not in luau

    def test_ternary_to_if_expression(self, tmp_path: Path) -> None:
        project = tmp_path / "Ternary"
        (project / "Assets").mkdir(parents=True)
        code = (
            "using UnityEngine;\n"
            "public class T : MonoBehaviour {\n"
            "    void Start() {\n"
            "        int x = 5;\n"
            "        int y = x > 0 ? x : 0;\n"
            "    }\n"
            "}\n"
        )
        (project / "Assets" / "T.cs").write_text(code, encoding="utf-8")
        result = transpile_scripts(project, use_ai=False)
        luau = result.scripts[0].luau_source
        assert "if" in luau and "then" in luau and "else" in luau

    def test_property_emitted_as_functions(self, tmp_path: Path) -> None:
        """Properties should become getter/setter functions."""
        project = tmp_path / "Prop"
        (project / "Assets").mkdir(parents=True)
        code = (
            "using UnityEngine;\n"
            "public class P : MonoBehaviour {\n"
            "    private float speed = 5.0f;\n"
            "    public float Speed {\n"
            "        get { return speed; }\n"
            "        set { speed = value; }\n"
            "    }\n"
            "}\n"
        )
        (project / "Assets" / "P.cs").write_text(code, encoding="utf-8")
        result = transpile_scripts(project, use_ai=False)
        luau = result.scripts[0].luau_source
        assert "getSpeed" in luau or "get_Speed" in luau or "function" in luau

    def test_comments_preserved_not_transformed(self, tmp_path: Path) -> None:
        """Comments should be converted to Lua comment syntax but content preserved."""
        project = tmp_path / "Comments"
        (project / "Assets").mkdir(parents=True)
        code = (
            "using UnityEngine;\n"
            "public class C : MonoBehaviour {\n"
            "    // int x = null; this is a comment\n"
            "    void Start() { Debug.Log(\"hi\"); }\n"
            "}\n"
        )
        (project / "Assets" / "C.cs").write_text(code, encoding="utf-8")
        result = transpile_scripts(project, use_ai=False)
        luau = result.scripts[0].luau_source
        # Comment should be preserved with content intact
        assert "int x = null" in luau
        # Should use Lua comment syntax
        assert "--" in luau

    def test_string_concat_uses_dotdot(self, tmp_path: Path) -> None:
        """String + string should become .. (concatenation)."""
        project = tmp_path / "Concat"
        (project / "Assets").mkdir(parents=True)
        code = (
            "using UnityEngine;\n"
            "public class S : MonoBehaviour {\n"
            '    void Start() { Debug.Log("hello " + "world"); }\n'
            "}\n"
        )
        (project / "Assets" / "S.cs").write_text(code, encoding="utf-8")
        result = transpile_scripts(project, use_ai=False)
        luau = result.scripts[0].luau_source
        assert ".." in luau

    def test_lifecycle_update_wrapped_in_heartbeat(self, tmp_path: Path) -> None:
        """Update() method should be wrapped in RunService.Heartbeat:Connect."""
        project = tmp_path / "Lifecycle"
        (project / "Assets").mkdir(parents=True)
        code = (
            "using UnityEngine;\n"
            "public class L : MonoBehaviour {\n"
            "    void Update() {\n"
            "        Debug.Log(\"tick\");\n"
            "    }\n"
            "}\n"
        )
        (project / "Assets" / "L.cs").write_text(code, encoding="utf-8")
        result = transpile_scripts(project, use_ai=False)
        luau = result.scripts[0].luau_source
        assert "Heartbeat" in luau
        assert "Connect" in luau
        assert 'GetService("RunService")' in luau
