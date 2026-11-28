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
| `devs_notes/tools/build_patches.py` | Rebuilds **all** patch entries in `patches.json` from source (assemble, encrypt, diff). |
| `devs_notes/tools/mame/*.lua` | Headless MAME scripts: program dump, read-tap research, rapid-fire and RF-cooldown regression tests. |
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
* **Web patcher:** pure client side. Reads zips with `DecompressionStream`, applies the same patch list, verifies every file against embedded output CRC/SHA-1 (the result table lists only files whose CRC differs from the original; unchanged files are verified and counted in the status line), writes a zip with `CompressionStream`, and offers the embedded MRA as a download. Works from `file://` and GitHub Pages.

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
* **$090088-$090817** (1936 bytes of zeros in `ggwj.04a`, file offset $10088), inside the encrypted range. A MAME read tap (`who_reads.lua`, `GW_LO=90088 GW_HI=90817`) over 8000 frames of gameplay saw **zero reads**. The rapid-fire code lives at **$090100-$0901A7**. Space used by the magnet: $0901C0-$090243; bullet cancel: $090250-$09038D; score extends: $0903A0-$0903DF. Space left: $0903E0-$090817.
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

### Player object and Reflect Force
* The P1 player object pointer is in A6 inside the input handler ($428xx-$42Axx); during the test run it was `$FFADEA`. Grab it in Lua from `cpu.state["A6"]` in a read tap on `$FF7068`.
* Useful fields: `$8D(a6)` autofire counter while Shot is held (every 10 frames sets bit 2 of `$47(a6)`), `$86`/`$98(a6)` long shift-register timers, `$5C(a6)` pointer to state flags.
* **RF gauge = word `$8A(a6)`**, range 0..`$1000`. Routine at `$4A5A2`:
  * holding Shot charges it: `addi.w #$C0,$8a(a6)` at `$4A5F4` per autofire tick, capped at `$1000` (Reflect Force);
  * afterwards it **drains** (red bar with the X): `subi.w #$10,$8a(a6)` at `$4A62E` every frame until 0, then RF shows OK again. Draining pauses while bit 3 of `$1(a6)` is set (player hit/respawn).

### Medals
* **Medal counter** (the `x NNN` under the score): BCD word at `$FF72E6`.
* Medals are 32-byte nodes in **two linked lists**, heads at `-$10C0(a5)` = `$FF6F40` and `-$10BC(a5)` = `$FF6F44`. Node: `+0` next pointer, `+6` X (16.16), `+$A` Y (16.16), `+$E` X velocity, `+$12` Y velocity. Spawned by `$2BFCC` from a free list at `-$10D8(a5)`.
* **Pickup:** `$23652` (P1, object `$2DEA(a5)` = `$FFADEA`) / `$237D6` (P2, `$2EAA(a5)` = `$FFAEAA`) build a box from the player's X/Y and size fields `$36`-`$3C`, then `$2BF2E` walks both lists and calls `$2369C` for each medal inside the box (adds its value to score and the counter, shows the `+NN` popup, frees the node).
* Player and medal coordinates share one space: player X word `+$A`, Y word `+$E`; medal X word `+6`, Y word `+$A`.

### Enemies, enemy bullets, medal spawning
* **Enemy destroyed:** common routine `$67E52` (23 callers). A6 = enemy object (position words `$A`/`$E`), A3 = enemy descriptor. It returns early if `$24(a6)` is set, otherwise `btst #4,$1(a6)` at `$67E5A`, awards kill score (`$57458`), flags the enemy's parts dead, drops its item (`$2B470`) and jumps to the death handler `$E(a3)`.
* **Enemy bullets:** linked lists `-$10E4(a5)` = `$FF6F1C` (just fired, spawn animation) and `-$10E0(a5)` = `$FF6F20` (moving); count `-$10D4(a5)` = `$FF6F2C`. All objects (bullets, medals) share the free node list `-$10D8(a5)`. Node: `+0` next, `+6` X, `+$A` Y (16.16), `+$E`/`+$12` velocity. Spawner `$24E20` (enemy fire). The game frees a bullet with `subq.w #1,-$10D4(a5)` and pushes the node back on the free list.
* **Medal spawner `$2B60E`:** `d0` = Y velocity, `d1` = X velocity, `d2`/`d3` = X/Y (clamped to the screen), `d4` = type. **Type 8 = small medal** (plain list `-$10BC`, capped at 100 by `-$107A`). The game itself turns reflected bullets that hit enemies into type-8 medals at `$23D36` with random velocity from `$378A` (`d0 & $1FFFF`, `(d1 & $3FFF) - $2000`).
* **Score:** BCD at `$FF70CC` (P1); per-frame pending add from `$FF72AA` (P1) / `$FF72B2` (P2) at `$645EC`.

