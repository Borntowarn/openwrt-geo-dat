from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import shutil
import sys
import urllib.request
import zipfile

import geoip_tool
import geosite_tool


def parse_categories(val: str | list[str] | None) -> list[str]:
    """Parse categories from comma- and/or newline-separated text."""
    if not val:
        return []
    if isinstance(val, list):
        items = val
    else:
        items = [val]
    result = []
    for item in items:
        for part in item.replace(",", "\n").splitlines():
            part = part.strip()
            if part:
                result.append(part)
    return result


def calc_sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def verify_sha256(file_path: pathlib.Path, sum_path: pathlib.Path) -> None:
    sum_content = sum_path.read_text(encoding="utf-8").strip()
    expected_hash = sum_content.split()[0].lower()
    actual_hash = calc_sha256(file_path).lower()
    if actual_hash != expected_hash:
        raise ValueError(
            f"SHA256 checksum verification failed for {file_path.name}:\n"
            f"  Expected: {expected_hash}\n"
            f"  Actual:   {actual_hash}"
        )


def download_file(url: str, dest: pathlib.Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "openwrt-geo-dat-builder/1.0"},
    )
    with urllib.request.urlopen(req) as response, open(dest, "wb") as out_file:
        shutil.copyfileobj(response, out_file)


def download_upstream(
    upstream: str,
    download_dir: pathlib.Path,
    skip_download: bool = False,
) -> tuple[pathlib.Path, pathlib.Path]:
    download_dir.mkdir(parents=True, exist_ok=True)
    base_url = f"https://github.com/{upstream}/releases/latest/download"
    files = [
        "geosite.dat",
        "geosite.dat.sha256sum",
        "geoip.dat",
        "geoip.dat.sha256sum",
    ]

    for fname in files:
        fpath = download_dir / fname
        if skip_download and fpath.exists():
            print(f"Using existing {fname}")
            continue
        url = f"{base_url}/{fname}"
        print(f"Downloading {url} -> {fpath}...")
        download_file(url, fpath)

    geosite_dat = download_dir / "geosite.dat"
    geosite_sum = download_dir / "geosite.dat.sha256sum"
    geoip_dat = download_dir / "geoip.dat"
    geoip_sum = download_dir / "geoip.dat.sha256sum"

    print("Verifying upstream checksums...")
    verify_sha256(geosite_dat, geosite_sum)
    verify_sha256(geoip_dat, geoip_sum)
    print("Upstream checksums verified successfully.")

    return geosite_dat, geoip_dat



def download_url_file(url: str, dest: pathlib.Path, skip_download: bool = False) -> pathlib.Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if skip_download and dest.exists():
        print(f"Using existing {dest.name}")
        return dest
    print(f"Downloading {url} -> {dest}...")
    download_file(url, dest)
    return dest


def download_optional_sha256(url: str, file_path: pathlib.Path, skip_download: bool = False) -> None:
    """Verify checksum if a sibling .sha256 / .sha256sum URL is available."""
    for sum_url in (url + ".sha256sum", url + ".sha256"):
        local_sum = pathlib.Path(str(file_path) + ".sha256sum")
        try:
            if not (skip_download and local_sum.exists()):
                download_file(sum_url, local_sum)
            verify_sha256(file_path, local_sum)
            print(f"Verified checksum via {sum_url}")
            return
        except Exception as exc:
            print(f"Checksum skip/fail for {sum_url}: {exc}")
            if local_sum.exists() and not skip_download:
                try:
                    local_sum.unlink()
                except OSError:
                    pass
    print(f"Warning: no checksum verified for {file_path.name}")

def create_zip(source_dir: pathlib.Path, zip_path: pathlib.Path, prefix: str) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(source_dir.rglob("*.txt")):
            if file.is_file():
                arcname = f"{prefix}/{file.name}"
                zf.write(file, arcname=arcname)


