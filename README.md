# Newsroom Entity Merge

Hack-night demo: **multi-angle video + simulated Slack → one desk ticket**, with a hard reject for the wrong asset.

Built for the Cognee × Qdrant Slack memory hack night. Uses **Twelve Labs** for video search; Slack bot optional (Socket Mode).

## Demo beat

| Intake | Route |
| --- | --- |
| Flaco owl clips (several angles) | Attach → `TICKET-FLACO-01` |
| Mona Lisa distractor clip | Route → `ART-MONA-220` — **never merge into Flaco** |

Simulated channels: `#politics`, `#video`, `#print`.

## Quick start (simulated Slack UI)

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # add TWELVELABS_API_KEY (+ INDEX_ID after indexing)

python demo.py         # chat merge + Twelve Labs search + tickets
python view_slack.py   # Slack-like UI with video previews
```

Videos are **not** in this repo (size + third-party footage). Put local MP4s under:

- `data/clips/flaco/` — owl angles  
- `data/clips/distractors/mona-lisa-effect.mp4` — Pixabay Mona Lisa distractor  

Then index:

```bash
python index_flaco.py
python index_mona.py
```

## Real Slack uploads

See [SLACK_SETUP.md](SLACK_SETUP.md). Socket Mode — **ngrok not required**.

```bash
# .env: SLACK_BOT_TOKEN + SLACK_APP_TOKEN
python slack_bot.py
```

Upload an MP4 in-channel → bot indexes with Twelve Labs → posts Flaco attach or Mona Lisa reject.

## Layout

```
data/synthetic-slack/   # fake workspace export
data/clips/             # local videos only (gitignored)
demo.py                 # end-to-end simulated demo
view_slack.py           # HTML Slack UI + previews
classify.py             # upload → Twelve Labs → ticket
slack_bot.py            # live Slack file_shared handler
SLACK_SETUP.md
```

## Pitch (2 minutes)

1. Same story, many names/angles across channels.  
2. Twelve Labs finds owl moments; Mona Lisa does not join that ticket.  
3. Auto write-back with provenance — keyword search cannot do this join.
