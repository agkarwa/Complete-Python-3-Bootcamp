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
    result = run_adb(["shell", "df", "/data"])
    print("\n--- Storage Usage ---")
    print(result.stdout)


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
