# Giga Wing Overpowered

Patch for **Giga Wing (Japan 990223)**, MAME set `gigawingj`.

## Patch your romset
- **Web:** open `index.html`, drop in your `gigawing.zip`, download `gigawingj.zip`.
- **Command line:** `python gigawing_patch.py patch path/to/gigawing.zip -o gigawingj.zip`

Put `gigawingj.zip` (plus `qsound.zip`) in your MAME roms folder. For MiSTer use `mister/Giga Wing Overpowered.mra`.

## Maintainers
1. Edit `patches.json` (`file`, `offset`, `original`, `patched` hex bytes on the raw ROM files).
2. Commit. The pre-commit hook (`git config core.hooksPath .githooks`) runs `python gigawing_patch.py sync`,
   which writes the new CRCs into the MRA, embeds the patch in `index.html`, bumps `BUILD` and logs it in `BUILDS.md`.
   Needs the romset at `roms/gigawing.zip` (gitignored).
