#!/usr/bin/env python3
"""Rebuild ALL patch entries in patches.json from source.

Patches built here (see devs_notes/DEV_NOTES.md):
  * Button 3 = 10Hz rapid Shot (4 hooked port reads + reader routines at $90100)
  * Reflect Force cooldown 2x faster (gauge drain $10 -> $20 per frame at $4A62E)
  * Boot screen: GIGAWING OVERPOWERED / 2 6 1 1 2 7 (plain text at $60090 / $600E4)

What it does
  1. Builds the CPS2 encrypt/decrypt tools from patches/mmxi_v1.0.0_20250412.zip
     (tools/common.c, trap15, derived from MAME cps2crypt) with gcc
     (native gcc if on PATH, otherwise gcc inside WSL).
  2. Assembles the 68000 code (hand-encoded below, see devs_notes/DEV_NOTES.md).
  3. Inserts them into the decrypted program, re-encrypts with gigawingj.key and
     diffs against the original files, so only the intended bytes change.
  4. Writes the resulting entries into patches.json (replacing all patches).

Then run:  python gigawing_patch.py sync   (or just commit; the pre-commit hook syncs)

Usage:  python devs_notes/tools/build_patches.py [path/to/gigawing.zip]
Needs:  Python 3, gcc (native or WSL). Optional: `pip install capstone` for a listing.
"""
import json, shutil, struct, subprocess, sys, tempfile, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROMSET = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "roms" / "gigawing.zip"
TOOLS_ZIP = ROOT / "patches" / "mmxi_v1.0.0_20250412.zip"
HOOK = 0x90100          # unused zero block in ggwj.04a, inside the encrypted range
FRAME_CTR = 0xFF2090    # word, +1 every vblank ($b56)

w = lambda *a: b"".join(struct.pack(">H", x) for x in a)
l = lambda x: struct.pack(">I", x)
swap = lambda b: bytes(x for i in range(0, len(b), 2) for x in (b[i + 1], b[i]))


def reader(port, r):
    """move.b port,dR ; if Button 3 (bit6, active low) held and frame%6<3: bclr #4,dR (Shot pressed)."""
    t = 1 if r == 0 else 0                              # scratch register, saved/restored
    code = w(0x1039 | (r << 9)) + l(port)               # move.b port.l,dR
    tail = (w(0x2F00 | t)                               # move.l dT,-(sp)
            + w(0x7000 | (t << 9))                      # moveq #0,dT
            + w(0x3039 | (t << 9)) + l(FRAME_CTR)       # move.w FRAME_CTR,dT
            + w(0x80FC | (t << 9), 6)                   # divu #6,dT
            + w(0x4840 | t)                             # swap dT  (remainder)
            + w(0x0C40 | t, 3)                          # cmpi.w #3,dT
            + w(0x6404)                                 # bcc.s +4 (off phase)
            + w(0x0880 | r, 0x0004)                     # bclr #4,dR (Shot pressed, active low)
            + w(0x201F | (t << 9)))                     # move.l (sp)+,dT
    code += w(0x0800 | r, 0x0006) + w(0x6600 | len(tail)) + tail + w(0x4E75)   # btst #6,dR; bne.s done; ...; rts
    return code


# Every place the game reads the shot button straight from the I/O port (found with a
# MAME read tap on $804000-$804001 during gameplay). Original instruction: move.b port.l,dR (6 bytes).
SITES = [
    (0x804001, 6, 0x89BA, "P1 shot read (menu path) $89ba"),
    (0x804000, 6, 0x898A, "P2 shot read $898a"),
    (0x804001, 0, 0x3EAC, "P1 in-game input read $3eac"),
    (0x804000, 0, 0x3ED0, "P2 in-game input read $3ed0"),
]


def run(tmp, cmd):
    if shutil.which("gcc"):
        subprocess.run(cmd, shell=True, cwd=tmp, check=True, capture_output=True)
    else:  # fall back to WSL
        wsl_dir = subprocess.run(["wsl", "wslpath", "-a", str(tmp).replace("\\", "/")],
                                 check=True, capture_output=True, text=True).stdout.strip()
        subprocess.run(["wsl", "-e", "sh", "-c", f"cd '{wsl_dir}' && {cmd}"], check=True, capture_output=True)


