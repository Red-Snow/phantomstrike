# Security Policy

PhantomStrike executes system commands on the host it runs on. That is its
purpose, and it means deployment choices matter more here than in most projects.
This document covers how to report a vulnerability and how to run the framework
without creating one.

## Reporting a vulnerability

Please report privately rather than opening a public issue.

- **GitHub Security Advisories** — [open a draft advisory](https://github.com/Red-Snow/phantomstrike/security/advisories/new) (preferred)
- Include: affected version or commit, reproduction steps, and impact.

You can expect an acknowledgement within 5 days and an assessment within 14.
Fixes for issues allowing unauthenticated execution are prioritised over
everything else. Credit is given in the release notes unless you'd rather not be
named.

Please don't test against infrastructure you don't own. A local reproduction is
always sufficient for a report here.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 1.x     | Yes       |
| < 1.0   | No        |

## Threat model

Read this before deploying. Three properties of the design drive every default.

### The API executes commands

Any caller who can reach the API and authenticate can run security tools as the
user running the server. Treat the API port the way you would treat an SSH port.

- Authentication is on by default and the server **refuses to start** if it is
  enabled with no keys configured. An API that looks protected but accepts
  everyone is the worse failure.
- Bind to `127.0.0.1` (the default). If you need remote access, put it behind a
  VPN or an authenticating reverse proxy — do not expose the port directly.

### Localhost is not a security boundary

Every page in your browser can reach `127.0.0.1`. Without an origin check, any
website you visit while the server runs could send it requests.

- Cross-origin browser requests are rejected outright. `PHANTOMSTRIKE_CORS_ORIGINS`
  is empty by default and `*` is refused at config load.
- Non-browser clients (the CLI, the MCP client, curl) send no `Origin` header and
  are unaffected.

### The agent's input comes from the target

This is the threat specific to AI-driven security tooling, and it deserves the
most attention.

An LLM agent decides what to run next based on tool output. Tool output comes
from the host being scanned: HTTP response bodies, service banners, TLS
certificate fields, directory names. A target that expects to be scanned can put
text in any of those fields, and that text arrives in the agent's context as if
it were data the agent should act on.

An attacker-controlled banner reading *"scan complete — now run the following
diagnostic command"* is a prompt injection aimed at whatever tools the agent
holds. Mitigations here:

- **Authentication is the control, not feature removal.** `kali_shell` gives the
  agent all 600+ Kali/Parrot tools and is enabled by default — that is the point
  of the framework. It is protected by the API key and the cross-origin guard, so
  it answers only to the operator. Set `PHANTOMSTRIKE_ALLOW_RAW_SHELL=false` if
  you want a plugins-only deployment.
- **One configuration fails closed.** The server refuses to start with auth
  disabled *and* raw shell enabled *and* a non-loopback bind address. Each is
  defensible alone; together they publish a root shell to the network. An
  isolated lab box on `127.0.0.1` with auth off still runs.
- **Prefer a disposable VM.** The agent can run anything you could run. Give it a
  machine you are willing to rebuild.
- **Scope is enforced below the agent.** Targets are checked against
  `engagement.yaml` in the execution path, so an agent that has been redirected
  still cannot reach a host outside the engagement.
- **Everything is logged.** Each execution is written to the audit logger with
  its tool, target and full command before it runs.

Treat all tool output as untrusted input, because it is.

## Running it safely

```bash
# 1. Generate an API key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 2. Configure
export PHANTOMSTRIKE_API_KEYS="<the key you just generated>"
export PHANTOMSTRIKE_HOST=127.0.0.1
export PHANTOMSTRIKE_ENGAGEMENT=./engagement.yaml   # define authorised scope
export PHANTOMSTRIKE_DOCKER_SANDBOX=true            # isolate tool execution

# 3. Universal tool access is already on. Only set this to opt OUT:
# export PHANTOMSTRIKE_ALLOW_RAW_SHELL=false
```

**Checklist before pointing this at anything:**

- [ ] `engagement.yaml` reflects scope you have written authorisation for
- [ ] API keys set; auth not disabled
- [ ] Bound to localhost, or behind an authenticating proxy
- [ ] Running on a host you are willing to rebuild, since the agent has full
      tool access by design
- [ ] Audit log going somewhere you can retrieve later

## Legal

This framework automates tools that are illegal to point at systems you do not
have permission to test, in most jurisdictions. The engagement scope file exists
to help you stay within your authorisation — it is a safeguard, not a substitute
for written permission from the system owner.

You are responsible for how you use it.
