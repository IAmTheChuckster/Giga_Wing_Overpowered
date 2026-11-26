-- Headless rapid-fire regression test for gigawingj (MAME autoboot script).
--
-- Plays a scripted game (coin, start, skip intro) and, from frame 2300 for 240 frames,
-- applies one input pattern chosen by env var GWMODE. It counts writes to the QSound
-- shared RAM ($618000-$619FFF) as a proxy for shot sounds and writes the count to
-- $HOME/gw/rate.txt.
--
-- MAME's gigawing driver has no Button 3 input, so Button 3 is injected with a read tap
-- on the input port (bit 6 of $804001 cleared = P1 Button 3 pressed, active low).
--
-- Run each mode as its own process (the emulation is deterministic, so modes compare fairly):
--   for m in 1 2 3 4; do GWMODE=$m mame gigawingj -rompath "<patched>;<bios>" \
--     -video none -sound none -nothrottle -autoboot_script rapidfire_test.lua; cat ~/gw/rate.txt; done
--
-- Expected (Build 7): none=13, b1 hold=247, b1 3on3off=754, b3 hook=741-754 (same as real 10Hz tapping; exact number depends on the frame-counter phase).
-- b3 hook == none (13) means rapid fire is broken.
local MODES = { {"none",0}, {"b1 hold",-1}, {"b1 3on3off",3}, {"b3 hook",-3} }
local t = MODES[tonumber(os.getenv("GWMODE") or "4")]
local sp = manager.machine.devices[":maincpu"].spaces["program"]
local held = false
btn3 = sp:install_read_tap(0x804000, 0x804001, "btn3", function(off, data, mask)
  if held then return data & ~0x0040 end
end)
local writes = 0
snd = sp:install_write_tap(0x618000, 0x619fff, "snd", function() writes = writes + 1 end)
local f = {}
for _, p in pairs(manager.machine.ioport.ports) do for nm, fl in pairs(p.fields) do f[nm] = fl end end
local function press(nm, on) if f[nm] then f[nm]:set_value(on and 1 or 0) end end
local n, START, LEN = 0, 2300, 240
emu.register_frame_done(function()
  n = n + 1
  press("Coin 1", n >= 600 and n < 610)
  press("1 Player Start", n >= 700 and n < 1700 and (n % 60) < 5)
  local pos, b1 = n - START, false
  held = false
  if pos >= 0 and pos < LEN then
    if t[2] == -1 then b1 = true elseif t[2] == -3 then held = true elseif t[2] > 0 then b1 = ((pos // t[2]) % 2 == 0) end
    if pos == 0 then writes = 0 end
  end
  press("P1 Button 1", b1)
  if pos == LEN then
    os.execute("mkdir -p " .. os.getenv("HOME") .. "/gw")
    local o = io.open(os.getenv("HOME") .. "/gw/rate.txt", "w")
    o:write(string.format("%-12s writes=%d\n", t[1], writes)) o:close()
    manager.machine:exit()
  end
end)
