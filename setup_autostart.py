"""
JARVIS — setup_autostart.py
Set up JARVIS to auto-start on Windows boot.
Creates a shortcut in the Windows Startup folder.
"""

import os
import sys
from pathlib import Path


def setup_autostart():
    """Add JARVIS to Windows Startup folder."""
    jarvis_dir = Path(__file__).parent
    bat_file = jarvis_dir / "start_jarvis.bat"

    if not bat_file.exists():
        print(f"ERROR: {bat_file} not found!")
        return False

    # Windows Startup folder
    startup_folder = Path(os.getenv("APPDATA")) / r"Microsoft\Windows\Start Menu\Programs\Startup"

    if not startup_folder.exists():
        print(f"ERROR: Startup folder not found: {startup_folder}")
        return False

    # Create a .bat shortcut in Startup
    startup_bat = startup_folder / "JARVIS_AutoStart.bat"
    startup_bat.write_text(f'@echo off\ncd /d "{jarvis_dir}"\nstart /min python main.py --wake\n')

    print(f"✅ JARVIS auto-start enabled!")
    print(f"   Startup file: {startup_bat}")
    print(f"   Mode: Wake Word (background)")
    print(f"\n   JARVIS will now start automatically when Windows boots.")
    print(f"   To disable: delete {startup_bat}")
    return True


def remove_autostart():
    """Remove JARVIS from Windows Startup."""
    startup_folder = Path(os.getenv("APPDATA")) / r"Microsoft\Windows\Start Menu\Programs\Startup"
    startup_bat = startup_folder / "JARVIS_AutoStart.bat"

    if startup_bat.exists():
        startup_bat.unlink()
        print("✅ JARVIS auto-start disabled.")
    else:
        print("JARVIS auto-start was not enabled.")


def create_desktop_shortcut():
    """Create a desktop shortcut for JARVIS."""
    jarvis_dir = Path(__file__).parent
    desktop = Path(os.getenv("USERPROFILE")) / "Desktop"
    shortcut = desktop / "JARVIS.bat"

    shortcut.write_text(
        f'@echo off\ntitle JARVIS\ncd /d "{jarvis_dir}"\npython main.py --gui\n'
    )
    print(f"✅ Desktop shortcut created: {shortcut}")


if __name__ == "__main__":
    if "--remove" in sys.argv:
        remove_autostart()
    elif "--desktop" in sys.argv:
        create_desktop_shortcut()
    else:
        setup_autostart()
        create_desktop_shortcut()
        print("\n🚀 JARVIS is fully set up!")
