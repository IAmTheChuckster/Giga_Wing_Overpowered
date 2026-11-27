#!/usr/bin/env python3
"""Rebuild ALL patch entries in patches.json from source.

Patches built here (see devs_notes/DEV_NOTES.md):
  * Button 3 = 10Hz rapid Shot (4 hooked port reads + reader routines at $90100)
  * Reflect Force cooldown 2x faster (gauge drain $10 -> $20 per frame at $4A62E)
  * Medal magnet: medals near the ship get pulled in (hooks $23652/$237D6, code at $901C0)
  * Bullet cancel: enemy kill turns nearby enemy bullets (chained) into small medals (hook $67E5A, code at $90250)
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


# ---------------- medal magnet ----------------
MAGNET = 0x901C0        # after the rapid-fire readers ($90100-$901A7), same verified-unused block
MAGNET_RANGE = 0x60     # pull medals within 96 px (both axes) of the ship
MAGNET_SHIFT = 14       # pull speed per frame: distance << SHIFT in 16.16 -> 16 = 100%, 15 = 50%, 14 = 25%, 13 = 12.5%
# Each frame, before the game's own medal pickup check, every medal within MAGNET_RANGE moves a fraction of
# the way to the ship (X/Y += distance << MAGNET_SHIFT in 16.16 fixed point), so it visibly gets sucked in and the normal
# pickup collects it. Medals live in two linked lists (heads at -$10C0(a5) and -$10BC(a5)); node layout:
# +0 next, +6 X (16.16), +$A Y (16.16). Players: P1 object $2DEA(a5), P2 $2EAA(a5), X word +$A, Y word +$E.
MAGNET_SITES = [(0x23652, 0x2DEA, "P1 medal pickup $23652"), (0x237D6, 0x2EAA, "P2 medal pickup $237d6")]


def assemble(items, base):
    """Tiny two-pass assembler: items are bytes, ("label", name), ("b8", opcode, name) for
    short branches, or ("b16", opcode, name) for word-displacement branches."""
    def size(it):
        return len(it) if isinstance(it, bytes) else {"label": 0, "b8": 2, "b16": 4}[it[0]]
    labels, pc = {}, base
    for it in items:
        if not isinstance(it, bytes) and it[0] == "label":
            labels[it[1]] = pc
        pc += size(it)
    out, pc = b"", base
    for it in items:
        if isinstance(it, bytes):
            out += it
        elif it[0] == "b8":
            d = labels[it[2]] - (pc + 2)
            assert -128 <= d <= 127 and d != 0, (it, d)
            out += w(it[1] | (d & 0xFF))
        elif it[0] == "b16":
            out += w(it[1], (labels[it[2]] - (pc + 2)) & 0xFFFF)
        pc += size(it)
    return out, labels


def asl(count, reg):
    """asl.l #count,dReg (count 1..8; encoding uses 0 for 8)."""
    assert 1 <= count <= 8
    return 0xE180 | ((count & 7) << 9) | reg


