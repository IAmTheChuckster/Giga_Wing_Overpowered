-- Research helper: which on-screen bullets are in the enemy-bullet lists the cancel scans?
--
-- Coins up, picks a character (GW_CHAR = number of Right taps on the select screen, default 0),
-- plays with fire held, and at GW_FRAMES (comma list, default 2600,2800,3000,3200) saves a snapshot
-- plus the positions of every node in the enemy-bullet lists (-$10E4/-$10E0 as B, -$10D0/-$10A8 as C), active
-- objects in the object pool $FF75CA (as O) and the P1 ship.
-- Screen mapping: screen x = X, screen y = 224 - Y. Draw markers with the overlay step in DEV_NOTES.
-- Output: snapshots in -snapshot_directory, node list in $HOME/gw/bmap.txt
local sp = manager.machine.devices[":maincpu"].spaces["program"]
local f = {}
for _, p in pairs(manager.machine.ioport.ports) do for nm, fl in pairs(p.fields) do f[nm] = fl end end
local function press(nm, on) if f[nm] then f[nm]:set_value(on and 1 or 0) end end
local taps = tonumber(os.getenv("GW_CHAR") or "0")
local FR, last = {}, 0
for v in string.gmatch(os.getenv("GW_FRAMES") or "2600,2800,3000,3200", "%d+") do FR[tonumber(v)] = true if tonumber(v) > last then last = tonumber(v) end end
local n, out = 0, {}
emu.register_frame_done(function()
  n = n + 1
  press("Coin 1", n >= 600 and n < 610)
  press("1 Player Start", (n >= 700 and n < 705) or (n >= 1000 and n < 1700 and (n % 60) < 5))
  local t = n - 820
  press("P1 Right", t >= 0 and t < taps * 20 and (t % 20) < 5)          -- tap Right GW_CHAR times
  press("P1 Button 1", (n >= 950 and n < 955) or (n >= 2000 and (n // 3) % 2 == 0))
  if FR[n] then
    manager.machine.video:snapshot()
    local l = {string.format("F %d P %d %d", n, sp:read_u16(0xffadea + 0xa), sp:read_u16(0xffadea + 0xe))}
    for _, h in ipairs({0xff6f1c, 0xff6f20, 0xff6f30, 0xff6f58}) do      -- B: -$10E4,-$10E0 ; C: -$10D0,-$10A8
      local x, g = sp:read_u32(h), 0
      local tag = (h == 0xff6f1c or h == 0xff6f20) and "B" or "C"
      while x ~= 0 and g < 300 do
        l[#l + 1] = string.format("%s %d %d %x", tag, sp:read_u16(x + 6), sp:read_u16(x + 0xa), sp:read_u16(x + 0x18))
        x, g = sp:read_u32(x), g + 1
      end
    end
    for i = 0, 47 do                                                     -- object pool $FF75CA, $80 each (O)
      local o = 0xff75ca + i * 0x80
      local w = sp:read_u16(o)
      if w & 0x8000 ~= 0 then
        l[#l + 1] = string.format("O %d %d %x", sp:read_u16(o + 0xa), sp:read_u16(o + 0xe), w)
      end
    end
    out[#out + 1] = table.concat(l, "\n")
  end
  if n == last + 1 then
    os.execute("mkdir -p " .. os.getenv("HOME") .. "/gw")
    local o = io.open(os.getenv("HOME") .. "/gw/bmap.txt", "w") o:write(table.concat(out, "\n") .. "\n") o:close()
    manager.machine:exit()
  end
end)
