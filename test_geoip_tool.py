from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

import geoip_tool


ROOT = pathlib.Path(__file__).resolve().parent
SCRIPT = ROOT / "geoip_tool.py"


class GeoIPToolCliTests(unittest.TestCase):
    def test_build_then_extract_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            input_dir = tmp_path / "lists"
            input_dir.mkdir()
            (input_dir / "ru.txt").write_text(
                "\n".join(
                    [
                        "# RU IPs",
                        "2.16.20.0/23",
                        "192.168.1.1/32",
                        "2001:db8::/32",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            output_dat = tmp_path / "custom_geoip.dat"
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

            extracted = (extracted_dir / "ru.txt").read_text(encoding="utf-8")
            self.assertIn("2.16.20.0/23\n", extracted)
            self.assertIn("192.168.1.1/32\n", extracted)
            self.assertIn("2001:db8::/32\n", extracted)

    def test_extract_category_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            input_dir = tmp_path / "lists"
            input_dir.mkdir()
            (input_dir / "ru.txt").write_text("2.16.20.0/23\n", encoding="utf-8")
            (input_dir / "cn.txt").write_text("1.0.1.0/24\n", encoding="utf-8")
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

    def test_filter_command_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            input_dir = tmp_path / "lists"
            input_dir.mkdir()
            (input_dir / "ru.txt").write_text("2.16.20.0/23\n", encoding="utf-8")
            (input_dir / "private.txt").write_text("10.0.0.0/8\n192.168.0.0/16\n", encoding="utf-8")
            (input_dir / "cn.txt").write_text("1.0.1.0/24\n", encoding="utf-8")
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
                    "private",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, res.stderr or res.stdout)
            self.assertTrue(output_dat.exists())
            self.assertTrue((output_txt / "ru.txt").exists())
            self.assertTrue((output_txt / "private.txt").exists())
            self.assertFalse((output_txt / "cn.txt").exists())

            check_txt = tmp_path / "check-txt"
            subprocess.run(
                [sys.executable, str(SCRIPT), "extract", str(output_dat), str(check_txt)],
                check=True,
            )
            self.assertTrue((check_txt / "ru.txt").exists())
            self.assertTrue((check_txt / "private.txt").exists())
            self.assertFalse((check_txt / "cn.txt").exists())
            priv_content = (check_txt / "private.txt").read_text(encoding="utf-8")
            self.assertIn("10.0.0.0/8", priv_content)
            self.assertIn("192.168.0.0/16", priv_content)

    def test_filter_comma_separated_categories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            input_dir = tmp_path / "lists"
            input_dir.mkdir()
            (input_dir / "ru.txt").write_text("2.16.20.0/23\n", encoding="utf-8")
            (input_dir / "private.txt").write_text("10.0.0.0/8\n", encoding="utf-8")
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
                    "ru,private",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, res.stderr or res.stdout)
            self.assertTrue((output_txt / "ru.txt").exists())
            self.assertTrue((output_txt / "private.txt").exists())

    def test_filter_missing_category_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            input_dir = tmp_path / "lists"
            input_dir.mkdir()
            (input_dir / "ru.txt").write_text("2.16.20.0/23\n", encoding="utf-8")
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
                    "ru,missing_country",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("missing_country", res.stderr or res.stdout)

    def test_filter_empty_category_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            input_dir = tmp_path / "lists"
            input_dir.mkdir()
            (input_dir / "ru.txt").write_text("2.16.20.0/23\n", encoding="utf-8")
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

    def test_parse_cidr_line_variations(self) -> None:
        c1 = geoip_tool.parse_cidr_line("192.168.1.1 # trailing comment")
        self.assertEqual(geoip_tool.format_cidr_entry(c1), "192.168.1.1/32")

        c2 = geoip_tool.parse_cidr_line("192.168.1.5/24")
        self.assertEqual(geoip_tool.format_cidr_entry(c2), "192.168.1.0/24")

        c3 = geoip_tool.parse_cidr_line("2001:db8::1/128")
        self.assertEqual(geoip_tool.format_cidr_entry(c3), "2001:db8::1/128")

        with self.assertRaises(ValueError):
            geoip_tool.parse_cidr_line("# only comment")


if __name__ == "__main__":
    unittest.main()
