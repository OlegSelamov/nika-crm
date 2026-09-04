"""Early runtime setup for Nika Business."""
import os
import socket
from dotenv import load_dotenv

# Always load the runtime env from the project directory unless explicitly overridden.
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_NAME = os.getenv("NIKA_ENV_FILE", ".env")
_ENV_PATH = _ENV_NAME if os.path.isabs(_ENV_NAME) else os.path.join(_PROJECT_DIR, _ENV_NAME)
load_dotenv(_ENV_PATH, override=True)

# The VPS currently has working IPv4 but a broken IPv6 route to api.openai.com.
# httpx/OpenAI normally resolves both families, so a dead IPv6 path can stall
# connections for many seconds before falling back. Force only OpenAI API DNS
# lookups to IPv4; leave every other host and protocol untouched.
_original_getaddrinfo = socket.getaddrinfo


def _nika_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        hostname = host.decode("ascii", "ignore") if isinstance(host, bytes) else str(host or "")
    except Exception:
        hostname = ""

    if hostname.rstrip(".").lower() == "api.openai.com" and family in (0, socket.AF_UNSPEC):
        family = socket.AF_INET

    return _original_getaddrinfo(host, port, family, type, proto, flags)


socket.getaddrinfo = _nika_getaddrinfo
