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
            f"Got *{f.get('name')}*. Indexing with Twelve Labs and routing to "
            f"`TICKET-FLACO-01` or `ART-MONA-220` (Mona Lisa must not merge into Flaco)..."
        ),
    )

    try:
        path = download_slack_file(f)
        if not path:
            client.chat_postMessage(channel=channel, text="Could not download the file.")
            return

        from classify import classify_video

        logs: list[str] = []
        result = classify_video(path, progress=logs.append)
        decision = result.get("decision")
        ticket = result.get("ticket")
        reason = result.get("reason")

        if decision == "flaco":
            text = (
                f"*Attached to `{ticket}`* (Flaco multi-angle)\n"
                f"Reason: {reason}\n"
                f"Indexed id: `{result.get('indexed_asset_id')}`\n"
                f"_Provenance: Slack upload `{f.get('name')}`_"
            )
        elif decision == "mona":
            text = (
                f"*Routed to `{ticket}`* — *rejected* for Flaco merge\n"
                f"This looks like Mona Lisa / art campaign, not the owl.\n"
                f"Reason: {reason}\n"
                f"Notify Mona Lisa owner — do not attach to `TICKET-FLACO-01`."
            )
        else:
            text = (
                f"*Unclear classification* for `{f.get('name')}`\n"
                f"Reason: {reason or 'n/a'}\n"
                f"Manual desk review needed."
            )
        if logs:
            text += "\n```" + "\n".join(logs[-6:]) + "```"
        client.chat_postMessage(channel=channel, text=text)
    except Exception as e:
        logger.exception("classify failed")
        client.chat_postMessage(channel=channel, text=f"Classification failed: `{e}`")


@app.command("/newsroom")
def newsroom_cmd(ack, respond, command):
    ack()
    respond(
        "Upload a video to this channel. I will index it and attach to "
        "`TICKET-FLACO-01` or `ART-MONA-220` (never merge Mona into Flaco)."
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
