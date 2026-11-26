#!/usr/bin/env python3
"""Giga Wing Overpowered - command line patcher (gigawingj, Japan 990223).

Usage:
  python gigawing_patch.py patch gigawing.zip [-o out/gigawingop.zip]
      Verify your romset and write a complete, patched gigawingop.zip
      (works in MAME; needs qsound.zip next to it like any CPS2 game).

  python gigawing_patch.py sync [gigawing.zip]
      Maintainer command. Applies patches.json to the local romset,
      writes the resulting CRCs into the MRA, embeds the patch into
      index.html and bumps BUILD when the patcher changed (logged in BUILDS.md).

Patches live in patches.json, each entry:
  {"file": "ggwj.03a", "offset": "0x1234", "original": "4e75", "patched": "4e71", "note": "..."}
Offsets/bytes are for the raw ROM files as stored in the zip. Note that CPS2
program ROMs are encrypted: opcode edits must be written in encrypted form.
"""
import argparse
import datetime
import hashlib
import json
import re
import sys
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATCHES = ROOT / "patches.json"
INDEX = ROOT / "index.html"
BUILDS = ROOT / "BUILDS.md"
MRA = ROOT / "mister" / "Giga Wing Overpowered.mra"
DEFAULT_ROM = ROOT / "roms" / "gigawing.zip"

# Every file MAME needs for gigawingj (clone + parent), with the original CRC32.
ROMSET = {
    "gigawingj.key": (20, "8121a25e"),
    "ggwj.03a": (524288, "fdd23b91"),
    "ggwj.04a": (524288, "8c6e093c"),
    "ggwj.05a": (524288, "43811454"),
    "ggw.01": (131072, "4c6351d5"),
    "ggw.11m": (4194304, "e172acf5"),
    "ggw.12m": (4194304, "4bee4e8f"),
    "ggw.13m": (4194304, "105530a4"),
    "ggw.15m": (4194304, "9e774ab9"),
    "ggw.17m": (4194304, "466e0ba4"),
    "ggw.19m": (4194304, "840c8dea"),
}

crc_hex = lambda b: f"{zlib.crc32(b) & 0xFFFFFFFF:08x}"


def load_patches():
    return json.loads(PATCHES.read_text(encoding="utf-8"))


def read_romset(path):
    """Find each needed file in the zip by CRC (any folder, any name)."""
    by_crc = {}
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if not info.is_dir():
                by_crc.setdefault((info.file_size, f"{info.CRC:08x}"), info)
        files, errors = {}, []
        for name, (size, crc) in ROMSET.items():
            info = by_crc.get((size, crc))
            if info is None:
                errors.append(f"{name}: not found (need CRC {crc}, {size} bytes)")
                continue
            data = z.read(info)
            if crc_hex(data) != crc:
                errors.append(f"{name}: data damaged inside zip")
                continue
            files[name] = data
    if errors:
        raise SystemExit("Romset check failed:\n  " + "\n  ".join(errors))
    return files


def apply_patches(files, patches):
    out = {n: bytearray(d) for n, d in files.items()}
    for i, p in enumerate(patches):
        name, off = p["file"], int(str(p["offset"]), 0)
        orig, new = bytes.fromhex(p["original"]), bytes.fromhex(p["patched"])
        if name not in out:
            raise SystemExit(f"patch {i}: unknown file {name}")
        if len(orig) != len(new):
            raise SystemExit(f"patch {i}: original and patched lengths differ")
        if out[name][off:off + len(orig)] != orig:
            raise SystemExit(f"patch {i} ({name} @ {off:#x}): original bytes don't match")
        out[name][off:off + len(new)] = new
    return {n: bytes(d) for n, d in out.items()}


def write_zip(files, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1996, 12, 24, 23, 32, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, files[name])


