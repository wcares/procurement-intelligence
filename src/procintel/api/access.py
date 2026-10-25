"""Who may call the administrative endpoints (reload, queue a job).

PROCINTEL_ADMIN_CLIENTS: comma-separated client addresses or networks (CIDR) allowed; default this machine only.
In Docker Compose the web container forwards requests, so its network is listed there (for example 172.16.0.0/12).
"""
from __future__ import annotations

import ipaddress
import os

from fastapi import Request
from fastapi.responses import JSONResponse

DEFAULT = "127.0.0.1,::1"


def allowed() -> list:
    out = []
    for part in os.environ.get("PROCINTEL_ADMIN_CLIENTS", DEFAULT).split(","):
        if part.strip():
            out.append(ipaddress.ip_network(part.strip(), strict=False))
    return out


def is_admin_client(request: Request) -> bool:
    if request.client is None:
        return False
    try:
        ip = ipaddress.ip_address(request.client.host)
    except ValueError:
        return False
    return any(ip in net for net in allowed())


def refuse(what: str) -> JSONResponse:
    return JSONResponse({"error": f"{what} is only accepted from an administrative client (PROCINTEL_ADMIN_CLIENTS)"},
                        status_code=403)
