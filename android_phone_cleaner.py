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


def _is_rooted():
    """Return True if the device has an accessible su binary."""
    res = run_adb(["shell", "su -c 'echo ok' 2>/dev/null"])
    return res.stdout.strip() == "ok"


def _total_cache_kb_from_diskstats():
    """
    Read aggregate cache size from dumpsys diskstats — works without root.
    Returns total cache KB, or 0 if unavailable.
    """
    res = run_adb(["shell", "dumpsys diskstats"])
    for line in res.stdout.splitlines():
        # Line format: "App Cache: 512345 KB"  or "Cache-Free: 512345"
        lower = line.lower()
        if "cache" in lower and "kb" in lower:
            parts = line.split()
            for p in parts:
                if p.isdigit():
                    return int(p)
    return 0


def list_all_app_caches():
    print("\n" + "═" * 60)
    print("  APP CACHE LIST")
    print("═" * 60)

    rooted = _is_rooted()
    print(f"  Root access : {'YES — per-app sizes and targeted clean available' if rooted else 'NO  — sizes via diskstats only; clean is system-wide'}")

    # ── Package list ─────────────────────────────────────────
    print("  Fetching installed packages...")
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

    # ── Cache sizes ──────────────────────────────────────────
    size_map = {}

    if rooted:
        # Root: du gives exact per-app cache sizes
        print(f"  Scanning cache for {len(all_pkgs)} apps via root du...")
        for path_prefix in ["/data/data", "/data/user/0"]:
            res = run_adb(["shell", f"su -c 'du -sk {path_prefix}/*/cache 2>/dev/null'"])
            for line in res.stdout.strip().splitlines():
                parts = line.split(None, 1)
                if len(parts) == 2:
                    try:
                        kb = int(parts[0])
                    except ValueError:
                        continue
                    pkg = parts[1].replace(f"{path_prefix}/", "").replace("/cache", "").strip()
                    if pkg not in size_map or size_map[pkg] == 0:
                        size_map[pkg] = kb
    else:
        # No root: du on /data/data is blocked. Get total from diskstats only.
        print("  No root — per-app sizes unavailable. Reading total from dumpsys diskstats...")

    # ── Build rows ───────────────────────────────────────────
    rows = []
    for pkg in all_pkgs:
        kb = size_map.get(pkg, 0)
        kind = "3rd-party" if pkg in third_pkgs else "system"
        rows.append((kb, pkg, kind))

    rows.sort(key=lambda r: r[0], reverse=True)

    total_cache_kb = sum(r[0] for r in rows)
    if not rooted:
        total_cache_kb = _total_cache_kb_from_diskstats()

    nonzero = [r for r in rows if r[0] > 0]

    # ── Filter (only meaningful with root) ───────────────────
    if rooted and nonzero:
        print("\n  Filter:  [1] All apps   [2] Third-party only   [3] Non-zero only")
        filt = input("  Choice (default 3): ").strip() or "3"
        if filt == "2":
            rows = [r for r in rows if r[2] == "3rd-party"]
        elif filt == "3":
            rows = nonzero
    else:
        # Without root all sizes are 0 — show package list without size column
        rows = sorted(rows, key=lambda r: (r[2] != "3rd-party", r[1]))

    # ── Table ────────────────────────────────────────────────
    print()
    if rooted:
        print(f"  {'#':>4}  {'Package':<45} {'Type':<10} {'Cache':>9}")
        print("  " + "-" * 72)
        for i, (kb, pkg, kind) in enumerate(rows, 1):
            size_str = _human(kb) if kb > 0 else "  —"
            display = pkg if len(pkg) <= 45 else pkg[:42] + "..."
            print(f"  {i:>4}  {display:<45} {kind:<10} {size_str:>9}")
    else:
        print(f"  {'#':>4}  {'Package':<50} {'Type':<10}")
        print("  " + "-" * 67)
        for i, (kb, pkg, kind) in enumerate(rows, 1):
            display = pkg if len(pkg) <= 50 else pkg[:47] + "..."
            print(f"  {i:>4}  {display:<50} {kind:<10}")

    # ── Summary ──────────────────────────────────────────────
    print("  " + "-" * (72 if rooted else 67))
    print(f"\n  Total apps : {len(all_pkgs)}  "
          f"({len(third_pkgs)} third-party, {len(system_pkgs)} system)")
    print(f"  Total cache: {_human(total_cache_kb)}"
          + ("  (from diskstats — system total)" if not rooted else ""))
    print("═" * 60)

    # ── Clean prompt ─────────────────────────────────────────
    print("\n  Clean options:")
    if rooted:
        print("  [A] Clean ALL shown caches        (root rm — precise, per-app)")
        print("  [S] Select specific apps by number (e.g. 1,3,5-7)")
    else:
        print("  [A] Clean ALL app caches")
        print("      (system-wide trim-caches — Android frees cache for all apps)")
        print("      Per-app selection is NOT possible without root.")
    print("  [N] Do nothing")
    action = input("\n  Choice: ").strip().upper()

    if action not in ("A", "S"):
        return

    if not rooted:
        # Non-root path: one system-wide trim-caches call
        if action != "A":
            print("  Per-app selection requires root. Run: adb root")
            return
        before_kb = total_cache_kb
        confirm = input(f"\n  Clear all caches (~{_human(before_kb)})? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("  Cancelled.")
            return
        # Request Android to free all known cache (pass a very large number so
        # it drains as much cache as possible, not just a small slice).
        want_bytes = max(before_kb * 1024 * 2, 512 * 1024 * 1024)  # at least 512 MB
        res = run_adb(["shell", f"cmd package trim-caches {want_bytes}"])
        after_kb = _total_cache_kb_from_diskstats()
        freed_kb = max(before_kb - after_kb, 0)
        print(f"\n  trim-caches sent to Android.")
        print(f"  Cache before : {_human(before_kb)}")
        print(f"  Cache after  : {_human(after_kb)}")
        print(f"  Freed        : {_human(freed_kb)}")
        print("\n  Note: Android controls how much it actually frees. Apps that are")
        print("  actively running may retain some cache until they're closed.")
        return

    # Rooted path: per-app rm
    targets = []
    if action == "A":
        targets = [r for r in rows if r[0] > 0]
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
            print("  No valid entries with cache selected.")
            return

    freed_kb = sum(r[0] for r in targets)
    confirm = input(f"\n  Clear cache for {len(targets)} app(s) (~{_human(freed_kb)})? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("  Cancelled.")
        return

    print()
    ok = fail = 0
    for kb, pkg, kind in targets:
        res = run_adb(["shell", f"su -c 'rm -rf /data/data/{pkg}/cache/* /data/user/0/{pkg}/cache/* 2>/dev/null'; echo $?"])
        success = res.stdout.strip().splitlines()[-1] == "0" if res.stdout.strip() else False
        status = "OK" if success else "FAIL"
        if success:
            ok += 1
        else:
            fail += 1
        display = pkg if len(pkg) <= 45 else pkg[:42] + "..."
        print(f"  [{status}] {display:<45} {_human(kb):>9}")

    print("\n" + "═" * 60)
    print(f"  Cleared : {ok}   Failed : {fail}")
    print(f"  Space freed (estimated) : {_human(freed_kb)}")
    print("═" * 60)


def clear_app_caches():
    print("\n--- Clearing App Caches ---")
    rooted = _is_rooted()
    print(f"    Root: {'YES — per-app rm' if rooted else 'NO  — system-wide trim-caches'}\n")

    before_kb = _total_cache_kb_from_diskstats()

    if rooted:
        result = run_adb(["shell", "pm", "list", "packages"])
        packages = [l.replace("package:", "").strip() for l in result.stdout.splitlines() if l.startswith("package:")]
        print(f"Clearing cache for {len(packages)} apps via root...")
        ok = fail = 0
        for pkg in packages:
            res = run_adb(["shell", f"su -c 'rm -rf /data/data/{pkg}/cache/* /data/user/0/{pkg}/cache/* 2>/dev/null'; echo $?"])
            if res.stdout.strip().splitlines()[-1] == "0":
                ok += 1
            else:
                fail += 1
        print(f"Done — cleared: {ok}  failed: {fail}")
    else:
        # Non-root: one system-wide trim-caches draining as much as possible
        want_bytes = max(before_kb * 1024 * 2, 512 * 1024 * 1024)
        print(f"Sending trim-caches to Android (requesting {_human(want_bytes // 1024)} freed)...")
        run_adb(["shell", f"cmd package trim-caches {want_bytes}"])
        print("Done.")

    after_kb = _total_cache_kb_from_diskstats()
    freed_kb = max(before_kb - after_kb, 0)
    print(f"\nCache before : {_human(before_kb)}")
    print(f"Cache after  : {_human(after_kb)}")
    print(f"Freed        : {_human(freed_kb)}")


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