def main():
    code, entries = b"", []
    for port, r, site, desc in SITES:
        entries.append((site, HOOK + len(code), desc, port, r))
        code += reader(port, r)
    try:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_M68K, capstone.CS_MODE_BIG_ENDIAN | capstone.CS_MODE_M68K_000)
        for i in md.disasm(code, HOOK):
            print(f"{i.address:06x}: {i.bytes.hex():<16} {i.mnemonic} {i.op_str}")
    except ImportError:
        print("(pip install capstone for a disassembly listing)")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with zipfile.ZipFile(TOOLS_ZIP) as z:
            (tmp / "common.c").write_bytes(z.read("mmxi_v1.0.0_20250412/tools/common.c"))
        with zipfile.ZipFile(ROMSET) as z:
            names = {n.split("/")[-1]: n for n in z.namelist()}
            for n in ("ggwj.03a", "ggwj.04a", "gigawingj.key"):
                (tmp / n).write_bytes(z.read(names[n]))
        run(tmp, "gcc -O2 -DBUILD_DECRYPTOR common.c -o decrypt && gcc -O2 -DBUILD_ENCRYPTOR common.c -o encrypt")

        def patch(fname, base, addr, new):
            run(tmp, f"./decrypt d.bin {fname} gigawingj.key {hex(base)} 2>/dev/null")
            d = bytearray((tmp / "d.bin").read_bytes())
            o = addr - base
            d[o:o + len(new)] = swap(new)
            (tmp / "pd.bin").write_bytes(d)
            run(tmp, f"./encrypt pe.bin pd.bin gigawingj.key {hex(base)} 2>/dev/null")
            orig, enc = (tmp / fname).read_bytes(), (tmp / "pe.bin").read_bytes()
            diff = [i for i in range(len(orig)) if orig[i] != enc[i]]
            assert diff and min(diff) >= o and max(diff) < o + len(new), "encryption changed unexpected bytes"
            return {"file": fname, "offset": hex(o), "original": orig[o:o + len(new)].hex(),
                    "patched": enc[o:o + len(new)].hex()}

        patches = []
        for site, entry, desc, port, r in entries:
            e = patch("ggwj.03a", 0, site, w(0x4EB9) + l(entry))
            e["note"] = f"{desc}: move.b ${port:x},d{r} -> jsr ${entry:x} (CPS2-encrypted)"
            patches.append(e)
        e = patch("ggwj.04a", 0x80000, HOOK, code)
        e["note"] = ("Rapid fire readers at $90100 (unused zero block, CPS2-encrypted): one per patched site; "
                     "each reads the player input port into the same register as the original and, while "
                     "Button 3 (bit6, active low) is held, forces Shot (bit4) pressed for 3 of every 6 frames "
                     "(frame counter $FF2090) = 10Hz.")
        patches.append(e)

        # Reflect Force cooldown: after a Reflect Force the RF gauge ($8A(a6), 0..$1000) drains with
        # `subi.w #$10,$8a(a6)` at $4A62E every frame (256 frames). Draining $20 halves the cooldown.
        RF_DRAIN = 0x20
        e = patch("ggwj.03a", 0, 0x4A62E, w(0x046E, RF_DRAIN, 0x008A))
        e["note"] = (f"Reflect Force cooldown 2x faster: subi.w #$10,$8a(a6) -> subi.w #${RF_DRAIN:x},$8a(a6) "
                     "at $4A62E (gauge $1000 drains in 128 frames instead of 256). CPS2-encrypted.")
        patches.append(e)

        # Boot screen text (Japan block of the region table at $60090). Data reads are never
        # decrypted, so text is plain in the ROM (just word-swapped). Each line is a 25-char field.
        def text(addr, old, new):
            assert len(old) == len(new) == 25, (old, new)
            raw = (tmp / "ggwj.03a").read_bytes()
            lo, hi = addr & ~1, (addr + 25 + 1) & ~1                  # whole words
            cpu = bytearray(swap(raw[lo:hi]))                       # CPU (big-endian) view
            assert cpu[addr - lo:addr - lo + 25] == old.encode(), cpu
            cpu[addr - lo:addr - lo + 25] = new.encode()
            return {"file": "ggwj.03a", "offset": hex(lo), "original": raw[lo:hi].hex(), "patched": swap(bytes(cpu)).hex()}
        e = text(0x60090, "       GIGAWING          ", "  GIGAWING OVERPOWERED   ")
        e["note"] = "Boot screen title: GIGAWING -> GIGAWING OVERPOWERED (plain data)"
        patches.append(e)
        e = text(0x600E4, "      9 9 0 2 2 3        ", "      2 6 1 1 2 7        ")
        e["note"] = "Boot screen date: 990223 -> 261127 (plain data)"
        patches.append(e)

    cfg_path = ROOT / "patches.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["patches"] = patches
    cfg.pop("outputs", None)
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(patches)} patch entries to patches.json. Now run: python gigawing_patch.py sync")


if __name__ == "__main__":
    main()
