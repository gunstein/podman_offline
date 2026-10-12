"""Minimal TLS-verified Proxmox client; token never enters command lines or logs."""

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def env_file(path):
    path = Path(path).expanduser()
    if path.stat().st_mode & 0o077:
        raise RuntimeError("Local lab/token configuration must have mode 0600")
    values = {}
    for line in path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, separator, value = line.partition("=")
            if not separator or key.strip() in values:
                raise RuntimeError("Invalid or duplicate configuration key")
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


class Proxmox:
    def __init__(self, filename):
        self.config = env_file(filename)
        context = ssl.create_default_context(cafile=self.config["PVE_CA"])
        # Proxmox's generated CA lacks Key Usage; retain chain/hostname verification.
        context.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=context),
        )

    def request(self, method, path, form=None):
        cfg = self.config
        path = path.replace("{node}", cfg["PVE_NODE"])
        url = "https://" + cfg["PVE_HOST"] + ":8006/api2/json" + path
        request = urllib.request.Request(
            url,
            data=urllib.parse.urlencode(form).encode() if form else None,
            method=method,
            headers={
                "Authorization": "PVEAPIToken="
                + cfg["PVE_TOKEN_ID"]
                + "="
                + cfg["PVE_TOKEN_SECRET"]
            },
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                return json.load(response)["data"]
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"Proxmox {method} {path}: HTTP {error.code}") from None

    def task(self, path, form=None):
        task = self.request("POST", path, form)
        endpoint = (
            "/nodes/{node}/tasks/" + urllib.parse.quote(task, safe="") + "/status"
        )
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            result = self.request("GET", endpoint)
            if result["status"] == "stopped":
                if result.get("exitstatus") != "OK":
                    raise RuntimeError(
                        "Proxmox task failed: " + result.get("exitstatus", "unknown")
                    )
                return
            time.sleep(2)
        raise RuntimeError("Proxmox task timed out")
