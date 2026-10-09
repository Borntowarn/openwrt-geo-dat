from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

import geoip_tool
import geosite_tool
import srs_tool


class SrsToolTests(unittest.TestCase):
    def test_domain_items_mapping(self) -> None:
        self.assertEqual(
            srs_tool.domain_items_for_entry(
                geosite_tool.DomainEntry(geosite_tool.DOMAIN_TYPE_PLAIN, "ads", [])
            ),
            [("domain_keyword", "ads")],
        )
        self.assertEqual(
            srs_tool.domain_items_for_entry(
                geosite_tool.DomainEntry(geosite_tool.DOMAIN_TYPE_REGEX, r"foo\d+", [])
            ),
            [("domain_regex", r"foo\d+")],
        )
        self.assertEqual(
            srs_tool.domain_items_for_entry(
                geosite_tool.DomainEntry(geosite_tool.DOMAIN_TYPE_FULL, "www.example.com", [])
            ),
            [("domain", "www.example.com")],
        )
        self.assertEqual(
            srs_tool.domain_items_for_entry(
                geosite_tool.DomainEntry(geosite_tool.DOMAIN_TYPE_ROOT, "example.com", [])
            ),
            [("domain", "example.com"), ("domain_suffix", ".example.com")],
        )
        self.assertEqual(
            srs_tool.domain_items_for_entry(
                geosite_tool.DomainEntry(geosite_tool.DOMAIN_TYPE_ROOT, "localhost", [])
            ),
            [("domain_suffix", ".localhost")],
        )

    def test_geosite_to_ruleset_map_with_attrs(self) -> None:
        sites = [
            geosite_tool.GeoSite(
                name="YouTube",
                domains=[
                    geosite_tool.DomainEntry(geosite_tool.DOMAIN_TYPE_ROOT, "youtube.com", []),
                    geosite_tool.DomainEntry(
                        geosite_tool.DOMAIN_TYPE_FULL, "ads.youtube.com", ["ads"]
                    ),
                ],
            )
        ]
        rulesets = srs_tool.geosite_to_ruleset_map(sites)
        self.assertIn("youtube", rulesets)
        self.assertIn("youtube@ads", rulesets)

        base = rulesets["youtube"]
        self.assertEqual(base["version"], srs_tool.RULESET_VERSION)
        rule = base["rules"][0]
        self.assertIn("youtube.com", rule["domain"])
        self.assertIn(".youtube.com", rule["domain_suffix"])
        self.assertIn("ads.youtube.com", rule["domain"])

        attr = rulesets["youtube@ads"]["rules"][0]
        self.assertEqual(attr["domain"], ["ads.youtube.com"])

    def test_geoip_to_ruleset_map(self) -> None:
        entries = [
            geoip_tool.GeoIP(
                country_code="RU",
                cidrs=[geoip_tool.parse_cidr_line("2.16.20.0/23")],
            )
        ]
        rulesets = srs_tool.geoip_to_ruleset_map(entries)
        self.assertEqual(
            rulesets["ru"],
            {
                "version": srs_tool.RULESET_VERSION,
                "rules": [{"ip_cidr": ["2.16.20.0/23"]}],
            },
        )

    def test_build_json_without_compile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            site_src = tmp_path / "site"
            site_src.mkdir()
            (site_src / "youtube.txt").write_text("domain:youtube.com\nfull:youtu.be\n", encoding="utf-8")
            geosite_dat = tmp_path / "geosite.dat"
            geosite_tool.build_from_directory(site_src, geosite_dat)

            ip_src = tmp_path / "ip"
            ip_src.mkdir()
            (ip_src / "telegram.txt").write_text("91.108.4.0/22\n", encoding="utf-8")
            geoip_dat = tmp_path / "geoip.dat"
            geoip_tool.build_from_directory(ip_src, geoip_dat)

            json_dir = tmp_path / "json"
            srs_dir = tmp_path / "srs"
            json_paths, srs_paths = srs_tool.build_srs_from_dat(
                geosite_dat=geosite_dat,
                geoip_dat=geoip_dat,
                json_dir=json_dir,
                srs_dir=srs_dir,
                require_compile=False,
            )
            self.assertEqual(srs_paths, [])
            names = sorted(p.name for p in json_paths)
            self.assertIn("geosite-youtube.json", names)
            self.assertIn("geoip-telegram.json", names)

            payload = json.loads((json_dir / "geosite" / "geosite-youtube.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], 3)
            self.assertTrue(payload["rules"][0]["domain_suffix"])


if __name__ == "__main__":
    unittest.main()
