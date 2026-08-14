"""Build a Slack-like HTML view with video previews + ticket routing."""
from __future__ import annotations

import json
import re
import shutil
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SLACK = ROOT / "data" / "synthetic-slack"
OUT = ROOT / "out"
MEDIA = OUT / "media"
HTML_PATH = OUT / "slack_view.html"
FLACO_DIR = ROOT / "data" / "clips" / "flaco"
DIST_DIR = ROOT / "data" / "clips" / "distractors"


def safe_name(name: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", name)


def stage_videos() -> list[dict]:
    MEDIA.mkdir(parents=True, exist_ok=True)
    items = []
    for folder, label in ((FLACO_DIR, "flaco"), (DIST_DIR, "distractor")):
        if not folder.exists():
            continue
        for src in sorted(folder.glob("*.mp4")):
            dest_name = safe_name(src.name)
            dest = MEDIA / dest_name
            if not dest.exists() or dest.stat().st_size != src.stat().st_size:
                shutil.copy2(src, dest)
            items.append(
                {
                    "label": label,
                    "title": src.stem[:60],
                    "src": f"media/{dest_name}",
                    "ticket": "TICKET-FLACO-01" if label == "flaco" else "ART-MONA-220",
                }
            )
    return items


def load_messages():
    users = {u["id"]: u for u in json.loads((SLACK / "users.json").read_text(encoding="utf-8"))}
    messages = []
    for channel_dir in sorted(p for p in SLACK.iterdir() if p.is_dir()):
        for day in sorted(channel_dir.glob("*.json")):
            for msg in json.loads(day.read_text(encoding="utf-8")):
                uid = msg.get("user", "")
                messages.append(
                    {
                        "channel": channel_dir.name,
                        "user": users.get(uid, {}).get("real_name")
                        or users.get(uid, {}).get("name")
                        or uid,
                        "handle": users.get(uid, {}).get("name", uid),
                        "text": msg.get("text", ""),
                        "ts": msg.get("ts", ""),
                        "files": msg.get("files", []),
                        "bot": bool(users.get(uid, {}).get("is_bot")),
                    }
                )
    messages.sort(key=lambda m: m["ts"])
    return messages


def ticket_preview(path: Path) -> str:
    if not path.exists():
        return "(run python demo.py first to generate tickets)"
    return path.read_text(encoding="utf-8")


def build_html(messages: list[dict], videos: list[dict]) -> str:
    channels = [
        {"name": name, "messages": [m for m in messages if m["channel"] == name]}
        for name in ("politics", "video", "print")
    ]
    payload = {
        "channels": channels,
        "videos": videos,
        "flaco": ticket_preview(OUT / "TICKET-FLACO-01.md"),
        "mona": ticket_preview(OUT / "ART-MONA-220.md"),
    }
    data = json.dumps(payload, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Newsroom Desk — simulated Slack</title>
  <style>
    :root {{
      --bg: #1a1d21; --sidebar: #19171d; --panel: #222529; --text: #d1d2d3;
      --muted: #ababad; --accent: #1164a3; --green: #2bac76; --warn: #e01e5a;
      --line: #2c2d30;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--bg); color: var(--text); height: 100vh; display: flex;
    }}
    aside {{
      width: 220px; background: var(--sidebar); padding: 16px 12px;
      border-right: 1px solid var(--line); flex-shrink: 0; overflow: auto;
    }}
    aside h1 {{ font-size: 15px; margin: 0 0 16px; font-weight: 700; }}
    .chan {{
      display: block; width: 100%; text-align: left; border: 0; background: transparent;
      color: var(--muted); padding: 6px 10px; border-radius: 6px; cursor: pointer;
      font-size: 15px; margin-bottom: 2px;
    }}
    .chan:hover, .chan.active {{ background: #2c2d31; color: #fff; }}
    .chan::before {{ content: "# "; opacity: 0.7; }}
    main {{ flex: 1; display: flex; flex-direction: column; min-width: 0; }}
    header {{
      padding: 12px 20px; border-bottom: 1px solid var(--line);
      font-weight: 700; font-size: 16px;
    }}
    header span {{ color: var(--muted); font-weight: 400; font-size: 13px; margin-left: 8px; }}
    .feed {{ flex: 1; overflow: auto; padding: 16px 20px 12px; }}
    .msg {{ display: flex; gap: 12px; margin-bottom: 16px; }}
    .avatar {{
      width: 36px; height: 36px; border-radius: 8px; background: var(--accent);
      display: grid; place-items: center; font-weight: 700; font-size: 13px;
      flex-shrink: 0; color: #fff;
    }}
    .avatar.bot {{ background: var(--green); }}
    .meta {{ font-size: 13px; margin-bottom: 2px; }}
    .meta b {{ color: #fff; margin-right: 8px; }}
    .meta .handle {{ color: var(--muted); }}
    .body {{ font-size: 15px; line-height: 1.45; white-space: pre-wrap; }}
    .file {{
      margin-top: 8px; display: inline-block; padding: 8px 10px; border: 1px solid var(--line);
      border-radius: 8px; background: var(--panel); font-size: 13px; color: #fff;
    }}
    .previews {{
      border-top: 1px solid var(--line); padding: 12px 20px 16px; background: #15171a;
      overflow-x: auto; display: flex; gap: 12px;
    }}
    .card {{
      width: 220px; flex-shrink: 0; background: var(--panel); border: 1px solid var(--line);
      border-radius: 10px; overflow: hidden;
    }}
    .card video {{ width: 100%; height: 124px; object-fit: cover; background: #000; display: block; }}
    .card .cap {{ padding: 8px 10px; font-size: 12px; }}
    .card .cap b {{ display: block; color: #fff; margin-bottom: 2px; }}
    .tag {{ font-size: 11px; color: var(--green); }}
    .tag.bad {{ color: #ff8aa0; }}
    .right {{
      width: 340px; background: var(--panel); border-left: 1px solid var(--line);
      padding: 16px; overflow: auto; flex-shrink: 0;
    }}
    .right h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }}
    .ticket {{
      background: #1a1d21; border: 1px solid var(--line); border-radius: 10px;
      padding: 12px; margin-bottom: 14px; font-size: 12px; white-space: pre-wrap;
      font-family: ui-monospace, Consolas, monospace; line-height: 1.4;
    }}
    .ticket.ok {{ border-color: #2bac76; }}
    .ticket.reject {{ border-color: var(--warn); }}
    .badge {{
      display: inline-block; font-size: 11px; font-weight: 700; padding: 2px 8px;
      border-radius: 999px; margin-bottom: 8px;
    }}
    .badge.ok {{ background: #1f3d32; color: #2bac76; }}
    .badge.reject {{ background: #3d1f28; color: #ff8aa0; }}
  </style>
</head>
<body>
  <aside>
    <h1>Newsroom Desk</h1>
    <div id="channels"></div>
  </aside>
  <main>
    <header id="title">#politics <span>simulated Slack</span></header>
    <div class="feed" id="feed"></div>
    <div class="previews" id="previews"></div>
  </main>
  <section class="right">
    <h2>Auto routing</h2>
    <div class="badge ok">ATTACH - Flaco</div>
    <div class="ticket ok" id="flaco"></div>
    <div class="badge reject">REJECT merge - Mona</div>
    <div class="ticket reject" id="mona"></div>
  </section>
  <script>
    const DATA = {data};
    const channelsEl = document.getElementById('channels');
    const feed = document.getElementById('feed');
    const title = document.getElementById('title');
    const previews = document.getElementById('previews');
    document.getElementById('flaco').textContent = DATA.flaco;
    document.getElementById('mona').textContent = DATA.mona;

    DATA.videos.forEach(v => {{
      const card = document.createElement('div');
      card.className = 'card';
      card.innerHTML = `
        <video src="${{v.src}}" controls preload="metadata" muted></video>
        <div class="cap">
          <b></b>
          <span class="tag ${{v.label === 'distractor' ? 'bad' : ''}}"></span>
        </div>`;
      card.querySelector('b').textContent = v.title;
      card.querySelector('.tag').textContent =
        (v.label === 'flaco' ? 'Flaco angle -> ' : 'Distractor -> ') + v.ticket;
      previews.appendChild(card);
    }});

    function initials(name) {{
      return name.split(/\\s+/).map(p => p[0]).join('').slice(0,2).toUpperCase();
    }}

    function show(channelName) {{
      const ch = DATA.channels.find(c => c.name === channelName);
      title.innerHTML = '#' + channelName + ' <span>simulated Slack — video strip below</span>';
      [...channelsEl.querySelectorAll('.chan')].forEach(b => {{
        b.classList.toggle('active', b.dataset.name === channelName);
      }});
      feed.innerHTML = '';
      (ch?.messages || []).forEach(m => {{
        const row = document.createElement('div');
        row.className = 'msg';
        row.innerHTML = `
          <div class="avatar ${{m.bot ? 'bot' : ''}}">${{initials(m.user)}}</div>
          <div>
            <div class="meta"><b>${{m.user}}</b><span class="handle">@${{m.handle}}</span></div>
            <div class="body"></div>
          </div>`;
        row.querySelector('.body').textContent = m.text;
        (m.files || []).forEach(f => {{
          const file = document.createElement('div');
          file.className = 'file';
          file.textContent = 'file: ' + (f.name || 'file');
          row.children[1].appendChild(file);
        }});
        feed.appendChild(row);
      }});
    }}

    DATA.channels.forEach((c, i) => {{
      const b = document.createElement('button');
      b.className = 'chan' + (i === 0 ? ' active' : '');
      b.dataset.name = c.name;
      b.textContent = c.name;
      b.onclick = () => show(c.name);
      channelsEl.appendChild(b);
    }});
    show(DATA.channels[0]?.name || 'politics');
  </script>
</body>
</html>
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    videos = stage_videos()
    html = build_html(load_messages(), videos)
    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {HTML_PATH} with {len(videos)} video previews")
    webbrowser.open(HTML_PATH.resolve().as_uri())


if __name__ == "__main__":
    main()
