"""
JARVIS — skills/files.py
File and folder operations by voice command.
Advanced: fuzzy search, recent files, zip/unzip, auto-organize downloads, duplicate finder.
"""

import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from utils.logger import log

# ─── Recent files tracker (in-memory) ──────────────────────────
_RECENT_FILES: list[dict] = []  # [{"path": str, "time": str}]
_MAX_RECENT = 10


def _track_recent(path: Path):
    """Track recently opened/created files."""
    entry = {"path": str(path), "time": datetime.now().strftime("%H:%M")}
    # Remove duplicate if exists
    _RECENT_FILES[:] = [r for r in _RECENT_FILES if r["path"] != str(path)]
    _RECENT_FILES.insert(0, entry)
    if len(_RECENT_FILES) > _MAX_RECENT:
        _RECENT_FILES.pop()


def _open_cross_platform(path: Path) -> bool:
    """Open a file with its default app — works on Windows, Mac, Linux."""
    try:
        if platform.system() == "Windows":
            os.startfile(str(path))
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception as e:
        log.error(f"Cross-platform open error: {e}")
        return False


class FileSkill:
    """Create, read, move, delete files and folders. With smart fuzzy search."""

    def create_file(self, filename: str, content: str = "", folder: str = None) -> str:
        """Create a new file with optional content."""
        try:
            base = Path(folder) if folder else Path.home() / "Desktop"
            base.mkdir(parents=True, exist_ok=True)

            filepath = base / filename
            # FIX: encoding fallback for binary-safe write
            try:
                filepath.write_text(content, encoding="utf-8")
            except UnicodeEncodeError:
                filepath.write_text(content, encoding="utf-8", errors="replace")

            _track_recent(filepath)
            log.info(f"File created: {filepath}")
            return f"Created file '{filename}' on Desktop."
        except Exception as e:
            log.error(f"File create error: {e}")
            return f"Couldn't create file: {str(e)[:80]}"

    def read_file(self, filepath: str) -> str:
        """Read and return the contents of a file."""
        try:
            path = Path(filepath)
            if not path.exists():
                return f"File not found: {filepath}"

            # Try UTF-8 first, then latin-1 for binary/legacy files
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = path.read_text(encoding="latin-1", errors="replace")

            _track_recent(path)
            if len(content) > 1000:
                return content[:1000] + "\n\n[... file truncated at 1000 chars]"
            return content
        except Exception as e:
            log.error(f"File read error: {e}")
            return f"Couldn't read file: {str(e)[:80]}"

    def delete_file(self, filepath: str) -> str:
        """Delete a file or folder."""
        try:
            path = Path(filepath)
            if not path.exists():
                return f"File not found: {filepath}"

            if path.is_file():
                path.unlink()
                return f"Deleted file: {path.name}"
            elif path.is_dir():
                shutil.rmtree(path)
                return f"Deleted folder: {path.name}"
        except Exception as e:
            log.error(f"File delete error: {e}")
            return f"Couldn't delete: {str(e)[:80]}"

    def move_file(self, src: str, dst: str) -> str:
        """Move a file from src to dst."""
        try:
            shutil.move(src, dst)
            return f"Moved '{Path(src).name}' to '{dst}'"
        except Exception as e:
            return f"Couldn't move file: {str(e)[:80]}"

    def copy_file(self, src: str, dst: str) -> str:
        """Copy a file from src to dst."""
        try:
            shutil.copy2(src, dst)
            return f"Copied '{Path(src).name}' to '{dst}'"
        except Exception as e:
            return f"Couldn't copy file: {str(e)[:80]}"

    def open_file(self, filepath: str) -> str:
        """Open a file with its default application (cross-platform)."""
        try:
            path = Path(filepath)
            if not path.exists():
                # Try Desktop
                desktop = Path.home() / "Desktop" / filepath
                if desktop.exists():
                    path = desktop
                else:
                    # Fuzzy search for the file
                    result = self.fuzzy_search(filepath)
                    if result.startswith("Found"):
                        return result + "\n(Say the exact path to open it)"
                    return f"File not found: {filepath}"

            if _open_cross_platform(path):
                _track_recent(path)
                return f"Opening {path.name}..."
            return f"Couldn't open {path.name}."
        except Exception as e:
            return f"Couldn't open file: {str(e)[:80]}"

    def search_files(self, name: str, search_dir: str = None) -> str:
        """Search for files by name (exact match)."""
        try:
            base = Path(search_dir) if search_dir else Path.home()
            matches = list(base.rglob(f"*{name}*"))[:10]

            if not matches:
                return f"No files found matching '{name}'."

            result = f"Found {len(matches)} file(s):\n"
            for m in matches:
                result += f"• {m}\n"
            return result.strip()
        except Exception as e:
            return f"Search failed: {str(e)[:80]}"

    def fuzzy_search(self, name: str, search_dir: str = None) -> str:
        """
        Smart fuzzy search — finds files even with typos or partial names.
        Say: 'find my resume' → finds 'Resume_2024.pdf' even if spelled wrong.
        """
        try:
            base = Path(search_dir) if search_dir else Path.home()
            name_lower = name.lower()

            scored = []
            search_dirs = [
                Path.home() / "Desktop",
                Path.home() / "Documents",
                Path.home() / "Downloads",
                Path.home(),
            ]
            if search_dir:
                search_dirs = [base]

            for sdir in search_dirs:
                if not sdir.exists():
                    continue
                for p in sdir.rglob("*"):
                    if p.is_file():
                        stem_lower = p.stem.lower()
                        score = SequenceMatcher(None, name_lower, stem_lower).ratio()
                        # Bonus if name is a substring
                        if name_lower in stem_lower or stem_lower in name_lower:
                            score = max(score, 0.85)
                        if score > 0.4:
                            scored.append((score, p))

            if not scored:
                return f"No files found matching '{name}', sir."

            scored.sort(key=lambda x: -x[0])
            top = scored[:5]
            result = (
                f"Found {len(top)} match{'es' if len(top) > 1 else ''} for '{name}':\n"
            )
            for score, p in top:
                result += f"• {p.name}  ({p.parent})\n"
            return result.strip()
        except Exception as e:
            log.error(f"Fuzzy search error: {e}")
            return f"Search failed: {str(e)[:80]}"

    def recent_files(self) -> str:
        """Show recently opened/created files."""
        if not _RECENT_FILES:
            return "No recent files tracked yet, sir."
        result = f"Recent {len(_RECENT_FILES)} files:\n"
        for r in _RECENT_FILES:
            result += f"• {Path(r['path']).name}  [{r['time']}]\n"
        return result.strip()

    def list_desktop(self) -> str:
        """List files and folders on Desktop."""
        try:
            desktop = Path.home() / "Desktop"
            items = list(desktop.iterdir())
            if not items:
                return "Desktop is empty."

            result = f"Desktop has {len(items)} items:\n"
            for item in items[:15]:
                kind = "📁" if item.is_dir() else "📄"
                result += f"{kind} {item.name}\n"
            return result.strip()
        except Exception as e:
            return f"Couldn't list desktop: {str(e)[:80]}"

    def create_folder(self, name: str, parent: str = None) -> str:
        """Create a new folder."""
        try:
            base = Path(parent) if parent else Path.home() / "Desktop"
            folder = base / name
            folder.mkdir(parents=True, exist_ok=True)
            return f"Created folder '{name}' at {base}"
        except Exception as e:
            return f"Couldn't create folder: {str(e)[:80]}"

    def write_note(self, content: str) -> str:
        """Quick note: create a timestamped text note on Desktop."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"JARVIS_note_{timestamp}.txt"
        return self.create_file(filename, content)

    # ════════════════════════════════════════════════════════════
    #  ADVANCED: ZIP / UNZIP
    # ════════════════════════════════════════════════════════════

    def zip_file(self, filepath: str, output_name: str = None) -> str:
        """
        Compress a file or folder to zip.
        Say: 'zip my downloads folder' / 'compress project folder'
        """
        try:
            src = Path(filepath)
            if not src.exists():
                # Try Desktop
                src = Path.home() / "Desktop" / filepath
                if not src.exists():
                    return f"File/folder not found: {filepath}"

            out_name = output_name or f"{src.stem}_jarvis"
            out_dir = src.parent
            out_zip = out_dir / f"{out_name}.zip"

            if src.is_dir():
                shutil.make_archive(
                    str(out_dir / out_name), "zip", str(src.parent), str(src.name)
                )
            else:
                with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(src, src.name)

            size_mb = out_zip.stat().st_size / (1024 * 1024)
            return f"Zipped '{src.name}' → '{out_zip.name}' ({size_mb:.1f} MB), sir."
        except Exception as e:
            log.error(f"Zip error: {e}")
            return f"Couldn't zip: {str(e)[:80]}"

    def unzip_file(self, filepath: str, dest_folder: str = None) -> str:
        """
        Extract a zip file.
        Say: 'unzip the archive' / 'extract this zip file'
        """
        try:
            src = Path(filepath)
            if not src.exists():
                src = Path.home() / "Desktop" / filepath
                if not src.exists():
                    return f"Zip file not found: {filepath}"

            dest = Path(dest_folder) if dest_folder else src.parent / src.stem
            dest.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(src, "r") as zf:
                zf.extractall(dest)
                files = len(zf.namelist())

            return f"Extracted {files} file(s) to '{dest.name}', sir."
        except Exception as e:
            log.error(f"Unzip error: {e}")
            return f"Couldn't extract: {str(e)[:80]}"

    # ════════════════════════════════════════════════════════════
    #  ADVANCED: AUTO-ORGANIZE DOWNLOADS
    # ════════════════════════════════════════════════════════════

    def organize_downloads(self) -> str:
        """
        Auto-sort Downloads folder into subfolders by file type.
        Say: 'organize my downloads' / 'sort my downloads folder'
        """
        try:
            dl = Path.home() / "Downloads"
            if not dl.exists():
                return "Downloads folder not found, sir."

            categories = {
                "Images": [
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".gif",
                    ".bmp",
                    ".svg",
                    ".webp",
                    ".heic",
                ],
                "Videos": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"],
                "Music": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"],
                "Documents": [
                    ".pdf",
                    ".doc",
                    ".docx",
                    ".xls",
                    ".xlsx",
                    ".ppt",
                    ".pptx",
                    ".txt",
                    ".odt",
                ],
                "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
                "Code": [
                    ".py",
                    ".js",
                    ".html",
                    ".css",
                    ".ts",
                    ".json",
                    ".yaml",
                    ".sql",
                ],
                "Executables": [".exe", ".msi", ".apk", ".dmg"],
            }

            moved = 0
            for item in dl.iterdir():
                if item.is_file():
                    ext = item.suffix.lower()
                    dest_cat = "Others"
                    for cat, exts in categories.items():
                        if ext in exts:
                            dest_cat = cat
                            break
                    dest_dir = dl / dest_cat
                    dest_dir.mkdir(exist_ok=True)
                    try:
                        shutil.move(str(item), str(dest_dir / item.name))
                        moved += 1
                    except Exception:
                        pass

            return (
                f"Organized {moved} file(s) in Downloads into categories, sir. "
                f"Images, Videos, Documents, Code and more!"
            )
        except Exception as e:
            log.error(f"Organize downloads error: {e}")
            return f"Couldn't organize downloads: {str(e)[:80]}"

    # ════════════════════════════════════════════════════════════
    #  ADVANCED: DUPLICATE FINDER
    # ════════════════════════════════════════════════════════════

    def find_duplicates(self, search_dir: str = None) -> str:
        """
        Find duplicate files by comparing MD5 hash.
        Say: 'find duplicate files' / 'find duplicates in downloads'
        """
        try:
            base = Path(search_dir) if search_dir else Path.home() / "Downloads"
            if not base.exists():
                return f"Folder not found: {base}"

            hashes: dict[str, list[Path]] = {}
            for path in base.rglob("*"):
                if path.is_file() and path.stat().st_size > 0:
                    try:
                        md5 = hashlib.md5(path.read_bytes()).hexdigest()
                        hashes.setdefault(md5, []).append(path)
                    except Exception:
                        pass

            dupes = {h: paths for h, paths in hashes.items() if len(paths) > 1}
            if not dupes:
                return "No duplicate files found, sir. All clean!"

            total = sum(len(p) - 1 for p in dupes.values())
            result = f"Found {len(dupes)} duplicate group(s), {total} extra copies:\n"
            for i, (_, paths) in enumerate(list(dupes.items())[:5]):
                result += f"• {paths[0].name} ({len(paths)} copies)\n"
            if len(dupes) > 5:
                result += f"  ...and {len(dupes) - 5} more groups.\n"
            result += "Say 'delete duplicates' to clean them up."
            return result.strip()
        except Exception as e:
            log.error(f"Duplicate find error: {e}")
            return f"Duplicate search failed: {str(e)[:80]}"

    # ════════════════════════════════════════════════════════════
    #  ADVANCED: ENCRYPTION
    # ════════════════════════════════════════════════════════════

    def encrypt_file(self, filepath: str, password: str = None) -> str:
        """Encrypt a file using Fernet symmetric encryption."""
        try:
            import base64
            import hashlib
            from pathlib import Path as _Path

            from cryptography.fernet import Fernet

            path = _Path(filepath)
            if not path.exists():
                # Try Desktop
                path = _Path.home() / "Desktop" / filepath
            if not path.exists():
                return f"File not found: {filepath}, sir."
            # Derive key from password or generate random
            if password:
                key = base64.urlsafe_b64encode(
                    hashlib.sha256(password.encode()).digest()
                )
            else:
                key = Fernet.generate_key()
                key_file = path.with_suffix(".key")
                key_file.write_bytes(key)
            fernet = Fernet(key)
            data = path.read_bytes()
            encrypted = fernet.encrypt(data)
            enc_path = path.with_suffix(path.suffix + ".enc")
            enc_path.write_bytes(encrypted)
            if not password:
                return (
                    f"File encrypted: {enc_path.name}. "
                    f"Key saved to: {path.stem}.key — keep it safe, sir!"
                )
            return f"File encrypted with password: {enc_path.name}, sir."
        except ImportError:
            return "Encryption library not installed. Run: pip install cryptography"
        except Exception as e:
            return f"Encryption failed: {str(e)[:60]}"

    def decrypt_file(self, filepath: str, password: str = None) -> str:
        """Decrypt a previously encrypted file."""
        # Stage 1: resolve imports — catch missing library before InvalidToken is used
        try:
            import base64
            import hashlib
            from pathlib import Path as _Path

            from cryptography.fernet import Fernet, InvalidToken
        except ImportError:
            return "Encryption library not installed. Run: pip install cryptography"
        # Stage 2: actual decryption — InvalidToken is guaranteed to be bound here
        try:
            path = _Path(filepath)
            if not path.exists():
                path = _Path.home() / "Desktop" / filepath
            if not path.exists():
                return f"Encrypted file not found: {filepath}, sir."
            # Load key
            if password:
                key = base64.urlsafe_b64encode(
                    hashlib.sha256(password.encode()).digest()
                )
            else:
                key_path = path.with_suffix("").with_suffix(".key")
                if not key_path.exists():
                    return (
                        f"Key file not found: {key_path.name}. Provide password, sir."
                    )
                key = key_path.read_bytes()
            fernet = Fernet(key)
            data = path.read_bytes()
            decrypted = fernet.decrypt(data)
            # Remove .enc extension
            out_path = (
                path.with_suffix("")
                if path.suffix == ".enc"
                else path.with_suffix(".decrypted")
            )
            out_path.write_bytes(decrypted)
            return f"File decrypted: {out_path.name}, sir."
        except InvalidToken:
            return "Wrong password or corrupted file, sir."
        except Exception as e:
            return f"Decryption failed: {str(e)[:60]}"

    # ════════════════════════════════════════════════════════════
    #  ADVANCED: BATCH RENAME
    # ════════════════════════════════════════════════════════════

    def batch_rename(
        self,
        folder: str = None,
        pattern: str = None,
        prefix: str = "",
        suffix: str = "",
        find: str = "",
        replace: str = "",
    ) -> str:
        """
        Batch rename files in a folder.
        Say: 'batch rename documents add prefix report_'
             'batch rename downloads replace old with new'
        """
        from pathlib import Path as _Path

        base = _Path(folder) if folder else _Path.home() / "Downloads"
        if not base.exists():
            return f"Folder not found: {base}, sir."
        files = [f for f in base.iterdir() if f.is_file()]
        if not files:
            return f"No files found in {base.name}, sir."
        renamed = 0
        errors = []
        for f in files:
            try:
                new_name = f.stem
                if find and replace:
                    new_name = new_name.replace(find, replace)
                if prefix:
                    new_name = prefix + new_name
                if suffix:
                    new_name = new_name + suffix
                new_path = f.parent / (new_name + f.suffix)
                if new_path != f:
                    f.rename(new_path)
                    renamed += 1
            except Exception:
                errors.append(f.name)
        result = f"Renamed {renamed} of {len(files)} files"
        if prefix:
            result += f" (added prefix '{prefix}')"
        if suffix:
            result += f" (added suffix '{suffix}')"
        if find:
            result += f" (replaced '{find}' with '{replace}')"
        if errors:
            result += f". {len(errors)} errors."
        return result + ", sir."

    # ════════════════════════════════════════════════════════════
    #  ADVANCED: CLOUD SYNC STATUS
    # ════════════════════════════════════════════════════════════

    def cloud_sync_status(self) -> str:
        """Check OneDrive and Dropbox sync status."""
        import os
        import subprocess

        results = []
        # OneDrive status
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq OneDrive.exe"],
                capture_output=True,
                text=True,
            )
            if "OneDrive.exe" in result.stdout:
                # Check sync status via registry or file
                onedrive_folder = os.path.expandvars(r"%USERPROFILE%\OneDrive")
                if os.path.exists(onedrive_folder):
                    results.append("OneDrive: Running ✅")
                else:
                    results.append("OneDrive: Running (folder not found)")
            else:
                results.append("OneDrive: Not running ❌")
        except Exception:
            results.append("OneDrive: Status unknown")
        # Dropbox status
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Dropbox.exe"],
                capture_output=True,
                text=True,
            )
            if "Dropbox.exe" in result.stdout:
                results.append("Dropbox: Running ✅")
            else:
                results.append("Dropbox: Not running")
        except Exception:
            results.append("Dropbox: Not installed")
        # Google Drive
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq googledrivesync.exe"],
                capture_output=True,
                text=True,
            )
            if "googledrivesync.exe" in result.stdout:
                results.append("Google Drive: Running ✅")
        except Exception:
            pass
        return "Cloud sync status:\n" + "\n".join(f"• {r}" for r in results)

    # ════════════════════════════════════════════════════════════
    #  ADVANCED: FILE INFO
    # ════════════════════════════════════════════════════════════

    def get_file_info(self, filepath: str) -> str:
        """Get detailed info about a file: size, dates, type."""
        from datetime import datetime
        from pathlib import Path as _Path

        path = _Path(filepath)
        if not path.exists():
            path = _Path.home() / "Desktop" / filepath
        if not path.exists():
            return f"File not found: {filepath}, sir."
        stat = path.stat()
        size = stat.st_size
        if size > 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        elif size > 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size} bytes"
        created = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M")
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        return (
            f"File: {path.name}\n"
            f"Size: {size_str}\n"
            f"Created: {created}\n"
            f"Modified: {modified}\n"
            f"Location: {path.parent}"
        )


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    fs = FileSkill()
    print(fs.list_desktop())
    print(fs.write_note("This is a test note from JARVIS!"))
    print(fs.fuzzy_search("resume"))
