-- Dump the 68000 program space twice: as data ("program", what data reads see) and as
-- decrypted opcodes ("opcodes", what instruction fetches see). Where they differ the ROM
-- is CPS2-encrypted. Output: $HOME/gw/program.bin and $HOME/gw/opcodes.bin (0-$17FFFF, big-endian).
local done = false
emu.register_frame_done(function()
  if done or manager.machine.screens[":screen"]:frame_number() < 5 then return end
  done = true
  local cpu = manager.machine.devices[":maincpu"]
  os.execute("mkdir -p " .. os.getenv("HOME") .. "/gw")
  for _, name in ipairs({"program", "opcodes"}) do
    local sp = cpu.spaces[name]
    local f = io.open(os.getenv("HOME") .. "/gw/" .. name .. ".bin", "wb")
    for a = 0, 0x17FFFE, 2 do local v = sp:read_u16(a); f:write(string.char(v >> 8, v & 255)) end
    f:close()
  end
  manager.machine:exit()
end)
