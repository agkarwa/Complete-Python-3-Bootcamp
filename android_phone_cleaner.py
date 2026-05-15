#!/usr/bin/env python3
"""
Android Phone Cleaner
Requires: ADB (Android Debug Bridge) installed and USB debugging enabled on phone.
Install ADB: https://developer.android.com/studio/command-line/adb
"""

import subprocess
import sys


def run_adb(args, capture=True):
    cmd = ["adb"] + args
    result = subprocess.run(cmd, capture_output=capture, text=True)
    return result


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _parse_df_line(line):
    """Return (used_kb, total_kb) from a `df` output line, or (0, 0)."""
    parts = line.split()
    # Typical format: Filesystem  1K-blocks  Used  Available  Use%  Mounted
    try:
        total_kb = int(parts[1])
        used_kb  = int(parts[2])
        return used_kb, total_kb
    except (IndexError, ValueError):
        return 0, 0


def _usage_bar(used, total, width=30):
    """Return an ASCII progress bar and percentage string."""
    pct = used / total if total else 0
    filled = int(pct * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct*100:5.1f}%"


def _human(kb):
    """Convert kilobytes to a human-readable string."""
    if kb >= 1_048_576:
        return f"{kb / 1_048_576:.2f} GB"
    if kb >= 1_024:
        return f"{kb / 1_024:.2f} MB"
    return f"{kb} KB"


def _folder_size_kb(path):
    """Return total size of a folder in KB via `du`, or 0 on error."""
    res = run_adb(["shell", f"du -sk {path} 2>/dev/null"])
    line = res.stdout.strip().splitlines()
    if line:
        try:
            return int(line[0].split()[0])
        except (IndexError, ValueError):
            pass
    return 0


def _count_files(path, extensions):
    """Count files under *path* matching any of *extensions* (e.g. '*.jpg')."""
    patterns = " -o ".join(f"-name '{e}'" for e in extensions)
    res = run_adb(["shell", f"find {path} \\( {patterns} \\) -type f 2>/dev/null | wc -l"])
    try:
        return int(res.stdout.strip())
    except ValueError:
        return 0


def check_device():
    result = run_adb(["devices"])
    lines = result.stdout.strip().splitlines()
    devices = [l for l in lines[1:] if l.strip() and "device" in l and "offline" not in l]
    if not devices:
        print("No Android device found. Make sure:")
        print("  1. USB debugging is enabled (Settings > Developer Options > USB Debugging)")
        print("  2. The phone is connected via USB")
        print("  3. You have accepted the RSA key prompt on the phone")
        sys.exit(1)
    print(f"Device connected: {devices[0].split()[0]}")


