"""Detect URLs for reaching the Comida UI (LAN, Tailscale)."""

from __future__ import annotations

import re
import socket
import subprocess

LOCAL_LABEL = "local"
LAN_LABEL = "lan"
TAILSCALE_LABEL = "tailscale"

LABELS_FR = {
    LOCAL_LABEL: "Mac (local)",
    LAN_LABEL: "Wi‑Fi (même réseau)",
    TAILSCALE_LABEL: "Tailscale (autre réseau)",
}


def _lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
        if ip and ip != "127.0.0.1":
            return ip
    except OSError:
        pass
    return None


def _tailscale_ip() -> str | None:
    try:
        proc = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                ip = line.strip()
                if ip.startswith("100."):
                    return ip
    except (OSError, subprocess.TimeoutExpired):
        pass

    try:
        proc = subprocess.run(
            ["ifconfig"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if proc.returncode == 0:
            for match in re.finditer(r"inet (100\.\d+\.\d+\.\d+)", proc.stdout):
                return match.group(1)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def access_urls(port: int) -> list[dict]:
    entries: list[dict] = [
        {
            "label": LOCAL_LABEL,
            "url": f"http://127.0.0.1:{port}",
            "description": LABELS_FR[LOCAL_LABEL],
        },
    ]
    lan = _lan_ip()
    if lan:
        entries.append({
            "label": LAN_LABEL,
            "url": f"http://{lan}:{port}",
            "description": LABELS_FR[LAN_LABEL],
        })
    ts = _tailscale_ip()
    if ts:
        entries.append({
            "label": TAILSCALE_LABEL,
            "url": f"http://{ts}:{port}",
            "description": LABELS_FR[TAILSCALE_LABEL],
            "preferred_mobile": True,
        })
    return entries


def print_access_urls(port: int) -> None:
    urls = access_urls(port)
    print(f"Comida UI — http://127.0.0.1:{port}  (Ctrl+C pour arrêter)")
    for entry in urls:
        if entry["label"] == LOCAL_LABEL:
            continue
        star = "★ " if entry.get("preferred_mobile") else "  "
        print(f"{star}{entry['description']} : {entry['url']}")
    if not any(e["label"] == TAILSCALE_LABEL for e in urls):
        print("  Tailscale : installez Tailscale sur le Mac et le téléphone pour l'accès hors Wi‑Fi")


def format_access_message(port: int, *, recipe: str | None = None) -> str:
    """Telegram-friendly summary of mobile access URLs."""
    urls = access_urls(port)
    lines = ["📱 Comida — interface mobile"]
    if recipe:
        lines.append(recipe)

    mobile = next((e for e in urls if e.get("preferred_mobile")), None)
    if mobile:
        lines.append(f"\n★ {mobile['description']} :\n{mobile['url']}")

    for entry in urls:
        if entry["label"] == LOCAL_LABEL or entry.get("preferred_mobile"):
            continue
        lines.append(f"\n{entry['description']} :\n{entry['url']}")

    if not any(e["label"] != LOCAL_LABEL for e in urls):
        lines.append(f"\nhttp://127.0.0.1:{port} (Mac uniquement)")

    lines.append("\nLe Mac doit rester allumé pendant la validation.")
    return "\n".join(lines)
