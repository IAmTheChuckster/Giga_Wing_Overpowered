-- Headless medal-magnet test for gigawingj (MAME autoboot script).
--
-- Plays a scripted game (fires, Reflect Force, sweeps left/right) and samples the medal counter
-- ($FF72E6, BCD; the "x NNN" number under the score) every 100 frames from 2400 to 3600.
-- Compare a build without the magnet against one with it, using identical inputs and a fresh
-- -nvram_directory per run so both games start the same.
-- Output: $HOME/gw/magnet.txt
local sp = manager.machine.devices[":maincpu"].spaces["program"]
local f = {}
for _, p in pairs(manager.machine.ioport.ports) do for nm, fl in pairs(p.fields) do f[nm] = fl end end
local function press(nm, on) if f[nm] then f[nm]:set_value(on and 1 or 0) end end
local n, row = 0, {}
emu.register_frame_done(function()
  n = n + 1
  press("Coin 1", n >= 600 and n < 610)
  press("1 Player Start", n >= 700 and n < 1700 and (n % 60) < 5)
  press("P1 Button 1", n >= 2300 and ((n % 200) < 100 or (n // 3) % 2 == 0))
  press("P1 Left", n >= 2300 and (n % 240) < 60)
  press("P1 Right", n >= 2300 and (n % 240) >= 120 and (n % 240) < 180)
  if n >= 2400 and n % 100 == 0 then row[#row + 1] = string.format("%d:%x", n, sp:read_u16(0xff72e6)) end
  if n == 3600 then
    os.execute("mkdir -p " .. os.getenv("HOME") .. "/gw")
    local o = io.open(os.getenv("HOME") .. "/gw/magnet.txt", "w")
    o:write("medals " .. table.concat(row, " ") .. "\n") o:close()
    manager.machine:exit()
  end
end)