def cmd_patch(args):
    cfg = load_patches()
    files = apply_patches(read_romset(args.romset), cfg["patches"])
    expected = cfg.get("outputs", {})
    for name, data in files.items():
        crc = crc_hex(data)
        if name in expected and expected[name] != crc:
            raise SystemExit(f"{name}: result CRC {crc} != expected {expected[name]}. Please report this.")
        print(f"  {name:14} {crc}" + ("  (patched)" if crc != ROMSET[name][1] else ""))
    write_zip(files, Path(args.output))
    print(f"Build {current_build()}: wrote {args.output} ({len(cfg['patches'])} patch(es) applied)")


# ---------------- maintainer: sync ----------------
BUILD_RE = re.compile(r"const BUILD = (\d+);")
MRA_RE = re.compile(r"(// MRA-BEGIN\n).*?(\n// MRA-END)", re.S)
DATA_RE = re.compile(r"(// PATCH-DATA-BEGIN\n).*?(\n// PATCH-DATA-END)", re.S)


def current_build():
    m = BUILD_RE.search(INDEX.read_text(encoding="utf-8"))
    return int(m.group(1)) if m else 0


def cmd_sync(args):
    cfg = load_patches()
    files = apply_patches(read_romset(args.romset), cfg["patches"])
    outputs = {n: crc_hex(d) for n, d in files.items()}
    sha1 = {n: hashlib.sha1(d).hexdigest() for n, d in files.items()}

    # 1. patches.json: record expected output CRCs
    cfg["outputs"] = outputs
    PATCHES.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    # 2. MRA: update every part crc
    mra = MRA.read_text(encoding="utf-8")
    for name, crc in outputs.items():
        mra = re.sub(rf'(<part name="{re.escape(name)}" crc=")[0-9a-fA-F]{{8}}"', rf'\g<1>{crc}"', mra)
    MRA.write_text(mra, encoding="utf-8", newline="\n")

    # 3. index.html: embed patch data, bump build if anything changed
    html = INDEX.read_text(encoding="utf-8")
    data = {"patches": cfg["patches"], "outputs": {n: {"crc": outputs[n], "sha1": sha1[n]} for n in outputs}}
    new = DATA_RE.sub(lambda m: m.group(1) + "const PATCH = " + json.dumps(data, indent=1) + ";" + m.group(2), html)
    new = MRA_RE.sub(lambda m: m.group(1) + "const MRA = " + json.dumps(mra) + ";" + m.group(2), new)
    hook = getattr(args, "staged_change", False)
    if new != html or hook:
        build = current_build() + 1
        new = BUILD_RE.sub(f"const BUILD = {build};", new)
        INDEX.write_text(new, encoding="utf-8", newline="\n")
        with BUILDS.open("a", encoding="utf-8") as f:
            f.write(f"- Build {build} ({datetime.date.today()}): {len(cfg['patches'])} patch(es); "
                    f"ggwj.03a {outputs['ggwj.03a']}, ggwj.04a {outputs['ggwj.04a']}, ggwj.05a {outputs['ggwj.05a']}\n")
        print(f"Patcher updated -> Build {build}")
    else:
        print(f"Patcher unchanged (Build {current_build()})")
    print("MRA CRCs:", ", ".join(f"{n}={c}" for n, c in outputs.items()))


def main():
    ap = argparse.ArgumentParser(description="Giga Wing Overpowered patcher (gigawingj)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("patch", help="patch your romset")
    p.add_argument("romset", nargs="?", default=str(DEFAULT_ROM))
    p.add_argument("-o", "--output", default=str(ROOT / "out" / "gigawingop.zip"))
    s = sub.add_parser("sync", help="update MRA CRCs and index.html from patches.json")
    s.add_argument("romset", nargs="?", default=str(DEFAULT_ROM))
    s.add_argument("--staged-change", action="store_true", help="force a build bump (used by the git hook)")
    args = ap.parse_args()
    {"patch": cmd_patch, "sync": cmd_sync}[args.cmd](args)


if __name__ == "__main__":
    main()
