#!/usr/bin/env python3
"""
Filesystem Watcher - Bronze Tier (Production-Grade)

Monitors Drop_Zone/ and creates actionable tasks in Needs_Action/.
Features:
- Startup backlog scan for files dropped while offline
- Idempotency protection via processed folder tracking
- Robust event handling with deduplication
- Structured logging with JSON log entries
"""

import hashlib
import json
import logging
import shutil
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

# =============================================================================
# PATH CONFIGURATION
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = PROJECT_ROOT / "AI_Employee_Vault"

DROP_ZONE = PROJECT_ROOT / "Drop_Zone"
PROCESSED_DIR = DROP_ZONE / "processed"
NEEDS_ACTION = VAULT_DIR / "Needs_Action"
LOGS_DIR = VAULT_DIR / "Logs"

# Required directories
REQUIRED_DIRS = [DROP_ZONE, PROCESSED_DIR, NEEDS_ACTION, LOGS_DIR]

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================


def setup_logging() -> logging.Logger:
    """Configure structured logging with file and console handlers."""
    for d in REQUIRED_DIRS:
        d.mkdir(parents=True, exist_ok=True)

    log_file = LOGS_DIR / f"watcher_{datetime.now().strftime('%Y-%m-%d')}.log"

    logger = logging.getLogger("FilesystemWatcher")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger


logger = setup_logging()


# =============================================================================
# JSON LOG WRITER
# =============================================================================


class JsonLogWriter:
    """Writes structured JSON log entries to daily log files."""

    def __init__(self, logs_dir: Path):
        self.logs_dir = logs_dir
        self._lock = threading.Lock()

    def _get_log_file(self) -> Path:
        """Get today's JSON log file path."""
        return self.logs_dir / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"

    def write(
        self,
        action_type: str,
        source_file: Optional[str] = None,
        target_file: Optional[str] = None,
        result: str = "success",
        details: Optional[dict] = None,
    ) -> None:
        """Write a structured log entry."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action_type": action_type,
            "actor": "filesystem_watcher",
            "source_file": source_file,
            "target_file": target_file,
            "details": details or {},
            "result": result,
        }

        log_file = self._get_log_file()

        with self._lock:
            try:
                if log_file.exists():
                    content = log_file.read_text(encoding="utf-8").strip()
                    if content:
                        try:
                            logs = json.loads(content)
                            if not isinstance(logs, list):
                                logs = [logs]
                        except json.JSONDecodeError:
                            logs = []
                    else:
                        logs = []
                else:
                    logs = []

                logs.append(entry)
                log_file.write_text(
                    json.dumps(logs, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception as e:
                logger.error(f"Failed to write JSON log: {e}")


json_logger = JsonLogWriter(LOGS_DIR)


# =============================================================================
# FILE PROCESSING UTILITIES
# =============================================================================


def compute_file_hash(file_path: Path, block_size: int = 65536) -> str:
    """Compute SHA-256 hash of a file for idempotency checks."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(block_size), b""):
                sha256.update(block)
        return sha256.hexdigest()[:16]
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")


def generate_deterministic_task_id(file_path: Path) -> str:
    """Generate a deterministic task ID based on filename and content hash."""
    file_hash = compute_file_hash(file_path)
    safe_stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in file_path.stem)
    return f"FILE_{safe_stem}_{file_hash}"


def is_temporary_file(path: Path) -> bool:
    """Check if a file is temporary or hidden."""
    name = path.name
    return (
        name.startswith(".")
        or name.startswith("~")
        or name.endswith(".tmp")
        or name.endswith(".temp")
        or name.endswith(".part")
        or name.endswith(".crdownload")
        or name.endswith(".partial")
        or name.startswith("~$")
    )


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def wait_for_file_ready(path: Path, timeout: int = 30, poll_interval: float = 0.5) -> bool:
    """Wait for a file to be fully written and stable."""
    if not path.exists():
        return False

    previous_size = -1
    stable_count = 0
    required_stable_checks = 3
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            if not path.exists():
                return False

            current_size = path.stat().st_size

            if current_size == previous_size:
                stable_count += 1
                if stable_count >= required_stable_checks and current_size > 0:
                    return True
            else:
                stable_count = 0

            previous_size = current_size
            time.sleep(poll_interval)

        except (OSError, FileNotFoundError):
            return False

    return path.exists() and previous_size > 0


