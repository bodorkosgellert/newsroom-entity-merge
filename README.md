# Newsroom Entity Merge

Hack-night demo: **multi-angle video + simulated Slack → one desk ticket**, with a hard reject for the wrong asset.

Built at [Give Your Slack a Memory (Cognee × Qdrant, Berlin)](https://luma.com/cognee-m078) — multi-angle video → existing desk ticket, with distractor reject.

Uses **Twelve Labs** for video search; Slack bot optional (Socket Mode).

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

Live HackNight workspace (`#all-hacknight`): upload named `eagle sighting.mp4` routed to `TICKET-FLACO-01` by **vision** (`ranks #20 for owl query`, Mona rank none) — not by the filename. The frame is clearly an owl (facial disk, mottled plumage), not an eagle; keyword search on “eagle” would miss the Flaco desk ticket.

![Live Slack: vision match to TICKET-FLACO-01 despite “eagle” filename](docs/eagle-sighting-live.png)

## Desk memory (Cognee-shaped + Qdrant)

**Plain English:** Twelve Labs looks at the *video*. Desk memory remembers *what the newsroom already said* — ticket names, nicknames (“eagle sighting” → Flaco), which Slack channels talked about it, and “don’t merge Mona into Flaco.”

| Role | Who does it here |
| --- | --- |
| Choose what to remember | `desk_memory.py` (Cognee’s job in the sponsor stack) |
| Turn text → number lists (embeddings) | free local model `all-MiniLM-L6-v2` (no API credit) |
| Store & search those number lists | **Qdrant on disk** via `qdrant-client` (`out/qdrant_local/`) — same idea as Docker Qdrant, no Docker install required on this machine |
| Video pixels / audio | **Twelve Labs** (separate). After it decides, we save a short *text note* of that decision into Qdrant too |

```bash
pip install -r requirements.txt
python vector_memory.py              # sync tickets + Slack chatter → Qdrant
python vector_memory.py search "eagle sighting"
python build_memory_map.py           # writes docs/memory-map.html
```

Open the map: [docs/memory-map.html](docs/memory-map.html) — dots that sit near each other mean “similar meaning.”

**Docker / full Cognee later:** this PC didn’t have Docker, and `.env` has no `LLM_API_KEY`, so we didn’t burn paid LLM credits. When you install Docker Desktop + add an LLM key, you can point real `cognee` at Qdrant; the demo story stays the same.

**Images:** video → Twelve Labs. Still photos / screenshots with text → better as “describe or OCR → save text into desk memory.” You don’t have to push raw pixels into Qdrant for this pitch.

**How to show memory value in Slack:** keep the bot running, re-upload a clip. The reply should show **Desk memory** (aliases + channels + reject rule) *and* the Twelve Labs vision reason — two layers, one decision.

## Layout

```
data/synthetic-slack/   # fake workspace export
data/clips/             # local videos only (gitignored)
demo.py                 # end-to-end simulated demo
view_slack.py           # HTML Slack UI + previews
classify.py             # upload → Twelve Labs → ticket
desk_memory.py          # what the desk knows (+ optional Cognee)
vector_memory.py        # embeddings + local Qdrant search
build_memory_map.py     # portfolio map → docs/memory-map.html
slack_bot.py            # live Slack file_shared handler
SLACK_SETUP.md
```

## Pitch (2 minutes)

1. Same story, many names/angles across channels.  
2. Twelve Labs finds owl moments; Mona Lisa does not join that ticket.  
3. Desk memory (Qdrant) reinforces aliases/channels; keyword search cannot do this join.
