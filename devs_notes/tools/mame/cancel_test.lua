-- Headless bullet-cancel test for gigawingj (MAME autoboot script).
--
-- Counts enemy bullets freed by the bullet-cancel routine: a write tap on the enemy-bullet
-- counter (-$10D4(a5) = $FF6F2C) where the writing PC is inside the cancel code ($90250-$9038F).
-- Reports total cancelled bullets, frames with a cancel, the biggest cancel in one frame, and the
-- medals collected (BCD counter $FF72E6), over the same scripted game as magnet_test.lua.
-- Optional: GW_SNAP=1 takes a snapshot on the frame with the biggest cancel so far (and the next).
-- Output: $HOME/gw/cancel.txt
local cpu = manager.machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local n, total, frames, best, this = 0, 0, 0, 0, 0
local snap = os.getenv("GW_SNAP") == "1"
tap = sp:install_write_tap(0xff6f2c, 0xff6f2d, "cnt", function()
  local pc = cpu.state["PC"].value
  if pc >= 0x90250 and pc < 0x90390 then this = this + 1 end
end)
local f = {}
for _, p in pairs(manager.machine.ioport.ports) do for nm, fl in pairs(p.fields) do f[nm] = fl end end
local function press(nm, on) if f[nm] then f[nm]:set_value(on and 1 or 0) end end
local snapnext = false
emu.register_frame_done(function()
  n = n + 1
  press("Coin 1", n >= 600 and n < 610)
  press("1 Player Start", n >= 700 and n < 1700 and (n % 60) < 5)
  press("P1 Button 1", n >= 2300 and ((n % 200) < 100 or (n // 3) % 2 == 0))
  press("P1 Left", n >= 2300 and (n % 240) < 60)
  press("P1 Right", n >= 2300 and (n % 240) >= 120 and (n % 240) < 180)
  if snapnext then manager.machine.video:snapshot() snapnext = false end
  if this > 0 then
    total, frames = total + this, frames + 1
    if this > best then best = this if snap and n > 2300 then manager.machine.video:snapshot() snapnext = true end end
    this = 0
  end
  if n == 3600 then
    os.execute("mkdir -p " .. os.getenv("HOME") .. "/gw")
    local o = io.open(os.getenv("HOME") .. "/gw/cancel.txt", "w")
    o:write(string.format("cancelled bullets=%d in %d frames, biggest cancel=%d, medals=%x\n", total, frames, best, sp:read_u16(0xff72e6)))
    o:close()
    manager.machine:exit()
  end
end)
