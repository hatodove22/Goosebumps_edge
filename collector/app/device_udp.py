from __future__ import annotations

import json
import socket
from typing import Any, Dict, Optional, Tuple


def send_udp_json(host: str, port: int, payload: Dict[str, Any], timeout_sec: float = 0.2) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Send a JSON payload over UDP and wait for a JSON response (best effort).
    """
    data = json.dumps(payload).encode("utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout_sec)
    try:
        sock.sendto(data, (host, port))
        try:
            resp, _ = sock.recvfrom(2048)
            try:
                return True, json.loads(resp.decode("utf-8", errors="ignore"))
            except Exception:
                return True, None
        except socket.timeout:
            return True, None
    except Exception:
        return False, None
    finally:
        sock.close()

def send_udp_json_oneway(host: str, port: int, payload: Dict[str, Any]) -> bool:
    """Send a JSON payload over UDP without waiting for response."""
    try:
        data = json.dumps(payload).encode("utf-8")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(data, (host, port))
        sock.close()
        return True
    except Exception:
        return False