def is_already_processed(task_id: str, needs_action: Path) -> bool:
    """Check if a task with this ID already exists in Needs_Action."""
    metadata_file = needs_action / f"{task_id}.md"
    return metadata_file.exists()


def is_in_processed_folder(file_path: Path, processed_dir: Path) -> bool:
    """Check if a file with the same name exists in processed folder."""
    processed_file = processed_dir / file_path.name
    return processed_file.exists()


# =============================================================================
# METADATA GENERATION
# =============================================================================


def generate_metadata(
    task_id: str,
    original_name: str,
    source_path: str,
    file_size: int,
    file_size_human: str,
    timestamp: datetime,
    dest_file_name: str,
) -> str:
    """Generate YAML frontmatter metadata file following vault standards."""
    return f"""---
type: file_drop
task_id: {task_id}
original_name: "{original_name}"
source_path: "{source_path}"
file_name: "{dest_file_name}"
file_size: {file_size}
file_size_human: "{file_size_human}"
created: {timestamp.isoformat()}
status: new
priority: medium
---

# File Drop: {original_name}

## Details

| Property | Value |
|----------|-------|
| Original Name | `{original_name}` |
| Source Path | `{source_path}` |
| Stored As | `{dest_file_name}` |
| Size | {file_size_human} |
| Received | {timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")} |

## Suggested Actions

- [ ] Review file contents
- [ ] Determine required processing
- [ ] Create execution plan

## Notes

> File automatically captured by Filesystem Watcher.
> Awaiting processing by AI Employee.
"""


# =============================================================================
# FILE PROCESSOR
# =============================================================================


class FileProcessor:
    """Handles processing of individual files with idempotency guarantees."""

    def __init__(self, needs_action: Path, processed_dir: Path):
        self.needs_action = needs_action
        self.processed_dir = processed_dir
        self._processing_lock = threading.Lock()
        self._in_progress: Set[str] = set()

    def process(self, source_path: Path, source: str = "event") -> bool:
        """
        Process a single file from Drop_Zone.

        Args:
            source_path: Path to the file to process
            source: Either "event" (from watchdog) or "backlog" (startup scan)

        Returns:
            True if processed successfully, False otherwise
        """
        file_key = str(source_path.resolve())

        with self._processing_lock:
            if file_key in self._in_progress:
                logger.debug(f"Skipping (already processing): {source_path.name}")
                return False
            self._in_progress.add(file_key)

        try:
            return self._process_file(source_path, source)
        finally:
            with self._processing_lock:
                self._in_progress.discard(file_key)

    def _process_file(self, source_path: Path, source: str) -> bool:
        """Internal file processing logic."""
        if not source_path.exists():
            logger.debug(f"File no longer exists: {source_path.name}")
            return False

        if source_path.is_dir():
            logger.debug(f"Skipping directory: {source_path.name}")
            return False

        if is_temporary_file(source_path):
            logger.debug(f"Skipping temporary file: {source_path.name}")
            return False

        task_id = generate_deterministic_task_id(source_path)

        if is_already_processed(task_id, self.needs_action):
            logger.info(f"Skipping (already in Needs_Action): {source_path.name} [{task_id}]")
            json_logger.write(
                action_type="file_skipped",
                source_file=str(source_path),
                result="skipped",
                details={"reason": "already_processed", "task_id": task_id},
            )
            return False

        if not wait_for_file_ready(source_path):
            logger.warning(f"File not ready or disappeared: {source_path.name}")
            json_logger.write(
                action_type="file_skipped",
                source_file=str(source_path),
                result="skipped",
                details={"reason": "file_not_ready"},
            )
            return False

        timestamp = datetime.now(timezone.utc)

        dest_file = self.needs_action / f"{task_id}{source_path.suffix}"
        dest_metadata = self.needs_action / f"{task_id}.md"

        try:
            shutil.copy2(source_path, dest_file)
            logger.info(f"Copied: {source_path.name} -> {dest_file.name}")
        except Exception as e:
            logger.error(f"Copy failed for {source_path.name}: {e}")
            json_logger.write(
                action_type="file_copy_failed",
                source_file=str(source_path),
                target_file=str(dest_file),
                result="error",
                details={"error": str(e)},
            )
            return False

        try:
            file_stats = dest_file.stat()
            file_size = file_stats.st_size
            file_size_human = format_file_size(file_size)
        except Exception as e:
            logger.error(f"Failed to get file stats: {e}")
            file_size = 0
            file_size_human = "unknown"

        metadata_content = generate_metadata(
            task_id=task_id,
            original_name=source_path.name,
            source_path=str(source_path),
            file_size=file_size,
            file_size_human=file_size_human,
            timestamp=timestamp,
            dest_file_name=dest_file.name,
        )

        try:
            dest_metadata.write_text(metadata_content, encoding="utf-8")
            logger.info(f"Created metadata: {dest_metadata.name}")
        except Exception as e:
            logger.error(f"Failed to create metadata: {e}")
            try:
                dest_file.unlink()
            except Exception:
                pass
            json_logger.write(
                action_type="metadata_creation_failed",
                source_file=str(source_path),
                target_file=str(dest_metadata),
                result="error",
                details={"error": str(e)},
            )
            return False

        try:
            processed_dest = self.processed_dir / source_path.name
            if processed_dest.exists():
                processed_dest = self.processed_dir / f"{source_path.stem}_{task_id[-8:]}{source_path.suffix}"
            shutil.move(str(source_path), str(processed_dest))
            logger.info(f"Moved to processed: {source_path.name}")
        except Exception as e:
            logger.warning(f"Could not move to processed (file may be locked): {e}")

        json_logger.write(
            action_type="file_processed",
            source_file=str(source_path),
            target_file=str(dest_file),
            result="success",
            details={
                "task_id": task_id,
                "file_size": file_size,
                "source": source,
            },
        )

        logger.info(f"Task created: {task_id} (source: {source})")
        return True


