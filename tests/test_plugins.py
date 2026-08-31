"""
Tests for tool plugins — validate command building and metadata.
"""

import functools
import http.server
import shutil
import socketserver
import subprocess
import threading

import pytest
from phantomstrike.plugins.network.nmap import NmapPlugin
from phantomstrike.plugins.network.rustscan import RustscanPlugin
from phantomstrike.plugins.network.masscan import MasscanPlugin
from phantomstrike.plugins.webapp.nuclei import NucleiPlugin
from phantomstrike.plugins.webapp.gobuster import GobusterPlugin
from phantomstrike.plugins.webapp.sqlmap import SqlmapPlugin
from phantomstrike.plugins.webapp.ffuf import FfufPlugin
from phantomstrike.plugins.webapp.nikto import NiktoPlugin
from phantomstrike.plugins.osint.subfinder import SubfinderPlugin
from phantomstrike.plugins.osint.amass import AmassPlugin
from phantomstrike.plugins.password.hydra import HydraPlugin
from phantomstrike.plugins.cloud.trivy import TrivyPlugin
from phantomstrike.plugins.base import ToolCategory


ALL_PLUGINS = [
    NmapPlugin, RustscanPlugin, MasscanPlugin,
    NucleiPlugin, GobusterPlugin, SqlmapPlugin, FfufPlugin, NiktoPlugin,
    SubfinderPlugin, AmassPlugin,
    HydraPlugin,
    TrivyPlugin,
]


class TestPluginMetadata:
    """Verify all plugins have required metadata."""

    @pytest.mark.parametrize("PluginClass", ALL_PLUGINS)
    def test_has_name(self, PluginClass):
        plugin = PluginClass()
        assert plugin.name, f"{PluginClass.__name__} must have a name"

    @pytest.mark.parametrize("PluginClass", ALL_PLUGINS)
    def test_has_description(self, PluginClass):
        plugin = PluginClass()
        assert len(plugin.description) > 10, f"{PluginClass.__name__} needs a proper description"

    @pytest.mark.parametrize("PluginClass", ALL_PLUGINS)
    def test_has_category(self, PluginClass):
        plugin = PluginClass()
        assert isinstance(plugin.category, ToolCategory)

    @pytest.mark.parametrize("PluginClass", ALL_PLUGINS)
    def test_has_required_binaries(self, PluginClass):
        plugin = PluginClass()
        assert isinstance(plugin.required_binaries, list)
        assert len(plugin.required_binaries) > 0

    @pytest.mark.parametrize("PluginClass", ALL_PLUGINS)
    def test_metadata_dict(self, PluginClass):
        plugin = PluginClass()
        meta = plugin.get_metadata()
        assert "name" in meta
        assert "category" in meta
        assert "input_schema" in meta


