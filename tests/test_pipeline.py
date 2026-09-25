"""验证对外产物、非法剧本和写入安全，而非仅检查内部调用。"""

import copy
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from manju.exporter import export_bundle, render_files, timecode
from manju.model import ValidationError, load_episode, parse_episode
from manju.planner import build_plan


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "episode.json"


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(SAMPLE.read_text(encoding="utf-8"))

    def plan(self):
        return build_plan(parse_episode(self.data))

    def test_demo_contract_and_role_consistency(self):
        plan = self.plan()
        self.assertEqual(plan["duration_ms"], 30000)
        self.assertEqual(len(plan["shots"]), 6)
        self.assertEqual(len(plan["characters"]), 2)
        self.assertEqual(plan["status"], "planned")
        linhe = self.data["characters"][0]["appearance"]
        shenlan = self.data["characters"][1]["appearance"]
        self.assertIn(linhe, plan["shots"][0]["image_prompt"])
        self.assertNotIn(shenlan, plan["shots"][0]["image_prompt"])
        self.assertIn(linhe, plan["shots"][3]["image_prompt"])
        self.assertIn(shenlan, plan["shots"][3]["image_prompt"])
        self.assertTrue(all(shot["image_status"] == "pending" for shot in plan["shots"]))

    def test_subtitles_preserve_silence_and_exact_shot_ends(self):
        plan = self.plan()
        self.assertEqual(plan["shots"][4]["lines"], [])
        cues = [line for shot in plan["shots"] for line in shot["lines"]]
        self.assertEqual(len(cues), 6)
        self.assertEqual(cues[4]["end_ms"], 20000)
        self.assertEqual(cues[5]["start_ms"], 24000)
        self.assertEqual(cues[-1]["end_ms"], 30000)
        for shot in plan["shots"]:
            if shot["lines"]:
                self.assertEqual(shot["lines"][0]["start_ms"], shot["start_ms"])
                self.assertEqual(shot["lines"][-1]["end_ms"], shot["end_ms"])
            for line in shot["lines"]:
                self.assertLess(line["start_ms"], line["end_ms"])
        srt = render_files(plan)["subtitles.srt"]
        self.assertIn("6\n00:00:24,000 --> 00:00:30,000", srt)
        self.assertNotIn("旁白：", srt)

    def test_fractional_durations_do_not_drift(self):
        for shot in self.data["scenes"][0]["shots"]:
            shot["duration_seconds"] = 1.001
        plan = self.plan()
        self.assertEqual(plan["duration_ms"], 6006)
        self.assertEqual(plan["shots"][-1]["end_ms"], 6006)
        self.assertEqual(timecode(3600001), "01:00:00,001")

    def test_silent_episode_and_offscreen_voice_are_valid(self):
        self.data["characters"] = []
        for shot in self.data["scenes"][0]["shots"]:
            shot["characters"] = []
            shot["lines"] = []
        files = render_files(self.plan())
        self.assertEqual(files["subtitles.srt"], "")
        self.assertEqual(len(list(csv.reader(io.StringIO(files["voice_lines.csv"])))), 1)
        self.data["characters"] = json.loads(SAMPLE.read_text(encoding="utf-8"))["characters"]
        self.data["scenes"][0]["shots"][0]["lines"] = [{"speaker": "linhe", "text": "画外音。"}]
        plan = self.plan()
        self.assertEqual(plan["shots"][0]["characters"], [])
        self.assertEqual(plan["shots"][0]["lines"][0]["speaker"], "linhe")

    def test_duplicate_ids_and_invalid_references_fail(self):
        cases = []
        duplicate_character = copy.deepcopy(self.data)
        duplicate_character["characters"].append(duplicate_character["characters"][0])
        cases.append(duplicate_character)
        duplicate_scene = copy.deepcopy(self.data)
        duplicate_scene["scenes"].append(duplicate_scene["scenes"][0])
        cases.append(duplicate_scene)
        duplicate_shot = copy.deepcopy(self.data)
        second_scene = copy.deepcopy(duplicate_shot["scenes"][0])
        second_scene["id"] = "scene-02"
        duplicate_shot["scenes"].append(second_scene)
        cases.append(duplicate_shot)
        for field, value in [("characters", ["missing"]), ("characters", ["linhe", "linhe"]),
                             ("lines", [{"speaker": "missing", "text": "台词"}])]:
            invalid = copy.deepcopy(self.data)
            invalid["scenes"][0]["shots"][0][field] = value
            cases.append(invalid)
        for index, data in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ValidationError):
                parse_episode(data)

    def test_invalid_durations_fail(self):
        shot = self.data["scenes"][0]["shots"][0]
        for duration in [0, -1, True, "5", 0.0001, 3601, float("inf"), float("nan")]:
            with self.subTest(duration=duration), self.assertRaises(ValidationError):
                shot["duration_seconds"] = duration
                self.plan()
        shot["duration_seconds"] = 0.001
        shot["lines"] = [{"speaker": "narrator", "text": "甲"}, {"speaker": "narrator", "text": "乙"}]
        with self.assertRaisesRegex(ValidationError, "至少需要"):
            self.plan()

    def test_malformed_schema_is_rejected(self):
        for field, value in [("schema_version", 2), ("schema_version", True), ("aspect_ratio", "4:3"),
                             ("id", "../../outside"), ("title", " "), ("scenes", []), ("characters", {})]:
            data = copy.deepcopy(self.data)
            data[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                parse_episode(data)
        data = copy.deepcopy(self.data)
        data["titel"] = data.pop("title")
        with self.assertRaises(ValidationError):
            parse_episode(data)
        data = copy.deepcopy(self.data)
        data["scenes"][0]["shots"][0]["duration_second"] = 5
        with self.assertRaisesRegex(ValidationError, "未知字段"):
            parse_episode(data)
        data = copy.deepcopy(self.data)
        data["title"] = chr(0xD800)
        with self.assertRaisesRegex(ValidationError, "无效 Unicode"):
            parse_episode(data)

    def test_bom_input_and_bad_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "episode.json"
            path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8-sig")
            self.assertEqual(load_episode(path).title, self.data["title"])
            for text in ['{"id":"a","id":"b"}', '{"duration":NaN}', '{bad json']:
                with self.subTest(text=text), self.assertRaises(ValidationError):
                    path.write_text(text, encoding="utf-8")
                    load_episode(path)

    def test_bundle_contents_and_determinism(self):
        plan = self.plan()
        expected = {"production.json", "storyboard.md", "storyboard.csv", "characters.md",
                    "image_prompts.json", "voice_lines.csv", "subtitles.srt", "release_checklist.md"}
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "one"
            second = Path(directory) / "two"
            export_bundle(plan, first)
            export_bundle(self.plan(), second)
            self.assertEqual({path.name for path in first.iterdir()}, expected)
            for name in expected:
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
            restored = json.loads((first / "production.json").read_text(encoding="utf-8"))
            self.assertEqual(restored, plan)
            with (first / "storyboard.csv").open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 6)
            self.assertEqual(rows[-1]["结束毫秒"], "30000")
            self.assertFalse((first / "images").exists())
            self.assertFalse((first / "audio").exists())

    def test_existing_outputs_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "existing"
            destination.mkdir()
            sentinel = destination / "important.txt"
            sentinel.write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                export_bundle(self.plan(), destination)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            self.assertEqual(list(destination.iterdir()), [sentinel])

    def test_failed_write_leaves_no_partial_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "failed"
            plan = self.plan()
            with patch("manju.exporter.Path.open", side_effect=OSError("simulated disk error")):
                with self.assertRaises(OSError):
                    export_bundle(plan, destination)
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_csv_formula_text_and_markdown_are_safe(self):
        shot = self.data["scenes"][0]["shots"][0]
        shot["visual"] = "=HYPERLINK(\"https://example.invalid\")"
        shot["lines"][0]["text"] = "@hello"
        self.data["title"] = "<script>alert(1)</script>"
        files = render_files(self.plan())
        rows = list(csv.DictReader(io.StringIO(files["storyboard.csv"].lstrip("\ufeff"))))
        self.assertTrue(rows[0]["画面"].startswith("'="))
        voices = list(csv.DictReader(io.StringIO(files["voice_lines.csv"].lstrip("\ufeff"))))
        self.assertEqual(voices[0]["台词"], "'@hello")
        self.assertNotIn("<script>", files["storyboard.md"])
        self.assertEqual(json.loads(files["production.json"])["shots"][0]["visual"], shot["visual"])


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "manju", *map(str, args)], cwd=ROOT,
            env={**os.environ, "PYTHONUTF8": "1"},
            capture_output=True, text=True, encoding="utf-8", check=False,
        )

    def test_validate_and_build_from_cli(self):
        result = self.run_cli("validate", SAMPLE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("6 个镜头", result.stdout)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "中文 目录"
            result = self.run_cli("build", SAMPLE, "--out", output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(list(output.iterdir())), 8)
            result = self.run_cli("build", SAMPLE, "--out", output)
            self.assertEqual(result.returncode, 2)
            self.assertIn("输出目录已存在", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_errors_are_actionable_and_create_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "bad.json"
            output = Path(directory) / "must-not-exist"
            bad.write_text('{"schema_version":1}', encoding="utf-8")
            result = self.run_cli("build", bad, "--out", output)
            self.assertEqual(result.returncode, 2)
            self.assertIn("缺少字段", result.stderr)
            self.assertFalse(output.exists())
            result = self.run_cli("validate", Path(directory) / "missing.json")
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