# =============================================================================
# EVENT HANDLER
# =============================================================================


class DropZoneHandler(FileSystemEventHandler):
    """Handles filesystem events in the Drop Zone directory."""

    def __init__(self, processor: FileProcessor, drop_zone: Path):
        super().__init__()
        self.processor = processor
        self.drop_zone = drop_zone
        self._recent_events: dict = {}
        self._event_lock = threading.Lock()
        self._debounce_seconds = 1.0

    def _should_process_event(self, path: Path) -> bool:
        """Debounce events to prevent duplicate processing."""
        key = str(path.resolve())
        current_time = time.time()

        with self._event_lock:
            last_time = self._recent_events.get(key, 0)
            if current_time - last_time < self._debounce_seconds:
                return False
            self._recent_events[key] = current_time

            cutoff = current_time - 60
            self._recent_events = {
                k: v for k, v in self._recent_events.items() if v > cutoff
            }

        return True

    def _is_valid_source(self, path: Path) -> bool:
        """Check if the path is a valid source file in Drop Zone."""
        try:
            path = path.resolve()
            if not path.is_relative_to(self.drop_zone.resolve()):
                return False
            if path.is_relative_to(PROCESSED_DIR.resolve()):
                return False
            return True
        except (ValueError, OSError):
            return False

    def on_created(self, event):
        """Handle file creation events."""
        if event.is_directory:
            return

        source_path = Path(event.src_path)

        if not self._is_valid_source(source_path):
            return

        if not self._should_process_event(source_path):
            logger.debug(f"Debounced event: {source_path.name}")
            return

        logger.debug(f"Event: created - {source_path.name}")

        time.sleep(0.5)

        threading.Thread(
            target=self.processor.process,
            args=(source_path, "event"),
            daemon=True,
        ).start()

    def on_modified(self, event):
        """Handle file modification events (for files that are created then written)."""
        if event.is_directory:
            return

        source_path = Path(event.src_path)

        if not self._is_valid_source(source_path):
            return

        if not self._should_process_event(source_path):
            return

        logger.debug(f"Event: modified - {source_path.name}")

        threading.Thread(
            target=self.processor.process,
            args=(source_path, "event"),
            daemon=True,
        ).start()


# =============================================================================
# BACKLOG PROCESSOR
# =============================================================================