def package_release(out_dir: pathlib.Path) -> pathlib.Path:
    rel_dir = out_dir / "release"
    rel_dir.mkdir(parents=True, exist_ok=True)

    geosite_dat = out_dir / "geosite.dat"
    geoip_dat = out_dir / "geoip.dat"
    geosite_txt_dir = out_dir / "geosite-txt"
    geoip_txt_dir = out_dir / "geoip-txt"

    if not geosite_dat.is_file():
        raise SystemExit(f"Missing {geosite_dat}")
    if not geoip_dat.is_file():
        raise SystemExit(f"Missing {geoip_dat}")
    if not geosite_txt_dir.is_dir():
        raise SystemExit(f"Missing directory {geosite_txt_dir}")
    if not geoip_txt_dir.is_dir():
        raise SystemExit(f"Missing directory {geoip_txt_dir}")

    rel_geosite_dat = rel_dir / "geosite.dat"
    rel_geoip_dat = rel_dir / "geoip.dat"
    shutil.copyfile(geosite_dat, rel_geosite_dat)
    shutil.copyfile(geoip_dat, rel_geoip_dat)

    create_zip(geosite_txt_dir, rel_dir / "geosite-txt.zip", "geosite-txt")
    create_zip(geoip_txt_dir, rel_dir / "geoip-txt.zip", "geoip-txt")

    geosite_hash = calc_sha256(rel_geosite_dat)
    geoip_hash = calc_sha256(rel_geoip_dat)

    (rel_dir / "geosite.dat.sha256sum").write_text(f"{geosite_hash}  geosite.dat\n", encoding="utf-8")
    (rel_dir / "geoip.dat.sha256sum").write_text(f"{geoip_hash}  geoip.dat\n", encoding="utf-8")

    print(f"\nRelease package generated in {rel_dir}:")
    for item in sorted(rel_dir.iterdir()):
        size_kb = item.stat().st_size / 1024
        print(f"  {item.name} ({size_kb:.1f} KB)")

    return rel_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Orchestrator for building filtered geo release assets")
    parser.add_argument(
        "--upstream",
        default=os.environ.get("UPSTREAM", "runetfreedom/russia-v2ray-rules-dat"),
        help="Upstream GitHub repo OWNER/REPO (default: env UPSTREAM or runetfreedom/russia-v2ray-rules-dat)",
    )
    parser.add_argument(
        "--geosite-categories",
        default=os.environ.get("GEOSITE_CATEGORIES", ""),
        help="GeoSite categories, comma- or newline-separated (default: env GEOSITE_CATEGORIES)",
    )
    parser.add_argument(
        "--geoip-categories",
        default=os.environ.get("GEOIP_CATEGORIES", ""),
        help="GeoIP categories, comma- or newline-separated (default: env GEOIP_CATEGORIES)",
    )
    parser.add_argument(
        "--download-dir",
        type=pathlib.Path,
        default=pathlib.Path(os.environ.get("DOWNLOAD_DIR", ".tmp/upstream")),
        help="Directory to store downloaded upstream assets (default: .tmp/upstream)",
    )
    parser.add_argument(
        "--out-dir",
        type=pathlib.Path,
        default=pathlib.Path(os.environ.get("OUT_DIR", "out")),
        help="Output directory (default: out)",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip downloading if assets already exist in download-dir and match checksums",
    )
    parser.add_argument(
        "--ads-merge-url",
        default=os.environ.get(
            "ADS_MERGE_URL",
            "https://raw.githubusercontent.com/yularzhi/geosite_russia/release/geosite.dat",
        ),
        help="Extra geosite.dat URL to merge into ads category (default: geosite_russia release)",
    )
    parser.add_argument(
        "--ads-merge-category",
        default=os.environ.get("ADS_MERGE_CATEGORY", "category-ads-all"),
        help="Category name to merge from ads-merge-url (default: category-ads-all)",
    )
    parser.add_argument(
        "--no-ads-merge",
        action="store_true",
        help="Disable merging ads category from ADS_MERGE_URL",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    geosite_cats = parse_categories(args.geosite_categories)
    if not geosite_cats:
        print("Error: GEOSITE_CATEGORIES is empty; refuse to build all categories", file=sys.stderr)
        return 1

    geoip_cats = parse_categories(args.geoip_categories)
    if not geoip_cats:
        print("Error: GEOIP_CATEGORIES is empty; refuse to build all categories", file=sys.stderr)
        return 1

    print("Building release with:")
    print(f"  Upstream:           {args.upstream}")
    print(f"  GeoSite categories: {', '.join(geosite_cats)}")
    print(f"  GeoIP categories:   {', '.join(geoip_cats)}")
    print(f"  Download dir:       {args.download_dir}")
    print(f"  Output dir:         {args.out_dir}")
    if not args.no_ads_merge and (args.ads_merge_url or "").strip():
        print(f"  Ads merge URL:      {args.ads_merge_url}")
        print(f"  Ads merge category: {args.ads_merge_category}")

    up_geosite, up_geoip = download_upstream(
        upstream=args.upstream,
        download_dir=args.download_dir,
        skip_download=args.skip_download,
    )

    category_merges: dict[str, list[pathlib.Path]] = {}
    ads_cat = (args.ads_merge_category or "").strip()
    ads_url = (args.ads_merge_url or "").strip()
    if (
        not args.no_ads_merge
        and ads_url
        and ads_cat
        and any(geosite_tool.normalize_name(c) == geosite_tool.normalize_name(ads_cat) for c in geosite_cats)
    ):
        merge_dat = download_url_file(
            ads_url,
            args.download_dir / "merge" / "geosite_russia.dat",
            skip_download=args.skip_download,
        )
        download_optional_sha256(ads_url, merge_dat, skip_download=args.skip_download)
        category_merges[ads_cat] = [merge_dat]
        print(f"Ads merge enabled: {ads_cat} += {ads_url}")

    print("\nFiltering GeoSite...")
    geosite_tool.filter_geosite(
        input_path=up_geosite,
        output_dat=args.out_dir / "geosite.dat",
        output_txt_dir=args.out_dir / "geosite-txt",
        categories=geosite_cats,
        category_merges=category_merges or None,
    )

    print("\nFiltering GeoIP...")
    geoip_tool.filter_geoip(
        input_path=up_geoip,
        output_dat=args.out_dir / "geoip.dat",
        output_txt_dir=args.out_dir / "geoip-txt",
        categories=geoip_cats,
    )

    print("\nPackaging release...")
    package_release(args.out_dir)
    print("\nBuild completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
