"""
JARVIS — utils/registry_helper.py
Windows Registry helper — locate installed applications without hardcoded paths.

Queries the Windows registry to find:
  - Application installation paths
  - Executable locations
  - Application metadata

Replaces hardcoded paths like: C:/Users/srini/AppData/...
"""

import winreg
from pathlib import Path
from utils.logger import log
from typing import Optional


def get_app_from_registry(app_name: str) -> Optional[str]:
    """
    Find application installation path from Windows Registry.

    Searches HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall
    for matching application and returns its installation path.

    Args:
        app_name: Application name to search for (case-insensitive)

    Returns:
        Path to application executable, or None if not found

    Example:
        >>> get_app_from_registry("Spotify")
        "C:/Users/.../AppData/Roaming/Spotify/Spotify.exe"
    """
    app_lower = app_name.lower().strip()

    # Common registry paths for installed applications
    registry_paths = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ]

    try:
        for reg_path in registry_paths:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                    # Iterate through all installed applications
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            subkey_path = f"{reg_path}\\{subkey_name}"

                            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey_path) as subkey:
                                try:
                                    display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                    display_name_lower = display_name.lower()

                                    # Check if this app matches what we're looking for
                                    if app_lower in display_name_lower or display_name_lower in app_lower:
                                        # Try to get InstallLocation first
                                        try:
                                            install_loc = winreg.QueryValueEx(
                                                subkey, "InstallLocation"
                                            )[0]
                                            if install_loc:
                                                exe_name = _get_executable_name(display_name)
                                                exe_path = Path(install_loc) / exe_name
                                                if exe_path.exists():
                                                    log.debug(f"Found {app_name} at {exe_path}")
                                                    return str(exe_path)
                                        except Exception:
                                            pass

                                        # Try UninstallString (contains path)
                                        try:
                                            uninstall = winreg.QueryValueEx(
                                                subkey, "UninstallString"
                                            )[0]
                                            exe_path = _extract_exe_from_uninstall_string(uninstall)
                                            if exe_path and Path(exe_path).exists():
                                                log.debug(f"Found {app_name} via uninstall at {exe_path}")
                                                return exe_path
                                        except Exception:
                                            pass

                                except Exception:
                                    pass

                            i += 1
                        except WindowsError:
                            break

            except Exception:
                continue

    except Exception as e:
        log.debug(f"Registry lookup failed for {app_name}: {e}")

    return None


def _get_executable_name(app_display_name: str) -> str:
    """Guess executable name from app display name."""
    # Common patterns
    name = app_display_name.strip()

    # Remove version numbers, etc
    import re
    name = re.split(r'\d+\.\d+', name)[0].strip()

    # Convert to exe filename
    exe_name = name.replace(" ", "").lower() + ".exe"
    return exe_name


def _extract_exe_from_uninstall_string(uninstall_str: str) -> Optional[str]:
    """Extract executable path from uninstall string."""
    if not uninstall_str:
        return None

    # Uninstall strings often contain: C:\path\to\uninstall.exe /S /D=C:\path\to\app
    # Or: MsiExec.exe /X{GUID}
    # Or: C:\path\to\app\uninstall.exe

    uninstall_str = uninstall_str.strip().strip('"')

    # Try to extract path before parameters
    parts = uninstall_str.split(" /")
    if parts:
        potential_path = parts[0].strip('"')

        # If it's an uninstaller, try to get the app directory
        if potential_path.lower().endswith(("uninstall.exe", "uninst.exe")):
            app_dir = str(Path(potential_path).parent)
            # Look for main executable in app directory
            for exe_name in ["spotify.exe", "chrome.exe", "firefox.exe", "notepad++.exe"]:
                exe_path = Path(app_dir) / exe_name
                if exe_path.exists():
                    return str(exe_path)
            # Return the app directory path
            return app_dir

    return None


def get_app_list() -> list[dict]:
    """
    Get list of all installed applications from registry.

    Returns:
        List of dicts with 'name' and 'install_path' keys
    """
    apps = []

    try:
        reg_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkey_path = f"{reg_path}\\{subkey_name}"

                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey_path) as subkey:
                        try:
                            display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                            try:
                                install_loc = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                                if install_loc:
                                    apps.append({
                                        "name": display_name,
                                        "path": install_loc
                                    })
                            except Exception:
                                pass
                        except Exception:
                            pass

                    i += 1
                except WindowsError:
                    break

    except Exception as e:
        log.debug(f"Failed to get app list: {e}")

    return apps


def resolve_app_path(app_name: str) -> Optional[str]:
    """
    Resolve application path using multiple strategies.

    1. Try registry lookup
    2. Try environment PATH
    3. Return None

    Args:
        app_name: Name of application to locate

    Returns:
        Full path to executable, or None if not found
    """
    # First try registry
    result = get_app_from_registry(app_name)
    if result:
        return result

    # Then try PATH environment variable
    import shutil
    exe_name = app_name.lower()
    if not exe_name.endswith(".exe"):
        exe_name += ".exe"

    result = shutil.which(exe_name)
    if result:
        return result

    log.debug(f"Could not locate {app_name} in registry or PATH")
    return None