def process_existing_files(processor: FileProcessor, drop_zone: Path) -> int:
    """
    Process all existing files in Drop Zone at startup.

    This ensures files dropped while the watcher was offline are not lost.

    Returns:
        Number of files successfully processed
    """
    logger.info("Scanning Drop Zone for existing files...")

    processed_count = 0
    skipped_count = 0
    error_count = 0

    try:
        files = []
        for f in drop_zone.iterdir():
            if not f.is_file():
                continue
            if is_temporary_file(f):
                continue
            # Skip files in processed subdirectory
            if PROCESSED_DIR.exists():
                try:
                    if f.is_relative_to(PROCESSED_DIR):
                        continue
                except ValueError:
                    pass
            files.append(f)
    except Exception as e:
        logger.error(f"Failed to scan Drop Zone: {e}")
        return 0

    file_count = len(files)

    if file_count == 0:
        logger.info("No existing files to process in Drop Zone.")
        return 0

    logger.info(f"Found {file_count} existing file(s) to evaluate.")

    for file_path in sorted(files, key=lambda f: f.stat().st_mtime):
        try:
            if file_path.parent.resolve() == PROCESSED_DIR.resolve():
                skipped_count += 1
                continue

            if processor.process(file_path, source="backlog"):
                processed_count += 1
            else:
                skipped_count += 1

        except Exception as e:
            logger.error(f"Error processing backlog file {file_path.name}: {e}")
            error_count += 1

    logger.info(
        f"Backlog scan complete: {processed_count} processed, "
        f"{skipped_count} skipped, {error_count} errors"
    )

    json_logger.write(
        action_type="backlog_scan_complete",
        result="success",
        details={
            "files_found": file_count,
            "processed": processed_count,
            "skipped": skipped_count,
            "errors": error_count,
        },
    )

    return processed_count


# =============================================================================
# MAIN WATCHER SERVICE
# =============================================================================


class FilesystemWatcher:
    """Main watcher service with startup backlog processing."""

    def __init__(self, drop_zone: Path, needs_action: Path, processed_dir: Path):
        self.drop_zone = drop_zone
        self.needs_action = needs_action
        self.processed_dir = processed_dir
        self.observer: Optional[Observer] = None
        self.processor: Optional[FileProcessor] = None
        self._running = False

    def setup(self) -> bool:
        """Initialize required directories and validate setup."""
        try:
            for directory in REQUIRED_DIRS:
                directory.mkdir(parents=True, exist_ok=True)

            logger.info(f"Drop Zone:     {self.drop_zone}")
            logger.info(f"Processed:     {self.processed_dir}")
            logger.info(f"Needs Action:  {self.needs_action}")
            logger.info(f"Logs:          {LOGS_DIR}")

            self.processor = FileProcessor(self.needs_action, self.processed_dir)

            return True

        except Exception as e:
            logger.error(f"Setup failed: {e}")
            return False

    def start(self) -> None:
        """Start the file watcher with backlog processing."""
        if not self.setup():
            logger.error("Watcher setup failed. Exiting.")
            sys.exit(1)

        json_logger.write(
            action_type="watcher_startup",
            result="success",
            details={
                "drop_zone": str(self.drop_zone),
                "needs_action": str(self.needs_action),
            },
        )

        process_existing_files(self.processor, self.drop_zone)

        handler = DropZoneHandler(self.processor, self.drop_zone)
        # Use PollingObserver for WSL2/Windows filesystem compatibility
        # Native Observer doesn't reliably detect changes on /mnt/c/...
        self.observer = PollingObserver(timeout=2)  # Poll every 2 seconds
        self.observer.schedule(handler, str(self.drop_zone), recursive=False)

        try:
            self.observer.start()
            self._running = True

            logger.info("Filesystem Watcher started. Monitoring for file drops...")
            logger.info("Mode: Polling (WSL2/Windows compatible)")
            logger.info("Press Ctrl+C to stop.")

            while self._running and self.observer.is_alive():
                self.observer.join(timeout=1)

        except KeyboardInterrupt:
            logger.info("Shutdown requested by user...")
        except Exception as e:
            logger.error(f"Watcher error: {e}")
            json_logger.write(
                action_type="watcher_error",
                result="error",
                details={"error": str(e)},
            )
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the file watcher gracefully."""
        self._running = False

        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)

            json_logger.write(
                action_type="watcher_shutdown",
                result="success",
            )

            logger.info("Filesystem Watcher stopped.")


# =============================================================================
# ENTRY POINT
# =============================================================================


def main():
    """Entry point for the filesystem watcher."""
    logger.info("=" * 60)
    logger.info("Personal AI Employee - Filesystem Watcher")
    logger.info("Tier: Bronze (Production-Grade)")
    logger.info(f"Started: {datetime.now(timezone.utc).isoformat()}")
    logger.info("=" * 60)

    watcher = FilesystemWatcher(
        drop_zone=DROP_ZONE,
        needs_action=NEEDS_ACTION,
        processed_dir=PROCESSED_DIR,
    )
    watcher.start()


if __name__ == "__main__":
    main()
