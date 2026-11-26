# Giga Wing Overpowered

## Changes
- **Button 3 = Rapid Shot**: same as Shot (button 1) but auto-fires at 10 Hz (3 frames on, 3 off) while held. MiSTer: mapped in the MRA. MAME's gigawing driver only defines 2 buttons, so button 3 can't be mapped there.

Patch for **Giga Wing (Japan 990223)**, MAME set `gigawingj`.

## Patch your romset
- **Web:** open `index.html`, drop in your `gigawing.zip`, download `gigawingop.zip`.
- **Command line:** `python gigawing_patch.py patch path/to/gigawing.zip -o gigawingop.zip`

For MiSTer, copy `gigawingop.zip` and `Giga Wing Overpowered.mra` (also downloadable from the web patcher). For MAME, rename it to `gigawingj.zip` (MAME finds sets by zip name) and keep `qsound.zip` alongside.

## Maintainers
1. Edit `patches.json` (`file`, `offset`, `original`, `patched` hex bytes on the raw ROM files).
2. Commit. The pre-commit hook (`git config core.hooksPath .githooks`) runs `python gigawing_patch.py sync`,
   which writes the new CRCs into the MRA, embeds the patch in `index.html`, bumps `BUILD` and logs it in `BUILDS.md`.
   Needs the romset at `roms/gigawing.zip` (gitignored).