class TestCommandBuilding:
    """Verify plugins build safe, correct commands."""

    def test_nmap_basic(self):
        plugin = NmapPlugin()
        params = plugin.InputSchema(target="192.168.1.1")
        cmd = plugin.build_command(params)
        assert cmd[0] == "nmap"
        assert "192.168.1.1" in cmd
        assert "-oX" in cmd  # XML output

    def test_nmap_with_ports(self):
        plugin = NmapPlugin()
        params = plugin.InputSchema(target="10.0.0.1", ports="22,80,443", timing=3)
        cmd = plugin.build_command(params)
        assert "-p" in cmd
        assert "22,80,443" in cmd
        assert "-T3" in cmd

    def test_nuclei_basic(self):
        plugin = NucleiPlugin()
        params = plugin.InputSchema(target="https://example.com")
        cmd = plugin.build_command(params)
        assert cmd[0] == "nuclei"
        assert "-target" in cmd
        assert "-jsonl" in cmd  # JSON output

    def test_nuclei_with_severity(self):
        plugin = NucleiPlugin()
        params = plugin.InputSchema(target="https://example.com", severity="critical,high")
        cmd = plugin.build_command(params)
        assert "-severity" in cmd
        assert "critical,high" in cmd

    def test_sqlmap_basic(self):
        plugin = SqlmapPlugin()
        params = plugin.InputSchema(target="http://example.com/page?id=1")
        cmd = plugin.build_command(params)
        assert cmd[0] == "sqlmap"
        assert "--batch" in cmd
        assert "-u" in cmd

    def test_gobuster_dir(self):
        plugin = GobusterPlugin()
        params = plugin.InputSchema(target="http://example.com", mode="dir")
        cmd = plugin.build_command(params)
        assert cmd[0] == "gobuster"
        assert "dir" in cmd
        assert "-u" in cmd

    def test_gobuster_status_codes_clears_default_blacklist(self):
        # Gobuster 3.6+ defaults -b/--status-codes-blacklist to "404" and
        # refuses to start if both -s and a non-empty -b are set. Since
        # status_codes defaults to a non-empty string, every default dir/fuzz
        # call must also clear -b, or gobuster exits 1 before scanning
        # anything (confirmed against the real 3.6 binary).
        plugin = GobusterPlugin()
        params = plugin.InputSchema(target="http://example.com", mode="dir")
        cmd = plugin.build_command(params)
        assert "-s" in cmd
        s_idx = cmd.index("-s")
        assert cmd[s_idx + 1] == params.status_codes
        assert "-b" in cmd
        b_idx = cmd.index("-b")
        assert cmd[b_idx + 1] == ""

    def test_gobuster_dir_runs_against_real_binary(self, tmp_path):
        # End-to-end: build the real command this plugin would run and
        # execute it against a throwaway local HTTP server. This is the
        # exact scenario that caught the -s/-b conflict above — a unit test
        # that only checks flags are present would have passed even with
        # the bug, since "-s" was always there; what broke was gobuster's
        # own argument validation at process-launch time.
        gobuster = shutil.which("gobuster")
        if not gobuster:
            pytest.skip("gobuster binary not installed")

        (tmp_path / "found.txt").write_text("ok")
        wordlist = tmp_path / "wordlist.txt"
        wordlist.write_text("found.txt\nmissing.txt\n")

        with socketserver.TCPServer(("127.0.0.1", 0), functools.partial(
            http.server.SimpleHTTPRequestHandler, directory=str(tmp_path)
        )) as httpd:
            port = httpd.server_address[1]
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                plugin = GobusterPlugin()
                params = plugin.InputSchema(
                    target=f"http://127.0.0.1:{port}", mode="dir", wordlist=str(wordlist),
                )
                cmd = plugin.build_command(params)
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                assert proc.returncode == 0, proc.stderr
                assert "found.txt" in proc.stdout
                assert "missing.txt" not in proc.stdout
            finally:
                httpd.shutdown()

    def test_hydra_ssh(self):
        plugin = HydraPlugin()
        params = plugin.InputSchema(
            target="192.168.1.1", service="ssh",
            username="admin", password_file="/usr/share/wordlists/rockyou.txt"
        )
        cmd = plugin.build_command(params)
        assert cmd[0] == "hydra"
        assert "-l" in cmd
        assert "admin" in cmd
        assert "ssh" in cmd

    def test_trivy_image(self):
        plugin = TrivyPlugin()
        params = plugin.InputSchema(target="nginx:latest", scan_type="image")
        cmd = plugin.build_command(params)
        assert cmd[0] == "trivy"
        assert "image" in cmd
        assert "--format" in cmd
        assert "json" in cmd

    def test_subfinder_basic(self):
        plugin = SubfinderPlugin()
        params = plugin.InputSchema(target="example.com")
        cmd = plugin.build_command(params)
        assert cmd[0] == "subfinder"
        assert "-d" in cmd
        assert "-silent" in cmd

    def test_ffuf_does_not_request_dev_stdout(self):
        # "-of json -o /dev/stdout" used to be here and reliably crashed ffuf
        # ("open /dev/stdout: no such device or address") because the runner
        # already holds stdout open as a pipe. Confirmed against the real
        # 2.1.0-dev binary; must never come back.
        plugin = FfufPlugin()
        params = plugin.InputSchema(target="http://example.com/FUZZ")
        cmd = plugin.build_command(params)
        assert "/dev/stdout" not in cmd

    def test_ffuf_parses_real_output(self, tmp_path):
        # End-to-end against the real binary: strips the ANSI cursor-control
        # codes ffuf uses to redraw its progress line, which otherwise land
        # inside the captured filename (confirmed while building this fix —
        # an ANSI-agnostic version of this test would have passed anyway).
        ffuf = shutil.which("ffuf")
        if not ffuf:
            pytest.skip("ffuf binary not installed")

        (tmp_path / "found.txt").write_text("ok")
        wordlist = tmp_path / "wordlist.txt"
        wordlist.write_text("found.txt\nmissing.txt\n")

        with socketserver.TCPServer(("127.0.0.1", 0), functools.partial(
            http.server.SimpleHTTPRequestHandler, directory=str(tmp_path)
        )) as httpd:
            port = httpd.server_address[1]
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                plugin = FfufPlugin()
                params = plugin.InputSchema(
                    target=f"http://127.0.0.1:{port}/FUZZ", wordlist=str(wordlist),
                )
                cmd = plugin.build_command(params)
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                assert proc.returncode == 0, proc.stderr
                result = plugin.parse_output(proc.stdout, proc.stderr, proc.returncode)
                assert result.parsed_data["total"] == 1
                assert result.parsed_data["discovered"][0]["input"] == "found.txt"
            finally:
                httpd.shutdown()

    def test_nikto_does_not_request_dev_stdout(self):
        # "-Format json -output /dev/stdout" used to be here. Nikto silently
        # rewrites that to "/dev/stdout.json" whenever -Format is json,
        # which isn't a real path, and the whole scan fails to write its
        # report and exits non-zero (confirmed against the real 2.6.0
        # binary). Must never come back.
        plugin = NiktoPlugin()
        params = plugin.InputSchema(target="http://example.com")
        cmd = plugin.build_command(params)
        assert "/dev/stdout" not in cmd

    def test_nikto_severity_keywords_use_word_boundaries(self):
        # A plain substring check for "rce" previously misclassified this
        # exact real Nikto message as HIGH severity, because "force" contains
        # "rce". Confirmed live, then fixed with \b-bounded regexes.
        plugin = NiktoPlugin()
        stdout = (
            "- Nikto v2.6.0\n"
            "+ Target IP:          127.0.0.1\n"
            "+ No CGI Directories found (use '-C all' to force check all possible dirs)\n"
            "+ 1 host(s) tested\n"
        )
        result = plugin.parse_output(stdout, "", 0)
        assert len(result.findings) == 1
        assert result.findings[0].severity.value == "medium"

    def test_nikto_parses_real_output(self):
        # End-to-end against the real binary and a throwaway local server —
        # the scenario that caught both the /dev/stdout crash and the OSVDB
        # filter matching nothing on a modern Nikto version.
        nikto = shutil.which("nikto")
        if not nikto:
            pytest.skip("nikto binary not installed")

        with socketserver.TCPServer(("127.0.0.1", 0), http.server.SimpleHTTPRequestHandler) as httpd:
            port = httpd.server_address[1]
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                plugin = NiktoPlugin()
                params = plugin.InputSchema(target=f"http://127.0.0.1:{port}")
                cmd = plugin.build_command(params)
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
                assert proc.returncode == 0, proc.stderr
                result = plugin.parse_output(proc.stdout, proc.stderr, proc.returncode)
                assert result.parsed_data["total"] > 0, proc.stdout
            finally:
                httpd.shutdown()

    def test_amass_passive_no_output_gets_explanatory_note(self):
        # Amass's own documented behavior in -passive mode: it stores
        # discovered names in its local graph database and prints none to
        # stdout/stderr at all (confirmed against the real v4.1.0 binary; no
        # flag changes this). Silently reporting "0 subdomains" here would
        # read as "this domain has none", which is not what happened.
        plugin = AmassPlugin()
        stderr = (
            "Passive mode does not generate output during the enumeration\n"
            "\tObtain your list of FQDNs using the following command:\n"
            "\tamass db -names -d example.com\n\n"
            "The enumeration has finished"
        )
        result = plugin.parse_output("", stderr, 0)
        assert result.parsed_data["total"] == 0
        assert "note" in result.parsed_data
        assert "amass db -names" in result.parsed_data["note"]
        # Real failures (bad flags, network errors) must still surface as
        # errors rather than being swallowed by the passive-mode note.
        assert result.error_message == ""

    def test_amass_genuine_failure_still_reports_error(self):
        plugin = AmassPlugin()
        result = plugin.parse_output("", "flag provided but not defined: -bogus", 1)
        assert result.parsed_data["total"] == 0
        assert "note" not in result.parsed_data
        assert result.error_message


