-- Deterministic unit test of the bullet-cancel routine ($90250) inside a running gigawingj (MAME).
--
-- At frame 2400 (in a scripted game) this script:
--   * sets the real enemy-bullet lists aside and builds a known layout from free nodes,
--   * makes a fake enemy at (256,128) in unused RAM with a hitbox 40 px left/right of its X,
--   * calls the cancel routine directly (A6 = fake enemy, interrupts masked) returning to a
--     "bra.s *" stub in RAM, and on the next frame checks the result.
-- Layout (offset from the enemy centre): A +100,0 (60 px from the box edge: inside 64, though 100 from the
--   centre)  B +113,0 (13 from A)  C +126,0 (13 from B)
--   D +148,0 (22 from C: outside 16)  E 0,+70 (70 px below the box: outside)
-- Expected: A,B,C cancelled (chain), D,E kept, bullet count -3, 3 small medals spawned.
-- Output: $HOME/gw/cunit.txt  ("PASS ..." or "FAIL ...")
--
-- Harness limitation: MAME 0.289's 68000 is cycle-accurate, so when Lua rewrites SP/PC the CPU may
-- still be mid-instruction and that instruction then writes over the new stack. The machine usually
-- ends in the divide-by-zero trap ($23D92) afterwards, EVEN WHEN THE PC IS POINTED STRAIGHT AT THE
-- STUB WITHOUT RUNNING THE CANCEL CODE (control run). So the "returned" flag is informational only;
-- PASS/FAIL is decided by the bullet/medal results, which the routine writes before returning.
local cpu = manager.machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local A5 = 0xff8000
local HEAD_SPAWN, HEAD_MOVE, FREE, COUNT = A5 - 0x10e4, A5 - 0x10e0, A5 - 0x10d8, A5 - 0x10d4
local MEDALS8 = A5 - 0x10bc                 -- small (type 8) medal list head
local ENEMY, STUB, STACK = 0xffd800, 0xffd900, 0xffdc00   -- unused RAM (see DEV_NOTES)
local f = {}
for _, p in pairs(manager.machine.ioport.ports) do for nm, fl in pairs(p.fields) do f[nm] = fl end end
local function press(nm, on) if f[nm] then f[nm]:set_value(on and 1 or 0) end end
local n, saved, nodes, count0, medals0 = 0, nil, {}, 0, 0
local function listlen(h) local c, x = 0, sp:read_u32(h) while x ~= 0 and c < 500 do c = c + 1 x = sp:read_u32(x) end return c end
local function inlist(h, node) local x = sp:read_u32(h) while x ~= 0 do if x == node then return true end x = sp:read_u32(x) end return false end
local function out(s)
  os.execute("mkdir -p " .. os.getenv("HOME") .. "/gw")
  local o = io.open(os.getenv("HOME") .. "/gw/cunit.txt", "w") o:write(s .. "\n") o:close()
  manager.machine:exit()
end
emu.register_frame_done(function()
  n = n + 1
  press("Coin 1", n >= 600 and n < 610)
  press("1 Player Start", n >= 700 and n < 1700 and (n % 60) < 5)
  if n == 2400 then
    sp:write_u32(HEAD_SPAWN, 0) sp:write_u32(HEAD_MOVE, 0)      -- set real bullets aside
    local ex, ey = 0x100, 0x80
    local layout = { {"A", 100, 0}, {"B", 113, 0}, {"C", 126, 0}, {"D", 148, 0}, {"E", 0, 70} }
    for _, b in ipairs(layout) do
      local node = sp:read_u32(FREE)
      sp:write_u32(FREE, sp:read_u32(node))                     -- pop a free node
      sp:write_u32(node, sp:read_u32(HEAD_MOVE)) sp:write_u32(HEAD_MOVE, node)
      sp:write_u32(node + 6, (ex + b[2]) << 16) sp:write_u32(node + 0xa, (ey + b[3]) << 16)
      sp:write_u16(COUNT, sp:read_u16(COUNT) + 1)
      nodes[b[1]] = node
    end
    for i = 0, 0x7f do sp:write_u8(ENEMY + i, 0) end
    sp:write_u16(ENEMY + 0xa, ex) sp:write_u16(ENEMY + 0xe, ey)
    sp:write_u16(ENEMY + 0x18, 40) sp:write_u16(ENEMY + 0x16, 40)   -- hitbox: 40 px left/right of X, 0 up/down
    sp:write_u16(STUB, 0x60fe)                                  -- bra.s *
    count0, medals0 = sp:read_u16(COUNT), listlen(MEDALS8)
    saved = {}
    for _, r in ipairs({"PC","SR","SP","A5","A6"}) do saved[r] = cpu.state[r].value end
    local s = STACK - 4
    sp:write_u32(s, STUB)                                       -- return address
    cpu.state["SP"].value = s
    cpu.state["A5"].value = A5
    cpu.state["A6"].value = ENEMY
    cpu.state["A3"].value = ENEMY + 0x7e                     -- descriptor: part count word = 0
    cpu.state["SR"].value = 0x2700                              -- supervisor, interrupts masked
    cpu.state["PC"].value = 0x90250
  elseif n == 2401 then
    local pc = cpu.state["PC"].value
    local kept, gone = {}, {}
    for _, k in ipairs({"A","B","C","D","E"}) do
      if inlist(HEAD_MOVE, nodes[k]) or inlist(HEAD_SPAWN, nodes[k]) then kept[#kept+1] = k else gone[#gone+1] = k end
    end
    local dc, dm = count0 - sp:read_u16(COUNT), listlen(MEDALS8) - medals0
    local back = pc >= STUB and pc <= STUB + 4          -- PC may read past the loop (prefetch)
    local ok = table.concat(gone) == "ABC" and table.concat(kept) == "DE" and dc == 3 and dm == 3
    out(string.format("%s returned=%s cancelled=%s kept=%s count-%d medals+%d", ok and "PASS" or "FAIL",
      string.format("%s(pc=%06x)", tostring(back), pc), table.concat(gone), table.concat(kept), dc, dm))
  end
end)
