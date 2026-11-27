"""Lifecycle wrapper around the official ngrok Python SDK."""

import os
import platform
from pathlib import Path

import yaml


class NgrokTunnelError(RuntimeError):
    """Raised when an ngrok tunnel cannot be opened or closed."""


class NgrokTunnel:
    """Hold an ngrok listener and close it through the SDK on shutdown."""

    def __init__(self, sdk, listener):
        self._sdk = sdk
        self._listener = listener

    @property
    def url(self):
        return self._listener.url()

    def close(self):
        self._sdk.disconnect(self.url)


def default_config_path(system=None, home=None, environ=None):
    """Return ngrok's default agent configuration path for an operating system."""
    system = system or platform.system()
    home = Path.home() if home is None else Path(home)
    environ = os.environ if environ is None else environ

    if system == "Linux":
        config_home = environ.get("XDG_CONFIG_HOME")
        if config_home:
            return Path(config_home) / "ngrok" / "ngrok.yml"
        return home / ".config" / "ngrok" / "ngrok.yml"
    if system == "Darwin":
        return home / "Library" / "Application Support" / "ngrok" / "ngrok.yml"
    if system == "Windows":
        local_app_data = environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "ngrok" / "ngrok.yml"
        return home / "AppData" / "Local" / "ngrok" / "ngrok.yml"
    return None


def resolve_auth_token(environ=None, system=None, home=None):
    """Resolve the ngrok token from the environment or the default config file."""
    environ = os.environ if environ is None else environ
    token = environ.get("NGROK_AUTHTOKEN", "").strip()
    if token:
        return token

    config_path = default_config_path(system=system, home=home, environ=environ)
    if config_path is None:
        raise NgrokTunnelError(
            "NGROK_AUTHTOKEN is not set and the ngrok config path is unknown for "
            "this operating system; set NGROK_AUTHTOKEN or use --no-ngrok."
        )

    try:
        config_text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise NgrokTunnelError(
            "No ngrok authtoken found. Set NGROK_AUTHTOKEN or add agent.authtoken "
            "to {}. Use --no-ngrok for local-only serving.".format(config_path)
        ) from error
    except UnicodeError as error:
        raise NgrokTunnelError(
            "The ngrok config file at {} must use UTF-8 encoding.".format(config_path)
        ) from error
    except OSError as error:
        raise NgrokTunnelError(
            "Could not read the ngrok config file at {}: {}".format(config_path, error)
        ) from error

    try:
        config = yaml.safe_load(config_text)
    except yaml.YAMLError as error:
        raise NgrokTunnelError(
            "The ngrok config file at {} is not valid YAML.".format(config_path)
        ) from error

    agent = config.get("agent") if isinstance(config, dict) else None
    token = agent.get("authtoken") if isinstance(agent, dict) else None
    if not isinstance(token, str) or not token.strip():
        raise NgrokTunnelError(
            "No agent.authtoken found in the ngrok config file at {}. Set "
            "NGROK_AUTHTOKEN or add agent.authtoken to the file.".format(config_path)
        )
    return token.strip()


def open_tunnel(port, domain=None, host="127.0.0.1", auth_token=None):
    """Open an ngrok HTTP tunnel to the local server."""
    if auth_token is None or not auth_token.strip():
        auth_token = resolve_auth_token()
    else:
        auth_token = auth_token.strip()
    try:
        import ngrok
    except Exception as error:
        raise NgrokTunnelError(
            "Could not load the ngrok SDK; run `uv sync` to install dependencies: {}".format(
                error
            )
        ) from error

    options = {"authtoken": auth_token}
    if domain:
        options["domain"] = domain
    if host in ("", "0.0.0.0", "::"):
        host = "localhost"
    if ":" in host and not host.startswith("["):
        host = "[{}]".format(host)
    address = "{}:{}".format(host, port)
    try:
        listener = ngrok.forward(address, **options)
    except Exception as error:
        detail = str(error).replace(auth_token, "[redacted]")
        raise NgrokTunnelError(
            "Failed to start ngrok tunnel: {}".format(detail)
        ) from error
    return NgrokTunnel(ngrok, listener)
