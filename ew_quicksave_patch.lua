-- EvilWithin_quicksave.lua
-- Run in Cheat Engine with the game running: File > Execute Script.
-- Run again to toggle back.
--
-- This makes saveGameSteam use the game's normal Save Game method:
--   saveGameSteam -> idGameLocal::SaveGame("QUICKSAVE")
--                 -> FUN_14082B0D0 -> FUN_14098A010(...)
--
-- That writes the same payload as the in-game save menu (spawn spot
-- "player_start", current player state). The old checkpoint autosave patch
-- could restore a stale checkpoint spawn spot and put you back or in the void.
--
-- It also bypasses the "Cannot save at this location" gate so you can save at
-- an arbitrary point. Do not save during cutscenes or map transitions.
--
-- RVAs, not file offsets:
--   0x549A3  default save name "" -> "QUICKSAVE"
--   0x54ABF  restore lea rdx,[rsp+0x48] if the old patch is still active
--   0x54AC4  call vtable+0x98 (SaveGame) instead of vtable+0xB0 (stub)
--   0x98A17B force the save-location check to pass

local MODULE = "EvilWithin.exe"

if not openProcess(MODULE) then
  print("Could not open " .. MODULE .. ". Start the game first.")
  return
end

local a_name = getAddress(MODULE .. "+549A3")
local a_arg  = getAddress(MODULE .. "+54ABF")
local a_call = getAddress(MODULE .. "+54AC4")
local a_gate = getAddress(MODULE .. "+98A17B")

if a_name == nil or a_arg == nil or a_call == nil or a_gate == nil then
  print("Could not find the patch addresses. Wrong game build?")
  return
end

-- The call opcode is FF 90 <disp32>. The first displacement byte is the
-- vtable slot: B0 = original stub, A0 = old checkpoint patch, 98 = new patch.
local current = readBytes(a_call + 2, 1, true)
if type(current) ~= "table" then
  local s = current
  current = {}
  current[1] = string.byte(s, 1)
end

if current[1] == 0x98 then
  writeBytes(a_name, {0x48,0x8D,0x3D,0x8E,0x72,0x4F,0x01})
  writeBytes(a_arg,  {0x48,0x8D,0x54,0x24,0x48})
  writeBytes(a_call, {0xFF,0x90,0xB0,0x00,0x00,0x00})
  writeBytes(a_gate, {0x75})
  print("Reverted quick-save patch.")
else
  writeBytes(a_name, {0x48,0x8D,0x3D,0xBE,0x09,0x57,0x01})
  writeBytes(a_arg,  {0x48,0x8D,0x54,0x24,0x48})
  writeBytes(a_call, {0xFF,0x90,0x98,0x00,0x00,0x00})
  writeBytes(a_gate, {0xEB})
  print("Patched quick-save. In-game console: saveGameSteam")
end
