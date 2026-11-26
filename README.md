# Giga Wing Overpowered

A gameplay patch for `Giga Wing (Japan 990223)` (MAME set `gigawingj`)<br>
This repository holds only source, tools and notes. **No ROM data is included**; you patch your own legally owned dump.
## To Do:

   
## About
Why did I make this? Because it's fun and for my own personal research to see the capabilities of Claude.<br>
While Claude was used I put effort in making sure there are balanced gameplay.<br>
I did all the testing and planning.

## Change Notes
- **Button 3 = Rapid Shot**: works like Shot (button 1) but auto-fires at 10 Hz (3 frames on, 3 off) while held. Button 1 is unchanged, so holding it still gives Reflect Force. On MiSTer, Rapid Shot is mapped to X in the MRA. MAME's gigawing driver only defines 2 buttons, so button 3 can't be mapped in MAME.
- **Reflect Force cooldown is twice as fast**: after a Reflect Force, the red RF gauge drains in about 2.1 s instead of about 4.3 s, so Reflect Force is available again sooner.

Every patcher build is listed in [BUILDS.md](BUILDS.md). Full technical notes, so anyone can rebuild or extend this project from scratch, are in [devs_notes/DEV_NOTES.md](devs_notes/DEV_NOTES.md).

## Patching the game

### Web Patcher
Open the **[Web Patcher](https://iamthechuckster.github.io/Giga_Wing_Overpowered/)** (`index.html`) and drop in your `gigawing.zip`. It checks the file names and CRCs, builds the patched files automatically, and lets you download a complete `gigawingop.zip` romset plus the matching `Giga Wing Overpowered.mra` for MiSTer. Everything runs in your browser; nothing is uploaded.

### With Python
```
python gigawing_patch.py patch path/to/gigawing.zip -o gigawingop.zip
```
This does the same checks and writes the same `gigawingop.zip` as the web patcher.

**MiSTer:** copy `gigawingop.zip` and `qsound.zip` to `games/mame/` and `Giga Wing Overpowered.mra` to `_Arcade/`.<br>
**MAME:** rename the zip to `gigawingj.zip` (MAME finds sets by zip name) and keep `qsound.zip` alongside.

## Testing
This patch was tested with MAME 0.289 and the [CPS2 core for the MiSTer FPGA by Jotego](https://github.com/jotego/jtcores) (jtcps2)<br>
It may even work on a PCB but do so on your own risk.

## Credits

- [IAmTheChuckster](https://github.com/IAmTheChuckster)  project, testing
- [Claude](https://claude.ai) (Anthropic)  reverse engineering and patcher code
- Tested on the CPS2 core for the MiSTer FPGA by [Jotego](https://patreon.com/jotego)
- CPS2 encryption tools (`patches/mmxi_v1.0.0_20250412.zip`, derived from MAME's cps2crypt) by Alex "trap15" Marshall

## Disclaimer

This repository contains a fan-made patch for research and technical analysis. The repository does not intentionally distribute the original game ROM, executable, or game assets. Users must obtain their own copy of the original game. This project is unofficial and is not affiliated with, endorsed by, or authorized by Takumi or Capcom. All rights to the original game and its associated intellectual property remain with their respective rights holders. No license to third-party copyrighted material is granted by this repository.
