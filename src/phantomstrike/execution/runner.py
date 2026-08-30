"""
PhantomStrike Tool Runner — subprocess execution with streaming.

Handles the process lifecycle: spawn → stream → capture → return.

Execution model
---------------
Tool plugins run through `create_subprocess_exec` with a list argv, so no shell
parses their arguments and a metacharacter in a target or flag cannot become
syntax.

One plugin is different. `kali_shell` sets `use_shell = True` and passes its
input to `create_subprocess_shell`, because running arbitrary Kali commands is
its stated purpose. That makes it an unrestricted execution primitive which
bypasses every validator in `utils.validation`, so it is unavailable unless the
operator sets `PHANTOMSTRIKE_ALLOW_RAW_SHELL=true`.

(This docstring previously claimed "Never uses shell=True. Always list-based
commands." That was untrue of the code below it, and would have misled anyone
auditing this file.)
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from phantomstrike.config import settings
from phantomstrike.engagement import ScopeViolation, enforce as enforce_scope
from phantomstrike.plugins.base import BaseToolPlugin, ToolResult, ToolStatus
from phantomstrike.utils.logging import get_logger

log = get_logger("runner")
audit = get_logger("audit")


class ToolRunner:
    """
    Execute tool commands as async subprocesses.

    Safety properties:
    - Plugin commands are list[str] with no shell interpretation. The single
      exception, `kali_shell`, is opt-in and documented above.
    - Targets are checked against the active engagement scope before a command
      is built, so an agent that has been talked into a new target by hostile
      tool output is still stopped here.
    - Every execution is written to the audit log with its target and command.
    - Timeout enforcement per execution.
    - stdout/stderr streamed line-by-line for real-time monitoring.
    """

    async def run(
        self,
        plugin: BaseToolPlugin,
        params: dict,
        timeout: Optional[int] = None,
        stream_callback: Optional[callable] = None,
    ) -> ToolResult:
        """
        Execute a tool plugin and return structured results.

        Args:
            plugin: The tool plugin to execute.
            params: Validated parameters dict.
            timeout: Override default timeout (seconds).
            stream_callback: Optional async callback for streaming output lines.

        Returns:
            Structured ToolResult.
        """
        effective_timeout = timeout or plugin.timeout

        # ── Raw shell gate ─────────────────────────────────────────────
        # Checked here as well as at registration: the registry filters the
        # plugin out, and this stops any path that obtained an instance directly.
        if getattr(plugin, "use_shell", False) and not settings.execution.allow_raw_shell:
            return ToolResult(
                tool_name=plugin.name,
                status=ToolStatus.FAILED,
                target=params.get("target", "unknown"),
                error_message=(
                    f"Plugin '{plugin.name}' executes arbitrary shell commands and is "
                    "disabled. Set PHANTOMSTRIKE_ALLOW_RAW_SHELL=true to enable it, "
                    "having understood that it bypasses all input validation."
                ),
            )

        # ── Engagement scope ───────────────────────────────────────────
        # Before the command is built, so an out-of-scope target never reaches
        # argv construction. No-op when the session is unscoped.
        raw_target = str(params.get("target", "") or "")
        if raw_target and settings.engagement.enforce:
            try:
                enforce_scope(raw_target)
            except ScopeViolation as violation:
                audit.warning(
                    f"BLOCKED out-of-scope execution | tool={plugin.name} "
                    f"target={raw_target} reason={violation.reason}"
                )
                return ToolResult(
                    tool_name=plugin.name,
                    status=ToolStatus.FAILED,
                    target=raw_target,
                    error_message=f"Refused: {violation}",
                )

        # Validate input schema
        try:
            validated = plugin.InputSchema(**params)
        except Exception as e:
            return ToolResult(
                tool_name=plugin.name,
                status=ToolStatus.FAILED,
                target=params.get("target", "unknown"),
                error_message=f"Parameter validation failed: {e}",
            )

        # Build command
        try:
            command = plugin.build_command(validated)
        except Exception as e:
            return ToolResult(
                tool_name=plugin.name,
                status=ToolStatus.FAILED,
                target=params.get("target", "unknown"),
                error_message=f"Command build failed: {e}",
            )

        cmd_str = " ".join(command)
        target = params.get("target", "unknown")
        log.info(f"[tool]{plugin.name}[/tool] → executing: {cmd_str[:120]}")

        # Audit trail. An operator asked to justify a scan needs a record of what
        # ran against which host and when — separate from the debug log, and
        # written before execution so it survives a crash mid-run.
        audit.info(
            f"EXEC tool={plugin.name} target={target} shell={getattr(plugin, 'use_shell', False)} "
            f"command={cmd_str}"
        )

        started_at = datetime.now(timezone.utc)
        start_time = time.monotonic()

        try:
            if getattr(plugin, "use_shell", False):
                process = await asyncio.create_subprocess_shell(
                    cmd_str,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

            # Stream output while collecting it
            stdout_lines: list[str] = []
            stderr_lines: list[str] = []

            async def read_stream(stream, target_list, prefix=""):
                async for line_bytes in stream:
                    line = line_bytes.decode("utf-8", errors="replace").rstrip()
                    target_list.append(line)
                    if stream_callback:
                        try:
                            await stream_callback(prefix + line)
                        except Exception:
                            pass

            # Read stdout and stderr concurrently
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        read_stream(process.stdout, stdout_lines, "[stdout] "),
                        read_stream(process.stderr, stderr_lines, "[stderr] "),
                    ),
                    timeout=effective_timeout,
                )
                exit_code = await asyncio.wait_for(process.wait(), timeout=10)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                duration = time.monotonic() - start_time
                return ToolResult(
                    tool_name=plugin.name,
                    status=ToolStatus.TIMEOUT,
                    target=target,
                    command_executed=cmd_str,
                    stdout="\n".join(stdout_lines),
                    stderr="\n".join(stderr_lines),
                    exit_code=-1,
                    duration_seconds=round(duration, 2),
                    started_at=started_at.isoformat(),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    error_message=f"Tool timed out after {effective_timeout}s",
                )

            duration = time.monotonic() - start_time
            stdout_str = "\n".join(stdout_lines)
            stderr_str = "\n".join(stderr_lines)

            # Let the plugin parse raw output into structured findings
            try:
                result = plugin.parse_output(stdout_str, stderr_str, exit_code)
            except Exception as e:
                log.warning(f"[tool]{plugin.name}[/tool] parse_output failed: {e}")
                result = ToolResult(
                    tool_name=plugin.name,
                    status=ToolStatus.SUCCESS if exit_code == 0 else ToolStatus.FAILED,
                    target=target,
                    stdout=stdout_str,
                    stderr=stderr_str,
                    exit_code=exit_code,
                    error_message=f"Output parsing failed: {e}" if exit_code != 0 else "",
                )

            # Enrich with execution metadata
            result.command_executed = cmd_str
            result.duration_seconds = round(duration, 2)
            result.started_at = started_at.isoformat()
            result.finished_at = datetime.now(timezone.utc).isoformat()
            result.exit_code = exit_code

            severity_tag = ""
            if result.finding_counts:
                severity_tag = f" | findings: {result.finding_counts}"

            log.info(
                f"[tool]{plugin.name}[/tool] → "
                f"{'[success]✅ done[/success]' if result.success else '[error]❌ failed[/error]'} "
                f"in {duration:.1f}s (exit={exit_code}){severity_tag}"
            )

            return result

        except FileNotFoundError:
            duration = time.monotonic() - start_time
            missing = plugin.get_missing_binaries()
            return ToolResult(
                tool_name=plugin.name,
                status=ToolStatus.FAILED,
                target=target,
                command_executed=cmd_str,
                duration_seconds=round(duration, 2),
                started_at=started_at.isoformat(),
                finished_at=datetime.now(timezone.utc).isoformat(),
                error_message=f"Tool binary not found. Missing: {missing}. "
                              f"Install with your package manager.",
            )
        except Exception as e:
            duration = time.monotonic() - start_time
            return ToolResult(
                tool_name=plugin.name,
                status=ToolStatus.FAILED,
                target=target,
                command_executed=cmd_str,
                duration_seconds=round(duration, 2),
                started_at=started_at.isoformat(),
                finished_at=datetime.now(timezone.utc).isoformat(),
                error_message=f"Execution error: {e}",
            )

    async def stream_run(
        self,
        plugin: BaseToolPlugin,
        params: dict,
        timeout: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        Execute a tool and yield output lines as they arrive.

        Yields:
            Output lines prefixed with [stdout] or [stderr].
        """
        output_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

        async def _callback(line: str):
            await output_queue.put(line)

        async def _run():
            result = await self.run(plugin, params, timeout, stream_callback=_callback)
            await output_queue.put(None)  # Sentinel
            return result

        task = asyncio.create_task(_run())

        while True:
            line = await output_queue.get()
            if line is None:
                break
            yield line

        await task


# Global runner instance
runner = ToolRunner()