### Lives and score
* **Lives:** words `-$D24(a5)` = `$FF72DC` (P1) and `-$D22(a5)` = `$FF72DE` (P2); the HUD "×N" shows this value. The 1UP item (`$20338`, only spawned while lives < 2) adds 1 at `$203B8`/`$203C0` and sets bit 2 of `-$D74(a5)` = `$FF728C`.
* **Score:** 16 BCD digits (8 bytes) at `$FF70CC` (P1) / `$FF70D4` (P2). Once per frame `$645F2`/`$64608` add the pending points (`$FF72AA` / `$FF72B2`) with `bsr $64704`, which also clears the pending amount and updates the high score (`$FF70DC`). The top word of the score is its trillions (4 BCD digits).

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
python devs_notes/tools/build_patches.py      # writes patches.json
python gigawing_patch.py sync                   # or just commit (hook syncs)
```
The script reproduces the committed bytes exactly.

**Result CRCs (Build 7, rapid fire only):** `ggwj.03a` = `84b06757`, `ggwj.04a` = `72e34c13`. Current CRCs for all patches are in `patches.json` → `outputs` and in `BUILDS.md`.

**MRA:** `<buttons names="Shot,Force Bomb,Rapid Shot,-,-,-,Start,Coin,Core credits" default="A,B,X,Start,Select,-" count="2"/>`. If X does nothing on MiSTer, redefine the core's buttons in the OSD (a saved mapping overrides MRA defaults); the game's input test should show button 3 when X is pressed.

### History / dead ends (don't repeat these)
| Build | Approach | Result |
|---|---|---|
| 5 | Vblank vector → plain code at $17E000, sets bit 4 of `$FF7061` after the IRQ handler | Black screen on MiSTer (code above the encryption limit). In MAME it ran but **didn't actually fire** (RAM copy not used for Shot); a screenshot test wrongly suggested it worked. |
| 6 | Same logic, code moved to $090100 and encrypted, vectors → hook | Loaded on MiSTer, still no rapid fire (same RAM-copy problem). Also tried hooking $C9C: no effect. |
| 7 | Hook the four direct port reads (above) | Works in MAME (measured) and confirmed on MiSTer. |

---

## 5b. Patch: Reflect Force cooldown 2x faster (Build 8)

**Behaviour:** after a Reflect Force the gauge drains twice as fast, about 2.1 s instead of 4.3 s (128 instead of 256 frames).

**Change:** one encrypted immediate word in `ggwj.03a`: `subi.w #$10,$8a(a6)` → `subi.w #$20,$8a(a6)` at `$4A62E` (`046E 0010 008A` → `046E 0020 008A`, only the middle word changes after encryption). Built by `build_patches.py` (`RF_DRAIN = 0x20`; change that constant to tune it, e.g. `0x40` = 4x).

**Measured** (`rf_cooldown_test.lua`, fresh nvram): original drain 15.8/frame (about 260 frames), patched 31.5/frame (about 130 frames).

---

## 5e. Patch: bullet cancels (Build 15)

**Behaviour:** when an enemy is destroyed, every enemy bullet **over its hitbox or within 64 px of the hitbox edge** is cancelled, for every part of a multi-part enemy (radius: 24 px in Build 15, 32 px in 16, 64 px from 17; measured from the centre point until Build 18); then every bullet within **16 px** of any cancelled bullet is cancelled too, repeatedly, so clusters chain. Each cancelled bullet becomes a **small medal** (type 8) at its position, with the same random pop as the game's own reflect conversion.

