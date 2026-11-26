-- Research helper: log every instruction (PC) that reads an address range during gameplay.
-- Set GW_LO / GW_HI (hex) to the range; defaults to the P1/P2 input port $804000-$804001.
-- Also handy for proving a ROM block is unused before putting code in it, e.g.
--   GW_LO=90088 GW_HI=90817  (expect no output).
-- Output: $HOME/gw/who.txt, lines "<PC after instruction> off=<addr> x<count>".
-- Note: the PC shown is the address after the reading instruction.
local cpu = manager.machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local lo = tonumber(os.getenv("GW_LO") or "804000", 16)
local hi = tonumber(os.getenv("GW_HI") or "804001", 16)
local seen, n = {}, 0
tap = sp:install_read_tap(lo, hi, "who", function(off)
  if n > 2300 then
    local k = string.format("%06x off=%06x", cpu.state["PC"].value, off)
    seen[k] = (seen[k] or 0) + 1
  end
end)
local f = {}
for _, p in pairs(manager.machine.ioport.ports) do for nm, fl in pairs(p.fields) do f[nm] = fl end end
local function press(nm, on) if f[nm] then f[nm]:set_value(on and 1 or 0) end end
emu.register_frame_done(function()
  n = n + 1
  press("Coin 1", n >= 600 and n < 610)
  press("1 Player Start", n >= 700 and n < 1700 and (n % 60) < 5)
  press("P1 Button 1", n > 2300 and (n // 3) % 2 == 0)
  press("P1 Button 2", n % 600 == 0)
  if n == (tonumber(os.getenv("GW_FRAMES") or "2500")) then
    os.execute("mkdir -p " .. os.getenv("HOME") .. "/gw")
    local o = io.open(os.getenv("HOME") .. "/gw/who.txt", "w")
    for k, v in pairs(seen) do o:write(k .. " x" .. v .. "\n") end
    o:close()
    manager.machine:exit()
  end
end)
