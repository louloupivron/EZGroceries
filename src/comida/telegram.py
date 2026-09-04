"""Send Comida exports to a Telegram group topic (forum thread)."""

from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_BASE = "https://api.telegram.org/bot{token}/{method}"


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: int | str
    topic_id: int | None = None

    @classmethod
    def from_env(cls, *, require_chat: bool = True) -> TelegramConfig:
        _load_dotenv()
        token = bot_token_from_env()
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        topic_raw = os.environ.get("TELEGRAM_TOPIC_ID", "").strip()
        if require_chat and not chat_id:
            raise RuntimeError(
                "TELEGRAM_CHAT_ID manquant dans .env — lancez : uv run python validate.py telegram-setup"
            )
        topic_id = int(topic_raw) if topic_raw else None
        return cls(bot_token=token, chat_id=chat_id or "0", topic_id=topic_id)


def bot_token_from_env() -> str:
    _load_dotenv()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN manquant dans .env — créez un bot via @BotFather"
        )
    return token


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = val


def _api_json(method: str, payload: dict, *, bot_token: str) -> dict:
    url = API_BASE.format(token=bot_token, method=method)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API {method} : {detail}") from e
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API {method} : {data.get('description', data)}")
    return data


def _api_multipart(
    method: str,
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
    *,
    config: TelegramConfig,
) -> dict:
    boundary = f"----comida-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(f"{value}\r\n".encode())

    for name, (filename, content, mime) in files.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        )
        chunks.append(f"Content-Type: {mime}\r\n\r\n".encode())
        chunks.append(content)
        chunks.append(b"\r\n")

    chunks.append(f"--{boundary}--\r\n".encode())
    body = b"".join(chunks)

    url = API_BASE.format(token=config.bot_token, method=method)
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API {method} : {detail}") from e
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API {method} : {data.get('description', data)}")
    return data


def _base_payload(config: TelegramConfig) -> dict[str, str | int]:
    payload: dict[str, str | int] = {"chat_id": config.chat_id}
    if config.topic_id is not None:
        payload["message_thread_id"] = config.topic_id
    return payload


def send_message(text: str, *, config: TelegramConfig | None = None) -> dict:
    cfg = config or TelegramConfig.from_env()
    payload = {**_base_payload(cfg), "text": text}
    return _api_json("sendMessage", payload, bot_token=cfg.bot_token)


def send_document(
    file_path: Path,
    *,
    caption: str | None = None,
    config: TelegramConfig | None = None,
) -> dict:
    cfg = config or TelegramConfig.from_env()
    content = file_path.read_bytes()
    mime, _ = mimetypes.guess_type(file_path.name)
    fields = {k: str(v) for k, v in _base_payload(cfg).items()}
    if caption:
        fields["caption"] = caption
    return _api_multipart(
        "sendDocument",
        fields,
        {"document": (file_path.name, content, mime or "text/plain")},
        config=cfg,
    )


def send_promos_export(
    file_path: Path,
    list_name: str,
    *,
    config: TelegramConfig | None = None,
) -> dict:
    """Send promo list as Telegram message + attached .txt file."""
    cfg = config or TelegramConfig.from_env()
    content = file_path.read_text(encoding="utf-8").strip()
    lines = [ln for ln in content.splitlines() if ln.strip()]
    header = f"📋 Promos {list_name} — {len(lines)} ingrédient(s)"
    preview = header + "\n\n" + content
    if len(preview) <= 4000:
        send_message(preview, config=cfg)
    else:
        send_message(header + "\n\n(voir fichier joint)", config=cfg)
    return send_document(file_path, caption=header, config=cfg)


def send_text(
    file_path: Path,
    *,
    title: str | None = None,
    config: TelegramConfig | None = None,
) -> dict:
    cfg = config or TelegramConfig.from_env()
    caption = title or file_path.name
    content = file_path.read_text(encoding="utf-8").strip()
    if len(content) <= 4000:
        send_message(f"{caption}\n\n{content}", config=cfg)
    return send_document(file_path, caption=caption, config=cfg)


def get_updates(*, bot_token: str | None = None, offset: int | None = None) -> list[dict]:
    token = bot_token or bot_token_from_env()
    payload: dict[str, int] = {"timeout": 0}
    if offset is not None:
        payload["offset"] = offset
    data = _api_json("getUpdates", payload, bot_token=token)
    return data.get("result", [])