**Hooks (Build 18; Build 15-17 had only the first):** every kill reaches at least one of these, A6 = destroyed object:
| Site | Displaced code | Entry | Notes |
|---|---|---|---|
| `$67E5A` | `btst #4,$1(a6)` | `btst1` | common enemy-destroyed routine `$67E52`; walks parts, so `(a3)` = part count − 1 |
| `$24B5C` | `btst #4,$1(a6)` | `btst0` | second destroy routine; single object |
| `$57458` | `btst #4,(a6)` + `beq.b $57464` | `score` | kill-score routine, 40+ enemy/boss callers; the entry re-runs the `btst` and adds 6 to its return address when the `beq` would branch. `d0` (score) is preserved |

A kill that passes two hooks runs the cancel twice; the second pass finds nothing. Each entry preserves `d0`, runs the core, then the displaced code; `rts` keeps the flags.

**Hitbox:** same as the shot collision at `$23C7E`: X from `X−$18` to `X+$16`, Y from `Y−$1C` to `Y+$1A` (object words). Distance = from the bullet to the nearest point of the box (0 inside). Multi-part enemies are consecutive `$80`-byte objects (capped at `CANCEL_MAX_PARTS` = 8).

**Bullet coverage:** the player-hit check (`$29DE8`) only tests `-$10E0`; fresh bullets in `-$10E4` move there. Other lists sharing the node pool are effects, not bullets: `-$10DC` = vanishing bullets (the game's own clear-all), `-$10B8` / `-$10CC` = hit/spark effects, `-$10A8` / `-$10D0` / `-$10B0` = other sprites.

**Routine** at `$90250`-`$9031B` (encrypted):
1. Save all registers. For each part: box from its hitbox fields, R² = 64² (`CANCEL_KILL_R`).
2. `gather`: walk both bullet lists (`-$10E4`, `-$10E0`) with a previous-link pointer; any bullet whose distance² to the box is < R² is unlinked and appended to a private "cancelled" list.
3. Chain: walk the cancelled list from its head; for each bullet, `gather` again with a zero-size box at that bullet and R² = 16². Newly found bullets are appended to the end, so they're processed in turn (breadth-first).
4. For each cancelled bullet: read X/Y, free the node exactly like the game (push on `-$10D8`, `subq.w #1,-$10D4`), then call `$2B60E` with type 8 and random velocity. Freeing first means the spawner can reuse the node.
5. Restore registers, displaced `btst`, `rts`.

Settings in `build_patches.py`: `CANCEL_KILL_R`, `CANCEL_CHAIN_R`, `SMALL_MEDAL`. Cost is O(cancelled × bullets) only on frames where an enemy dies.

**Tests:**
* `cancel_unit_test.lua` (deterministic): builds a fake enemy with a hitbox 40 px left/right of its X, plus bullets A (+100 px: 60 px from the box edge), B (+113), C (+126), D (+148, 22 px from C), E (0,+70) and calls the routine. Result: **PASS: A,B,C cancelled (chain), D,E kept, count −3, medals +3.** (The harness can't return cleanly from the forced call on MAME's cycle-accurate 68000; a control run that jumps straight to the stub without the cancel code crashes the same way, so the return isn't checked. See the script header.)
* `cancel_coverage_test.lua`: distinct kills handled + bullets cancelled. Scripted stage 1: Build 17 = 54 kills / 3 bullets; Build 18 = 56 kills / 6 bullets (stage 1 rarely has bullets near a kill; later stages and bosses use the extra hooks).
* `cancel_test.lua` (real play): counts bullets freed by the routine. In the scripted stage-1 game it cancelled 3 bullets in 2 kills; the game kept running normally (no trap, frame counter advancing). Medals collected: 2101 → 2224.

---

## 5d. Patch: medal magnet (Build 10)

**Behaviour:** every frame, each medal within `MAGNET_RANGE` = `$60` (96 px; was `$30` = 48 px in Build 10) of the ship on both axes moves **25% of the remaining distance** toward it (`MAGNET_SHIFT = 14`; Build 13 tried 12.5%) and **its own velocity is cleared**, so it visibly gets pulled in. The game's normal pickup then collects it. Works for P1 and P2, and only while that player is active.

**Hooks:** the first 6 bytes of each pickup routine (`lea $2DEA(a5),a2` + `move.w (a2),d0` at `$23652`; the P2 copy with `$2EAA` at `$237D6`) become `jsr` to the magnet code at **`$901C0`-`$9023B`** (encrypted, same verified-unused block as rapid fire). The routine:

```asm
p1:     lea     $2dea(a5),a2 / bra.s common      ; p2: lea $2eaa(a5),a2
common: movem.l d0-d5/a0,-(sp)
        (player active test, same as the game) / bne done
        move.w  $a(a2),d1 ; move.w $e(a2),d2     ; player X, Y
        lea -$10c0(a5),a0 / bsr pull ; lea -$10bc(a5),a0 / bsr pull
done:   movem.l (sp)+,d0-d5/a0 ; move.w (a2),d0 ; rts   ; displaced instruction
pull:   follow next pointers; for each medal: dx = px - X, dy = py - Y;
        if |dx| < R and |dy| < R: X += dx << SHIFT ; Y += dy << SHIFT   (SHIFT 14 = 25% in 16.16)
                                   clr.l $E(a0) ; clr.l $12(a0)        ; stop the medal's own drift/fall
```

Tune `MAGNET_RANGE` in `build_patches.py` for a bigger or smaller pull radius. Pull speed is `MAGNET_SHIFT` (asl.l #8 + asl.l #SHIFT-8): 16 = 100%, 15 = 50%, 14 = 25%, 13 = 12.5%. Current: 14.

**Why the velocity clear:** medals have velocity at node `+$E` (X) / `+$12` (Y), added every frame, with gravity lowering Y velocity by `$A00`/frame. A falling medal below the ship settles where the pull equals its fall speed and **trails the ship without being collected** (seen on MiSTer in Build 13). Clearing the velocity while in range makes the pull the only motion.

**Measured** (`magnet_test.lua`, same scripted game, fresh nvram): medals collected by frame 3600: **216 without magnet → 781 with 48 px (Build 10) → 2101 with 96 px (Build 11) → 1791 with 96 px and the slower 12.5% pull (Build 13)**. Snapshots show `+NN` popups at the ship.

---

## 5g. Patch: score extends (Build 19)

**Behaviour:** an extra life every **1,000,000,000,000** points, for P1 and P2, with the same 1UP flag the 1UP item sets; no extend is given beyond 9 lives in stock (`EXTEND_MAX_LIVES`).

**Hooks:** at `$645F8` (P1) and `$6460E` (P2), `lea score,a1` + `bsr.w $64704` (10 bytes) → `jsr` + `nop nop` (encrypted). Routine at `$903A0`:
```asm
p1: pea $ff72dc.l / lea $ff70cc.l,a1 / bra.s common     ; p2: pea $ff72de.l / lea $ff70d4.l,a1
common: move.w (a1),-(sp)          ; score's top word (trillions) before the add
        move.l a1,-(sp)
        jsr $64704.l               ; the game's own score add (a0 = pending, set by the caller)
        movea.l (sp)+,a1 / move.w (sp)+,d0 / movea.l (sp)+,a3   ; a3 = lives word
        cmp.w (a1),d0 / beq done   ; trillions unchanged
        cmpi.w #9,(a3) / bcc done  ; stock full
        addq.w #1,(a3)
        bset #2,$ff728c.l          ; 1UP flag, as the 1UP item
done:   rts
```
Only registers `$64704` already clobbers are used. Crossing several trillions in one frame gives one life.

**Test** (`extend_test.lua`, score written directly): crossing 1 trillion → +1 life; 300 frames without crossing → +0; crossing 2 trillion with 9 lives → stays 9. **PASS.** Regression (rapid fire, magnet trailing, cancel unit test, stability) also passes.

---

## 5c. Patch: boot screen text (Build 9)

The region/version screen comes from a text table at `$60000+` (data, so **plain, never encrypted**, only word-swapped in the file). Each entry: 2 bytes position (`$0C $yy`), a **25-character field**, `$00`. There's one block per region; gigawingj uses the first (Japan) block:

| Addr | Original | Now |
|---|---|---|
| `$60090` | `       GIGAWING          ` | `  GIGAWING OVERPOWERED   ` |
| `$600E4` | `      9 9 0 2 2 3        ` | `      2 6 1 1 2 7        ` |

Other regions' copies (USA/EURO/HISPANIC/BRAZIL/ASIA at `$6011E`+, `$90`-byte blocks) are untouched. Built by `text()` in `build_patches.py`; strings must stay exactly 25 characters. Checked with a headless MAME snapshot (`video:snapshot()` around frame 150).

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
* `cancel_unit_test.lua` / `cancel_test.lua` / `cancel_coverage_test.lua`: bullet cancel, see §5e.
* `magnet_dwell_test.lua`: longest time any medal stays in magnet range without being collected (player active only). Build 13: 55 frames, 2 medals over 30 (trailing). Build 14: 10 frames, 0.
* `magnet_test.lua`: samples the medal counter every 100 frames; compare a build with and without the magnet.
* `rf_cooldown_test.lua`: holds Shot for a Reflect Force and reports the gauge drain rate. Expect 16/frame original, 32/frame from Build 8.
* **Use a fresh `-nvram_directory` (and `-cfg_directory`) for every run.** The game's EEPROM is saved between runs otherwise and the scripted games diverge (a death at a different moment, for example).
* `who_reads.lua`: find which instructions read an address (`GW_LO`/`GW_HI` hex env vars), or prove a ROM block is unused.
* `dump_program.lua`: dumps `program.bin` (data view) and `opcodes.bin` (decrypted) for disassembly, e.g. with capstone (`CS_ARCH_M68K`, `CS_MODE_BIG_ENDIAN|CS_MODE_M68K_000`). Linear-sweep the `opcodes` view below $100000.
* MAME can take snapshots headless (`manager.machine.video:snapshot()` with `-video none -snapshot_directory …`) if you need an image.
* Final check is always on MiSTer (jtcps2): it can differ from MAME (see §4).

---

## 7. Adding a new patch (recipe)

1. Find the code: dump with `dump_program.lua`, disassemble the `opcodes` view, use `who_reads.lua` read taps during scripted gameplay to find the real readers/writers (don't assume RAM copies are used).
2. Pick free space: tap-test a zero block below $100000 (or reuse the rest of $0901A8-$090817).
3. Write the 68000 code; hook with a same-size replacement (`jsr abs.l` = 6 bytes replaces a 6-byte instruction; re-run displaced instructions in your routine if needed).
4. Encrypt: decrypt the raw file, insert the code (word-swapped), encrypt, diff against the original (only your bytes may change). `build_patches.py` is a template for this.
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
| 8 | Reflect Force cooldown 2x faster (gauge drain $10 → $20) |
| 9 | Boot screen: GIGAWING OVERPOWERED / 261127 |
| 10 | Medal magnet (pull medals within 48 px into the ship) |
| 11 | Medal magnet radius doubled to 96 px |
| 12 | Web patcher lists only the patched files in the download table |
| 13 | Medal magnet pull slowed from 25% to 12.5% per frame (medals could trail the ship) |
| 14 | Magnet back to 25%, clears medal velocity while pulling (fixes trailing) |
| 15 | Bullet cancels: enemy kill turns bullets within 24 px (chain 16 px) into small medals |
| 16 | Bullet cancel kill radius widened 24 → 32 px |
| 17 | Bullet cancel kill radius doubled 32 → 64 px |
| 18 | Bullet cancel on all kill paths ($67E5A, $24B5C, $57458), measured from the enemy hitbox (all parts) |
| 19 | Score extends: a life every 1,000,000,000,000 points (max 9 lives) |

---

## Keeping these notes updated

Whenever you change the patch, tools, MRA or findings:
* add or adjust the relevant section here (addresses, free space used, CRCs);
* add a row to §8;
* keep `build_patches.py` (or a new build script) able to regenerate every entry in `patches.json`;
* mention user-facing changes in the README *Change Notes*.
