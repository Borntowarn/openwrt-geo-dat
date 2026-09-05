from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

import geosite_tool


ROOT = pathlib.Path(__file__).resolve().parent
SCRIPT = ROOT / "geosite_tool.py"


class GeositeToolCliTests(unittest.TestCase):
    def test_build_then_extract_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            input_dir = tmp_path / "lists"
            input_dir.mkdir()
            (input_dir / "category-ads-all.txt").write_text(
                "\n".join(
                    [
                        "# comment should be ignored",
                        "example.com @attr",
                        "full:ads.example.com",
                        "keyword:tracker",
                        r"regexp:^ad[sx]\d+\.example\.org$",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            output_dat = tmp_path / "custom.dat"
            extracted_dir = tmp_path / "extracted"

            build = subprocess.run(
                [sys.executable, str(SCRIPT), "build", str(input_dir), str(output_dat)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr or build.stdout)
            self.assertTrue(output_dat.exists())

            extract = subprocess.run(
                [sys.executable, str(SCRIPT), "extract", str(output_dat), str(extracted_dir)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(extract.returncode, 0, extract.stderr or extract.stdout)

            extracted = (extracted_dir / "category-ads-all.txt").read_text(encoding="utf-8")
            self.assertIn("example.com @attr\n", extracted)
            self.assertIn("full:ads.example.com\n", extracted)
            self.assertIn("keyword:tracker\n", extracted)
            self.assertIn(r"regexp:^ad[sx]\d+\.example\.org$", extracted)

    def test_extract_category_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            input_dir = tmp_path / "lists"
            input_dir.mkdir()
            (input_dir / "ru.txt").write_text("ru.example.com\n", encoding="utf-8")
            (input_dir / "cn.txt").write_text("cn.example.com\n", encoding="utf-8")
            output_dat = tmp_path / "custom.dat"
            extracted_dir = tmp_path / "extracted"

            subprocess.run(
                [sys.executable, str(SCRIPT), "build", str(input_dir), str(output_dat)],
                check=True,
            )

            extract = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "extract",
                    str(output_dat),
                    str(extracted_dir),
                    "--category",
                    "ru",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(extract.returncode, 0, extract.stderr or extract.stdout)
            self.assertTrue((extracted_dir / "ru.txt").exists())
            self.assertFalse((extracted_dir / "cn.txt").exists())

    def test_extract_one_category(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            input_dir = tmp_path / "lists"
            input_dir.mkdir()
            (input_dir / "ru.txt").write_text("ru.example.com\n", encoding="utf-8")
            output_dat = tmp_path / "custom.dat"
            one_out = tmp_path / "single_ru.txt"

            subprocess.run(
                [sys.executable, str(SCRIPT), "build", str(input_dir), str(output_dat)],
                check=True,
            )

            res = subprocess.run(
                [sys.executable, str(SCRIPT), "extract-category", str(output_dat), "RU", str(one_out)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, res.stderr or res.stdout)
            self.assertTrue(one_out.exists())
            self.assertEqual(one_out.read_text(encoding="utf-8").strip(), "ru.example.com")

    def test_filter_command_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            input_dir = tmp_path / "lists"
            input_dir.mkdir()
            (input_dir / "ru.txt").write_text("ru.example.com\nfull:login.ru.example.com\n", encoding="utf-8")
            (input_dir / "cn.txt").write_text("cn.example.com\n", encoding="utf-8")
            (input_dir / "ads.txt").write_text("ad.example.com\n", encoding="utf-8")
            input_dat = tmp_path / "all.dat"
            output_dat = tmp_path / "filtered.dat"
            output_txt = tmp_path / "filtered-txt"

            subprocess.run(
                [sys.executable, str(SCRIPT), "build", str(input_dir), str(input_dat)],
                check=True,
            )

            res = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "filter",
                    str(input_dat),
                    str(output_dat),
                    str(output_txt),
                    "--category",
                    "ru",
                    "--category",
                    "ads",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, res.stderr or res.stdout)
            self.assertTrue(output_dat.exists())
            self.assertTrue((output_txt / "ru.txt").exists())
            self.assertTrue((output_txt / "ads.txt").exists())
            self.assertFalse((output_txt / "cn.txt").exists())

            check_txt = tmp_path / "check-txt"
            subprocess.run(
                [sys.executable, str(SCRIPT), "extract", str(output_dat), str(check_txt)],
                check=True,
            )
            self.assertTrue((check_txt / "ru.txt").exists())
            self.assertTrue((check_txt / "ads.txt").exists())
            self.assertFalse((check_txt / "cn.txt").exists())
            ru_content = (check_txt / "ru.txt").read_text(encoding="utf-8")
            self.assertIn("ru.example.com", ru_content)
            self.assertIn("full:login.ru.example.com", ru_content)

    def test_filter_comma_separated_categories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            input_dir = tmp_path / "lists"
            input_dir.mkdir()
            (input_dir / "ru.txt").write_text("ru.example.com\n", encoding="utf-8")
            (input_dir / "cn.txt").write_text("cn.example.com\n", encoding="utf-8")
            input_dat = tmp_path / "all.dat"
            output_dat = tmp_path / "filtered.dat"
            output_txt = tmp_path / "filtered-txt"

            subprocess.run(
                [sys.executable, str(SCRIPT), "build", str(input_dir), str(input_dat)],
                check=True,
            )

            res = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "filter",
                    str(input_dat),
                    str(output_dat),
                    str(output_txt),
                    "--category",
                    " ru , cn ",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, res.stderr or res.stdout)
            self.assertTrue((output_txt / "ru.txt").exists())
            self.assertTrue((output_txt / "cn.txt").exists())

    def test_filter_missing_category_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            input_dir = tmp_path / "lists"
            input_dir.mkdir()
            (input_dir / "ru.txt").write_text("ru.example.com\n", encoding="utf-8")
            input_dat = tmp_path / "all.dat"
            output_dat = tmp_path / "filtered.dat"
            output_txt = tmp_path / "filtered-txt"

            subprocess.run(
                [sys.executable, str(SCRIPT), "build", str(input_dir), str(input_dat)],
                check=True,
            )

            res = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "filter",
                    str(input_dat),
                    str(output_dat),
                    str(output_txt),
                    "--category",
                    "ru,nonexistent_category",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("nonexistent_category", res.stderr or res.stdout)

    def test_filter_empty_category_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            input_dir = tmp_path / "lists"
            input_dir.mkdir()
            (input_dir / "ru.txt").write_text("ru.example.com\n", encoding="utf-8")
            input_dat = tmp_path / "all.dat"
            output_dat = tmp_path / "filtered.dat"
            output_txt = tmp_path / "filtered-txt"

            subprocess.run(
                [sys.executable, str(SCRIPT), "build", str(input_dir), str(input_dat)],
                check=True,
            )

            res = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "filter",
                    str(input_dat),
                    str(output_dat),
                    str(output_txt),
                    "--category",
                    " , , ",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(res.returncode, 0)


if __name__ == "__main__":
    unittest.main()
