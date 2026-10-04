"""외부 접속 기본값과 HTTP Host/키 파일의 경계를 고정한다."""

import subprocess
from pathlib import Path

from django.test import RequestFactory, SimpleTestCase, override_settings
from server.conf import settings as project_settings
from server.conf.mssp import MSSPTable


class NetworkSettingsTests(SimpleTestCase):
    def test_public_services_use_all_ipv4_with_stable_ports(self):
        for name, port in (("TELNET", 8700), ("SSL", 8703), ("SSH", 8704)):
            with self.subTest(service=name):
                self.assertIs(getattr(project_settings, name + "_ENABLED"), True)
                self.assertEqual(getattr(project_settings, name + "_PORTS"), [port])
                self.assertEqual(getattr(project_settings, name + "_INTERFACES"), ["0.0.0.0"])
        self.assertIs(project_settings.WEBSERVER_ENABLED, True)
        self.assertEqual(project_settings.WEBSERVER_PORTS, [(8701, 8705)])
        self.assertEqual(project_settings.WEBSERVER_INTERFACES, ["0.0.0.0"])
        self.assertIs(project_settings.WEBSOCKET_CLIENT_ENABLED, True)
        self.assertEqual(project_settings.WEBSOCKET_CLIENT_PORT, 8702)
        self.assertEqual(project_settings.WEBSOCKET_CLIENT_INTERFACE, "0.0.0.0")
        self.assertEqual(project_settings.AMP_PORT, 8706)
        self.assertEqual(project_settings.AMP_INTERFACE, "127.0.0.1")
        self.assertEqual(MSSPTable["PORT"], ["8700"])

    def test_http_host_accepts_lan_ip_and_hostname(self):
        self.assertEqual(project_settings.ALLOWED_HOSTS, ["*"])
        with override_settings(ALLOWED_HOSTS=project_settings.ALLOWED_HOSTS):
            for host in ("localhost:8701", "192.168.1.100:8701", "game.example:8701"):
                with self.subTest(host=host):
                    request = RequestFactory().get("/webclient/", HTTP_HOST=host)
                    self.assertEqual(request.get_host(), host)

    def test_generated_key_files_are_ignored_and_untracked(self):
        root = Path(__file__).resolve().parents[2]
        paths = ["game/server/" + name for name in (
            "ssl.key", "ssl-public.key", "ssl.cert", "ssh-private.key", "ssh-public.key")]
        ignored = subprocess.run(["git", "check-ignore", "--no-index", *paths],
                                 cwd=root, capture_output=True, text=True, check=True)
        self.assertEqual(set(ignored.stdout.splitlines()), set(paths))
        tracked = subprocess.run(["git", "ls-files", "--", *paths],
                                 cwd=root, capture_output=True, text=True, check=True)
        self.assertEqual(tracked.stdout, "")
