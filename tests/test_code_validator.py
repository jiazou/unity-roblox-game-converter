"""Tests for modules/code_validator.py."""

import pytest

from modules.code_validator import ValidationResult, validate_luau


class TestValidateLuau:
    """Tests for the validate_luau() public API."""

    def test_valid_luau_returns_valid(self) -> None:
        source = (
            "local function greet(name)\n"
            "    print('Hello ' .. name)\n"
            "end\n"
        )
        result = validate_luau(source)
        assert result.valid is True
        assert result.error_count == 0

    def test_returns_validation_result(self) -> None:
        result = validate_luau("print('hi')")
        assert isinstance(result, ValidationResult)

    def test_detects_unbalanced_end(self) -> None:
        source = (
            "local function foo()\n"
            "    print('bar')\n"
            # missing 'end'
        )
        result = validate_luau(source)
        assert result.valid is False
        assert any("E001" in i.code for i in result.issues)

    def test_detects_extra_end(self) -> None:
        source = (
            "print('bar')\n"
            "end\n"
        )
        result = validate_luau(source)
        assert any("W001" in i.code for i in result.issues)

    def test_detects_csharp_using(self) -> None:
        source = "using UnityEngine;\nprint('hi')\n"
        result = validate_luau(source)
        assert result.valid is False
        assert any("E010" in i.code for i in result.issues)

    def test_detects_csharp_class(self) -> None:
        source = "class Foo\n    print('hi')\nend\n"
        result = validate_luau(source)
        assert result.valid is False
        assert any("E011" in i.code for i in result.issues)

    def test_detects_csharp_namespace(self) -> None:
        source = "namespace MyGame\nprint('hi')\n"
        result = validate_luau(source)
        assert result.valid is False
        assert any("E012" in i.code for i in result.issues)

    def test_detects_curly_braces(self) -> None:
        source = "if true {\n    print('hi')\n}\n"
        result = validate_luau(source)
        assert result.valid is False
        assert any("E030" in i.code for i in result.issues)

    def test_detects_trailing_semicolons(self) -> None:
        source = "local x = 1;\nlocal y = 2;\n"
        result = validate_luau(source)
        assert any("W030" in i.code for i in result.issues)

    def test_detects_unbalanced_parens(self) -> None:
        source = "print(('hi')\n"
        result = validate_luau(source)
        assert result.valid is False
        assert any("E022" in i.code for i in result.issues)

    def test_ignores_strings(self) -> None:
        """Curly braces inside strings should not be flagged."""
        source = 'local s = "hello {world}"\nprint(s)\n'
        result = validate_luau(source)
        # Braces inside strings should be stripped by preprocessor
        brace_issues = [i for i in result.issues if i.code == "E030"]
        assert len(brace_issues) == 0

    def test_ignores_comments(self) -> None:
        """C# keywords in comments should not be flagged."""
        source = "-- using UnityEngine;\nprint('hi')\n"
        result = validate_luau(source)
        using_issues = [i for i in result.issues if i.code == "E010"]
        assert len(using_issues) == 0

    def test_balanced_if_then_end(self) -> None:
        source = (
            "if true then\n"
            "    print('yes')\n"
            "end\n"
        )
        result = validate_luau(source)
        assert result.valid is True

    def test_balanced_for_do_end(self) -> None:
        source = (
            "for i = 1, 10 do\n"
            "    print(i)\n"
            "end\n"
        )
        result = validate_luau(source)
        assert result.valid is True

    def test_balanced_while_do_end(self) -> None:
        source = (
            "while true do\n"
            "    print('loop')\n"
            "end\n"
        )
        result = validate_luau(source)
        assert result.valid is True

    def test_repeat_until(self) -> None:
        source = (
            "repeat\n"
            "    print('loop')\n"
            "until true\n"
        )
        result = validate_luau(source)
        assert result.valid is True

    def test_source_name_in_result(self) -> None:
        result = validate_luau("print('hi')", source_name="test.lua")
        assert result.source_name == "test.lua"

    def test_empty_source(self) -> None:
        result = validate_luau("")
        assert result.valid is True

    def test_error_and_warning_counts(self) -> None:
        source = "using UnityEngine;\nlocal x = 1;\n"
        result = validate_luau(source)
        assert result.error_count >= 1
        assert result.warning_count >= 1

    def test_csharp_access_modifier(self) -> None:
        source = "public static void Main()\nprint('hi')\n"
        result = validate_luau(source)
        assert any("E013" in i.code for i in result.issues)
