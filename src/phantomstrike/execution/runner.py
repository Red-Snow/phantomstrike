"""
PhantomStrike Tool Runner — safe subprocess execution with streaming.

Handles the actual process lifecycle: spawn → stream → capture → return.
Never uses shell=True. Always list-based commands.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from phantomstrike.plugins.base import BaseToolPlugin, ToolResult, ToolStatus
from phantomstrike.utils.logging import get_logger

log = get_logger("runner")


class ToolRunner:
    """
    Execute tool commands as async subprocesses.

    Key safety properties:
    - Commands are list[str] — no shell interpretation.
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

        started_at = datetime.now(timezone.utc)
        start_time = time.monotonic()

        try:
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
