import contextlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ownserver.ngrok_tunnel import (
    NgrokTunnelError,
    default_config_path,
    open_tunnel,
    resolve_auth_token,
)


class NgrokConfigPathTests(unittest.TestCase):
    def test_linux_uses_xdg_config_home_when_set(self):
        with TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory) / "home"
            config_home = Path(temporary_directory) / "config"

            self.assertEqual(
                default_config_path(
                    "Linux",
                    home=home,
                    environ={"XDG_CONFIG_HOME": str(config_home)},
                ),
                config_home / "ngrok" / "ngrok.yml",
            )

    def test_linux_uses_home_config_directory_by_default(self):
        with TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory)

            self.assertEqual(
                default_config_path("Linux", home=home, environ={}),
                home / ".config" / "ngrok" / "ngrok.yml",
            )

    def test_macos_uses_application_support_directory(self):
        with TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory)

            self.assertEqual(
                default_config_path("Darwin", home=home, environ={}),
                home / "Library" / "Application Support" / "ngrok" / "ngrok.yml",
            )

    def test_windows_uses_local_app_data(self):
        with TemporaryDirectory() as temporary_directory:
            local_app_data = Path(temporary_directory) / "AppData" / "Local"
            home = Path(temporary_directory) / "home"

            self.assertEqual(
                default_config_path(
                    "Windows",
                    home=home,
                    environ={"LOCALAPPDATA": str(local_app_data)},
                ),
                local_app_data / "ngrok" / "ngrok.yml",
            )

    def test_windows_uses_home_fallback_without_local_app_data(self):
        with TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory)

            self.assertEqual(
                default_config_path("Windows", home=home, environ={}),
                home / "AppData" / "Local" / "ngrok" / "ngrok.yml",
            )


class NgrokAuthTokenTests(unittest.TestCase):
    def _write_config(self, home, contents, system="Linux", environ=None):
        environ = {} if environ is None else environ
        path = default_config_path(system, home=home, environ=environ)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        return path

    def test_environment_token_takes_precedence_and_skips_config(self):
        with TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory)
            self._write_config(home, "invalid: [yaml", system="Linux")

            token = resolve_auth_token(
                environ={"NGROK_AUTHTOKEN": "  environment-secret  "},
                system="Linux",
                home=home,
            )

            self.assertEqual(token, "environment-secret")

    def test_config_token_is_used_when_environment_is_missing(self):
        with TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory)
            self._write_config(
                home,
                'version: "3"\nagent:\n  authtoken: "file-secret"\n',
            )

            self.assertEqual(
                resolve_auth_token(environ={}, system="Linux", home=home),
                "file-secret",
            )

    def test_blank_environment_token_falls_back_to_config(self):
        with TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory)
            self._write_config(
                home,
                'version: "3"\nagent:\n  authtoken: "file-secret"\n',
            )

            self.assertEqual(
                resolve_auth_token(
                    environ={"NGROK_AUTHTOKEN": "  "},
                    system="Linux",
                    home=home,
                ),
                "file-secret",
            )

    def test_missing_config_reports_both_configuration_options(self):
        with TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(
                NgrokTunnelError, "No ngrok authtoken found"
            ) as error:
                resolve_auth_token(
                    environ={}, system="Linux", home=temporary_directory
                )

            self.assertIn("NGROK_AUTHTOKEN", str(error.exception))
            self.assertIn("agent.authtoken", str(error.exception))

    def test_invalid_yaml_has_clear_error_without_echoing_contents(self):
        with TemporaryDirectory() as temporary_directory:
            self._write_config(
                Path(temporary_directory),
                'agent:\n  authtoken: "secret-token"\n  invalid: [\n',
            )

            with self.assertRaisesRegex(NgrokTunnelError, "not valid YAML") as error:
                resolve_auth_token(environ={}, system="Linux", home=temporary_directory)

            self.assertNotIn("secret-token", str(error.exception))

    def test_non_utf8_config_reports_clear_error(self):
        with TemporaryDirectory() as temporary_directory:
            config_path = default_config_path(
                "Linux", home=temporary_directory, environ={}
            )
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_bytes(b"agent:\n  authtoken: \xff\n")

            with self.assertRaisesRegex(NgrokTunnelError, "must use UTF-8"):
                resolve_auth_token(environ={}, system="Linux", home=temporary_directory)

    def test_config_without_agent_token_reports_clear_error(self):
        with TemporaryDirectory() as temporary_directory:
            self._write_config(Path(temporary_directory), 'version: "3"\n')

            with self.assertRaisesRegex(
                NgrokTunnelError, "No agent.authtoken found"
            ):
                resolve_auth_token(environ={}, system="Linux", home=temporary_directory)

    def test_unsupported_system_can_still_use_environment_token(self):
        self.assertEqual(
            resolve_auth_token(
                environ={"NGROK_AUTHTOKEN": "environment-secret"},
                system="Plan9",
            ),
            "environment-secret",
        )

    def test_unsupported_system_without_environment_token_reports_error(self):
        with self.assertRaisesRegex(NgrokTunnelError, "config path is unknown"):
            resolve_auth_token(environ={}, system="Plan9")

    def test_sdk_receives_explicit_token(self):
        listener = Mock()
        listener.url.return_value = "https://example.ngrok.app"
        sdk = SimpleNamespace(forward=Mock(return_value=listener), disconnect=Mock())

        with patch.dict("sys.modules", {"ngrok": sdk}):
            tunnel = open_tunnel(8000, auth_token="file-secret")

        sdk.forward.assert_called_once_with("127.0.0.1:8000", authtoken="file-secret")
        self.assertEqual(tunnel.url, "https://example.ngrok.app")

    def test_sdk_error_redacts_token_from_config(self):
        sdk = SimpleNamespace(
            forward=Mock(side_effect=RuntimeError("invalid token file-secret")),
            disconnect=Mock(),
        )

        with patch.dict("sys.modules", {"ngrok": sdk}):
            with self.assertRaises(NgrokTunnelError) as error:
                open_tunnel(8000, auth_token="file-secret")

        self.assertNotIn("file-secret", str(error.exception))
        self.assertIn("[redacted]", str(error.exception))


class NoNgrokStartupTests(unittest.TestCase):
    def test_no_ngrok_skips_token_resolution(self):
        with TemporaryDirectory() as temporary_directory:
            server = Mock()
            server.server_address = ("127.0.0.1", 8000)
            server.serve_forever.side_effect = KeyboardInterrupt

            with (
                patch("ownserver.app.resolve_auth_token", side_effect=AssertionError),
                patch("ownserver.app.open_tunnel") as open_tunnel_mock,
                patch("ownserver.app.create_server", return_value=server),
                patch("ownserver.app.StatusLine"),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                from ownserver.app import main

                exit_code = main(
                    ["-p", "8000", "--no-ngrok", temporary_directory]
                )

            self.assertEqual(exit_code, 0)
            open_tunnel_mock.assert_not_called()
            server.server_close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
