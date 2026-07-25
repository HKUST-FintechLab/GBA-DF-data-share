"""The connection configuration an administrator hands to a partner institution.

Version 1 carries only how to reach the federation. Version 2 additionally embeds the
coordinator-signed institution invitation (see invitations.py), so a partner performs one
import instead of juggling a URL, a password, a node id, and a separate invitation file.

Exported files may contain the shared password, so every write is atomic and mode 0600.
They are runtime secrets: distribute them over an approved channel and never commit them.
"""
import json
import os
import tempfile
from urllib.parse import urlparse

CLIENT_CONFIG_FORMAT = "gba-df-client-config"
CLIENT_CONFIG_VERSION = 1              # connection details only
CLIENT_CONFIG_INVITED_VERSION = 2      # connection details + signed institution invitation
SUPPORTED_VERSIONS = (CLIENT_CONFIG_VERSION, CLIENT_CONFIG_INVITED_VERSION)


def clean_coordinator_url(coordinator_url: str) -> str:
    """Return a bare http(s) origin, or raise ValueError.

    Credentials, paths, and queries are refused so an exported config cannot smuggle a
    token into a URL or point a partner at an unexpected endpoint path.
    """
    url = str(coordinator_url or "").strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("public coordinator URL must be a full http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("public coordinator URL must not contain credentials")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise ValueError("public coordinator URL must not include a path, query, or fragment")
    return url


def build(coordinator_url: str, *, password: str = "", cohort: int = None,
          modality: str = None, node_id: str = None, display_name: str = None,
          invitation: dict = None) -> dict:
    """Assemble a client configuration. Including `invitation` produces a version 2 file."""
    config = {
        "format": CLIENT_CONFIG_FORMAT,
        "version": CLIENT_CONFIG_INVITED_VERSION if invitation else CLIENT_CONFIG_VERSION,
        "coordinator_url": clean_coordinator_url(coordinator_url),
        "password_required": bool(password),
    }
    if cohort is not None:
        config["cohort"] = int(cohort)
    if modality is not None:
        config["modality"] = modality
    if node_id:
        config["node_id"] = node_id
    if display_name:
        config["display_name"] = display_name
    if password:
        config["password"] = password
    if invitation:
        config["invitation"] = invitation
    return config


def write(path: str, config: dict) -> str:
    """Atomically write a client configuration with owner-only permissions."""
    out = os.path.abspath(os.path.expanduser(path))
    parent = os.path.dirname(out) or "."
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".gba-df-client-config-", suffix=".json", dir=parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, out)
        os.chmod(out, 0o600)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return out
