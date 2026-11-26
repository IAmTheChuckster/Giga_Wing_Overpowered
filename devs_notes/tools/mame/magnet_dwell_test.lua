-- Headless medal-magnet "trailing" test for gigawingj (MAME autoboot script).
--
-- A medal caught by the magnet should reach the ship and be collected within a few frames.
-- Bug seen in Build 10-13: a falling medal below the ship balanced gravity against the pull and
-- trailed the ship instead of being collected. This script tracks, every frame, how long each medal
-- node stays within MAGNET range (96 px both axes) of P1 without disappearing, and reports the
-- longest stay and how many medals stayed longer than 30 frames.
-- Output: $HOME/gw/dwell.txt   Expected (Build 14+): max a few frames, 0 medals over 30.
local sp = manager.machine.devices[":maincpu"].spaces["program"]
local RANGE = 0x60
local f = {}
for _, p in pairs(manager.machine.ioport.ports) do for nm, fl in pairs(p.fields) do f[nm] = fl end end
local function press(nm, on) if f[nm] then f[nm]:set_value(on and 1 or 0) end end
local n, dwell, maxd, over = 0, {}, 0, 0
local function s16(v) if v >= 0x8000 then return v - 0x10000 end return v end
emu.register_frame_done(function()
  n = n + 1
  press("Coin 1", n >= 600 and n < 610)
  press("1 Player Start", n >= 700 and n < 1700 and (n % 60) < 5)
  press("P1 Button 1", n >= 2300 and ((n % 200) < 100 or (n // 3) % 2 == 0))
  press("P1 Left", n >= 2300 and (n % 240) < 60)
  press("P1 Right", n >= 2300 and (n % 240) >= 120 and (n % 240) < 180)
  local active = ((sp:read_u16(0xffadea) ~ 0x8000) & 0xe000) == 0   -- same test the game/magnet uses
  if n >= 2300 and not active then dwell = {} end                     -- magnet is off while dead/respawning
  if n >= 2300 and active then
    local px, py = sp:read_u16(0xffadea + 0xa), sp:read_u16(0xffadea + 0xe)
    local now = {}
    for _, head in ipairs({0xff6f40, 0xff6f44}) do
      local node, guard = sp:read_u32(head), 0
      while node ~= 0 and guard < 300 do
        local dx, dy = s16((px - sp:read_u16(node + 6)) & 0xffff), s16((py - sp:read_u16(node + 0xa)) & 0xffff)
        if math.abs(dx) < RANGE and math.abs(dy) < RANGE then
          now[node] = (dwell[node] or 0) + 1
          if now[node] > maxd then maxd = now[node] end
          if now[node] == 31 then over = over + 1 end
        end
        node, guard = sp:read_u32(node), guard + 1
      end
    end
    dwell = now
  end
  if n == 3600 then
    os.execute("mkdir -p " .. os.getenv("HOME") .. "/gw")
    local o = io.open(os.getenv("HOME") .. "/gw/dwell.txt", "w")
    o:write(string.format("longest stay in range=%d frames, medals staying >30 frames=%d\n", maxd, over)) o:close()
    manager.machine:exit()
  end
end)
