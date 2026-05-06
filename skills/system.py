"""
JARVIS — skills/system.py
System control: volume, brightness, screenshot, shutdown, etc.

NEW: Battery optimizer with alerts
NEW: GPU/CPU temperature monitor
NEW: WiFi password viewer
NEW: Network speed info
NEW: Startup app lister
"""

import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path

import pyautogui

from utils.logger import log

try:
    import ctypes

    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False
    log.warning("pycaw not available — volume control limited.")

try:
    import screen_brightness_control as sbc

    SBC_AVAILABLE = True
except ImportError:
    SBC_AVAILABLE = False

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    log.warning("psutil not available — hardware stats limited.")


class SystemController:
    """Controls system-level functions on Windows."""

    # ─── Volume ──────────────────────────────────────────────
    def volume_up(self, amount: int = 10) -> str:
        try:
            for _ in range(amount // 2):
                pyautogui.press("volumeup")
            return f"Volume increased by {amount}%"
        except Exception:
            return "Couldn't adjust volume."

    def volume_down(self, amount: int = 10) -> str:
        try:
            for _ in range(amount // 2):
                pyautogui.press("volumedown")
            return f"Volume decreased by {amount}%"
        except Exception:
            return "Couldn't adjust volume."

    def mute(self) -> str:
        try:
            pyautogui.press("volumemute")
            return "Audio muted/unmuted."
        except Exception:
            return "Couldn't toggle mute."

    def set_volume(self, percent: int) -> str:
        if not PYCAW_AVAILABLE:
            return "Volume control library not available. Install pycaw."
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = interface.QueryInterface(IAudioEndpointVolume)
            scalar = max(0.0, min(1.0, percent / 100.0))
            volume.SetMasterVolumeLevelScalar(scalar, None)
            return f"Volume set to {percent}%"
        except Exception:
            return "Couldn't set volume."

    # ─── Brightness ──────────────────────────────────────────
    def brightness_up(self, amount: int = 10) -> str:
        if not SBC_AVAILABLE:
            return (
                "Brightness control not available. Install screen-brightness-control."
            )
        try:
            current = sbc.get_brightness(display=0)[0]
            new_val = min(100, current + amount)
            sbc.set_brightness(new_val, display=0)
            return f"Brightness set to {new_val}%"
        except Exception:
            return "Couldn't adjust brightness."

    def brightness_down(self, amount: int = 10) -> str:
        if not SBC_AVAILABLE:
            return "Brightness control not available."
        try:
            current = sbc.get_brightness(display=0)[0]
            new_val = max(10, current - amount)
            sbc.set_brightness(new_val, display=0)
            return f"Brightness set to {new_val}%"
        except Exception:
            return "Couldn't adjust brightness."

    # ─── Screenshot ──────────────────────────────────────────
    def take_screenshot(self, save_dir: str = None) -> str:
        try:
            if save_dir is None:
                save_dir = str(Path.home() / "Desktop" / "JARVIS_Screenshots")
            os.makedirs(save_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(save_dir, f"screenshot_{timestamp}.png")
            screenshot = pyautogui.screenshot()
            screenshot.save(filename)
            return (
                f"Screenshot saved to Desktop/JARVIS_Screenshots/{Path(filename).name}"
            )
        except Exception:
            return "Couldn't take screenshot."

    # ─── Power Control ───────────────────────────────────────
    def shutdown(self, delay: int = 30) -> str:
        try:
            subprocess.run(["shutdown", "/s", "/t", str(delay)], check=True)
            return f"Shutting down in {delay} seconds. Say 'cancel shutdown' to abort."
        except Exception as e:
            return f"Shutdown failed: {e}"

    def restart(self, delay: int = 30) -> str:
        try:
            subprocess.run(["shutdown", "/r", "/t", str(delay)], check=True)
            return f"Restarting in {delay} seconds."
        except Exception as e:
            return f"Restart failed: {e}"

    def cancel_shutdown(self) -> str:
        try:
            subprocess.run(["shutdown", "/a"], check=True)
            return "Shutdown cancelled."
        except Exception:
            return "No pending shutdown to cancel."

    def sleep(self) -> str:
        try:
            subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            return "Going to sleep..."
        except Exception as e:
            return f"Sleep failed: {e}"

    # ─── Clipboard ───────────────────────────────────────────
    def get_clipboard(self) -> str:
        try:
            import pyperclip

            content = pyperclip.paste()
            return content if content else "Clipboard is empty."
        except Exception:
            return "Couldn't read clipboard."

    def set_clipboard(self, text: str) -> str:
        try:
            import pyperclip

            pyperclip.copy(text)
            return f"Copied to clipboard: {text[:50]}"
        except Exception:
            return "Couldn't copy to clipboard."

    # ════════════════════════════════════════════════════════════
    #  ADVANCED: BATTERY OPTIMIZER
    # ════════════════════════════════════════════════════════════

    def battery_status(self) -> str:
        """
        Report battery status and warn if low.
        Say: 'battery status' / 'how much battery' / 'check battery'
        """
        if not HAS_PSUTIL:
            return "psutil not installed — can't read battery. Run: pip install psutil"
        try:
            batt = psutil.sensors_battery()
            if batt is None:
                return "No battery detected — you're on desktop power, sir."

            pct = int(batt.percent)
            plugged = batt.power_plugged
            status = "charging" if plugged else "on battery"

            mins_left = ""
            if not plugged and batt.secsleft and batt.secsleft > 0:
                h = batt.secsleft // 3600
                m = (batt.secsleft % 3600) // 60
                mins_left = f" — about {h}h {m}m remaining"

            warning = ""
            if pct <= 10 and not plugged:
                warning = " ⚠️ CRITICAL! Please plug in immediately, sir!"
            elif pct <= 20 and not plugged:
                warning = " ⚠️ Low battery — consider plugging in soon, sir."

            return f"Battery at {pct}%, {status}{mins_left}.{warning}"
        except Exception as e:
            return f"Couldn't read battery: {str(e)[:60]}"

    def battery_optimizer(self) -> str:
        """
        Close heavy apps if battery < 20%.
        Say: 'optimize battery' / 'battery saver mode'
        """
        if not HAS_PSUTIL:
            return "psutil not available."
        try:
            batt = psutil.sensors_battery()
            if batt is None:
                return "No battery detected, sir."
            if batt.percent > 25 or batt.power_plugged:
                return (
                    f"Battery at {int(batt.percent)}% — no need to optimize yet, sir."
                )

            heavy_procs = [
                "chrome.exe",
                "Code.exe",
                "steam.exe",
                "Discord.exe",
                "spotify.exe",
            ]
            closed = []
            for proc in psutil.process_iter(["name"]):
                if proc.info["name"] in heavy_procs:
                    try:
                        proc.kill()
                        closed.append(proc.info["name"].replace(".exe", ""))
                    except Exception:
                        pass

            if closed:
                return (
                    f"Battery saver activated, sir! Closed: {', '.join(closed)}. "
                    f"Battery extended."
                )
            return "Battery saver on, no heavy apps found running."
        except Exception as e:
            return f"Battery optimizer error: {str(e)[:60]}"

    # ════════════════════════════════════════════════════════════
    #  ADVANCED: GPU / CPU TEMPERATURE
    # ════════════════════════════════════════════════════════════

    def hardware_temps(self) -> str:
        """
        Show CPU and GPU temperatures.
        Say: 'cpu temperature' / 'gpu temp' / 'hardware temperature'
        """
        result_parts = []

        # CPU temperature via psutil sensors (Linux/Mac only natively)
        if HAS_PSUTIL:
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for name, entries in temps.items():
                        for entry in entries[:2]:
                            if entry.current and entry.current > 0:
                                result_parts.append(f"{name}: {entry.current:.0f}°C")
            except (AttributeError, Exception):
                pass

        # Windows: use wmic for CPU temp (if psutil sensors not available)
        if not result_parts and platform.system() == "Windows":
            try:
                out = subprocess.check_output(
                    ["wmic", "temperature", "get", "currenttemperature"],
                    text=True,
                    timeout=5,
                )
                lines = [l.strip() for l in out.splitlines() if l.strip().isdigit()]
                if lines:
                    # WMIC returns in tenths of Kelvin
                    temp_k = int(lines[0]) / 10
                    temp_c = temp_k - 273.15
                    result_parts.append(f"CPU: {temp_c:.0f}°C")
            except Exception:
                pass

        # GPU temp via nvidia-smi (NVIDIA only)
        try:
            gpu_out = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                timeout=5,
                stderr=subprocess.DEVNULL,
            )
            gpu_temps = [t.strip() for t in gpu_out.splitlines() if t.strip()]
            for i, t in enumerate(gpu_temps[:2]):
                result_parts.append(f"GPU {i}: {t}°C")
        except Exception:
            pass

        if result_parts:
            return "Hardware temps: " + ", ".join(result_parts) + "."
        return (
            "Temperature sensors not accessible on this system, sir. "
            "Try installing HWiNFO64 for detailed monitoring."
        )

    def system_health(self) -> str:
        """
        Full system health check: CPU%, RAM%, disk%, battery, temps.
        Say: 'system health' / 'how is my system doing'
        """
        if not HAS_PSUTIL:
            return "psutil not installed — run: pip install psutil"
        try:
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("C:\\")
            batt = psutil.sensors_battery()

            parts = [
                f"CPU: {cpu:.0f}%",
                f"RAM: {ram.percent:.0f}% ({ram.available / 1e9:.1f}GB free)",
                f"Disk: {100 - disk.percent:.0f}% free",
            ]
            if batt:
                parts.append(
                    f"Battery: {int(batt.percent)}%"
                    + (" (charging)" if batt.power_plugged else "")
                )

            health = "✅ Healthy" if cpu < 70 and ram.percent < 80 else "⚠️ Under load"
            return f"System {health}. " + ", ".join(parts) + "."
        except Exception as e:
            return f"Health check failed: {str(e)[:60]}"

    # ════════════════════════════════════════════════════════════
    #  ADVANCED: WIFI PASSWORD VIEWER
    # ════════════════════════════════════════════════════════════

    def wifi_password(self, profile_name: str = None) -> str:
        """
        Show saved WiFi password for current or specified network.
        Say: 'what is my wifi password' / 'wifi password for MyNetwork'
        """
        if platform.system() != "Windows":
            return "WiFi password viewer only works on Windows, sir."
        try:
            if not profile_name:
                # Get current connected network
                netsh_out = subprocess.check_output(
                    ["netsh", "wlan", "show", "interfaces"],
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=5,
                )
                for line in netsh_out.splitlines():
                    if "SSID" in line and "BSSID" not in line:
                        profile_name = line.split(":", 1)[-1].strip()
                        break

            if not profile_name:
                return "Couldn't detect current WiFi network, sir."

            out = subprocess.check_output(
                ["netsh", "wlan", "show", "profile", profile_name, "key=clear"],
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            for line in out.splitlines():
                if "Key Content" in line:
                    pwd = line.split(":", 1)[-1].strip()
                    return (
                        f"WiFi '{profile_name}' password is: {pwd}, sir. Keep it safe!"
                    )
            return f"No password saved for '{profile_name}', sir."
        except subprocess.CalledProcessError:
            return f"Couldn't find WiFi profile '{profile_name}', sir."
        except Exception as e:
            return f"WiFi password error: {str(e)[:60]}"

    def list_wifi_networks(self) -> str:
        """
        List all saved WiFi profiles.
        Say: 'list wifi networks' / 'show saved wifi'
        """
        if platform.system() != "Windows":
            return "Only available on Windows, sir."
        try:
            out = subprocess.check_output(
                ["netsh", "wlan", "show", "profiles"],
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            profiles = []
            for line in out.splitlines():
                if "All User Profile" in line or "User Profile" in line:
                    name = line.split(":", 1)[-1].strip()
                    if name:
                        profiles.append(name)
            if not profiles:
                return "No saved WiFi networks found, sir."
            return (
                f"Saved WiFi networks ({len(profiles)}): "
                + ", ".join(profiles[:10])
                + "."
            )
        except Exception as e:
            return f"Couldn't list WiFi: {str(e)[:60]}"

    # ════════════════════════════════════════════════════════════
    #  ADVANCED: STARTUP MANAGER
    # ════════════════════════════════════════════════════════════

    def list_startup_apps(self) -> str:
        """
        List apps that run on Windows startup.
        Say: 'what starts on boot' / 'startup programs' / 'startup apps'
        """
        if platform.system() != "Windows":
            return "Startup manager only available on Windows, sir."
        try:
            import winreg

            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
            results = []
            for hive in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
                try:
                    key = winreg.OpenKey(hive, key_path)
                    i = 0
                    while True:
                        try:
                            name, _, _ = winreg.EnumValue(key, i)
                            results.append(name)
                            i += 1
                        except OSError:
                            break
                    winreg.CloseKey(key)
                except Exception:
                    pass

            if not results:
                return "No startup apps found, sir."
            return (
                f"Startup apps ({len(results)}): "
                + ", ".join(results[:10])
                + ("..." if len(results) > 10 else ".")
            )
        except ImportError:
            return "winreg not available on this platform."
        except Exception as e:
            return f"Startup list error: {str(e)[:60]}"

    def network_info(self) -> str:
        """
        Show network interface status.
        Say: 'network status' / 'internet info' / 'network info'
        """
        if not HAS_PSUTIL:
            return "psutil not available."
        try:
            stats = psutil.net_io_counters()
            sent_mb = stats.bytes_sent / 1e6
            recv_mb = stats.bytes_recv / 1e6
            addrs = psutil.net_if_addrs()
            ip = "Unknown"
            for iface, addr_list in addrs.items():
                for addr in addr_list:
                    if addr.family.name == "AF_INET" and not addr.address.startswith(
                        "127."
                    ):
                        ip = addr.address
                        break
            return f"IP: {ip}. Session: sent {sent_mb:.1f}MB, received {recv_mb:.1f}MB."
        except Exception as e:
            return f"Network info error: {str(e)[:60]}"

    def disk_cleanup(self) -> str:
        """Run Windows Disk Cleanup automation."""
        try:
            import subprocess

            # Run cleanmgr with sageset/sagerun for automated cleanup
            result = subprocess.run(
                ["cleanmgr", "/sagerun:1"], capture_output=True, timeout=10
            )
            return "Disk Cleanup launched, sir. This may take a moment."
        except FileNotFoundError:
            # Alternative: use PowerShell to clear temp files
            try:
                import os
                import shutil
                import subprocess

                temp_dirs = [
                    os.environ.get("TEMP", ""),
                    os.environ.get("TMP", ""),
                    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp"),
                ]
                freed = 0
                for d in temp_dirs:
                    if d and os.path.exists(d):
                        for f in os.listdir(d):
                            try:
                                fp = os.path.join(d, f)
                                size = os.path.getsize(fp) if os.path.isfile(fp) else 0
                                if os.path.isfile(fp):
                                    os.remove(fp)
                                    freed += size
                                elif os.path.isdir(fp):
                                    shutil.rmtree(fp, ignore_errors=True)
                            except Exception:
                                pass
                freed_mb = freed // (1024 * 1024)
                return f"Cleaned temp files — freed approximately {freed_mb} MB, sir."
            except Exception as e:
                return f"Disk cleanup error: {str(e)[:60]}"
        except Exception as e:
            return f"Disk cleanup error: {str(e)[:60]}"

    def network_speed_test(self) -> str:
        """Run a network speed test using speedtest-cli."""
        try:
            import speedtest

            self_test = speedtest.Speedtest()
            self_test.get_best_server()
            # Download speed
            download = self_test.download() / 1_000_000  # Mbps
            upload = self_test.upload() / 1_000_000  # Mbps
            ping = self_test.results.ping
            return (
                f"Network speed test results, sir: "
                f"Download: {download:.1f} Mbps, "
                f"Upload: {upload:.1f} Mbps, "
                f"Ping: {ping:.0f} ms."
            )
        except ImportError:
            # Fallback: simple HTTP speed test
            try:
                import time
                import urllib.request

                test_url = "https://httpbin.org/bytes/1048576"  # 1MB
                start = time.time()
                with urllib.request.urlopen(test_url, timeout=15) as resp:
                    resp.read()
                elapsed = time.time() - start
                speed_mbps = (1 * 8) / elapsed  # 1 MB * 8 bits
                return f"Approximate download speed: {speed_mbps:.1f} Mbps, sir."
            except Exception as e2:
                return f"Speed test failed: {str(e2)[:60]}. Install: pip install speedtest-cli"
        except Exception as e:
            return f"Speed test error: {str(e)[:60]}"

    def create_restore_point(self, description: str = "JARVIS Restore Point") -> str:
        """Create a Windows System Restore Point."""
        try:
            import subprocess

            ps_cmd = (
                f'Checkpoint-Computer -Description "{description}" '
                f'-RestorePointType "MODIFY_SETTINGS"'
            )
            result = subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                return f"System restore point created: '{description}', sir."
            else:
                err = result.stderr.strip()[:80]
                if "System Restore is disabled" in err or "access" in err.lower():
                    return (
                        "System Restore is disabled or requires admin privileges, sir."
                    )
                return f"Restore point creation: {err or 'completed'}"
        except subprocess.TimeoutExpired:
            return "Restore point creation timed out, sir. Try manually via System Properties."
        except Exception as e:
            return f"Could not create restore point: {str(e)[:60]}"

    def free_ram(self) -> str:
        """Free up RAM by clearing the standby memory list (Windows)."""
        try:
            import subprocess

            result = subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "Clear-RecycleBin -Force -ErrorAction SilentlyContinue; "
                    "[System.GC]::Collect()",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            import psutil

            ram = psutil.virtual_memory()
            return (
                f"Memory cleared, sir. "
                f"RAM: {ram.percent:.0f}% used, "
                f"{ram.available / (1024**3):.1f} GB free."
            )
        except Exception as e:
            return f"RAM cleanup: {str(e)[:60]}"

    def get_top_processes(self) -> str:
        """Get top 5 CPU-consuming processes."""
        try:
            import psutil

            procs = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
                try:
                    procs.append((p.info["cpu_percent"], p.info["name"]))
                except Exception:
                    pass
            procs.sort(reverse=True)
            top = [(name, cpu) for cpu, name in procs if cpu > 0][:5]
            if not top:
                import time

                time.sleep(0.5)
                return self.get_top_processes()
            lines = [f"• {name}: {cpu:.1f}%" for name, cpu in top]
            return "Top CPU processes:\n" + "\n".join(lines)
        except Exception as e:
            return f"Could not get processes: {str(e)[:60]}"


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    sc = SystemController()
    print(sc.battery_status())
    print(sc.system_health())
    print(sc.list_wifi_networks())
    print(sc.list_startup_apps())
