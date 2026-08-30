"""
Universal shell plugin — arbitrary command execution.

Read this before enabling it
----------------------------
This plugin is not a scanner wrapper. It takes a command string and hands it to
a shell. It bypasses `utils.validation` entirely: the target parsing, port
validation and shell-metacharacter blocklist that protect every other plugin do
not apply here, because running whatever is passed in is the whole point.

It is therefore disabled unless the operator sets:

    PHANTOMSTRIKE_ALLOW_RAW_SHELL=true

Two properties of the surrounding system make that the right default:

  * The API is reachable from the operator's browser. Localhost is not a
    boundary — without the origin guard in `server.auth`, a page in any open tab
    could drive this plugin.

  * The caller is usually an LLM agent whose decisions are shaped by tool output,
    and tool output comes from the target being scanned. A host that plants
    instructions in a service banner or an HTTP response is talking directly to
    the agent holding this shell. Enabling it is a decision about that threat,
    not a convenience toggle.

When enabled, run it against a disposable VM or container rather than a host you
care about, and keep `PHANTOMSTRIKE_ENGAGEMENT` set so commands are still
recorded against an authorised scope.
"""

from pydantic import BaseModel, Field

from phantomstrike.plugins.base import BaseToolPlugin, ToolCategory, ToolResult, ToolStatus


class KaliShellPlugin(BaseToolPlugin):
    """Run an arbitrary command on the host. Opt-in — see module docstring."""

    name = "kali_shell"
    category = ToolCategory.OSINT
    description = (
        "Arbitrary shell execution on the PhantomStrike host. Runs ANY command "
        "(wpscan, dirb, grep, pip …) and returns raw stdout and stderr. "
        "DANGEROUS: no input validation is applied. Disabled unless "
        "PHANTOMSTRIKE_ALLOW_RAW_SHELL=true."
    )
    required_binaries = ["bash"]
    version = "1.1.0"
    timeout = 1800  # 30 minutes for long-running commands
    use_shell = True

    #: Marks this plugin as an unrestricted execution primitive. The registry
    #: will not register it, and the runner will not run it, unless the operator
    #: has explicitly opted in.
    requires_raw_shell_optin = True

    class InputSchema(BaseModel):
        command: str = Field(
            ...,
            description="Full bash command to execute, e.g. 'wpscan --url http://target'",
        )
        target: str = Field(
            "localhost",
            description=(
                "Host this command acts against. Recorded in the audit log and "
                "checked against the engagement scope — set it accurately."
            ),
        )

    def build_command(self, params: BaseModel) -> list[str]:
        """
        Return the command as a single-element list.

        `ToolRunner` joins the list and passes the resulting string to
        `create_subprocess_shell` when `use_shell` is set.
        """
        return [params.command]

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> ToolResult:
        """Return raw output — arbitrary commands have no parseable shape."""
        return ToolResult(
            tool_name=self.name,
            status=ToolStatus.SUCCESS if exit_code == 0 else ToolStatus.FAILED,
            target="",  # Populated by the runner
            parsed_data={"raw_output": stdout, "raw_error": stderr},
        )
