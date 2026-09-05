from __future__ import annotations

import argparse
import ipaddress
import pathlib
import sys
from dataclasses import dataclass, field


@dataclass
class CIDREntry:
    ip: bytes
    prefix: int


@dataclass
class GeoIP:
    country_code: str
    cidrs: list[CIDREntry] = field(default_factory=list)
    reverse_match: bool = False


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


def parse_cidr(block: bytes) -> CIDREntry:
    ip_bytes = b""
    prefix = 0
    offset = 0
    while offset < len(block):
        tag, offset = read_varint(block, offset)
        field_no = tag >> 3
        wire_type = tag & 0x07
        if field_no == 1 and wire_type == 2:
            length, offset = read_varint(block, offset)
            ip_bytes = block[offset : offset + length]
            offset += length
        elif field_no == 2 and wire_type == 0:
            prefix, offset = read_varint(block, offset)
        else:
            offset = skip_field(block, offset, wire_type)
    return CIDREntry(ip=ip_bytes, prefix=prefix)


def build_cidr(entry: CIDREntry) -> bytes:
    parts = [b"\x0a" + write_varint(len(entry.ip)) + entry.ip]
    if entry.prefix != 0:
        parts.append(b"\x10" + write_varint(entry.prefix))
    return b"".join(parts)


def parse_geoip(block: bytes) -> GeoIP:
    country_code = ""
    cidrs: list[CIDREntry] = []
    reverse_match = False
    offset = 0
    while offset < len(block):
        tag, offset = read_varint(block, offset)
        field_no = tag >> 3
        wire_type = tag & 0x07
        if field_no == 1 and wire_type == 2:
            length, offset = read_varint(block, offset)
            country_code = block[offset : offset + length].decode("utf-8")
            offset += length
        elif field_no == 2 and wire_type == 2:
            length, offset = read_varint(block, offset)
            cidrs.append(parse_cidr(block[offset : offset + length]))
            offset += length
        elif field_no == 3 and wire_type == 0:
            val, offset = read_varint(block, offset)
            reverse_match = bool(val)
        else:
            offset = skip_field(block, offset, wire_type)
    if not country_code:
        raise ValueError("GeoIP entry without country_code")
    return GeoIP(country_code=country_code, cidrs=cidrs, reverse_match=reverse_match)


def build_geoip(item: GeoIP) -> bytes:
    cc_bytes = item.country_code.encode("utf-8")
    parts = [b"\x0a" + write_varint(len(cc_bytes)) + cc_bytes]
    for cidr in item.cidrs:
        block = build_cidr(cidr)
        parts.append(b"\x12" + write_varint(len(block)) + block)
    if item.reverse_match:
        parts.append(b"\x18" + write_varint(1))
    return b"".join(parts)


def parse_geoip_file(path: pathlib.Path) -> list[GeoIP]:
    data = path.read_bytes()
    entries: list[GeoIP] = []
    offset = 0
    while offset < len(data):
        tag, offset = read_varint(data, offset)
        field_no = tag >> 3
        wire_type = tag & 0x07
        if field_no != 1 or wire_type != 2:
            raise ValueError(f"Unexpected top-level field {field_no} wire type {wire_type}")
        length, offset = read_varint(data, offset)
        entries.append(parse_geoip(data[offset : offset + length]))
        offset += length
    return entries


def build_geoip_file(entries: list[GeoIP]) -> bytes:
    out = bytearray()
    for item in entries:
        block = build_geoip(item)
        out.extend(b"\x0a")
        out.extend(write_varint(len(block)))
        out.extend(block)
    return bytes(out)


def normalize_name(name: str) -> str:
    return name.strip().lower()


def safe_filename(name: str) -> str:
    return normalize_name(name).replace("/", "_") + ".txt"


def format_cidr_entry(entry: CIDREntry) -> str:
    ip_obj = ipaddress.ip_address(entry.ip)
    return f"{ip_obj}/{entry.prefix}"


