-- Headless Reflect Force cooldown test for gigawingj (MAME autoboot script).
--
-- Plays a scripted game, holds Button 1 from frame 2300 to charge a Reflect Force, then
-- releases it and measures how many frames the RF gauge ($8A(a6) in the P1 object, $1000 = full)
-- takes to drain from its peak back to 0 (the red "X" cooldown bar).
-- The P1 object address (A6) is captured from the input handler's read of $FF7068.
-- Output: $HOME/gw/rfcool.txt
--
-- Expected: original drain=16.0 per frame (256 frames), Build 8+ drain=32.0 (128 frames).
-- Use a fresh -nvram_directory per run: the game's EEPROM otherwise carries over and runs diverge.
local cpu = manager.machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local a6
tap = sp:install_read_tap(0xff7068, 0xff7069, "p1obj", function()
  if not a6 and n and n > 2200 then a6 = cpu.state["A6"].value end
end)
local f = {}
for _, p in pairs(manager.machine.ioport.ports) do for nm, fl in pairs(p.fields) do f[nm] = fl end end
local function press(nm, on) if f[nm] then f[nm]:set_value(on and 1 or 0) end end
n = 0
local peak_frame, peak, zero_frame, prev
emu.register_frame_done(function()
  n = n + 1
  press("Coin 1", n >= 600 and n < 610)
  press("1 Player Start", n >= 700 and n < 1700 and (n % 60) < 5)
  press("P1 Button 1", n >= 2300 and n < 2400)
  if a6 and n >= 2300 then
    local g = sp:read_u16(a6 + 0x8a)
    if g == 0x1000 then peak_frame = n; peak = g end           -- last frame at full
    if peak_frame and n == peak_frame + 60 then rate = (0x1000 - g) / 60 end   -- drain per frame
    if peak_frame and not zero_frame and g == 0 and prev and prev > 0 then zero_frame = n end
    prev = g
  end
  if zero_frame or n == 3200 then
    os.execute("mkdir -p " .. os.getenv("HOME") .. "/gw")
    local o = io.open(os.getenv("HOME") .. "/gw/rfcool.txt", "w")
    o:write(string.format("drain=%s per frame -> full cooldown %s frames\n", rate and string.format("%.1f", rate) or "?",
      rate and rate > 0 and string.format("%d", math.floor(0x1000 / rate + 0.5)) or "?"))
    if zero_frame then o:write(string.format("observed: full at %d, empty at %d (%d frames; a hit/death can cut this short)\n", peak_frame, zero_frame, zero_frame - peak_frame)) end
    o:close()
    manager.machine:exit()
  end
end)