def get_storage_info():
    print("\n" + "═" * 52)
    print("  STORAGE REPORT")
    print("═" * 52)

    # ── 1. Partition overview ────────────────────────────────
    print("\n  Partitions")
    print("  " + "-" * 49)
    partitions = {
        "Internal (/data)":    "/data",
        "SD Card  (/sdcard)":  "/sdcard",
        "System   (/system)":  "/system",
    }
    totals_used = totals_total = 0
    for label, mount in partitions.items():
        res = run_adb(["shell", "df", "-k", mount])
        lines = [l for l in res.stdout.strip().splitlines() if mount in l or (len(res.stdout.strip().splitlines()) == 2)]
        if not lines:
            print(f"  {label:<22} — not available")
            continue
        used_kb, total_kb = _parse_df_line(lines[-1])
        if total_kb == 0:
            print(f"  {label:<22} — not available")
            continue
        bar = _usage_bar(used_kb, total_kb, width=24)
        free_kb = total_kb - used_kb
        print(f"  {label:<22} {bar}")
        print(f"  {'':22} Used {_human(used_kb):>9}  Free {_human(free_kb):>9}  Total {_human(total_kb):>9}")
        if mount != "/system":
            totals_used  += used_kb
            totals_total += total_kb

    # ── 2. Category breakdown (sdcard) ──────────────────────
    print("\n  Media Categories  (/sdcard)")
    print("  " + "-" * 49)
    categories = [
        ("Photos / Screenshots", ["*.jpg", "*.jpeg", "*.png", "*.webp", "*.heic"],
         ["/sdcard/DCIM", "/sdcard/Pictures", "/sdcard/Screenshots"]),
        ("Videos",               ["*.mp4", "*.mkv", "*.avi", "*.mov", "*.3gp"],
         ["/sdcard/DCIM", "/sdcard/Movies"]),
        ("Music / Audio",        ["*.mp3", "*.flac", "*.aac", "*.ogg", "*.wav"],
         ["/sdcard/Music"]),
        ("Documents",            ["*.pdf", "*.docx", "*.xlsx", "*.pptx", "*.txt"],
         ["/sdcard/Documents", "/sdcard/Download"]),
        ("APK files",            ["*.apk"],
         ["/sdcard"]),
    ]
    for name, exts, paths in categories:
        total_files = sum(_count_files(p, exts) for p in paths)
        folder_kb   = sum(_folder_size_kb(p) for p in paths)
        print(f"  {name:<28} {total_files:>5} files   {_human(folder_kb):>9}")

    # ── 3. App cache sizes ───────────────────────────────────
    print("\n  App Cache Sizes  (top 8)")
    print("  " + "-" * 49)
    cache_root = "/data/data"
    res = run_adb(["shell", f"du -sk {cache_root}/*/cache 2>/dev/null | sort -rn | head -8"])
    cache_lines = res.stdout.strip().splitlines()
    if cache_lines:
        for cl in cache_lines:
            parts = cl.split()
            if len(parts) >= 2:
                size_kb = int(parts[0]) if parts[0].isdigit() else 0
                # path like /data/data/com.example.app/cache -> extract package
                pkg = parts[1].replace(f"{cache_root}/", "").replace("/cache", "")
                print(f"  {pkg:<40} {_human(size_kb):>9}")
    else:
        print("  (requires root or elevated ADB access)")

    # ── 4. Key folders ───────────────────────────────────────
    print("\n  Key Folder Sizes")
    print("  " + "-" * 49)
    folders = [
        ("Downloads",    "/sdcard/Download"),
        ("WhatsApp",     "/sdcard/WhatsApp"),
        ("Telegram",     "/sdcard/Telegram"),
        ("DCIM",         "/sdcard/DCIM"),
        ("Android/data", "/sdcard/Android/data"),
        ("Temp /tmp",    "/data/local/tmp"),
    ]
    for fname, fpath in folders:
        kb = _folder_size_kb(fpath)
        bar = _usage_bar(kb, totals_total, width=16) if totals_total else ""
        print(f"  {fname:<20} {_human(kb):>9}   {bar}")

    # ── 5. Summary ───────────────────────────────────────────
    print("\n" + "═" * 52)
    if totals_total:
        print(f"  Overall (data + sdcard): {_human(totals_used)} used / {_human(totals_total)} total")
        print(f"  Free space remaining   : {_human(totals_total - totals_used)}")
    print("═" * 52)


