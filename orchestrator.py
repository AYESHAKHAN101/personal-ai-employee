#!/usr/bin/env python3
"""
Bronze Tier Orchestrator - Control Plane
Coordinates filesystem watcher and Claude CLI processing.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class Orchestrator:

    def __init__(self):
        self.project_root = Path(__file__).resolve().parent
        self.vault_dir = self.project_root / "AI_Employee_Vault"
        self.needs_action_dir = self.vault_dir / "Needs_Action"
        self.logs_dir = self.vault_dir / "Logs"
        self.watcher_script = self.project_root / "watcher" / "filesystem_watcher.py"

        self.dry_run = os.environ.get("DRY_RUN", "").lower() in ("true", "1", "yes")
        self.loop_interval = 60
        self.max_retries = 3
        self.base_backoff = 1

        self._running = False
        self._watcher_process: Optional[subprocess.Popen] = None
        self._log_lock = threading.Lock()

        # --- Step 05: Lifecycle Resolution Engine paths ---
        self.in_progress_dir = self.vault_dir / "In_Progress"
        self.plans_dir = self.vault_dir / "Plans"
        self.approved_dir = self.vault_dir / "Approved"
        self.approved_archive_dir = self.approved_dir / "archive"
        self.rejected_dir = self.vault_dir / "Rejected"
        self.rejected_archive_dir = self.rejected_dir / "archive"
        self.done_dir = self.vault_dir / "Done"
        self.dashboard_file = self.vault_dir / "Dashboard.md"

        self._setup_directories()
        self._setup_signal_handlers()

    def _setup_directories(self):
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.needs_action_dir.mkdir(parents=True, exist_ok=True)
        # --- Step 05: Ensure archive directories exist ---
        self.approved_archive_dir.mkdir(parents=True, exist_ok=True)
        self.rejected_archive_dir.mkdir(parents=True, exist_ok=True)
        self.done_dir.mkdir(parents=True, exist_ok=True)

    def _setup_signal_handlers(self):
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        self.stop()

    def _get_log_file(self) -> Path:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.logs_dir / f"orchestrator_{date_str}.json"

    def _log_event(
        self,
        event: str,
        details: Optional[dict] = None,
        result: str = "success"
    ):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": "orchestrator",
            "event": event,
            "details": details or {},
            "result": result
        }

        log_file = self._get_log_file()

        with self._log_lock:
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

                temp_file = log_file.with_suffix(".tmp")
                temp_file.write_text(
                    json.dumps(logs, indent=2, ensure_ascii=False),
                    encoding="utf-8"
                )
                temp_file.replace(log_file)

            except Exception:
                pass

    def _start_watcher(self):
        if self._watcher_process and self._watcher_process.poll() is None:
            return

        try:
            python_exe = sys.executable
            self._watcher_process = subprocess.Popen(
                [python_exe, str(self.watcher_script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(self.project_root),
                text=True
            )
            self._log_event(
                "watcher_started",
                {"pid": self._watcher_process.pid}
            )
        except Exception as e:
            self._log_event(
                "watcher_start_failed",
                {"error": str(e)},
                result="error"
            )

    def _check_watcher(self):
        if self._watcher_process is None:
            self._start_watcher()
            return

        poll_result = self._watcher_process.poll()
        if poll_result is not None:
            self._log_event(
                "watcher_crashed",
                {"exit_code": poll_result},
                result="error"
            )
            self._start_watcher()

    def _stop_watcher(self):
        if self._watcher_process and self._watcher_process.poll() is None:
            self._watcher_process.terminate()
            try:
                self._watcher_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._watcher_process.kill()
                self._watcher_process.wait()
            self._log_event("watcher_stopped")

    def _count_needs_action_files(self) -> int:
        try:
            count = sum(
                1 for f in self.needs_action_dir.iterdir()
                if f.is_file() and not f.name.startswith(".")
            )
            return count
        except Exception:
            return 0

    def _retry_with_backoff(self, func, *args, **kwargs):
        last_error = None

        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                wait_time = self.base_backoff * (2 ** attempt)

                self._log_event(
                    "retry_attempt",
                    {
                        "attempt": attempt + 1,
                        "max_retries": self.max_retries,
                        "wait_seconds": wait_time,
                        "error": str(e)
                    },
                    result="error"
                )

                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)

        self._log_event(
            "max_retries_exceeded",
            {"error": str(last_error)},
            result="error"
        )
        return None

    def _execute_claude(self, prompt: str) -> dict:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(self.project_root)
        )

        if result.returncode != 0:
            raise RuntimeError(f"Claude CLI failed: {result.stderr}")

        return {
            "return_code": result.returncode,
            "stdout": result.stdout[:1000] if result.stdout else "",
            "stderr": result.stderr[:500] if result.stderr else ""
        }

    def run_claude_processing(self):
        file_count = self._count_needs_action_files()

        if file_count == 0:
            return

        prompt = "Process all files in /Needs_Action and create plans"

        self._log_event(
            "processing_triggered",
            {"file_count": file_count, "prompt": prompt}
        )

        if self.dry_run:
            self._log_event(
                "dry_run_skip",
                {"command": f'claude -p "{prompt}"', "file_count": file_count}
            )
            return

        result = self._retry_with_backoff(self._execute_claude, prompt)

        if result:
            self._log_event(
                "claude_execution_complete",
                {
                    "return_code": result["return_code"],
                    "stdout_length": len(result["stdout"]),
                    "file_count": file_count
                }
            )
        else:
            self._log_event(
                "claude_execution_failed",
                {"file_count": file_count},
                result="error"
            )

    # =========================================================================
    # --- Step 05: Lifecycle Resolution Engine ---
    # =========================================================================

    def _extract_task_id_from_approval(self, filename: str) -> Optional[str]:
        """Extract TASK_ID from APPROVAL_<TASK_ID>.md filename."""
        if filename.startswith("APPROVAL_") and filename.endswith(".md"):
            return filename[9:-3]
        return None

    def _extract_task_id_from_rejection(self, filename: str) -> Optional[str]:
        """Extract TASK_ID from rejection filename (APPROVAL_* or CLARIFICATION_*)."""
        if filename.endswith(".md"):
            if filename.startswith("APPROVAL_"):
                return filename[9:-3]
            elif filename.startswith("CLARIFICATION_"):
                return filename[14:-3]
        return None

    def _read_file_status(self, file_path: Path) -> Optional[str]:
        """Read status from YAML frontmatter."""
        try:
            if not file_path.exists():
                return None
            content = file_path.read_text(encoding="utf-8")
            for line in content.split("\n"):
                if line.startswith("status:"):
                    return line.split(":", 1)[1].strip()
            return None
        except Exception:
            return None

    def _update_file_status(self, file_path: Path, new_status: str) -> bool:
        """Update status in YAML frontmatter."""
        try:
            if not file_path.exists():
                return False
            content = file_path.read_text(encoding="utf-8")
            lines = content.split("\n")
            updated = False
            for i, line in enumerate(lines):
                if line.startswith("status:"):
                    lines[i] = f"status: {new_status}"
                    updated = True
                    break
            if updated:
                temp_file = file_path.with_suffix(".tmp")
                temp_file.write_text("\n".join(lines), encoding="utf-8")
                temp_file.replace(file_path)
            return updated
        except Exception:
            return False

    def _update_dashboard_timestamp(self):
        """Update Dashboard.md last_updated timestamp."""
        try:
            if not self.dashboard_file.exists():
                return
            content = self.dashboard_file.read_text(encoding="utf-8")
            timestamp = datetime.now(timezone.utc).isoformat()
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line.startswith("last_updated:"):
                    lines[i] = f"last_updated: {timestamp}"
                    break
            if lines[-1].startswith("*Last refreshed:"):
                lines[-1] = f"*Last refreshed: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC*"
            temp_file = self.dashboard_file.with_suffix(".tmp")
            temp_file.write_text("\n".join(lines), encoding="utf-8")
            temp_file.replace(self.dashboard_file)
        except Exception:
            pass

    def process_approved(self):
        """Process approval files in /Approved/ directory."""
        try:
            if not self.approved_dir.exists():
                return

            for approval_file in self.approved_dir.iterdir():
                if not approval_file.is_file():
                    continue
                if approval_file.name.startswith("."):
                    continue
                if not approval_file.name.startswith("APPROVAL_"):
                    continue
                if not approval_file.name.endswith(".md"):
                    continue

                try:
                    self._process_single_approval(approval_file)
                except Exception as e:
                    self._log_event(
                        "lifecycle_resolution_failed",
                        {"file": approval_file.name, "error": str(e)},
                        result="error"
                    )
        except Exception as e:
            self._log_event(
                "lifecycle_resolution_failed",
                {"error": str(e), "phase": "process_approved"},
                result="error"
            )

    def _process_single_approval(self, approval_file: Path):
        """Process a single approval file."""
        task_id = self._extract_task_id_from_approval(approval_file.name)
        if not task_id:
            return

        task_file = self.in_progress_dir / f"{task_id}.md"
        plan_file = self.plans_dir / f"PLAN_{task_id}.md"

        current_status = self._read_file_status(task_file)
        if current_status in ("approved", "rejected", "completed"):
            archive_dest = self.approved_archive_dir / approval_file.name
            if not archive_dest.exists():
                approval_file.rename(archive_dest)
            return

        if task_file.exists():
            self._update_file_status(task_file, "approved")

        if plan_file.exists():
            self._update_file_status(plan_file, "approved")

        self._log_event(
            "approval_granted",
            {"task_id": task_id},
            result="success"
        )

        archive_dest = self.approved_archive_dir / approval_file.name
        if archive_dest.exists():
            archive_dest = self.approved_archive_dir / f"{approval_file.stem}_{int(time.time())}.md"
        approval_file.rename(archive_dest)

        self._update_dashboard_timestamp()

    def process_rejected(self):
        """Process rejection files in /Rejected/ directory."""
        try:
            if not self.rejected_dir.exists():
                return

            for rejection_file in self.rejected_dir.iterdir():
                if not rejection_file.is_file():
                    continue
                if rejection_file.name.startswith("."):
                    continue
                if not rejection_file.name.endswith(".md"):
                    continue
                if not (rejection_file.name.startswith("APPROVAL_") or
                        rejection_file.name.startswith("CLARIFICATION_")):
                    continue

                try:
                    self._process_single_rejection(rejection_file)
                except Exception as e:
                    self._log_event(
                        "lifecycle_resolution_failed",
                        {"file": rejection_file.name, "error": str(e)},
                        result="error"
                    )
        except Exception as e:
            self._log_event(
                "lifecycle_resolution_failed",
                {"error": str(e), "phase": "process_rejected"},
                result="error"
            )

    def _process_single_rejection(self, rejection_file: Path):
        """Process a single rejection file."""
        task_id = self._extract_task_id_from_rejection(rejection_file.name)
        if not task_id:
            return

        task_file = self.in_progress_dir / f"{task_id}.md"
        task_data_file = self.in_progress_dir / f"{task_id}.txt"
        plan_file = self.plans_dir / f"PLAN_{task_id}.md"

        current_status = self._read_file_status(task_file)
        if current_status in ("rejected", "completed"):
            archive_dest = self.rejected_archive_dir / rejection_file.name
            if not archive_dest.exists():
                rejection_file.rename(archive_dest)
            return

        if task_file.exists():
            self._update_file_status(task_file, "rejected")
            done_dest = self.done_dir / task_file.name
            if done_dest.exists():
                done_dest = self.done_dir / f"{task_file.stem}_{int(time.time())}.md"
            task_file.rename(done_dest)

        if task_data_file.exists():
            done_data_dest = self.done_dir / task_data_file.name
            if done_data_dest.exists():
                done_data_dest = self.done_dir / f"{task_data_file.stem}_{int(time.time())}.txt"
            task_data_file.rename(done_data_dest)

        if plan_file.exists():
            self._update_file_status(plan_file, "cancelled")

        self._log_event(
            "approval_rejected",
            {"task_id": task_id, "reason": "human_rejected"},
            result="success"
        )

        archive_dest = self.rejected_archive_dir / rejection_file.name
        if archive_dest.exists():
            archive_dest = self.rejected_archive_dir / f"{rejection_file.stem}_{int(time.time())}.md"
        rejection_file.rename(archive_dest)

        self._update_dashboard_timestamp()

    # =========================================================================
    # --- End Step 05 ---
    # =========================================================================

    def run_loop(self):
        while self._running:
            try:
                self._check_watcher()
                self.run_claude_processing()
                # --- Step 05: Lifecycle Resolution Engine ---
                self.process_approved()
                self.process_rejected()
            except Exception as e:
                self._log_event(
                    "loop_error",
                    {"error": str(e)},
                    result="error"
                )

            for _ in range(self.loop_interval):
                if not self._running:
                    break
                time.sleep(1)

    def start(self):
        self._running = True

        self._log_event(
            "orchestrator_started",
            {
                "dry_run": self.dry_run,
                "loop_interval": self.loop_interval,
                "project_root": str(self.project_root)
            }
        )

        self._start_watcher()

        try:
            self.run_loop()
        except Exception as e:
            self._log_event(
                "orchestrator_error",
                {"error": str(e)},
                result="error"
            )
        finally:
            self.stop()

    def stop(self):
        if not self._running:
            return

        self._running = False
        self._stop_watcher()

        self._log_event("orchestrator_stopped")


if __name__ == "__main__":
    orchestrator = Orchestrator()
    orchestrator.start()
