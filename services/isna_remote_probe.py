"""Read-only SSH reachability probe through the existing Smart Bridge VPN host.

The TEST web app can invoke only the configured SSH identity, hostname and
fixed "probe" command. The VPN host must independently enforce a dedicated
authorized_keys forced command with forwarding disabled. No filing, raw XML,
EDS, token or password crosses this channel.
"""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess

EXPECTED_VPN_HOST = "195.49.215.49"


def probe_configured() -> bool:
    return bool((os.getenv("ISNA_BIP_DIAG_SSH_HOST") or "").strip())


def probe_vpn_host() -> dict:
    """Return safe result. Never expose SSH stderr or any secrets in the API."""
    if (os.getenv("APP_MODE") or "").lower().strip() != "test":
        return {"ok": False, "configured": False, "reason": "test_only"}

    host = (os.getenv("ISNA_BIP_DIAG_SSH_HOST") or "").strip()
    key_path = (os.getenv("ISNA_BIP_DIAG_SSH_KEY") or "").strip()
    known_hosts = (os.getenv("ISNA_BIP_DIAG_SSH_KNOWN_HOSTS") or "").strip()
    user = (os.getenv("ISNA_BIP_DIAG_SSH_USER") or "isna-probe").strip()
    port_text = (os.getenv("ISNA_BIP_DIAG_SSH_PORT") or "22").strip()

    if not host:
        return {"ok": False, "configured": False, "reason": "not_configured"}

    try:
        if str(ipaddress.ip_address(host)) != EXPECTED_VPN_HOST:
            raise ValueError("Invalid pinned host")
        if user != "isna-probe":
            raise ValueError("Invalid probe user")
        port = int(port_text)
        if not 1 <= port <= 65535:
            raise ValueError("Invalid probe port")
        # Absolute paths only; no shell expansion or injected SSH arguments.
        for path in (key_path, known_hosts):
            if not path or not Path(path).is_absolute() or not Path(path).is_file():
                raise ValueError("Probe credentials unavailable")
    except ValueError:
        return {"ok": False, "configured": True, "reason": "bad_config"}

    if shutil.which("ssh") is None:
        return {"ok": False, "configured": True, "reason": "ssh_unavailable"}

    command = [
        "ssh", "-T", "-F", "/dev/null",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "PasswordAuthentication=no",
        "-o", "KbdInteractiveAuthentication=no",
        "-o", "IdentitiesOnly=yes",
        "-o", "ClearAllForwardings=yes",
        "-o", "ControlMaster=no",
        "-o", "ProxyCommand=none",
        "-o", "ConnectTimeout=5",
        "-o", "ConnectionAttempts=1",
        "-o", "LogLevel=ERROR",
        "-o", f"UserKnownHostsFile={known_hosts}",
        "-i", key_path,
        "-p", str(port),
        f"{user}@{host}",
        "probe",  # overridden by the VPN host's authorized_keys forced command
    ]
    try:
        completed = subprocess.run(
            command, input="", capture_output=True, text=True,
            timeout=13, check=False,
        )
        if completed.returncode != 0 or len(completed.stdout) > 2048:
            return {"ok": False, "configured": True, "reason": "connection_failed"}
        payload = json.loads(completed.stdout)
        if not isinstance(payload, dict) or payload.get("schema") != 1:
            raise ValueError("Unexpected response")
        tcp = payload.get("tcpOk")
        http = payload.get("httpOk")
        status = payload.get("httpStatus")
        if type(tcp) is not bool or type(http) is not bool:
            raise ValueError("Invalid probe results")
        if status is not None and (type(status) is not int or status < 100 or status > 599):
            raise ValueError("Invalid HTTP status")
        return {
            "ok": True, "configured": True, "tcpOk": tcp,
            "httpOk": http, "httpStatus": status,
        }
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "configured": True, "reason": "connection_failed"}
    except (ValueError, TypeError, json.JSONDecodeError):
        return {"ok": False, "configured": True, "reason": "invalid_reply"}
