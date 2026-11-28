-- Headless score-extend test for gigawingj (MAME autoboot script).
--
-- Score = 16 BCD digits at $FF70CC (P1); lives = word $FF72DC. A trillion points can't be reached in
-- a short run, so the score is written directly:
--   A) frame 2400: score = 999,999,999,900, then normal scoring crosses 1 trillion  -> expect lives +1
--   B) frames 2700-3000: no crossing (score stays in the 1-trillion range)          -> expect lives +0
--   C) frame 3000: lives = 9, score = 1,999,999,999,900, crossing 2 trillion          -> expect lives stay 9
-- Lives can also drop if the player is hit, so each check looks at increases only.
-- Output: $HOME/gw/extend.txt ("PASS ..." or "FAIL ...")
local sp = manager.machine.devices[":maincpu"].spaces["program"]
local SCORE, LIVES = 0xff70cc, 0xff72dc
local f = {}
for _, p in pairs(manager.machine.ioport.ports) do for nm, fl in pairs(p.fields) do f[nm] = fl end end
local function press(nm, on) if f[nm] then f[nm]:set_value(on and 1 or 0) end end
local function setscore(bytes) for i, b in ipairs(bytes) do sp:write_u8(SCORE + i - 1, b) end end
local function top() return sp:read_u16(SCORE) end
local n, prev, gains, res = 0, nil, {A = 0, B = 0, C = 0}, {}
local function phase() if n < 2700 then return "A" elseif n < 3000 then return "B" else return "C" end end
emu.register_frame_done(function()
  n = n + 1
  press("Coin 1", n >= 600 and n < 610)
  press("1 Player Start", n >= 700 and n < 1700 and (n % 60) < 5)
  press("P1 Button 1", n >= 2000 and (n // 3) % 2 == 0)
  if n == 2400 then setscore({0x00, 0x00, 0x99, 0x99, 0x99, 0x99, 0x99, 0x00}) res.a0 = sp:read_u16(LIVES) prev = res.a0 end
  if n == 3000 then
    sp:write_u16(LIVES, 9)
    setscore({0x00, 0x01, 0x99, 0x99, 0x99, 0x99, 0x99, 0x00})
    prev = 9
  end
  if prev and n > 2400 then
    local l = sp:read_u16(LIVES)
    if l > prev then gains[phase()] = gains[phase()] + (l - prev) end
    prev = l
  end
  if n == 2699 then res.topA = top() end
  if n == 3300 then
    res.topC = top()
    local ok = gains.A == 1 and gains.B == 0 and gains.C == 0 and res.topA == 0x0001 and res.topC == 0x0002
    os.execute("mkdir -p " .. os.getenv("HOME") .. "/gw")
    local o = io.open(os.getenv("HOME") .. "/gw/extend.txt", "w")
    o:write(string.format("%s A(cross 1T)=+%d B(no cross)=+%d C(cross 2T at 9 lives)=+%d trillions A=%x C=%x lives now=%d\n",
      ok and "PASS" or "FAIL", gains.A, gains.B, gains.C, res.topA or 0, res.topC or 0, sp:read_u16(LIVES)))
    o:close()
    manager.machine:exit()
  end
end)