def magnet_code():
    R = MAGNET_RANGE
    items = [
        ("label", "p1"), w(0x45ED, 0x2DEA), ("b8", 0x6000, "common"),     # lea $2dea(a5),a2 ; bra.s common
        ("label", "p2"), w(0x45ED, 0x2EAA),                               # lea $2eaa(a5),a2
        ("label", "common"),
        w(0x48E7, 0xFC80),                                                # movem.l d0-d5/a0,-(sp)
        w(0x3012), w(0x0A40, 0x8000), w(0x0240, 0xE000),                  # player active? (same test as the game)
        ("b8", 0x6600, "done"),
        w(0x322A, 0x000A), w(0x342A, 0x000E),                             # d1 = player X, d2 = player Y
        w(0x41ED, 0xEF40), ("b16", 0x6100, "pull"),                       # lea -$10c0(a5),a0 ; bsr.w pull
        w(0x41ED, 0xEF44), ("b16", 0x6100, "pull"),                       # lea -$10bc(a5),a0 ; bsr.w pull
        ("label", "done"),
        w(0x4CDF, 0x013F),                                                # movem.l (sp)+,d0-d5/a0
        w(0x3012), w(0x4E75),                                             # move.w (a2),d0 (displaced) ; rts
        ("label", "pull"),                                                # walk one medal list from (a0)
        w(0x2010), ("b8", 0x6700, "ret"), w(0x2040),                      # move.l (a0),d0 ; beq ret ; movea.l d0,a0
        w(0x3601), w(0x9668, 0x0006),                                     # d3 = px - medal X
        w(0x3803), w(0x6A02), w(0x4444), w(0x0C44, R), ("b8", 0x6400, "pull"),   # |dx| < R ?
        w(0x3A02), w(0x9A68, 0x000A),                                     # d5 = py - medal Y
        w(0x3805), w(0x6A02), w(0x4444), w(0x0C44, R), ("b8", 0x6400, "pull"),   # |dy| < R ?
        w(0x48C3), w(0xE183), w(asl(MAGNET_SHIFT - 8, 3)), w(0xD7A8, 0x0006),   # X += dx << MAGNET_SHIFT
        w(0x48C5), w(0xE185), w(asl(MAGNET_SHIFT - 8, 5)), w(0xDBA8, 0x000A),   # Y += dy << MAGNET_SHIFT
        w(0x42A8, 0x000E), w(0x42A8, 0x0012),                             # clr.l vx, vy: stop its own fall/drift
                                                                          # (else gravity holds it below the ship)
        ("b8", 0x6000, "pull"),
        ("label", "ret"), w(0x4E75),
    ]
    return assemble(items, MAGNET)


# ---------------- bullet cancel ----------------
CANCEL = 0x90250          # after the magnet code, same verified-unused block
CANCEL_SITE = 0x67E5A     # in the common "enemy destroyed" routine $67E52: btst #4,$1(a6) (6 bytes, kill path only)
CANCEL_KILL_R = 32        # bullets within 32 px of the dead enemy are cancelled
CANCEL_CHAIN_R = 16       # ...and any bullet within 16 px of a cancelled bullet, repeatedly (chain)
SMALL_MEDAL = 8           # medal type used by the game's own bullet->medal conversion ($23D50)
# Enemy bullets: two linked lists (heads -$10E4(a5) spawning, -$10E0(a5) moving), count -$10D4(a5),
# free node list -$10D8(a5); node +0 next, +6 X, +$A Y. Medal spawner $2B60E: d0 = Y vel, d1 = X vel,
# d2/d3 = X/Y, d4 = type. Random: $378A (returns d0, clobbers nothing else).


