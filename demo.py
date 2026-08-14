"""
Newsroom demo: simulated Slack + Twelve Labs.
- Owl / Flaco queries → attach to TICKET-FLACO-01
- Mona Lisa must NOT merge into the owl ticket
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
SLACK = ROOT / "data" / "synthetic-slack"
OUT = ROOT / "out"
STATE_PATH = OUT / "twelvelabs_flaco_state.json"

FLACO_TICKET = "TICKET-FLACO-01"
MONA_TICKET = "ART-MONA-220"


def load_simulated_chat() -> list[dict]:
    users = {u["id"]: u for u in json.loads((SLACK / "users.json").read_text(encoding="utf-8"))}
    channels = {c["name"]: c for c in json.loads((SLACK / "channels.json").read_text(encoding="utf-8"))}
    messages = []
    for channel_dir in sorted(p for p in SLACK.iterdir() if p.is_dir()):
        for day in sorted(channel_dir.glob("*.json")):
            for msg in json.loads(day.read_text(encoding="utf-8")):
                uid = msg.get("user", "")
                messages.append(
                    {
                        "channel": channel_dir.name,
                        "user": users.get(uid, {}).get("name", uid),
                        "text": msg.get("text", ""),
                        "ts": msg.get("ts"),
                        "files": msg.get("files", []),
                    }
                )
    messages.sort(key=lambda m: m["ts"] or "")
    return messages, channels


def print_chat(messages: list[dict]) -> None:
    print("\n=== SIMULATED SLACK ===\n")
    for m in messages:
        print(f"#{m['channel']}  @{m['user']}")
        print(f"  {m['text']}")
        for f in m.get("files") or []:
            print(f"  [file] {f.get('name')}")
        print()


def extract_aliases(messages: list[dict]) -> dict[str, set[str]]:
    """Very small entity hints from chat text."""
    entities: dict[str, set[str]] = defaultdict(set)
    for m in messages:
        t = m["text"]
        if re.search(r"flaco|eagle-?owl|peeping owl|central park owl", t, re.I):
            entities[FLACO_TICKET].update(
                re.findall(
                    r"Flaco|Central Park owl|NYC peeping owl|Eurasian eagle-owl|eagle owl",
                    t,
                    flags=re.I,
                )
            )
            entities[FLACO_TICKET].add(f"slack:#{m['channel']}")
        if re.search(r"mona\s*lisa", t, re.I):
            entities[MONA_TICKET].add("Mona Lisa")
            entities[MONA_TICKET].add(f"slack:#{m['channel']}")
    return entities


def tl_search(client, index_id: str, query: str, limit: int = 5) -> list[dict]:
    results = client.search.query(
        index_id=index_id,
        query_text=query,
        search_options=["visual", "audio"],
    )
    rows = []
    for i, clip in enumerate(results):
        if i >= limit:
            break
        rows.append(
            {
                "video_id": getattr(clip, "video_id", None) or getattr(clip, "id", None),
                "start": getattr(clip, "start", None),
                "end": getattr(clip, "end", None),
                "score": getattr(clip, "score", None) or getattr(clip, "rank", None),
            }
        )
    return rows


def write_ticket(path: Path, title: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")


def main() -> None:
    load_dotenv(ROOT / ".env")
    messages, _ = load_simulated_chat()
    print_chat(messages)

    entities = extract_aliases(messages)
    print("=== ENTITY MERGE (from chat) ===")
    for ticket, aliases in entities.items():
        print(f"  {ticket}: {sorted(aliases)}")

    api_key = os.getenv("TWELVELABS_API_KEY", "").strip()
    index_id = os.getenv("TWELVELABS_INDEX_ID", "").strip()
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        index_id = index_id or state.get("index_id", "")
    else:
        state = {}

    owl_hits: list[dict] = []
    mona_hits: list[dict] = []
    if api_key and index_id:
        from twelvelabs import TwelveLabs

        client = TwelveLabs(api_key=api_key)
        print("\n=== TWELVE LABS SEARCH ===")
        owl_q = "Eurasian eagle owl perched on apartment windowsill orange eyes"
        mona_q = "Mona Lisa painting Leonardo da Vinci face"
        print(f"Owl query: {owl_q}")
        owl_hits = tl_search(client, index_id, owl_q)
        for h in owl_hits:
            print(f"  hit video={h['video_id']} {h['start']}s–{h['end']}s score={h['score']}")
        print(f"Mona query: {mona_q}")
        mona_hits = tl_search(client, index_id, mona_q)
        for h in mona_hits:
            print(f"  hit video={h['video_id']} {h['start']}s–{h['end']}s score={h['score']}")
    else:
        print("\n(Twelve Labs skipped — missing key/index)")

    # Routing rule for the demo
    print("\n=== AUTO ATTACH / REJECT ===")
    flaco_body = [
        f"Ticket: {FLACO_TICKET}",
        "Entity: Flaco (NYC Eurasian eagle-owl)",
        f"Aliases from simulated Slack: {sorted(entities.get(FLACO_TICKET, []))}",
        "",
        "Attached multi-angle evidence (Twelve Labs):",
    ]
    if owl_hits:
        for h in owl_hits:
            flaco_body.append(f"- video `{h['video_id']}` @ {h['start']}–{h['end']}s (score={h['score']})")
        print(f"[ok] Attach {len(owl_hits)} owl hit(s) -> {FLACO_TICKET}")
    else:
        flaco_body.append("- (no live hits yet - Flaco files are on disk under data/clips/flaco)")
        print(f"... Owl ticket updated from chat only ({FLACO_TICKET})")

    # Mona Lisa must not land on Flaco ticket
    if mona_hits:
        print(f"[ok] Mona Lisa matches found -> route to {MONA_TICKET}, NOT {FLACO_TICKET}")
        print("[reject] Merge blocked: Mona Lisa is not Flaco")
    else:
        print(f"Mona Lisa distractor file present on disk; keep on {MONA_TICKET} only")

    write_ticket(
        OUT / "TICKET-FLACO-01.md",
        "TICKET-FLACO-01 — Flaco multi-angle",
        "\n".join(flaco_body)
        + "\n\nProvenance: simulated #politics #video #print\n"
        + "Rule: do not attach Mona Lisa / art-campaign clips.\n",
    )
    write_ticket(
        OUT / "ART-MONA-220.md",
        "ART-MONA-220 — Mona Lisa campaign (distractor)",
        "Entity: Mona Lisa creative campaign\n"
        "Source file: data/clips/distractors/mona-lisa-effect.mp4\n"
        f"Twelve Labs hits: {json.dumps(mona_hits, indent=2)}\n"
        f"Routing: NEVER merge into {FLACO_TICKET}.\n"
        "Action: notify Mona Lisa owner (@sam.print / art desk), not owl desk.\n",
    )

    print(f"\nWrote {OUT / 'TICKET-FLACO-01.md'}")
    print(f"Wrote {OUT / 'ART-MONA-220.md'}")
    print("\nDemo beat: same chat intake → owl angles merge to Flaco; Mona Lisa gets its own ticket.")


if __name__ == "__main__":
    main()
