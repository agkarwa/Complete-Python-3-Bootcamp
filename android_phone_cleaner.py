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


def clear_app_caches():
    print("\n--- Clearing App Caches ---")
    result = run_adb(["shell", "pm", "list", "packages", "-3"])
    packages = [line.replace("package:", "").strip() for line in result.stdout.splitlines()]

    if not packages:
        print("No third-party apps found.")
        return

    print(f"Found {len(packages)} third-party apps. Clearing caches...")
    cleared = 0
    for pkg in packages:
        res = run_adb(["shell", "pm", "clear", "--cache-only", pkg])
        if res.returncode == 0:
            cleared += 1

    print(f"Cleared cache for {cleared}/{len(packages)} apps.")


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
        "1": ("Show storage usage",         get_storage_info),
        "2": ("Clear app caches",           clear_app_caches),
        "3": ("Clear system temp files",    clear_system_temp),
        "4": ("Clear logcat buffer",        clear_logcat),
        "5": ("List top 10 largest files",  list_large_files),
        "6": ("Manage Downloads folder",    clear_downloads),
        "7": ("Uninstall a third-party app",uninstall_app),
        "8": ("Run all safe cleanups (1-5)", None),
        "0": ("Exit",                       None),
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
