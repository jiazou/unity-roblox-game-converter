"""Black-box tests for modules/report_generator.py."""

import json
from pathlib import Path

import pytest

from modules.report_generator import (
    AssetSummary,
    ConversionReport,
    MaterialSummary,
    OutputSummary,
    SceneSummary,
    ScriptSummary,
    generate_report,
)


class TestGenerateReport:
    """Tests for the generate_report() public API."""

    def test_returns_path(self, tmp_path: Path) -> None:
        report = ConversionReport()
        result = generate_report(report, tmp_path / "report.json", print_summary=False)
        assert isinstance(result, Path)

    def test_creates_file(self, tmp_path: Path) -> None:
        report = ConversionReport()
        path = generate_report(report, tmp_path / "report.json", print_summary=False)
        assert path.exists()
        assert path.stat().st_size > 0

    def test_valid_json(self, tmp_path: Path) -> None:
        report = ConversionReport()
        path = generate_report(report, tmp_path / "report.json", print_summary=False)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_contains_generated_at(self, tmp_path: Path) -> None:
        report = ConversionReport()
        path = generate_report(report, tmp_path / "report.json", print_summary=False)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "generated_at" in data
        assert len(data["generated_at"]) > 0

    def test_contains_all_sections(self, tmp_path: Path) -> None:
        report = ConversionReport()
        path = generate_report(report, tmp_path / "report.json", print_summary=False)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "assets" in data
        assert "materials" in data
        assert "scripts" in data
        assert "scene" in data
        assert "output" in data

    def test_success_flag(self, tmp_path: Path) -> None:
        report = ConversionReport(success=True, errors=[])
        path = generate_report(report, tmp_path / "report.json", print_summary=False)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["success"] is True

    def test_failure_flag(self, tmp_path: Path) -> None:
        report = ConversionReport(success=False, errors=["something broke"])
        path = generate_report(report, tmp_path / "report.json", print_summary=False)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["success"] is False
        assert "something broke" in data["errors"]

    def test_asset_summary_serialised(self, tmp_path: Path) -> None:
        report = ConversionReport()
        report.assets = AssetSummary(
            total=42,
            by_kind={"texture": 10, "mesh": 5},
            total_size_bytes=123456,
            duplicates_removed=3,
        )
        path = generate_report(report, tmp_path / "report.json", print_summary=False)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["assets"]["total"] == 42
        assert data["assets"]["by_kind"]["texture"] == 10
        assert data["assets"]["total_size_bytes"] == 123456

    def test_material_summary_serialised(self, tmp_path: Path) -> None:
        report = ConversionReport()
        report.materials = MaterialSummary(
            total=10,
            fully_converted=7,
            partially_converted=2,
            unconvertible=1,
            texture_ops=5,
        )
        path = generate_report(report, tmp_path / "report.json", print_summary=False)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["materials"]["total"] == 10
        assert data["materials"]["fully_converted"] == 7

    def test_script_summary_serialised(self, tmp_path: Path) -> None:
        report = ConversionReport()
        report.scripts = ScriptSummary(
            total=5,
            succeeded=3,
            flagged_for_review=1,
            skipped=1,
            ai_transpiled=2,
            rule_based=3,
            flagged_scripts=["BadScript.cs"],
        )
        path = generate_report(report, tmp_path / "report.json", print_summary=False)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["scripts"]["total"] == 5
        assert data["scripts"]["flagged_scripts"] == ["BadScript.cs"]

    def test_scene_summary_serialised(self, tmp_path: Path) -> None:
        report = ConversionReport()
        report.scene = SceneSummary(
            scenes_parsed=2,
            total_game_objects=50,
            prefabs_parsed=3,
            prefab_instances_resolved=5,
            meshes_decimated=2,
            meshes_compliant=10,
        )
        path = generate_report(report, tmp_path / "report.json", print_summary=False)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["scene"]["scenes_parsed"] == 2
        assert data["scene"]["prefab_instances_resolved"] == 5
        assert data["scene"]["meshes_decimated"] == 2

    def test_output_summary_serialised(self, tmp_path: Path) -> None:
        report = ConversionReport()
        report.output = OutputSummary(
            rbxl_path="/out/game.rbxl",
            parts_written=100,
            scripts_in_place=5,
            report_path="/out/report.json",
        )
        path = generate_report(report, tmp_path / "report.json", print_summary=False)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["output"]["parts_written"] == 100

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        report = ConversionReport()
        path = generate_report(
            report, tmp_path / "sub" / "deep" / "report.json", print_summary=False
        )
        assert path.exists()

    def test_verbose_includes_flagged_scripts(self, tmp_path: Path) -> None:
        report = ConversionReport()
        report.scripts.flagged_scripts = ["Foo.cs", "Bar.cs"]
        path = generate_report(report, tmp_path / "report.json", verbose=True, print_summary=False)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "flagged_scripts" in data["scripts"]
        assert data["scripts"]["flagged_scripts"] == ["Foo.cs", "Bar.cs"]

    def test_non_verbose_strips_flagged_scripts(self, tmp_path: Path) -> None:
        report = ConversionReport()
        report.scripts.flagged_scripts = ["Foo.cs"]
        path = generate_report(report, tmp_path / "report.json", verbose=False, print_summary=False)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "flagged_scripts" not in data["scripts"]

    def test_print_summary_output(self, tmp_path: Path, capsys) -> None:
        report = ConversionReport(success=True)
        report.assets.total = 10
        generate_report(report, tmp_path / "report.json", print_summary=True)
        captured = capsys.readouterr()
        assert "Conversion Report" in captured.out
        assert "SUCCESS" in captured.out

    def test_print_summary_failure(self, tmp_path: Path, capsys) -> None:
        report = ConversionReport(success=False, errors=["disk full"])
        generate_report(report, tmp_path / "report.json", print_summary=True)
        captured = capsys.readouterr()
        assert "FAILED" in captured.out
        assert "disk full" in captured.out

    def test_warnings_displayed(self, tmp_path: Path, capsys) -> None:
        report = ConversionReport(warnings=["low confidence script"])
        generate_report(report, tmp_path / "report.json", print_summary=True)
        captured = capsys.readouterr()
        assert "Warning" in captured.out

    def test_duration_in_json(self, tmp_path: Path) -> None:
        report = ConversionReport(duration_seconds=12.5)
        path = generate_report(report, tmp_path / "report.json", print_summary=False)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["duration_seconds"] == 12.5

    def test_overwrite_existing(self, tmp_path: Path) -> None:
        rpath = tmp_path / "report.json"
        rpath.write_text("{}", encoding="utf-8")
        report = ConversionReport(success=True)
        generate_report(report, rpath, print_summary=False)
        data = json.loads(rpath.read_text(encoding="utf-8"))
        assert "success" in data

    def test_resolved_path_returned(self, tmp_path: Path) -> None:
        report = ConversionReport()
        result = generate_report(report, tmp_path / "report.json", print_summary=False)
        assert result.is_absolute()
