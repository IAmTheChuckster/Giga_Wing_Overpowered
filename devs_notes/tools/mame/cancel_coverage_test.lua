-- Headless bullet-cancel coverage test for gigawingj (MAME autoboot script).
--
-- Counts how many distinct kills (frame + object A6) the bullet-cancel routine handles: each starts with a scan of
-- the bullet list head (-$10E4(a5) = $FF6F1C) from inside the cancel code while D5 holds the kill
-- radius squared (64^2 = $1000). Also counts bullets freed by the routine (writes to the bullet
-- counter $FF6F2C from inside the code) and the medal counter, over the same scripted game as
-- magnet_test.lua. Set GW_CODE_END (hex) if the routine grows; default $90390.
-- Output: $HOME/gw/coverage.txt
local cpu = manager.machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local LO, HI = 0x90250, tonumber(os.getenv("GW_CODE_END") or "90390", 16)
local KILL_R2 = tonumber(os.getenv("GW_KILL_R2") or "1000", 16)
local n, kills, cancelled, scans = 0, 0, 0, 0
local seen = {}                       -- distinct (frame, object) pairs = kills
t1 = sp:install_read_tap(0xff6f1c, 0xff6f1f, "kill", function()
  local pc = cpu.state["PC"].value
  if pc >= LO and pc < HI and cpu.state["D5"].value == KILL_R2 then
    scans = scans + 1
    local k = n .. ":" .. cpu.state["A6"].value
    if not seen[k] then seen[k] = true kills = kills + 1 end
  end
end)
t2 = sp:install_write_tap(0xff6f2c, 0xff6f2d, "cnt", function()
  local pc = cpu.state["PC"].value
  if pc >= LO and pc < HI then cancelled = cancelled + 1 end
end)
local f = {}
for _, p in pairs(manager.machine.ioport.ports) do for nm, fl in pairs(p.fields) do f[nm] = fl end end
local function press(nm, on) if f[nm] then f[nm]:set_value(on and 1 or 0) end end
emu.register_frame_done(function()
  n = n + 1
  press("Coin 1", n >= 600 and n < 610)
  press("1 Player Start", n >= 700 and n < 1700 and (n % 60) < 5)
  press("P1 Button 1", n >= 2300 and ((n % 200) < 100 or (n // 3) % 2 == 0))
  press("P1 Left", n >= 2300 and (n % 240) < 60)
  press("P1 Right", n >= 2300 and (n % 240) >= 120 and (n % 240) < 180)
  if n == 3600 then
    os.execute("mkdir -p " .. os.getenv("HOME") .. "/gw")
    local o = io.open(os.getenv("HOME") .. "/gw/coverage.txt", "w")
    o:write(string.format("kills handled=%d (scans: one or more per kill) cancelled bullets=%d medals=%x\n", kills, cancelled, sp:read_u16(0xff72e6)))
    o:close()
    manager.machine:exit()
  end
end)
