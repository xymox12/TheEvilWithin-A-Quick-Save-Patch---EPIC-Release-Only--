# Technical notes

These notes document how the patch was derived. They are not required to use it.

## Target

```text
File:    EvilWithin.exe
Format:  PE32+ (x86-64)
SHA-256: 6310988039DB58FC27DCA9C8E6AC00CB45C898DA38BFCCBB00898FA56DD414DB
PDB:     Zweid3d64_NGShippingRetail.pdb
```

The addresses below are for this exact build. If the game is updated, re-derive
them.

## `saveGameSteam` is a no-op

The command is registered in the command table:

```text
saveGameSteam -> FUN_140054980
```

`FUN_140054980` builds an `idStr` from the console argument and then calls the
object's vtable slot `+0xB0`:

```c
// 0x140054980
idGameLocal *game = DAT_142258e00;
game->vtable[0xB0](game, &idStr);
```

The vtable is a function-pointer table at `0x1416AD418` (runtime image base
`0x140000000`):

| Slot | Address | Function |
|---|---|---|
| `+0x98` | `0x1416AD4B0` | `FUN_14082B0D0` — normal `SaveGame(idStr*)` |
| `+0xA0` | `0x1416AD4B8` | `FUN_1408204D0` — checkpoint save wrapper |
| `+0xA8` | `0x1416AD4C0` | `0x140A2B800` — `ret 0` stub |
| `+0xB0` | `0x1416AD4C8` | `0x140A2B800` — `ret 0` stub |

`0x140A2B800` starts with `C2 00 00` (`ret 0`), so the retail command does
nothing. `loadGameSteam` calls `+0xA8`, which is the same stub.

## Why the old checkpoint patch failed

The first patch changed the call to `+0xA0`, i.e.:

```c
FUN_1408204D0(game, spawnSpotName, flag, ...)
{
    FUN_1408352B0(...);
    tngSaveLoadModule::CheckPointSaveGame(&DAT_149C83210, spawnSpotName);
    if (flag) { FUN_140989DB0(...); }
    FUN_1408352E0(...);
}
```

`CheckPointSaveGame` (`0x1409878F0`) calls the checkpoint save processor:

```c
FUN_1408B7C00(module, "QUICKSAVE", type, spawnSpotName);
```

It stores the checkpoint spawn spot in the save. If `spawnSpotName` is `NULL`,
the checkpoint system's last spawn entity is used. That entity can be from an
earlier chapter or an unloaded layer, so loading the save puts the player at that
entity or out of the world.

Evidence from `QUICKSAVE\mapstart.zwei`:

```text
old patch:    st06_asylummain_player_start_chapter4_division
normal save:  player_start
```

The old save also contained extra checkpoint-related strings
(`mapcontrol/village_mzone/...`, `stage/st01e/...`), while normal saves only
contain `player_start`.

## The normal save path

`idGameLocal` vtable `+0x98` is `FUN_14082B0D0`:

```c
void FUN_14082B0D0(idGameLocal *game, idStr *slotName)
{
    FUN_1408352B0(...);
    FUN_14098A010(&DAT_149C83210, slotName, 0, 0, -1, 0x100);
    FUN_1408352E0(...);
}
```

`FUN_14098A010` is the normal Save Game handler used by the in-game menu:

```c
FUN_14098A010(module, slotName, cpEntity, cpData, saveRoomNum, flags)
{
    ...
    if (!game->IsSaveAllowed(...)) {
        print("Cannot save at this location\n");
        return false;
    }
    ...
    if (cpEntity == NULL)
        FUN_1408B7E30(module, slotName, ...);   // normal save
    else
        FUN_1408B8620(module, slotName, ...);   // checkpoint save

    module->state = 2;
}
```

`FUN_1408B7E30` sets the normal save flags and calls `FUN_1408B8300`, which
writes the standard payload. The player state is captured by
`FUN_14082E050` -> `FUN_14082B230`, which calls the player's save virtual method.
The resulting save has spawn spot `player_start` and restores the saved player
position.

## The patch

```asm
; default slot name "" -> "QUICKSAVE"
0x1400549A3: 48 8D 3D 8E 72 4F 01
       ->    48 8D 3D BE 09 57 01

; call normal SaveGame instead of the stub
0x140054AC4: FF 90 B0 00 00 00
       ->    FF 90 98 00 00 00

; force the save-location check to pass
0x14098A17B: 75 11
       ->    EB 11
```

The second site is technically a one-byte change (`B0` -> `98` in the vtable
displacement), but the scripts write the whole 6-byte instruction for clarity.

The `0x140054ABF` site is not changed by this patch. It is restored to
`48 8D 54 24 48` so that a leftover old checkpoint patch cannot leave
`xor r8d,r8d; xor edx,edx` in place.

## Original quick-save bindings

The retail `base\default.cfg` still contains the disabled original bindings:

```text
//<workshop> REMOVE_QUICK_SAVE_LOAD_FUNCTIONALITY AANG 2014-09-15
//DEL:
//bind F8 "savegame quick"
//bind F9 "loadgame quick"
//</workshop>
```

The autosave callback at `0x140B461C0` also executes `savegame quick` through
the save manager. The normal save path above is the same one the game uses for
that command.

## Verifying a build

Check the file hash first:

```powershell
Get-FileHash .\EvilWithin.exe -Algorithm SHA256
```

Expected:

```text
6310988039DB58FC27DCA9C8E6AC00CB45C898DA38BFCCBB00898FA56DD414DB
```

Check the original bytes at the patch sites:

```text
File offset 0x53DA3: 48 8D 3D 8E 72 4F 01
File offset 0x53EBF: 48 8D 54 24 48
File offset 0x53EC4: FF 90 B0 00 00 00
File offset 0x98957B: 75 11
```

If any differ, stop and re-derive the addresses for your build.