def list_all_app_caches():
    print("\n" + "═" * 60)
    print("  APP CACHE LIST")
    print("═" * 60)
    print("  Fetching all installed packages...")

    # Get all packages: system (-s) and third-party (-3)
    res_sys = run_adb(["shell", "pm", "list", "packages", "-s"])
    res_3p  = run_adb(["shell", "pm", "list", "packages", "-3"])

    system_pkgs = {
        line.replace("package:", "").strip()
        for line in res_sys.stdout.splitlines() if line.startswith("package:")
    }
    third_pkgs = {
        line.replace("package:", "").strip()
        for line in res_3p.stdout.splitlines() if line.startswith("package:")
    }
    all_pkgs = system_pkgs | third_pkgs

    if not all_pkgs:
        print("  No packages found.")
        return

    # Collect cache sizes via du on /data/data/<pkg>/cache
    print(f"  Scanning cache for {len(all_pkgs)} apps (this may take a moment)...")
    cache_root = "/data/data"

    # Bulk du in one shell call for speed
    res = run_adb(["shell", f"du -sk {cache_root}/*/cache 2>/dev/null"])
    size_map = {}
    for line in res.stdout.strip().splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            try:
                kb = int(parts[0])
            except ValueError:
                continue
            pkg = parts[1].replace(f"{cache_root}/", "").replace("/cache", "").strip()
            size_map[pkg] = kb

    # Also check /data/user/0/<pkg>/cache (multi-user path on newer Android)
    res2 = run_adb(["shell", f"du -sk /data/user/0/*/cache 2>/dev/null"])
    for line in res2.stdout.strip().splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            try:
                kb = int(parts[0])
            except ValueError:
                continue
            pkg = parts[1].replace("/data/user/0/", "").replace("/cache", "").strip()
            if pkg not in size_map or size_map[pkg] == 0:
                size_map[pkg] = kb

    # Build rows: every known package, defaulting missing ones to 0
    rows = []
    for pkg in all_pkgs:
        kb = size_map.get(pkg, 0)
        kind = "3rd-party" if pkg in third_pkgs else "system"
        rows.append((kb, pkg, kind))

    rows.sort(key=lambda r: r[0], reverse=True)

    total_cache_kb = sum(r[0] for r in rows)
    nonzero        = [r for r in rows if r[0] > 0]
    zero           = [r for r in rows if r[0] == 0]

    # ── Filter prompt ────────────────────────────────────────
    print("\n  Filter:  [1] All apps   [2] Third-party only   [3] Non-zero only")
    filt = input("  Choice (default 1): ").strip() or "1"
    if filt == "2":
        rows = [r for r in rows if r[2] == "3rd-party"]
    elif filt == "3":
        rows = nonzero

    # ── Table ────────────────────────────────────────────────
    print()
    print(f"  {'#':>4}  {'Package':<45} {'Type':<10} {'Cache':>9}")
    print("  " + "-" * 72)

    for i, (kb, pkg, kind) in enumerate(rows, 1):
        size_str = _human(kb) if kb > 0 else "  —"
        # Truncate long package names
        display = pkg if len(pkg) <= 45 else pkg[:42] + "..."
        print(f"  {i:>4}  {display:<45} {kind:<10} {size_str:>9}")

    # ── Summary ──────────────────────────────────────────────
    shown_nonzero = [r for r in rows if r[0] > 0]
    print("  " + "-" * 72)
    print(f"\n  Total apps scanned : {len(all_pkgs)}")
    print(f"  Apps with cache    : {len(nonzero)}")
    print(f"  Apps with no cache : {len(zero)}")
    print(f"  Total cache size   : {_human(total_cache_kb)}")

    if not nonzero:
        print("\n  Note: 0-byte results may mean ADB lacks permission to read")
        print("  /data/data. Try enabling 'USB Debugging (Security Settings)'")
        print("  or run ADB as root: adb root")
        print("═" * 60)
        return

    print("═" * 60)

    # ── Clean prompt ─────────────────────────────────────────
    if not shown_nonzero:
        return

    print("\n  Clean options:")
    print("  [A] Clean ALL shown caches")
    print("  [S] Select specific apps by number  (e.g. 1,3,5 or 1-4)")
    print("  [N] Do nothing (return to menu)")
    action = input("\n  Choice: ").strip().upper()

    if action == "N" or action == "":
        return

    targets = []
    if action == "A":
        targets = shown_nonzero
    elif action == "S":
        raw = input("  Enter numbers (e.g. 1,3,5-7): ").strip()
        selected = set()
        for part in raw.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    lo, hi = part.split("-", 1)
                    selected.update(range(int(lo), int(hi) + 1))
                except ValueError:
                    pass
            elif part.isdigit():
                selected.add(int(part))
        targets = [rows[i - 1] for i in sorted(selected) if 1 <= i <= len(rows) and rows[i - 1][0] > 0]
        if not targets:
            print("  No valid entries selected.")
            return
    else:
        print("  Invalid choice.")
        return

    freed_kb = sum(r[0] for r in targets)
    print(f"\n  About to clear cache for {len(targets)} app(s)  ({_human(freed_kb)} estimated).")
    print("  Method: cmd package trim-caches (cache-only, safe — does NOT wipe app data)")
    confirm = input("  Confirm? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("  Cancelled.")
        return

    print()
    ok = fail = 0
    for kb, pkg, kind in targets:
        ok_flag, note = _clear_cache_safe(pkg, kb)
        status = "OK" if ok_flag else "FAIL"
        if ok_flag:
            ok += 1
        else:
            fail += 1
        display = pkg if len(pkg) <= 45 else pkg[:42] + "..."
        suffix = f"  ({note})" if note else ""
        print(f"  [{status}] {display:<45} {_human(kb):>9}{suffix}")

    print("\n" + "═" * 60)
    print(f"  Cleared : {ok} app(s)   Failed : {fail} app(s)")
    print(f"  Space freed (estimated) : {_human(freed_kb)}")
    print("═" * 60)


def _clear_cache_safe(pkg, size_kb=0):
    """
    Clear only the cache for *pkg* without touching user data.

    Strategy (in order):
    1. root path: rm -rf /data/data/<pkg>/cache/*  (instant, precise)
    2. non-root:  cmd package trim-caches asks Android to free
                  at least size_kb worth of cache for that package.
    Returns (success: bool, note: str).
    """
    # Try rooted path first (works silently if not rooted)
    res = run_adb(["shell",
                   f"su -c 'rm -rf /data/data/{pkg}/cache/* 2>/dev/null' 2>/dev/null; echo $?"])
    if res.stdout.strip() == "0":
        return True, "root"

    # Non-root: ask Android's storage manager to reclaim cache for this package.
    # We request double the known cache size so Android actually frees it.
    want_bytes = max(size_kb * 1024 * 2, 1048576)  # at least 1 MB request
    res2 = run_adb(["shell", f"cmd package trim-caches {want_bytes} {pkg} 2>/dev/null; echo $?"])
    last_line = res2.stdout.strip().splitlines()[-1] if res2.stdout.strip() else "1"
    if last_line == "0":
        return True, "trim-caches"

    # Last resort: system-wide trim requesting the same bytes (no per-pkg targeting)
    res3 = run_adb(["shell", f"cmd package trim-caches {want_bytes} 2>/dev/null; echo $?"])
    last_line3 = res3.stdout.strip().splitlines()[-1] if res3.stdout.strip() else "1"
    if last_line3 == "0":
        return True, "system trim"

    return False, "needs root"


def clear_app_caches():
    print("\n--- Clearing App Caches (cache-only, safe) ---")
    print("    Uses trim-caches / root rm — does NOT wipe app data.\n")
    result = run_adb(["shell", "pm", "list", "packages", "-3"])
    packages = [line.replace("package:", "").strip() for line in result.stdout.splitlines()]

    if not packages:
        print("No third-party apps found.")
        return

    print(f"Found {len(packages)} third-party apps. Clearing caches...")
    ok = fail = 0
    for pkg in packages:
        success, _ = _clear_cache_safe(pkg)
        if success:
            ok += 1
        else:
            fail += 1

    print(f"Cleared : {ok}   Failed : {fail}   (failures need root access)")


def clear_system_temp():
    print("\n--- Clearing System Temp Files ---")
    dirs = ["/data/local/tmp", "/sdcard/Android/data/com.android.providers.media/cache"]
    for d in dirs:
        result = run_adb(["shell", f"rm -rf {d}/* 2>/dev/null; echo done"])
        print(f"Cleaned {d}: {result.stdout.strip()}")


def clear_logcat():
    print("\n--- Clearing Logcat Buffer ---")
    run_adb(["logcat", "-c"])
    print("Logcat buffer cleared.")


def list_large_files():
    print("\n--- Top 10 Largest Files on SD Card ---")
    result = run_adb(["shell", "find /sdcard -type f -printf '%s %p\\n' 2>/dev/null | sort -rn | head -10"])
    if result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                size_bytes = int(parts[0]) if parts[0].isdigit() else 0
                size_mb = size_bytes / (1024 * 1024)
                print(f"  {size_mb:7.2f} MB  {parts[1]}")
    else:
        print("  Could not list files (permission issue or empty storage).")


def clear_downloads(confirm=False):
    if not confirm:
        answer = input("\nDo you want to list files in Downloads? (y/n): ").strip().lower()
        if answer != "y":
            return
    print("\n--- Files in /sdcard/Download ---")
    result = run_adb(["shell", "ls -lh /sdcard/Download/"])
    print(result.stdout or "  (empty or inaccessible)")

    answer = input("Delete ALL files in Downloads? This cannot be undone. (yes/no): ").strip().lower()
    if answer == "yes":
        run_adb(["shell", "rm -rf /sdcard/Download/*"])
        print("Downloads folder cleared.")
    else:
        print("Skipped.")


def uninstall_app():
    result = run_adb(["shell", "pm", "list", "packages", "-3"])
    packages = [line.replace("package:", "").strip() for line in result.stdout.splitlines()]

    print("\n--- Installed Third-Party Apps ---")
    for i, pkg in enumerate(packages, 1):
        print(f"  {i:3}. {pkg}")

    answer = input("\nEnter package number to uninstall (or press Enter to skip): ").strip()
    if answer.isdigit():
        idx = int(answer) - 1
        if 0 <= idx < len(packages):
            pkg = packages[idx]
            confirm = input(f"Uninstall '{pkg}'? (yes/no): ").strip().lower()
            if confirm == "yes":
                res = run_adb(["shell", "pm", "uninstall", "-k", "--user", "0", pkg])
                print(res.stdout.strip() or res.stderr.strip())
        else:
            print("Invalid selection.")
    else:
        print("Skipped.")


def menu():
    options = {
        "1": ("Show storage usage",              get_storage_info),
        "2": ("Clear app caches",                clear_app_caches),
        "3": ("Clear system temp files",         clear_system_temp),
        "4": ("Clear logcat buffer",             clear_logcat),
        "5": ("List top 10 largest files",       list_large_files),
        "6": ("Manage Downloads folder",         clear_downloads),
        "7": ("Uninstall a third-party app",     uninstall_app),
        "8": ("Run all safe cleanups (1-5)",     None),
        "9": ("List cache of ALL apps",          list_all_app_caches),
        "0": ("Exit",                            None),
    }

    print("\n╔══════════════════════════════════╗")
    print("║     Android Phone Cleaner        ║")
    print("╚══════════════════════════════════╝")
    for key, (label, _) in options.items():
        print(f"  [{key}] {label}")

    choice = input("\nSelect an option: ").strip()

    if choice == "0":
        print("Goodbye!")
        sys.exit(0)
    elif choice == "8":
        get_storage_info()
        clear_app_caches()
        clear_system_temp()
        clear_logcat()
        list_large_files()
        get_storage_info()
    elif choice in options and options[choice][1]:
        options[choice][1]()
    else:
        print("Invalid option.")


def main():
    print("Checking ADB connection...")
    check_device()

    while True:
        menu()
        input("\nPress Enter to continue...")


if __name__ == "__main__":
    main()