def cancel_code():
    items = [
        w(0x48E7, 0xFFFE),                                   # movem.l d0-d7/a0-a6,-(sp)
        w(0x3C2E, 0x000A), w(0x3E2E, 0x000E),                # d6/d7 = enemy X/Y
        w(0x95CA), w(0x97CB),                                # a2 = a3 = 0 (cancelled list head/tail)
        w(0x2A3C) + l(CANCEL_KILL_R ** 2),                   # d5 = R^2
        ("b16", 0x6100, "gather"),
        w(0x224A),                                           # a1 = cancelled head (chain cursor)
        ("label", "chain"),
        w(0x2009), ("b8", 0x6700, "spawn"),                  # while a1
        w(0x3C29, 0x0006), w(0x3E29, 0x000A),                # centre = this cancelled bullet
        w(0x2A3C) + l(CANCEL_CHAIN_R ** 2),
        w(0x2F09), ("b16", 0x6100, "gather"), w(0x225F),     # gather (keeps a1)
        w(0x2251), ("b8", 0x6000, "chain"),                  # a1 = a1->next
        ("label", "spawn"),
        w(0x200A), ("b8", 0x6700, "done"),                   # while cancelled list not empty
        w(0x2240), w(0x2451),                                # a1 = node, a2 = next
        w(0x3429, 0x0006), w(0x3629, 0x000A),                # d2/d3 = X/Y
        w(0x22AD, 0xEF28), w(0x2B49, 0xEF28), w(0x536D, 0xEF2C),   # free node like the game, count--
        w(0x4EB9) + l(0x378A), w(0x2200), w(0x4EB9) + l(0x378A),   # random velocity (as $23D52)
        w(0x0280) + l(0x1FFFF), w(0x0281) + l(0x3FFF), w(0x0481) + l(0x2000),
        w(0x7800 | SMALL_MEDAL), w(0x4EB9) + l(0x2B60E),     # spawn small medal
        ("b8", 0x6000, "spawn"),
        ("label", "done"),
        w(0x4CDF, 0x7FFF),                                   # movem.l (sp)+,d0-d7/a0-a6
        w(0x082E, 0x0004, 0x0001), w(0x4E75),                # btst #4,$1(a6) (displaced) ; rts (keeps CCR)
        ("label", "gather"),                                 # move bullets within sqrt(d5) of (d6,d7) to cancel list
        w(0x49ED, 0xEF1C), ("b16", 0x6100, "scan"),          # lea -$10e4(a5),a4
        w(0x49ED, 0xEF20),                                   # lea -$10e0(a5),a4 ; fall into scan
        ("label", "scan"),                                   # a4 = address of the previous link field
        w(0x2014), ("b8", 0x6700, "sret"), w(0x2040),        # a0 = next bullet
        w(0x3228, 0x0006), w(0x9246), w(0xC3C1),             # d1 = dx^2
        w(0x3428, 0x000A), w(0x9447), w(0xC5C2),             # d2 = dy^2
        w(0xD282), w(0xB285), ("b8", 0x6400, "keep"),        # if dx^2+dy^2 >= R^2: keep
        w(0x2890), w(0x4290),                                # unlink: *a4 = a0->next ; a0->next = 0
        w(0x200B), ("b8", 0x6600, "app"), w(0x2448), ("b8", 0x6000, "set"),
        ("label", "app"), w(0x2688),                         # tail->next = a0
        ("label", "set"), w(0x2648), ("b8", 0x6000, "scan"), # tail = a0
        ("label", "keep"), w(0x2848), ("b8", 0x6000, "scan"),
        ("label", "sret"), w(0x4E75),
    ]
    return assemble(items, CANCEL)


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
        # Medal magnet
        mcode, mlab = magnet_code()
        assert MAGNET + len(mcode) <= 0x90818 and MAGNET >= HOOK + len(code)
        try:
            for i in md.disasm(mcode, MAGNET):
                print(f"{i.address:06x}: {i.bytes.hex():<16} {i.mnemonic} {i.op_str}")
        except NameError:
            pass
        for site, poff, desc in MAGNET_SITES:
            entry = mlab["p1"] if poff == 0x2DEA else mlab["p2"]
            e = patch("ggwj.03a", 0, site, w(0x4EB9) + l(entry))
            e["note"] = f"{desc}: lea ${poff:x}(a5),a2 + move.w (a2),d0 -> jsr ${entry:x} (medal magnet, CPS2-encrypted)"
            patches.append(e)
        e = patch("ggwj.04a", 0x80000, MAGNET, mcode)
        e["note"] = (f"Medal magnet at ${MAGNET:x} (CPS2-encrypted): medals within {MAGNET_RANGE} px of the ship "
                     "move 25% closer each frame (both medal lists), then the game's normal pickup collects them.")
        patches.append(e)

        # Bullet cancel
        ccode, _ = cancel_code()
        assert CANCEL >= MAGNET + len(mcode) and CANCEL + len(ccode) <= 0x90818
        try:
            for i in md.disasm(ccode, CANCEL):
                print(f"{i.address:06x}: {i.bytes.hex():<16} {i.mnemonic} {i.op_str}")
        except NameError:
            pass
        e = patch("ggwj.03a", 0, CANCEL_SITE, w(0x4EB9) + l(CANCEL))
        e["note"] = f"Enemy destroyed $67E52: btst #4,$1(a6) at ${CANCEL_SITE:x} -> jsr ${CANCEL:x} (bullet cancel, CPS2-encrypted)"
        patches.append(e)
        e = patch("ggwj.04a", 0x80000, CANCEL, ccode)
        e["note"] = (f"Bullet cancel at ${CANCEL:x} (CPS2-encrypted): on enemy kill, enemy bullets within {CANCEL_KILL_R} px, "
                     f"then any within {CANCEL_CHAIN_R} px of a cancelled bullet (chained), become small medals (type {SMALL_MEDAL}).")
        patches.append(e)

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
