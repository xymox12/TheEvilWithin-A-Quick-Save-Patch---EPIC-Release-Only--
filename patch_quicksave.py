#!/usr/bin/env python3
"""
The Evil Within - quick save runtime patch.

This is the Python equivalent of the Cheat Engine scripts. It attaches to the
running game and patches the process memory; it does not modify EvilWithin.exe
on disk.

Usage:
    python patch_quicksave.py            # toggle patch on/off
    python patch_quicksave.py --revert   # force the original bytes
    python patch_quicksave.py --check    # only report the current state

Windows only. If the game is running elevated, run this from an elevated
terminal as well.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import sys
from ctypes import wintypes

# ---------------------------------------------------------------------------
# Windows API
# ---------------------------------------------------------------------------

if os.name != "nt":
    sys.exit("This script only works on Windows.")

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400

TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010

PAGE_EXECUTE_READWRITE = 0x40


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", ctypes.c_char * 256),
        ("szExePath", ctypes.c_char * 260),
    ]


kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE

kernel32.Process32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
kernel32.Process32First.restype = wintypes.BOOL
kernel32.Process32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
kernel32.Process32Next.restype = wintypes.BOOL

kernel32.Module32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32)]
kernel32.Module32First.restype = wintypes.BOOL
kernel32.Module32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32)]
kernel32.Module32Next.restype = wintypes.BOOL

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE

kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.LPVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.ReadProcessMemory.restype = wintypes.BOOL

kernel32.WriteProcessMemory.argtypes = [
    wintypes.HANDLE,
    wintypes.LPVOID,
    wintypes.LPCVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.WriteProcessMemory.restype = wintypes.BOOL

kernel32.VirtualProtectEx.argtypes = [
    wintypes.HANDLE,
    wintypes.LPVOID,
    ctypes.c_size_t,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.VirtualProtectEx.restype = wintypes.BOOL

kernel32.FlushInstructionCache.argtypes = [
    wintypes.HANDLE,
    wintypes.LPCVOID,
    ctypes.c_size_t,
]
kernel32.FlushInstructionCache.restype = wintypes.BOOL

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


def _last_error(action: str) -> OSError:
    err = ctypes.get_last_error()
    return OSError(err, f"{action}: {ctypes.FormatError(err)}")


# ---------------------------------------------------------------------------
# Process / module lookup
# ---------------------------------------------------------------------------

def find_pid(exe_name: str) -> int | None:
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        raise _last_error("CreateToolhelp32Snapshot(processes)")

    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Process32First(snapshot, ctypes.byref(entry)):
            return None
        while True:
            name = entry.szExeFile.decode(errors="ignore")
            if name.lower() == exe_name.lower():
                return int(entry.th32ProcessID)
            if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                return None
    finally:
        kernel32.CloseHandle(snapshot)


def find_module_base(pid: int, module_name: str) -> int | None:
    flags = TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32
    for _ in range(5):
        snapshot = kernel32.CreateToolhelp32Snapshot(flags, pid)
        if snapshot == wintypes.HANDLE(-1).value:
            # ERROR_BAD_LENGTH can happen while a process is still loading.
            if ctypes.get_last_error() == 24:
                continue
            raise _last_error("CreateToolhelp32Snapshot(modules)")
        try:
            entry = MODULEENTRY32()
            entry.dwSize = ctypes.sizeof(entry)
            if not kernel32.Module32First(snapshot, ctypes.byref(entry)):
                return None
            while True:
                name = entry.szModule.decode(errors="ignore")
                if name.lower() == module_name.lower():
                    return int(ctypes.cast(entry.modBaseAddr, ctypes.c_void_p).value)
                if not kernel32.Module32Next(snapshot, ctypes.byref(entry)):
                    return None
        finally:
            kernel32.CloseHandle(snapshot)
    return None


def open_process(pid: int) -> int:
    access = (
        PROCESS_VM_READ
        | PROCESS_VM_WRITE
        | PROCESS_VM_OPERATION
        | PROCESS_QUERY_INFORMATION
    )
    handle = kernel32.OpenProcess(access, False, pid)
    if not handle:
        raise _last_error("OpenProcess")
    return int(handle)


# ---------------------------------------------------------------------------
# Memory access
# ---------------------------------------------------------------------------

def read_bytes(handle: int, address: int, size: int) -> bytes:
    buffer = (ctypes.c_ubyte * size)()
    read = ctypes.c_size_t(0)
    if not kernel32.ReadProcessMemory(
        handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(read)
    ):
        raise _last_error(f"ReadProcessMemory at 0x{address:X}")
    return bytes(buffer[: read.value])


def write_bytes(handle: int, address: int, data: bytes) -> None:
    size = len(data)
    old_protect = wintypes.DWORD(0)
    if not kernel32.VirtualProtectEx(
        handle,
        ctypes.c_void_p(address),
        size,
        PAGE_EXECUTE_READWRITE,
        ctypes.byref(old_protect),
    ):
        raise _last_error(f"VirtualProtectEx at 0x{address:X}")

    try:
        buffer = (ctypes.c_ubyte * size).from_buffer_copy(data)
        written = ctypes.c_size_t(0)
        if not kernel32.WriteProcessMemory(
            handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(written)
        ):
            raise _last_error(f"WriteProcessMemory at 0x{address:X}")
        if written.value != size:
            raise OSError(f"Short write at 0x{address:X}: {written.value}/{size}")
    finally:
        restored = wintypes.DWORD(0)
        kernel32.VirtualProtectEx(
            handle,
            ctypes.c_void_p(address),
            size,
            old_protect.value,
            ctypes.byref(restored),
        )

    kernel32.FlushInstructionCache(handle, ctypes.c_void_p(address), size)


def hexdump(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


# ---------------------------------------------------------------------------
# Patch definition
# ---------------------------------------------------------------------------

# RVAs, not file offsets.
NAME_RVA = 0x549A3
ARG_RVA = 0x54ABF
CALL_RVA = 0x54AC4
GATE_RVA = 0x98A17B

NAME_ORIGINAL = bytes.fromhex("48 8D 3D 8E 72 4F 01")
NAME_PATCHED = bytes.fromhex("48 8D 3D BE 09 57 01")

ARG_ORIGINAL = bytes.fromhex("48 8D 54 24 48")
ARG_OLD_PATCH = bytes.fromhex("45 31 C0 31 D2")

CALL_ORIGINAL = bytes.fromhex("FF 90 B0 00 00 00")
CALL_OLD_PATCH = bytes.fromhex("FF 90 A0 00 00 00")
CALL_PATCHED = bytes.fromhex("FF 90 98 00 00 00")

GATE_ORIGINAL = bytes.fromhex("75")
GATE_PATCHED = bytes.fromhex("EB")


def current_state(handle: int, base: int) -> str:
    call = read_bytes(handle, base + CALL_RVA, len(CALL_ORIGINAL))
    if call == CALL_PATCHED:
        return "patched"
    if call == CALL_OLD_PATCH:
        return "old-checkpoint-patch"
    if call == CALL_ORIGINAL:
        return "original"
    return f"unknown ({hexdump(call)})"


def check_sites(handle: int, base: int) -> None:
    """Abort if any site contains bytes we do not recognize."""
    name = read_bytes(handle, base + NAME_RVA, len(NAME_ORIGINAL))
    if name not in (NAME_ORIGINAL, NAME_PATCHED):
        raise RuntimeError(
            f"Unexpected bytes at NAME site (+0x{NAME_RVA:X}): {hexdump(name)}"
        )

    arg = read_bytes(handle, base + ARG_RVA, len(ARG_ORIGINAL))
    if arg not in (ARG_ORIGINAL, ARG_OLD_PATCH):
        raise RuntimeError(
            f"Unexpected bytes at ARG site (+0x{ARG_RVA:X}): {hexdump(arg)}"
        )

    call = read_bytes(handle, base + CALL_RVA, len(CALL_ORIGINAL))
    if call not in (CALL_ORIGINAL, CALL_OLD_PATCH, CALL_PATCHED):
        raise RuntimeError(
            f"Unexpected bytes at CALL site (+0x{CALL_RVA:X}): {hexdump(call)}"
        )

    gate = read_bytes(handle, base + GATE_RVA, len(GATE_ORIGINAL))
    if gate not in (GATE_ORIGINAL, GATE_PATCHED):
        raise RuntimeError(
            f"Unexpected bytes at GATE site (+0x{GATE_RVA:X}): {hexdump(gate)}"
        )


def apply_patch(handle: int, base: int) -> None:
    check_sites(handle, base)
    write_bytes(handle, base + NAME_RVA, NAME_PATCHED)
    write_bytes(handle, base + ARG_RVA, ARG_ORIGINAL)
    write_bytes(handle, base + CALL_RVA, CALL_PATCHED)
    write_bytes(handle, base + GATE_RVA, GATE_PATCHED)
    print("Patched quick-save. In-game console: saveGameSteam")


def revert_patch(handle: int, base: int) -> None:
    check_sites(handle, base)
    write_bytes(handle, base + NAME_RVA, NAME_ORIGINAL)
    write_bytes(handle, base + ARG_RVA, ARG_ORIGINAL)
    write_bytes(handle, base + CALL_RVA, CALL_ORIGINAL)
    write_bytes(handle, base + GATE_RVA, GATE_ORIGINAL)
    print("Reverted quick-save patch.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Runtime patch for The Evil Within saveGameSteam."
    )
    parser.add_argument(
        "--process",
        default="EvilWithin.exe",
        help="process name (default: EvilWithin.exe)",
    )
    parser.add_argument(
        "--module",
        default="EvilWithin.exe",
        help="module name (default: EvilWithin.exe)",
    )
    parser.add_argument(
        "--pid",
        type=int,
        default=0,
        help="process id; overrides --process",
    )
    parser.add_argument(
        "--revert",
        action="store_true",
        help="restore the original bytes instead of toggling",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="only report the current state",
    )
    args = parser.parse_args()

    pid = args.pid or find_pid(args.process)
    if not pid:
        print(f"Could not find process: {args.process}")
        return 1

    base = find_module_base(pid, args.module)
    if base is None:
        print(f"Could not find module: {args.module} in pid {pid}")
        return 1

    try:
        handle = open_process(pid)
    except OSError as exc:
        print(exc)
        print("If the game is elevated, run this script from an elevated terminal.")
        return 1

    try:
        state = current_state(handle, base)
        print(f"Process: {args.process} (pid {pid})")
        print(f"Module base: 0x{base:X}")
        print(f"State: {state}")

        if args.check:
            return 0

        if args.revert or state == "patched":
            revert_patch(handle, base)
        else:
            apply_patch(handle, base)

        print(f"New state: {current_state(handle, base)}")
        return 0
    finally:
        kernel32.CloseHandle(handle)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)
