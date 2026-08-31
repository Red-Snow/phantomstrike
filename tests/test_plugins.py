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
