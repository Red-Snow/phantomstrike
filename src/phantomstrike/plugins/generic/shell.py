"""
Universal Shell Plugin — allows arbitrary command execution.
"""

from typing import Any

from pydantic import BaseModel, Field

from phantomstrike.plugins.base import BaseToolPlugin, Finding, Severity, ToolCategory, ToolResult, ToolStatus


class KaliShellPlugin(BaseToolPlugin):
    """Universal plugin to run any Kali Linux command."""

    name = "kali_shell"
    category = ToolCategory.OSINT  # Putting it in OSINT or generic
    description = (
        "Universal shell execution tool. Use this to run ANY command on the Kali VM "
        "(e.g., wpscan, dirb, grep, pip, etc.). Returns raw stdout and stderr."
    )
    required_binaries = ["bash"]
    version = "1.0.0"
    timeout = 1800  # 30 minutes for arbitrary commands
    use_shell = True

    class InputSchema(BaseModel):
        command: str = Field(..., description="The full bash command to execute (e.g. 'wpscan --url http://target.com')")
        target: str = Field("localhost", description="Optional target identifier for the database record")

    def build_command(self, params: BaseModel) -> list[str]:
        # Because use_shell = True, the runner expects a single string or a list where the first element is the string.
        # We return it as a list with one item for the runner.py logic to do `cmd_str = " ".join(command)`.
        # Wait, runner.py does `cmd_str = " ".join(command)` and then passes `cmd_str` to `create_subprocess_shell`.
        # So returning `[params.command]` works perfectly.
        return [params.command]

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> ToolResult:
        """
        We don't try to parse 600 different tool formats.
        We just return the raw text and let Claude read it from the ToolResult!
        """
        # If there's an obvious error but exit_code is 0 (some tools do this), flag it
        status = ToolStatus.SUCCESS if exit_code == 0 else ToolStatus.FAILED

        return ToolResult(
            tool_name=self.name,
            status=status,
            target="",  # Overridden by runner
            parsed_data={"raw_output": stdout, "raw_error": stderr},
        )