def parse_cidr_line(line: str) -> CIDREntry:
    content = line.split("#", 1)[0].strip()
    if not content:
        raise ValueError("Empty line is not a valid CIDR")
    net = ipaddress.ip_network(content, strict=False)
    return CIDREntry(ip=net.network_address.packed, prefix=net.prefixlen)


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


def extract_entries(input_path: pathlib.Path, output_dir: pathlib.Path, categories: list[str] | None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    wanted = {normalize_name(name) for name in parse_categories_arg(categories)} if categories else None
    entries = parse_geoip_file(input_path)
    written = 0
    for item in entries:
        if wanted and normalize_name(item.country_code) not in wanted:
            continue
        out_path = output_dir / safe_filename(item.country_code)
        lines = [format_cidr_entry(c) for c in item.cidrs]
        out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        written += 1
    suffix = "y" if written == 1 else "ies"
    print(f"Extracted {written} categor{suffix} to {output_dir}")


def build_from_directory(input_dir: pathlib.Path, output_path: pathlib.Path) -> None:
    entries: list[GeoIP] = []
    for txt_file in sorted(input_dir.glob("*.txt")):
        lines = txt_file.read_text(encoding="utf-8").splitlines()
        cidrs = []
        for raw_line in lines:
            stripped = raw_line.split("#", 1)[0].strip()
            if not stripped:
                continue
            cidrs.append(parse_cidr_line(stripped))
        if cidrs:
            entries.append(GeoIP(country_code=txt_file.stem.upper(), cidrs=cidrs))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(build_geoip_file(entries))
    print(f"Built {len(entries)} categories into {output_path}")


def list_categories(input_path: pathlib.Path) -> None:
    for item in parse_geoip_file(input_path):
        print(f"{item.country_code}\t{len(item.cidrs)}")


def filter_geoip(
    input_path: pathlib.Path,
    output_dat: pathlib.Path,
    output_txt_dir: pathlib.Path,
    categories: list[str],
) -> None:
    cleaned = parse_categories_arg(categories)
    if not cleaned:
        raise SystemExit("Error: category list is empty; refuse to build all categories")

    entries = parse_geoip_file(input_path)
    available: dict[str, GeoIP] = {normalize_name(e.country_code): e for e in entries}

    missing = [cat for cat in cleaned if normalize_name(cat) not in available]
    if missing:
        missing_str = ", ".join(missing)
        raise SystemExit(f"Error: categories not found in {input_path.name}: {missing_str}")

    seen = set()
    filtered: list[GeoIP] = []
    for cat in cleaned:
        norm = normalize_name(cat)
        if norm not in seen:
            seen.add(norm)
            filtered.append(available[norm])

    output_dat.parent.mkdir(parents=True, exist_ok=True)
    output_dat.write_bytes(build_geoip_file(filtered))

    output_txt_dir.mkdir(parents=True, exist_ok=True)
    for item in filtered:
        out_path = output_txt_dir / safe_filename(item.country_code)
        lines = [format_cidr_entry(c) for c in item.cidrs]
        out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    print(f"Filtered {len(filtered)} GeoIP categories into {output_dat} and {output_txt_dir}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract, build, and filter custom geoip.dat files")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List categories inside geoip.dat")
    list_parser.add_argument("input", type=pathlib.Path)

    extract_parser = subparsers.add_parser("extract", help="Extract categories to text files")
    extract_parser.add_argument("input", type=pathlib.Path)
    extract_parser.add_argument("output_dir", type=pathlib.Path)
    extract_parser.add_argument("--category", action="append", default=[], help="Category to extract")

    build_parser_cmd = subparsers.add_parser("build", help="Build geoip.dat from text files")
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
        extract_entries(args.input, args.output_dir, args.category)
    elif args.command == "build":
        build_from_directory(args.input_dir, args.output)
    elif args.command == "filter":
        filter_geoip(args.input, args.output_dat, args.output_txt_dir, args.category)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
