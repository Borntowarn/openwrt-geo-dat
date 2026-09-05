from __future__ import annotations

import argparse
import pathlib
import sys
from dataclasses import dataclass


DOMAIN_TYPE_PLAIN = 0
DOMAIN_TYPE_REGEX = 1
DOMAIN_TYPE_ROOT = 2
DOMAIN_TYPE_FULL = 3

DOMAIN_PREFIX_TO_TYPE = {
    "keyword": DOMAIN_TYPE_PLAIN,
    "regexp": DOMAIN_TYPE_REGEX,
    "domain": DOMAIN_TYPE_ROOT,
    "full": DOMAIN_TYPE_FULL,
}

DOMAIN_TYPE_TO_PREFIX = {
    DOMAIN_TYPE_PLAIN: "keyword",
    DOMAIN_TYPE_REGEX: "regexp",
    DOMAIN_TYPE_ROOT: "domain",
    DOMAIN_TYPE_FULL: "full",
}


@dataclass
class DomainEntry:
    match_type: int
    value: str
    attrs: list[str]


@dataclass
class GeoSite:
    name: str
    domains: list[DomainEntry]


def read_varint(buf: bytes, offset: int) -> tuple[int, int]:
    shift = 0
    result = 0
    while True:
        if offset >= len(buf):
            raise ValueError("Unexpected end of file while reading varint")
        byte = buf[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, offset
        shift += 7


def write_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("Negative varint is not supported")
    out = bytearray()
    while True:
        chunk = value & 0x7F
        value >>= 7
        if value:
            out.append(chunk | 0x80)
        else:
            out.append(chunk)
            return bytes(out)


def skip_field(buf: bytes, offset: int, wire_type: int) -> int:
    if wire_type == 0:
        _, offset = read_varint(buf, offset)
        return offset
    if wire_type == 1:
        return offset + 8
    if wire_type == 2:
        length, offset = read_varint(buf, offset)
        return offset + length
    if wire_type == 5:
        return offset + 4
    raise ValueError(f"Unsupported wire type: {wire_type}")


def parse_attribute(block: bytes) -> str:
    key = None
    bool_value = None
    int_value = None
    offset = 0
    while offset < len(block):
        tag, offset = read_varint(block, offset)
        field_no = tag >> 3
        wire_type = tag & 0x07
        if field_no == 1 and wire_type == 2:
            length, offset = read_varint(block, offset)
            key = block[offset : offset + length].decode("utf-8")
            offset += length
        elif field_no == 2 and wire_type == 0:
            value, offset = read_varint(block, offset)
            bool_value = bool(value)
        elif field_no == 3 and wire_type == 0:
            int_value, offset = read_varint(block, offset)
        else:
            offset = skip_field(block, offset, wire_type)
    if key is None:
        raise ValueError("Attribute without key")
    if bool_value is not None:
        return key if bool_value else f"{key}=false"
    if int_value is not None:
        return f"{key}={int_value}"
    return key


def build_attribute(attr: str) -> bytes:
    if "=" in attr:
        key, raw_value = attr.split("=", 1)
        raw_value = raw_value.strip()
        if raw_value.lower() == "false":
            value_tag = b"\x10" + write_varint(0)
        else:
            value_tag = b"\x18" + write_varint(int(raw_value))
    else:
        key = attr
        value_tag = b"\x10" + write_varint(1)
    key_bytes = key.encode("utf-8")
    payload = b"\x0a" + write_varint(len(key_bytes)) + key_bytes + value_tag
    return b"\x1a" + write_varint(len(payload)) + payload


def parse_domain(block: bytes) -> DomainEntry:
    match_type = DOMAIN_TYPE_PLAIN
    value = ""
    attrs: list[str] = []
    offset = 0
    while offset < len(block):
        tag, offset = read_varint(block, offset)
        field_no = tag >> 3
        wire_type = tag & 0x07
        if field_no == 1 and wire_type == 0:
            match_type, offset = read_varint(block, offset)
        elif field_no == 2 and wire_type == 2:
            length, offset = read_varint(block, offset)
            value = block[offset : offset + length].decode("utf-8")
            offset += length
        elif field_no == 3 and wire_type == 2:
            length, offset = read_varint(block, offset)
            attrs.append(parse_attribute(block[offset : offset + length]))
            offset += length
        else:
            offset = skip_field(block, offset, wire_type)
    return DomainEntry(match_type=match_type, value=value, attrs=attrs)


def build_domain(entry: DomainEntry) -> bytes:
    value_bytes = entry.value.encode("utf-8")
    parts = [
        b"\x08" + write_varint(entry.match_type),
        b"\x12" + write_varint(len(value_bytes)) + value_bytes,
    ]
    parts.extend(build_attribute(attr) for attr in entry.attrs)
    return b"".join(parts)


def parse_geosite(block: bytes) -> GeoSite:
    name = None
    domains: list[DomainEntry] = []
    offset = 0
    while offset < len(block):
        tag, offset = read_varint(block, offset)
        field_no = tag >> 3
        wire_type = tag & 0x07
        if field_no in (1, 4) and wire_type == 2:
            length, offset = read_varint(block, offset)
            text = block[offset : offset + length].decode("utf-8")
            offset += length
            if field_no == 1 or name is None:
                name = text
        elif field_no == 2 and wire_type == 2:
            length, offset = read_varint(block, offset)
            domains.append(parse_domain(block[offset : offset + length]))
            offset += length
        else:
            offset = skip_field(block, offset, wire_type)
    if not name:
        raise ValueError("GeoSite entry without name")
    return GeoSite(name=name, domains=domains)


def build_geosite(site: GeoSite) -> bytes:
    name_bytes = site.name.encode("utf-8")
    parts = [b"\x0a" + write_varint(len(name_bytes)) + name_bytes]
    for domain in site.domains:
        block = build_domain(domain)
        parts.append(b"\x12" + write_varint(len(block)) + block)
    return b"".join(parts)


def parse_geosite_file(path: pathlib.Path) -> list[GeoSite]:
    data = path.read_bytes()
    sites: list[GeoSite] = []
    offset = 0
    while offset < len(data):
        tag, offset = read_varint(data, offset)
        field_no = tag >> 3
        wire_type = tag & 0x07
        if field_no != 1 or wire_type != 2:
            raise ValueError(f"Unexpected top-level field {field_no} wire type {wire_type}")
        length, offset = read_varint(data, offset)
        sites.append(parse_geosite(data[offset : offset + length]))
        offset += length
    return sites


def build_geosite_file(sites: list[GeoSite]) -> bytes:
    out = bytearray()
    for site in sites:
        block = build_geosite(site)
        out.extend(b"\x0a")
        out.extend(write_varint(len(block)))
        out.extend(block)
    return bytes(out)


def normalize_name(name: str) -> str:
    return name.strip().lower()


def safe_filename(name: str) -> str:
    return normalize_name(name).replace("/", "_") + ".txt"


def format_entry(entry: DomainEntry) -> str:
    prefix = DOMAIN_TYPE_TO_PREFIX.get(entry.match_type, "keyword")
    if entry.match_type == DOMAIN_TYPE_ROOT:
        base = entry.value
    else:
        base = f"{prefix}:{entry.value}"
    if entry.attrs:
        base += " " + " ".join(f"@{attr}" for attr in entry.attrs)
    return base


def parse_text_entry(line: str) -> DomainEntry:
    content = line.split("#", 1)[0].strip()
    if not content:
        raise ValueError("Empty line is not a domain rule")
    parts = content.split()
    token = parts[0]
    attrs = [part[1:] for part in parts[1:] if part.startswith("@")]
    if ":" in token:
        prefix, value = token.split(":", 1)
        prefix = prefix.lower()
        match_type = DOMAIN_PREFIX_TO_TYPE.get(prefix)
        if match_type is None:
            raise ValueError(f"Unsupported prefix: {prefix}")
    else:
        value = token
        match_type = DOMAIN_TYPE_ROOT
    return DomainEntry(match_type=match_type, value=value, attrs=attrs)


def parse_categories_arg(categories_arg: list[str] | None) -> list[str]:
    if not categories_arg:
        return []
    result = []
    for item in categories_arg:
        for part in item.split(","):
            part = part.strip()
            if part:
                result.append(part)
    return result


def extract_sites(input_path: pathlib.Path, output_dir: pathlib.Path, categories: list[str] | None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    wanted = {normalize_name(name) for name in parse_categories_arg(categories)} if categories else None
    sites = parse_geosite_file(input_path)
    written = 0
    for site in sites:
        if wanted and normalize_name(site.name) not in wanted:
            continue
        out_path = output_dir / safe_filename(site.name)
        lines = [format_entry(entry) for entry in site.domains]
        out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        written += 1
    suffix = "y" if written == 1 else "ies"
    print(f"Extracted {written} categor{suffix} to {output_dir}")


def extract_one_category(input_path: pathlib.Path, category: str, output_file: pathlib.Path) -> None:
    wanted = normalize_name(category)
    for site in parse_geosite_file(input_path):
        if normalize_name(site.name) == wanted:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(
                "\n".join(format_entry(entry) for entry in site.domains) + "\n",
                encoding="utf-8",
            )
            print(f"Extracted {site.name} to {output_file}")
            return
    raise SystemExit(f"Category not found: {category}")


def build_from_directory(input_dir: pathlib.Path, output_path: pathlib.Path) -> None:
    sites: list[GeoSite] = []
    for txt_file in sorted(input_dir.glob("*.txt")):
        lines = txt_file.read_text(encoding="utf-8").splitlines()
        entries = []
        for raw_line in lines:
            stripped = raw_line.split("#", 1)[0].strip()
            if not stripped:
                continue
            entries.append(parse_text_entry(stripped))
        if entries:
            sites.append(GeoSite(name=txt_file.stem.upper(), domains=entries))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(build_geosite_file(sites))
    print(f"Built {len(sites)} categories into {output_path}")


def list_categories(input_path: pathlib.Path) -> None:
    for site in parse_geosite_file(input_path):
        print(f"{site.name}\t{len(site.domains)}")


def filter_geosite(
    input_path: pathlib.Path,
    output_dat: pathlib.Path,
    output_txt_dir: pathlib.Path,
    categories: list[str],
) -> None:
    cleaned = parse_categories_arg(categories)
    if not cleaned:
        raise SystemExit("Error: category list is empty; refuse to build all categories")

    sites = parse_geosite_file(input_path)
    available: dict[str, GeoSite] = {normalize_name(s.name): s for s in sites}

    missing = [cat for cat in cleaned if normalize_name(cat) not in available]
    if missing:
        missing_str = ", ".join(missing)
        raise SystemExit(f"Error: categories not found in {input_path.name}: {missing_str}")

    seen = set()
    filtered: list[GeoSite] = []
    for cat in cleaned:
        norm = normalize_name(cat)
        if norm not in seen:
            seen.add(norm)
            filtered.append(available[norm])

    output_dat.parent.mkdir(parents=True, exist_ok=True)
    output_dat.write_bytes(build_geosite_file(filtered))

    output_txt_dir.mkdir(parents=True, exist_ok=True)
    for site in filtered:
        out_path = output_txt_dir / safe_filename(site.name)
        lines = [format_entry(entry) for entry in site.domains]
        out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    print(f"Filtered {len(filtered)} GeoSite categories into {output_dat} and {output_txt_dir}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract, build, and filter custom geosite.dat files")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List categories inside geosite.dat")
    list_parser.add_argument("input", type=pathlib.Path)

    extract_parser = subparsers.add_parser("extract", help="Extract categories to text files")
    extract_parser.add_argument("input", type=pathlib.Path)
    extract_parser.add_argument("output_dir", type=pathlib.Path)
    extract_parser.add_argument("--category", action="append", default=[], help="Category to extract")

    one_parser = subparsers.add_parser("extract-category", help="Extract one category to one text file")
    one_parser.add_argument("input", type=pathlib.Path)
    one_parser.add_argument("category")
    one_parser.add_argument("output_file", type=pathlib.Path)

    build_parser_cmd = subparsers.add_parser("build", help="Build geosite.dat from text files")
    build_parser_cmd.add_argument("input_dir", type=pathlib.Path)
    build_parser_cmd.add_argument("output", type=pathlib.Path)

    filter_parser = subparsers.add_parser("filter", help="Filter categories to dat and txt dir")
    filter_parser.add_argument("input", type=pathlib.Path)
    filter_parser.add_argument("output_dat", type=pathlib.Path)
    filter_parser.add_argument("output_txt_dir", type=pathlib.Path)
    filter_parser.add_argument("--category", action="append", required=True, help="Category to keep")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list":
        list_categories(args.input)
    elif args.command == "extract":
        extract_sites(args.input, args.output_dir, args.category)
    elif args.command == "extract-category":
        extract_one_category(args.input, args.category, args.output_file)
    elif args.command == "build":
        build_from_directory(args.input_dir, args.output)
    elif args.command == "filter":
        filter_geosite(args.input, args.output_dat, args.output_txt_dir, args.category)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
