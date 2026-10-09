from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
from collections import defaultdict
from typing import Any

import geoip_tool
import geosite_tool

# Source format version supported by sing-box >= 1.11 (router uses 1.13.x).
RULESET_VERSION = 3


def domain_items_for_entry(entry: geosite_tool.DomainEntry) -> list[tuple[str, str]]:
    """Map a v2ray DomainEntry to (rule_field, value) pairs like geodat2srs."""
    value = entry.value
    match entry.match_type:
        case geosite_tool.DOMAIN_TYPE_PLAIN:
            return [("domain_keyword", value)]
        case geosite_tool.DOMAIN_TYPE_REGEX:
            return [("domain_regex", value)]
        case geosite_tool.DOMAIN_TYPE_ROOT:
            items: list[tuple[str, str]] = []
            if "." in value:
                items.append(("domain", value))
            items.append(("domain_suffix", f".{value}"))
            return items
        case geosite_tool.DOMAIN_TYPE_FULL:
            return [("domain", value)]
        case _:
            raise ValueError(f"Unsupported domain match type: {entry.match_type}")


def geosite_to_ruleset_map(sites: list[geosite_tool.GeoSite]) -> dict[str, dict[str, Any]]:
    """
    Build rule-set source JSON objects keyed by category name.

    Base category includes all domains. Domains with attributes also produce
    extra keys like ``youtube@ads`` (same as runetfreedom/geodat2srs).
    """
    buckets: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {
            "domain": set(),
            "domain_suffix": set(),
            "domain_keyword": set(),
            "domain_regex": set(),
        }
    )

    def add_items(key: str, entry: geosite_tool.DomainEntry) -> None:
        for field, value in domain_items_for_entry(entry):
            buckets[key][field].add(value)

    for site in sites:
        code = geosite_tool.normalize_name(site.name)
        attr_groups: dict[str, list[geosite_tool.DomainEntry]] = defaultdict(list)
        for entry in site.domains:
            add_items(code, entry)
            for attr in entry.attrs:
                attr_key = attr.split("=", 1)[0].strip().lower()
                if attr_key:
                    attr_groups[attr_key].append(entry)
        for attr_key, entries in attr_groups.items():
            for entry in entries:
                add_items(f"{code}@{attr_key}", entry)

    result: dict[str, dict[str, Any]] = {}
    for key, fields in sorted(buckets.items()):
        rule: dict[str, list[str]] = {}
        for field in ("domain", "domain_suffix", "domain_keyword", "domain_regex"):
            values = sorted(fields[field])
            if values:
                rule[field] = values
        if not rule:
            continue
        result[key] = {"version": RULESET_VERSION, "rules": [rule]}
    return result


def geoip_to_ruleset_map(entries: list[geoip_tool.GeoIP]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in entries:
        code = geoip_tool.normalize_name(item.country_code)
        cidrs = sorted({geoip_tool.format_cidr_entry(c) for c in item.cidrs})
        if not cidrs:
            continue
        result[code] = {
            "version": RULESET_VERSION,
            "rules": [{"ip_cidr": cidrs}],
        }
    return result


def write_ruleset_json(rulesets: dict[str, dict[str, Any]], output_dir: pathlib.Path, prefix: str) -> list[pathlib.Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[pathlib.Path] = []
    for name, payload in sorted(rulesets.items()):
        path = output_dir / f"{prefix}{name}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


def find_sing_box(binary: str | None = None) -> str | None:
    candidate = binary or "sing-box"
    resolved = shutil.which(candidate)
    if resolved:
        return resolved
    path = pathlib.Path(candidate)
    if path.is_file() and os_access_executable(path):
        return str(path.resolve())
    return None


def os_access_executable(path: pathlib.Path) -> bool:
    return path.exists() and path.is_file()


def compile_ruleset_json(
    json_path: pathlib.Path,
    output_srs: pathlib.Path,
    sing_box: str,
) -> None:
    output_srs.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sing_box, "rule-set", "compile", "--output", str(output_srs), str(json_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"sing-box compile failed for {json_path.name}: {detail}")


def compile_json_dir(
    json_dir: pathlib.Path,
    srs_dir: pathlib.Path,
    sing_box: str,
) -> list[pathlib.Path]:
    compiled: list[pathlib.Path] = []
    for json_path in sorted(json_dir.glob("*.json")):
        srs_path = srs_dir / (json_path.stem + ".srs")
        compile_ruleset_json(json_path, srs_path, sing_box)
        compiled.append(srs_path)
    return compiled


def build_srs_from_dat(
    geosite_dat: pathlib.Path,
    geoip_dat: pathlib.Path,
    json_dir: pathlib.Path,
    srs_dir: pathlib.Path,
    sing_box: str | None = None,
    require_compile: bool = True,
) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    sites = geosite_tool.parse_geosite_file(geosite_dat)
    ips = geoip_tool.parse_geoip_file(geoip_dat)

    site_map = geosite_to_ruleset_map(sites)
    ip_map = geoip_to_ruleset_map(ips)

    if json_dir.exists():
        shutil.rmtree(json_dir)
    json_paths = write_ruleset_json(site_map, json_dir / "geosite", "geosite-")
    json_paths.extend(write_ruleset_json(ip_map, json_dir / "geoip", "geoip-"))

    if not require_compile:
        print("Skipping .srs compile; wrote JSON sources only")
        return json_paths, []

    binary = find_sing_box(sing_box)
    if not binary:
        raise SystemExit(
            "sing-box binary not found; install it or pass --sing-box / path, "
            "or use --skip-srs-compile"
        )

    if srs_dir.exists():
        shutil.rmtree(srs_dir)
    srs_paths = compile_json_dir(json_dir / "geosite", srs_dir, binary)
    srs_paths.extend(compile_json_dir(json_dir / "geoip", srs_dir, binary))
    print(f"Compiled {len(srs_paths)} .srs files into {srs_dir}")
    return json_paths, srs_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert filtered geo dat to sing-box rule-set JSON/.srs")
    parser.add_argument("geosite_dat", type=pathlib.Path)
    parser.add_argument("geoip_dat", type=pathlib.Path)
    parser.add_argument("--json-dir", type=pathlib.Path, default=pathlib.Path("out/srs-json"))
    parser.add_argument("--srs-dir", type=pathlib.Path, default=pathlib.Path("out/srs"))
    parser.add_argument("--sing-box", default=None, help="Path to sing-box binary")
    parser.add_argument(
        "--skip-compile",
        action="store_true",
        help="Only write JSON sources; do not compile .srs",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    build_srs_from_dat(
        geosite_dat=args.geosite_dat,
        geoip_dat=args.geoip_dat,
        json_dir=args.json_dir,
        srs_dir=args.srs_dir,
        sing_box=args.sing_box,
        require_compile=not args.skip_compile,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