def discover_targets(*, bot_token: str | None = None) -> list[dict]:
    """List recent group/topic targets seen by the bot."""
    updates = get_updates(bot_token=bot_token)
    seen: set[tuple[str, str | None]] = set()
    targets: list[dict] = []

    for update in updates:
        message = update.get("message") or update.get("channel_post")
        if message:
            chat = message.get("chat") or {}
            chat_type = chat.get("type")
            if chat_type not in ("group", "supergroup"):
                continue
            chat_id = str(chat.get("id"))
            thread_id = message.get("message_thread_id")
            key = (chat_id, str(thread_id) if thread_id is not None else None)
            if key in seen:
                continue
            seen.add(key)
            targets.append({
                "chat_id": chat_id,
                "chat_title": chat.get("title") or chat.get("username") or "?",
                "topic_id": thread_id,
                "topic_label": "General" if thread_id is None else f"topic {thread_id}",
                "from_user": (message.get("from") or {}).get("first_name"),
                "text_preview": (message.get("text") or "")[:80],
                "source": "message",
            })
            continue

        member = update.get("my_chat_member") or update.get("chat_member")
        if member:
            chat = member.get("chat") or {}
            chat_type = chat.get("type")
            if chat_type not in ("group", "supergroup"):
                continue
            chat_id = str(chat.get("id"))
            key = (chat_id, "member")
            if key in seen:
                continue
            seen.add(key)
            new_status = (member.get("new_chat_member") or {}).get("status")
            targets.append({
                "chat_id": chat_id,
                "chat_title": chat.get("title") or chat.get("username") or "?",
                "topic_id": None,
                "topic_label": f"bot {new_status or 'update'} (pas de topic — envoyez un msg dans Comida)",
                "from_user": None,
                "text_preview": "",
                "source": "member",
            })
    return targets


def format_setup_instructions() -> str:
    return """
Configuration Telegram (topic Comida)

1. Créez un bot : parlez à @BotFather → /newbot → copiez le token
2. Ajoutez TELEGRAM_BOT_TOKEN dans .env
3. Invitez le bot dans le groupe « Betty's coloc » (ou votre coloc)
4. Envoyez un message dans le topic « Comida » (ex. « test comida »)
5. Relancez : uv run python validate.py telegram-setup

Le script affichera TELEGRAM_CHAT_ID et TELEGRAM_TOPIC_ID à copier dans .env.
""".strip()


def run_telegram_setup() -> None:
    _load_dotenv()
    if not os.environ.get("TELEGRAM_BOT_TOKEN", "").strip():
        print(format_setup_instructions())
        print()
        print("⚠ TELEGRAM_BOT_TOKEN absent — commencez par l’étape 1.")
        return

    print(format_setup_instructions())
    print()
    print("Messages récents vus par le bot :")
    print()

    try:
        targets = discover_targets()
    except RuntimeError as e:
        print(f"Erreur : {e}")
        return

    if not targets:
        print("  (aucun message de groupe reçu)")
        print()
        print("Le bot n'a encore rien reçu de Telegram. Essayez dans l'ordre :")
        print()
        print("  1. Retirer @JeanThimBot du groupe, puis le ré-ajouter")
        print("  2. Dans le topic Comida, envoyer : @JeanThimBot test")
        print("  3. Relancer : uv run python validate.py telegram-setup")
        print()
        print("Plan B — ids manuels (sans attendre le bot) :")
        print("  • Ajoutez @getidsbot au groupe → il affiche le TELEGRAM_CHAT_ID")
        print("  • Transférez un message du topic Comida à @RawDataBot")
        print("    → cherchez chat.id et message_thread_id dans le JSON")
        return

    for i, t in enumerate(targets, 1):
        topic = "General (pas de topic)" if t["topic_id"] is None else f"topic id={t['topic_id']}"
        print(f"  {i}. {t['chat_title']} — {topic}")
        print(f"     TELEGRAM_CHAT_ID={t['chat_id']}")
        if t["topic_id"] is not None:
            print(f"     TELEGRAM_TOPIC_ID={t['topic_id']}")
        if t["text_preview"]:
            print(f"     message : « {t['text_preview']} »")
        print()

    print("Copiez les lignes du topic Comida dans .env, puis testez :")
    print("  uv run python validate.py telegram-test")


def run_telegram_test() -> None:
    cfg = TelegramConfig.from_env()
    topic = f"topic {cfg.topic_id}" if cfg.topic_id else "General"
    send_message(f"✅ Comida connecté — test envoyé dans {topic}.", config=cfg)
    print(f"Message de test envoyé (chat {cfg.chat_id}, {topic}).")


def telegram_auto_send_enabled() -> bool:
    _load_dotenv()
    return os.environ.get("TELEGRAM_AUTO_SEND", "").strip().lower() in ("1", "true", "yes")
