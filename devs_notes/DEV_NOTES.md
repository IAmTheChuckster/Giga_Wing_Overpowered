# Giga Wing Overpowered: developer notes

Everything needed to rebuild this project from an empty repo, understand why it is built this way, and keep it updated. Add to this file whenever a patch, tool or finding changes (see [Keeping these notes updated](#keeping-these-notes-updated)).

Target set: **Giga Wing (Japan 990223)**, MAME `gigawingj` (clone of `gigawing`), Capcom CPS2, 68000 main CPU.

---

## 1. Repository layout

| Path | What it is |
|---|---|
| `patches.json` | **Single source of truth** for the patch: list of byte edits on the raw ROM files, plus the expected output CRCs (written by `sync`). |
| `gigawing_patch.py` | Command line patcher (`patch`) and maintainer tool (`sync`). |
| `index.html` | Self-contained web patcher. Patch data, MRA text and `BUILD` are embedded between markers by `sync`; never edit those blocks by hand. |
| `mister/Giga Wing Overpowered.mra` | MiSTer MRA for core `jtcps2`. CRCs of patched files are updated by `sync`. |
| `BUILDS.md` | One line per patcher build, appended by `sync`. |
| `.githooks/pre-commit` | Runs `sync` on commits that touch the patcher, `patches.json` or the MRA. |
| `patches/mmxi_v1.0.0_20250412.zip` | trap15's Mars Matrix Improvement release; its `tools/common.c` is the CPS2 encrypt/decrypt we use. |
| `devs_notes/tools/build_rapidfire.py` | Rebuilds the rapid-fire patch entries in `patches.json` from source (assemble, encrypt, diff). |
| `devs_notes/tools/mame/*.lua` | Headless MAME scripts: program dump, read-tap research, rapid-fire regression test. |
| `roms/` | Your own `gigawing.zip` (merged set incl. `gigawingj/`). **Gitignored, never committed.** |

`.gitignore` ignores `roms/`, all `*.zip` except `patches/*.zip`, `out/` and `__pycache__/`.

---

## 2. Setting up from scratch

1. **Romset:** put a MAME `gigawing.zip` (merged, must contain the `gigawingj` files) in `roms/`. A split `gigawingj.zip` + `gigawing.zip` also works for the patchers.
2. **Python 3** (any recent version). Optional: `pip install capstone` for 68000 disassembly listings.
3. **gcc** (native or inside WSL) to build the CPS2 encryptor from `patches/…zip`.
4. **Enable the build hook** (once per clone):
   ```
   git config core.hooksPath .githooks
   ```
5. **MAME** for testing. This project used MAME 0.289 built for Linux in WSL (`~/mame/bin/cps2`), with `qsound.zip` in its roms folder. Note that MAME's `-rompath` separator is `;` (quote it in sh).
6. Check everything works:
   ```
   python gigawing_patch.py sync      # should say "Patcher unchanged"
   python gigawing_patch.py patch -o some/dir/gigawingj.zip
   ```

### Files the set needs (original CRC32)

| File | Size | CRC32 | Notes |
|---|---|---|---|
| `gigawingj.key` | 20 | `8121a25e` | CPS2 decryption key |
| `ggwj.03a` | 512 KB | `fdd23b91` | 68000 program $000000-$07FFFF (patched) |
| `ggwj.04a` | 512 KB | `8c6e093c` | 68000 program $080000-$0FFFFF (patched) |
| `ggwj.05a` | 512 KB | `43811454` | 68000 program $100000-$17FFFF |
| `ggw.01` | 128 KB | `4c6351d5` | Z80 sound |
| `ggw.11m`, `ggw.12m` | 4 MB each | `e172acf5`, `4bee4e8f` | QSound samples |
| `ggw.13m` `ggw.15m` `ggw.17m` `ggw.19m` | 4 MB each | `105530a4` `9e774ab9` `466e0ba4` `840c8dea` | graphics |
| `dl-1425.bin` | 8 KB | `d6cf5ef5` | QSound firmware, lives in `qsound.zip` |

---

## 3. How the patcher pipeline works

```
patches.json ──► gigawing_patch.py sync ──► mister/*.mra (CRCs)
                                       ├──► index.html (PATCH data, MRA text, BUILD)
                                       └──► BUILDS.md (log line)
```

* **Patch entries** (`patches.json`):
  ```json
  {"file": "ggwj.03a", "offset": "0x3eac", "original": "<hex>", "patched": "<hex>", "note": "..."}
  ```
  Offsets and bytes are for the **raw file as stored in the zip** (word-swapped, encrypted where applicable, see §4). Both patchers refuse to patch if `original` doesn't match.
* **`python gigawing_patch.py patch [zip] [-o out.zip]`**: finds each needed file by size+CRC (any folder/name), verifies the data, applies the patches, checks results against `outputs` and writes a flat zip with all 11 files.
* **`python gigawing_patch.py sync [zip] [--build N]`**: applies the patches to your local romset, stores output CRC/SHA-1 in `patches.json`, rewrites `crc="…"` in the MRA for each patched part, embeds patch data and the full MRA text into `index.html` (between `// PATCH-DATA-BEGIN/END` and `// MRA-BEGIN/END`), and sets `BUILD`.
* **Build numbers:** the pre-commit hook runs `sync --build <last committed BUILD + 1>` whenever a commit touches `index.html`, `gigawing_patch.py`, `patches.json` or `mister/*.mra`, then stages the generated files. So every such commit is exactly one new build, logged in `BUILDS.md`.
* **Output name:** the patched romset is `gigawingop.zip` (MRA `zip="gigawingop.zip|qsound.zip"`, `<setname>gigawingop</setname>`). For MAME it must be renamed to `gigawingj.zip`.
* **Web patcher:** pure client side. Reads zips with `DecompressionStream`, applies the same patch list, verifies against embedded output CRC/SHA-1, writes a zip with `CompressionStream`, and offers the embedded MRA as a download. Works from `file://` and GitHub Pages.

---

## 4. Hardware and ROM facts (the important part)

### Program ROM layout
* `ggwj.03a` = $000000, `ggwj.04a` = $080000, `ggwj.05a` = $100000 (`ROM_LOAD16_WORD_SWAP`).
* **File bytes are word-swapped** relative to the CPU's big-endian view: CPU word `AABB` at address A is stored as `BB AA` at file offset `A - base`. Every patch must swap.

### CPS2 encryption
* Instruction fetches (68000 function code = program) from $000000 to the key's upper limit are decrypted on the fly; data reads are not.
* For `gigawingj.key` the decoded bounds are **$000000-$100000** (confirmed by MAME: the `program` and `opcodes` spaces differ only below $100000, and by `common.c` printing `BOUNDS: 00000000~00100000`).
* **Interrupt vectors ($0-$FF) are read as data**, so they're plain in the ROM and can be edited without encryption.
* ⚠ **MiSTer jtcps2 is not MAME above the limit.** Plain code placed at $17E000 (above the limit) ran in MAME but gave a **black screen on MiSTer** (Build 5). The safe rule: **all new code goes below $100000 and is encrypted.** Inside the range both decrypt identically.
* Encryptor: `patches/mmxi_v1.0.0_20250412.zip` → `tools/common.c`.
  ```
  gcc -O2 -DBUILD_DECRYPTOR common.c -o decrypt
  gcc -O2 -DBUILD_ENCRYPTOR common.c -o encrypt
  ./decrypt dec.04 ggwj.04a gigawingj.key 0x080000     # raw file in, decrypted (still word-swapped) out
  ./encrypt enc.04 dec.04  gigawingj.key 0x080000
  ```
  Check: `encrypt(decrypt(x)) == x` byte for byte, and the decryption equals MAME's `opcodes` space.
* Every 68000 word of new code is encrypted, including extension words (immediates, absolute addresses), because they're fetched as program.

### Free ROM space
* **$090088-$090817** (1936 bytes of zeros in `ggwj.04a`, file offset $10088), inside the encrypted range. A MAME read tap (`who_reads.lua`, `GW_LO=90088 GW_HI=90817`) over 8000 frames of gameplay saw **zero reads**. The rapid-fire code lives at **$090100-$0901A7**. Space left: $0901A8-$090817.
* Other zero runs exist ($08B040, $08C168, $08E926, …) but are **unverified**; tap-test before use.
* $17DBE2-$17F0B4 is zero but above the encryption limit (don't use for code, see above). The game reads $17DF82 and $17EF80 there.

### Interrupts
* Vblank = IRQ level 2, vector $68 → $9D8 (calls $A4C). Level 4 (raster) → $A06. Level 6 → $A1A. jtcps2 uses autovectors (VPA) with vblank on IPL level 2, raster on level 4.
* $A4C is the per-frame work: … `bsr $c9c` (input copy) … `addq.w #1,$FF2090` at $B56 …

### Inputs
* I/O port `$804000` word: low byte `$804001` = **P1**, high byte `$804000` = **P2**. Active low. Bits: 0 right, 1 left, 2 down, 3 up, **4 Shot (button 1)**, **5 Force Bomb (button 2)**, **6 button 3**, 7 button 4. `$804020` = coins/start/service.
* jtcps2 routes MiSTer button 3 to bit 6 for every game (no per-game masking). MAME's gigawing driver defines only 2 buttons, so button 3 can't be mapped in MAME (inject it with a read tap for tests).
* RAM copies made by $C9C (A5 = $FF8000): `$FF204B` raw P1, `$FF7061` inverted P1, `$FF7062` inverted P2, `$FF7060` coins.
* ⚠ **The game does NOT take Shot from those RAM copies.** During gameplay it reads the port directly. Readers found with `who_reads.lua` (PCs are after the instruction):

  | Site | Instruction | Use |
  |---|---|---|
  | $0CD4 / $0CEC | `move.b $804001/$804000,d0` | RAM input copy ($C9C) |
  | **$3EAC** | `move.b $804001.l,d0` | **P1 in game** → `$FF7069` |
  | **$3ED0** | `move.b $804000.l,d0` | **P2 in game** → `$FF706B` |
  | $89BA | `move.b $804001.l,d6` | P1 shot (other mode) |
  | $898A | `move.b $804000.l,d6` | P2 shot / join |
  | $7F8C / $7FA8 | `move.b $80400x.l,d1` | continue/insert check |

* `$31A2` tests `$FF7061 & $40` (button 3) only together with Start and a DIP switch; not used in normal play.

### Frame counter
* `$FF2090` (word) is incremented once per vblank at $B56. Used as the rapid-fire phase.

---

## 5. Patch: Button 3 = 10 Hz rapid Shot (current, Build 7)

**Behaviour:** while button 3 is held, Shot reads as pressed for 3 frames and released for 3 frames (6-frame cycle at ~59.64 Hz ≈ 10 Hz). Button 1 is untouched, so holding it still triggers Reflect Force. Works for P1 and P2.

**Design:** each of the four direct port reads (`$3EAC`, `$3ED0`, `$89BA`, `$898A`, each a 6-byte `move.b $80400x.l,dR`) is replaced by a 6-byte `jsr` to a reader routine at $090100+. Each routine:

```asm
reader:  move.b  $804001.l,dR        ; same read as the original (port per site)
         btst    #6,dR               ; button 3 held? (active low: 0 = held)
         bne.s   .done
         move.l  dT,-(sp)            ; dT = d0, or d1 when dR is d0
         moveq   #0,dT
         move.w  $FF2090.l,dT        ; frame counter
         divu    #6,dT
         swap    dT                  ; remainder 0..5
         cmpi.w  #3,dT
         bcc.s   .off                ; frames 3..5: leave Shot as is
         bclr    #4,dR               ; frames 0..2: Shot pressed (active low)
.off:    move.l  (sp)+,dT
.done:   rts
```

The instruction after each original read (`not.b d0` or `andi.w #$10,d6`) sets the flags itself, so returning through `rts` is safe. Readers: $090100 (P1,d6), $09012A (P2,d6), $090154 (P1,d0), $09017E (P2,d0).

**Patch entries:** 4 encrypted `jsr` words in `ggwj.03a` + the encrypted reader block in `ggwj.04a`. Regenerate them any time with:
```
python devs_notes/tools/build_rapidfire.py      # writes patches.json
python gigawing_patch.py sync                   # or just commit (hook syncs)
```
The script reproduces the committed Build 7 bytes exactly.

**Result CRCs (Build 7):** `ggwj.03a` = `84b06757`, `ggwj.04a` = `72e34c13`, others unchanged.

**MRA:** `<buttons names="Shot,Force Bomb,Rapid Shot,-,-,-,Start,Coin,Core credits" default="A,B,X,Start,Select,-" count="2"/>`. If X does nothing on MiSTer, redefine the core's buttons in the OSD (a saved mapping overrides MRA defaults); the game's input test should show button 3 when X is pressed.

### History / dead ends (don't repeat these)
| Build | Approach | Result |
|---|---|---|
| 5 | Vblank vector → plain code at $17E000, sets bit 4 of `$FF7061` after the IRQ handler | Black screen on MiSTer (code above the encryption limit). In MAME it ran but **didn't actually fire** (RAM copy not used for Shot); a screenshot test wrongly suggested it worked. |
| 6 | Same logic, code moved to $090100 and encrypted, vectors → hook | Loaded on MiSTer, still no rapid fire (same RAM-copy problem). Also tried hooking $C9C: no effect. |
| 7 | Hook the four direct port reads (above) | Works in MAME (measured) and confirmed on MiSTer. |

---

## 6. Testing (headless MAME, no windows, no key presses)

Always run with `-video none -sound none -nothrottle` and an `-autoboot_script`; the Lua script presses coin/start/buttons itself. (A windowed run stops on MAME's game-info and "might not run correctly" screens, which need a key press because the patched CRCs don't match MAME's database.)

```sh
# build a test set (outside the repo) named gigawingj.zip for MAME
python gigawing_patch.py patch -o /path/to/testroms/gigawingj.zip
# rapid-fire regression (4 modes, each a fresh deterministic run)
for m in 1 2 3 4; do GWMODE=$m ~/mame/bin/cps2 gigawingj -rompath "/path/to/testroms;$HOME/mame/roms" \
  -video none -sound none -nothrottle -autoboot_script devs_notes/tools/mame/rapidfire_test.lua; cat ~/gw/rate.txt; done
```
Expected output (shot sounds per 240 frames):
```
none         writes=13
b1 hold      writes=247
b1 3on3off   writes=754
b3 hook      writes=741-754    # 13 here = rapid fire broken
```
* **Measure, don't eyeball.** Counting writes to QSound shared RAM ($618000-$619FFF) is a reliable shot proxy; screenshots misled us in Build 5.
* `who_reads.lua`: find which instructions read an address (`GW_LO`/`GW_HI` hex env vars), or prove a ROM block is unused.
* `dump_program.lua`: dumps `program.bin` (data view) and `opcodes.bin` (decrypted) for disassembly, e.g. with capstone (`CS_ARCH_M68K`, `CS_MODE_BIG_ENDIAN|CS_MODE_M68K_000`). Linear-sweep the `opcodes` view below $100000.
* MAME can take snapshots headless (`manager.machine.video:snapshot()` with `-video none -snapshot_directory …`) if you need an image.
* Final check is always on MiSTer (jtcps2): it can differ from MAME (see §4).

---

## 7. Adding a new patch (recipe)

1. Find the code: dump with `dump_program.lua`, disassemble the `opcodes` view, use `who_reads.lua` read taps during scripted gameplay to find the real readers/writers (don't assume RAM copies are used).
2. Pick free space: tap-test a zero block below $100000 (or reuse the rest of $0901A8-$090817).
3. Write the 68000 code; hook with a same-size replacement (`jsr abs.l` = 6 bytes replaces a 6-byte instruction; re-run displaced instructions in your routine if needed).
4. Encrypt: decrypt the raw file, insert the code (word-swapped), encrypt, diff against the original (only your bytes may change). `build_rapidfire.py` is a template for this.
5. Add the entries to `patches.json` (keep existing ones), run `sync` or commit.
6. Test headless in MAME with a measurable signal, then on MiSTer.
7. Update **this file** (sections 4, 5/new section, 8), the README *Change Notes*, and the MRA button names if inputs change.

---

## 8. Build log summary

See `BUILDS.md` for the generated log. Human summary:

| Build | Change |
|---|---|
| 1 | Patcher framework (web + Python + MRA sync), no patches |
| 2 | MRA embedded in web patcher, output renamed `gigawingop.zip` |
| 3 | MRA setname `gigawingop`, hook syncs on MRA changes |
| 4 | MRA: Rapid Shot button on X |
| 5 | Rapid fire v1 (plain code at $17E000): MiSTer black screen |
| 6 | Rapid fire v2 (encrypted, vector hook): loads, doesn't fire |
| 7 | Rapid fire v3 (hook direct port reads): **working, confirmed on MiSTer** |

---

## Keeping these notes updated

Whenever you change the patch, tools, MRA or findings:
* add or adjust the relevant section here (addresses, free space used, CRCs);
* add a row to §8;
* keep `build_rapidfire.py` (or a new build script) able to regenerate every entry in `patches.json`;
* mention user-facing changes in the README *Change Notes*.
