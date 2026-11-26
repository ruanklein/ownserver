"""Lifecycle wrapper around the official ngrok Python SDK."""

import os


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


def require_auth_token():
    """Require the environment token before opening a public tunnel."""
    if not os.environ.get("NGROK_AUTHTOKEN", "").strip():
        raise NgrokTunnelError(
            "NGROK_AUTHTOKEN is required to start ngrok; set it or use --no-ngrok."
        )


def open_tunnel(port, domain=None, host="127.0.0.1"):
    """Open an ngrok HTTP tunnel to the local server."""
    require_auth_token()
    try:
        import ngrok
    except Exception as error:
        raise NgrokTunnelError(
            "Could not load the ngrok SDK; run `uv sync` to install dependencies: {}".format(
                error
            )
        ) from error

    options = {"authtoken_from_env": True}
    if domain:
        options["domain"] = domain
    if host in ("", "0.0.0.0", "::"):
        host = "localhost"
    if ":" in host and not host.startswith("["):
        host = "[{}]".format(host)
    address = "{}:{}".format(host, port)
    token = os.environ.get("NGROK_AUTHTOKEN", "")
    try:
        listener = ngrok.forward(address, **options)
    except Exception as error:
        detail = str(error).replace(token, "[redacted]") if token else str(error)
        raise NgrokTunnelError("Failed to start ngrok tunnel: {}".format(detail)) from error
    return NgrokTunnel(ngrok, listener)
