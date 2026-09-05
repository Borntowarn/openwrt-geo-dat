from __future__ import annotations

import hashlib
import pathlib
import tempfile
import unittest
import zipfile

import build_release
import geoip_tool
import geosite_tool


class BuildReleaseTests(unittest.TestCase):
    def test_parse_categories(self) -> None:
        self.assertEqual(build_release.parse_categories("ru, private, ,CN"), ["ru", "private", "CN"])
        self.assertEqual(build_release.parse_categories(["ru,private", "cn"]), ["ru", "private", "cn"])
        self.assertEqual(build_release.parse_categories("   ,  "), [])
        self.assertEqual(build_release.parse_categories(None), [])
        self.assertEqual(
            build_release.parse_categories("category-ads-all\nyoutube\nopenai\n"),
            ["category-ads-all", "youtube", "openai"],
        )
        self.assertEqual(
            build_release.parse_categories("ru\nprivate,cn"),
            ["ru", "private", "cn"],
        )

    def test_calc_and_verify_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            f = tmp_path / "sample.txt"
            f.write_bytes(b"hello world\n")
            digest = hashlib.sha256(b"hello world\n").hexdigest()

            self.assertEqual(build_release.calc_sha256(f), digest)

            sum_file = tmp_path / "sample.txt.sha256sum"
            sum_file.write_text(f"{digest}  sample.txt\n", encoding="utf-8")
            build_release.verify_sha256(f, sum_file)

            bad_sum = tmp_path / "bad.sha256sum"
            bad_sum.write_text("0" * 64 + "  sample.txt\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                build_release.verify_sha256(f, bad_sum)

    def test_create_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            src_dir = tmp_path / "geosite-txt"
            src_dir.mkdir()
            (src_dir / "ru.txt").write_bytes(b"example.com\n")
            (src_dir / "ads.txt").write_bytes(b"ads.com\n")

            zip_out = tmp_path / "geosite-txt.zip"
            build_release.create_zip(src_dir, zip_out, "geosite-txt")

            self.assertTrue(zip_out.exists())
            with zipfile.ZipFile(zip_out, "r") as zf:
                names = sorted(zf.namelist())
                self.assertEqual(names, ["geosite-txt/ads.txt", "geosite-txt/ru.txt"])
                self.assertEqual(zf.read("geosite-txt/ru.txt"), b"example.com\n")

    def test_pipeline_with_mock_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            download_dir = tmp_path / "upstream"
            download_dir.mkdir()
            out_dir = tmp_path / "out"

            site_src = tmp_path / "site_src"
            site_src.mkdir()
            (site_src / "ru.txt").write_bytes(b"example.ru\n")
            (site_src / "cn.txt").write_bytes(b"example.cn\n")
            geosite_dat = download_dir / "geosite.dat"
            geosite_tool.build_from_directory(site_src, geosite_dat)
            (download_dir / "geosite.dat.sha256sum").write_text(
                f"{build_release.calc_sha256(geosite_dat)}  geosite.dat\n", encoding="utf-8"
            )

            ip_src = tmp_path / "ip_src"
            ip_src.mkdir()
            (ip_src / "ru.txt").write_bytes(b"2.16.20.0/23\n")
            (ip_src / "private.txt").write_bytes(b"192.168.0.0/16\n")
            (ip_src / "cn.txt").write_bytes(b"1.0.1.0/24\n")
            geoip_dat = download_dir / "geoip.dat"
            geoip_tool.build_from_directory(ip_src, geoip_dat)
            (download_dir / "geoip.dat.sha256sum").write_text(
                f"{build_release.calc_sha256(geoip_dat)}  geoip.dat\n", encoding="utf-8"
            )

            rc = build_release.main(
                [
                    "--geosite-categories",
                    "ru",
                    "--geoip-categories",
                    "ru,private",
                    "--download-dir",
                    str(download_dir),
                    "--out-dir",
                    str(out_dir),
                    "--skip-download",
                ]
            )
            self.assertEqual(rc, 0)

            rel_dir = out_dir / "release"
            self.assertTrue((rel_dir / "geosite.dat").exists())
            self.assertTrue((rel_dir / "geoip.dat").exists())
            self.assertTrue((rel_dir / "geosite-txt.zip").exists())
            self.assertTrue((rel_dir / "geoip-txt.zip").exists())
            self.assertTrue((rel_dir / "geosite.dat.sha256sum").exists())
            self.assertTrue((rel_dir / "geoip.dat.sha256sum").exists())

            build_release.verify_sha256(rel_dir / "geosite.dat", rel_dir / "geosite.dat.sha256sum")
            build_release.verify_sha256(rel_dir / "geoip.dat", rel_dir / "geoip.dat.sha256sum")

            sites = geosite_tool.parse_geosite_file(rel_dir / "geosite.dat")
            self.assertEqual([s.name for s in sites], ["RU"])

            ips = geoip_tool.parse_geoip_file(rel_dir / "geoip.dat")
            self.assertEqual([i.country_code for i in ips], ["RU", "PRIVATE"])


if __name__ == "__main__":
    unittest.main()