class TestOutputParsing:
    """Verify plugins can parse output correctly."""

    def test_nmap_xml_parsing(self):
        plugin = NmapPlugin()
        xml_output = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <status state="up"/>
    <address addr="192.168.1.1" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="22">
        <state state="open"/>
        <service name="ssh" product="OpenSSH" version="8.9"/>
      </port>
      <port protocol="tcp" portid="80">
        <state state="open"/>
        <service name="http" product="nginx" version="1.18"/>
      </port>
    </ports>
  </host>
  <runstats><finished elapsed="5.23" summary="1 host up"/><hosts up="1" down="0" total="1"/></runstats>
</nmaprun>"""
        result = plugin.parse_output(xml_output, "", 0)
        assert result.success
        assert len(result.findings) == 2  # Two open ports
        assert result.parsed_data["hosts"][0]["ports"][0]["port"] == 22
        assert result.parsed_data["hosts"][0]["ports"][0]["service"] == "ssh"

    def test_subfinder_parsing(self):
        plugin = SubfinderPlugin()
        output = "sub1.example.com\nsub2.example.com\napi.example.com\n"
        result = plugin.parse_output(output, "", 0)
        assert result.success
        assert len(result.findings) == 3
        assert result.parsed_data["total"] == 3

    def test_hydra_credential_parsing(self):
        plugin = HydraPlugin()
        output = "[22][ssh] host: 192.168.1.1   login: admin   password: password123\n"
        result = plugin.parse_output(output, "", 0)
        assert result.success
        assert len(result.findings) == 1
        assert result.findings[0].severity.value == "critical"


class TestRegistry:
    """Verify the plugin registry works."""

    def test_auto_discover(self, loaded_registry):
        assert len(loaded_registry) >= 10  # We have 12 plugins

    def test_get_by_name(self, loaded_registry):
        nmap = loaded_registry.get("nmap")
        assert nmap is not None
        assert nmap.name == "nmap"

    def test_get_by_category(self, loaded_registry):
        network = loaded_registry.get_by_category(ToolCategory.NETWORK)
        assert "nmap" in network

    def test_summary(self, loaded_registry):
        summary = loaded_registry.summary()
        assert summary["total_plugins"] >= 10
        assert "plugins" in summary
