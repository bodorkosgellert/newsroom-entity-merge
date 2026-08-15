"""
Slack bot for newsroom video intake.
Prefer Socket Mode (no ngrok). Optional HTTP mode behind ngrok.

Env:
  SLACK_BOT_TOKEN=xoxb-...
  SLACK_APP_TOKEN=xapp-...   (Socket Mode)
  SLACK_SIGNING_SECRET=...   (HTTP mode only)
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import requests
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

ROOT = Path(__file__).resolve().parent
INBOX = ROOT / "out" / "slack_inbox"
load_dotenv(ROOT / ".env")

BOT = os.getenv("SLACK_BOT_TOKEN", "").strip()
APP_TOKEN = os.getenv("SLACK_APP_TOKEN", "").strip()

if not BOT:
    raise SystemExit("Set SLACK_BOT_TOKEN in .env (see SLACK_SETUP.md)")

app = App(token=BOT)
INBOX.mkdir(parents=True, exist_ok=True)
_SEEN_FILES: set[str] = set()


def download_slack_file(file_obj: dict) -> Path | None:
    url = file_obj.get("url_private_download") or file_obj.get("url_private")
    name = file_obj.get("name") or f"{file_obj.get('id')}.bin"
    if not url:
        return None
    safe = re.sub(r"[^\w.\-]+", "_", name)
    dest = INBOX / f"{file_obj.get('id')}_{safe}"
    r = requests.get(url, headers={"Authorization": f"Bearer {BOT}"}, timeout=120)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest


def is_video(file_obj: dict) -> bool:
    mt = (file_obj.get("mimetype") or "").lower()
    name = (file_obj.get("name") or "").lower()
    return mt.startswith("video/") or name.endswith((".mp4", ".mov", ".webm", ".mkv", ".m4v"))


@app.event("file_shared")
def on_file_shared(event, client, logger):
    file_id = event.get("file_id")
    if not file_id:
        return
    # Slack often delivers file_shared more than once; only process once per file.
    if file_id in _SEEN_FILES:
        logger.info("skip duplicate file_shared for %s", file_id)
        return
    _SEEN_FILES.add(file_id)

    info = client.files_info(file=file_id)
    f = info.get("file") or {}
    if not is_video(f):
        return

    channels = f.get("channels") or []
    channel = event.get("channel_id") or (channels[0] if channels else None)
    if not channel:
        logger.warning("No channel for file %s", file_id)
        return

    client.chat_postMessage(
        channel=channel,
        text=(
            f"Got *{f.get('name')}*. Indexing with Twelve Labs "
            f"(usually 30–90s) then routing to a desk ticket…"
        ),
    )

    try:
        path = download_slack_file(f)
        if not path:
            client.chat_postMessage(channel=channel, text="Could not download the file.")
            return

        from classify import classify_video

        def progress(msg: str) -> None:
            logger.info("classify: %s", msg)
            if any(k in msg.lower() for k in ("uploading", "indexing", "indexed as")):
                try:
                    client.chat_postMessage(channel=channel, text=f"_{msg}_")
                except Exception:
                    logger.exception("progress post failed")

        result = classify_video(path, progress=progress)
        decision = result.get("decision")
        ticket = result.get("ticket")
        reason = result.get("reason")
        memory_block = result.get("desk_memory_slack") or ""
        source_meta = result.get("source_meta") or {}
        source_line = ""
        if source_meta.get("source_id"):
            source_line = (
                f"*Source intake:* `{source_meta.get('source_id')}` — "
                f"{source_meta.get('outlet')}\n"
                f"_{source_meta.get('episode')}_\n"
            )

        if decision == "flaco":
            text = (
                f"*Same story, new source — merged into existing ticket:* `{ticket}`\n"
                f"{source_line}"
                f"_Reason: {reason or 'n/a'}_\n"
                f"_Slack file: `{f.get('name')}`_\n"
                f"{memory_block}"
            )
        elif decision == "mona":
            text = (
                f"*Matched a different ticket:* `{ticket}` — not the owl story.\n"
                f"Left Flaco’s ticket unchanged.\n"
                f"{source_line}"
                f"_Reason: {reason or 'n/a'}_\n"
                f"_Slack file: `{f.get('name')}`_\n"
                f"{memory_block}"
            )
        else:
            text = (
                f"*No clear match* for `{f.get('name')}` — needs a human on the desk.\n"
                f"{source_line}"
                f"({reason or 'n/a'})\n"
                f"{memory_block}"
            )
        client.chat_postMessage(channel=channel, text=text)
    except Exception as e:
        logger.exception("classify failed")
        client.chat_postMessage(channel=channel, text=f"Classification failed: `{e}`")
        _SEEN_FILES.discard(file_id)


@app.command("/newsroom")
def newsroom_cmd(ack, respond, command):
    ack()
    respond(
        "Upload a video here. I’ll check whether it belongs on an existing desk ticket."
    )


def main() -> None:
    if not APP_TOKEN:
        raise SystemExit(
            "Set SLACK_APP_TOKEN (xapp-...) for Socket Mode. See SLACK_SETUP.md\n"
            "Socket Mode does not need ngrok."
        )
    print("Newsroom Slack bot starting (Socket Mode)...")
    SocketModeHandler(app, APP_TOKEN).start()


if __name__ == "__main__":
    main()
