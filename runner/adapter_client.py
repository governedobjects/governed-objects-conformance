# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""Generic subprocess client for conformance adapters.

The runner knows nothing about how an adapter is built or which implementation it
exercises: it starts the given command line, speaks NDJSON over stdin/stdout and
reads the adapter's self-declaration from its ``capabilities`` response."""

from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

# Seconds an adapter has to answer one request. The first response (capabilities) gets the
# longer startup timeout because an adapter may have to build or load before it can answer.
DEFAULT_REQUEST_TIMEOUT = 30.0
DEFAULT_STARTUP_TIMEOUT = 300.0


class AdapterError(RuntimeError):
    pass


class AdapterTimeout(AdapterError):
    """The adapter did not answer within the timeout; its process was terminated."""


class AdapterClient:
    def __init__(
        self,
        name: str,
        command: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        startup_timeout: float = DEFAULT_STARTUP_TIMEOUT,
    ):
        if not command:
            raise AdapterError("empty adapter command")
        self.name = name
        self.command = list(command)
        self.cwd = cwd
        self.env = env
        self.request_timeout = request_timeout
        self.startup_timeout = startup_timeout
        self._counter = 0
        self.capabilities: dict[str, Any] = {}
        self._start()

    def _start(self) -> None:
        # Adapter diagnostics go to a temporary file so an adapter that writes a lot to
        # stderr (for example while building) can never block on a full pipe.
        self._stderr = tempfile.TemporaryFile()
        try:
            self._proc = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._stderr,
                text=True,
                cwd=self.cwd,
                env=self.env,
                start_new_session=(os.name == 'posix'),  # so a timeout can end the whole process group
            )
        except OSError as exc:
            self._stderr.close()
            raise AdapterError(f"cannot start adapter command {self.command!r}: {exc}") from exc
        self._lines: queue.Queue = queue.Queue()
        self._first_response = True
        threading.Thread(target=self._pump, args=(self._proc, self._lines), daemon=True).start()

    @staticmethod
    def _pump(proc: subprocess.Popen, lines: queue.Queue) -> None:
        # Reads the adapter's stdout so request() can wait with a timeout.
        assert proc.stdout
        try:
            for line in proc.stdout:
                lines.put(line)
        except (OSError, ValueError):
            pass
        lines.put(None)  # end of output

    @property
    def alive(self) -> bool:
        return self._proc.poll() is None

    def restart(self) -> None:
        """Terminate the adapter (if still running) and start it again. Used after a timeout
        so one hung request cannot stop the remaining scenarios from being reported."""
        self._terminate()
        self._start()

    def _terminate(self) -> None:
        try:
            if os.name == "posix":
                os.killpg(self._proc.pid, signal.SIGKILL)
            else:
                self._proc.kill()
        except (OSError, ProcessLookupError):
            pass
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        for stream in (self._proc.stdin, self._proc.stdout):
            try:
                if stream:
                    stream.close()
            except (OSError, ValueError):
                pass
        self._stderr.close()

    def stderr_tail(self, limit: int = 2000) -> str:
        self._stderr.flush()
        self._stderr.seek(0)
        return self._stderr.read().decode("utf-8", "replace")[-limit:]

    def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._counter += 1
        payload = dict(payload)
        payload.setdefault("id", f"{self.name}-{self._counter}")
        assert self._proc.stdin and self._proc.stdout
        try:
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()
        except BrokenPipeError:
            raise AdapterError(f"adapter {self.name} closed stdin; stderr: {self.stderr_tail()}") from None
        timeout = self.startup_timeout if self._first_response else self.request_timeout
        try:
            line = self._lines.get(timeout=timeout)
        except queue.Empty:
            stderr = self.stderr_tail()
            self._terminate()
            raise AdapterTimeout(
                f"adapter {self.name} did not answer {payload.get('op')!r} within {timeout:g} s; "
                f"process terminated; stderr: {stderr}"
            ) from None
        self._first_response = False
        if not line:
            raise AdapterError(f"adapter {self.name} closed stdout; stderr: {self.stderr_tail()}")
        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise AdapterError(f"adapter {self.name} sent a non-JSON line: {line[:200]!r}") from exc

    def close(self) -> None:
        if self._proc.stdin:
            try:
                self._proc.stdin.close()
            except BrokenPipeError:
                pass
        try:
            self._proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()
        try:
            if self._proc.stdout:
                self._proc.stdout.close()
        except (OSError, ValueError):
            pass
        self._stderr.close()

    def read_capabilities(self) -> dict[str, Any]:
        resp = self.request({"op": "capabilities"})
        self.capabilities = resp.get("capabilities") or {}
        return self.capabilities

    def define_fixtures(self, fixtures: dict[str, Any], fixtures_sha256: str) -> dict[str, Any]:
        """Send the suite-owned fixture definitions. The adapter must echo their digest."""
        return self.request({"op": "define_fixture_types", "fixtures": fixtures, "fixtures_sha256": fixtures_sha256})
