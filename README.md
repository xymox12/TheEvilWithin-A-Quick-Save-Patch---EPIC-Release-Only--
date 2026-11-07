# The Evil Within — Quick Save Patch

A small, reversible patch for the retail PC build of **The Evil Within** that
makes the disabled `saveGameSteam` console command perform a normal quick save.

The patch is applied with **Cheat Engine** as a runtime memory patch. It does not
modify `EvilWithin.exe` on disk and can be toggled off instantly.

> Single-player, offline use only. Back up your saves. This project is not
> affiliated with Tango Gameworks, Bethesda, or Epic Games.

---

## What it fixes

In the retail build, `saveGameSteam` is registered but does nothing:

```c
idGameLocal *game = DAT_142258e00;
game->vtable[0xB0](game, &idStr);   // slot +0xB0 is a `ret 0` stub
```

The patch changes that call to the game's normal Save Game method:

```c
game->vtable[0x98](game, &idStr);   // idGameLocal::SaveGame
```

With the default slot name changed to `QUICKSAVE`, the command becomes:

```text
saveGameSteam -> idGameLocal::SaveGame("QUICKSAVE")
              -> FUN_14082B0D0 -> FUN_14098A010(...)
```

That is the same path used by the in-game save menu. It writes the normal
`QUICKSAVE` payload: spawn spot `player_start`, the current player state, and the
normal save blocks.

A second small patch forces the `"Cannot save at this location"` check to pass,
so you can save at an arbitrary point.

---

## Important: do not use the old checkpoint patch

An earlier version of this patch redirected the call to vtable `+0xA0`
(`tngSaveLoadModule::CheckPointSaveGame`) with a `NULL` spawn spot. That writes a
**checkpoint** save whose spawn entity is the last checkpoint's spawn. At an
arbitrary point that entity can be stale or belong to another map, so loading
the save puts you back at the checkpoint or out of the world.

You can see the difference in `QUICKSAVE\mapstart.zwei`:

| Save source | Spawn spot stored |
|---|---|
| Old checkpoint patch | `st06_asylummain_player_start_chapter4_division` (stale) |
| Game's normal save | `player_start` |

This project uses the normal save path, so the old checkpoint patch must be
disabled before applying this one. The scripts handle that automatically.

---

## Requirements

- The Evil Within retail PC build with this SHA-256:

  ```text
  6310988039DB58FC27DCA9C8E6AC00CB45C898DA38BFCCBB00898FA56DD414DB
  ```

- [Cheat Engine](https://cheatengine.org/)

---

## Usage (Cheat Engine)

### Lua script

1. Start the game.
2. In Cheat Engine: `File > Execute Script`, select
   `ew_quicksave_patch.lua`.
3. Run it again to revert.

### Auto Assembler script

1. Start the game and attach Cheat Engine to `EvilWithin.exe`.
2. Open `Memory View` (`Ctrl+M`) → `Tools > Auto Assembler` (`Ctrl+Alt+A`).
3. Paste `ew_quicksave_patch.aa.txt`.
4. `File > Assign to current cheat table`, then tick/untick the entry.

> Cheat Engine AA comments must use `//`, not `;`. CE may try to parse a leading
> `;` as a command.

---

## Usage in game

Open the console and type:

```text
saveGameSteam
```

Or bind it to a key:

```text
bind F5 saveGameSteam
```

The save is written to:

```text
%USERPROFILE%\Saved Games\TangoGameworks\The Evil Within (Epic)\base\savegame\QUICKSAVE
```

Load it from the normal **Continue** / **Load Game** menu. In some builds
`loadgame quick` also works.

### No-patch alternative

The retail `base\default.cfg` still references the original quick-save bindings:

```text
//<workshop> REMOVE_QUICK_SAVE_LOAD_FUNCTIONALITY AANG 2014-09-15
//DEL:
//bind F8 "savegame quick"
//bind F9 "loadgame quick"
//</workshop>
```

Try `savegame quick` in the console. If it is available, it uses the same normal
save path. The patch is mainly useful when that command is hidden or gated by the
save-location check.

---

## Patch details

RVA = module offset for Cheat Engine. File offset = RVA − `0xC00` for these
`.text` sites.

| Site | RVA | File offset | Original | Patched |
|---|---|---|---|---|
| Default save name | `0x549A3` | `0x53DA3` | `48 8D 3D 8E 72 4F 01` | `48 8D 3D BE 09 57 01` |
| idStr argument | `0x54ABF` | `0x53EBF` | `48 8D 54 24 48` | unchanged (restores old patch) |
| Save call | `0x54AC4` | `0x53EC4` | `FF 90 B0 00 00 00` | `FF 90 98 00 00 00` |
| Save-location gate | `0x98A17B` | `0x98957B` | `75 11` | `EB 11` |

Meaning:

```asm
; default slot name "" -> "QUICKSAVE"
lea rdi,[empty]          -> lea rdi,["QUICKSAVE"]

; call idGameLocal::SaveGame instead of the stub
call [rax+0xB0]          -> call [rax+0x98]

; force the "Cannot save at this location" check to pass
jnz allowed              -> jmp allowed
```

---

## Troubleshooting

- **Position still wrong after loading:** the current `QUICKSAVE` may still be the
  old bad checkpoint save. Load a known-good save (or restart the chapter) once,
  then save again.
- **`Cannot save at this location` appears:** the gate patch is not active. Check
  that `EvilWithin.exe+98A17B` is `EB`.
- **Cheat Engine syntax error:** AA comments use `//`, not `;`. If the Lua script
  errors, use the AA script.
- **Save during a cutscene/loading screen:** don't. Wait until gameplay is fully
  active.
- **Game updated:** the RVAs and bytes may differ. Verify the SHA-256 first.

---

## Safety

- The Cheat Engine patch changes only process memory, not `EvilWithin.exe` on disk.
- Do not use this with anti-cheat-protected or multiplayer games. The Evil Within
  is single-player.
- Saving in an invalid game state can still produce a bad save. Save during normal
  gameplay, not during transitions.

---

## License

The scripts and documentation in this repository are released under the MIT
License. See [LICENSE](LICENSE).

No game files, assets, or binaries are included. The Evil Within and all related
trademarks are property of their respective owners.
