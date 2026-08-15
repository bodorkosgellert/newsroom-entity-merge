"""
Desk memory: “what does the newsroom already know about this story?”

Default backend is a local JSON graph (no Docker). Optional Cognee (+ Qdrant)
path activates when COGNEE_ENABLED=1 and dependencies/LLM keys are present.

Difficulty ladder (for humans / judges):
  1. Local JSON memory (this file) ………… easy — always on
  2. Cognee + default LanceDB …………… medium — needs LLM_API_KEY, `pip install cognee`
  3. Cognee + Qdrant Docker …………… medium-hard — register adapter + running Qdrant
  4. Official Cognee Slack slash app …… hard — pre-release, HTTPS/ngrok, separate Slack app
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MEMORY_PATH = ROOT / "out" / "desk_memory.json"
SLACK = ROOT / "data" / "synthetic-slack"

FLACO_TICKET = "TICKET-FLACO-01"
MONA_TICKET = "ART-MONA-220"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_memory() -> dict:
    return {
        "tickets": {
            FLACO_TICKET: {
                "title": "Flaco multi-angle (NYC Eurasian eagle-owl)",
                "aliases": [
                    "Flaco",
                    "Central Park owl",
                    "NYC peeping owl",
                    "Eurasian eagle-owl",
                    "eagle owl",
                    "eagle sighting",
                    "owl on windowsill",
                ],
                "channels": ["politics", "video"],
                "notes": [
                    "Wildlife desk story; multi-angle clips should merge here.",
                ],
                "rejects": [
                    {
                        "ticket": MONA_TICKET,
                        "reason": "Art desk Mona Lisa must never merge into Flaco",
                    }
                ],
                "attachments": [],
            },
            MONA_TICKET: {
                "title": "Mona Lisa / art desk",
                "aliases": ["Mona Lisa", "Leonardo", "Da Vinci portrait"],
                "channels": ["print", "video"],
                "notes": [
                    "Distractor asset for demo — route here, leave Flaco unchanged.",
                ],
                "rejects": [],
                "attachments": [],
            },
        },
        "channel_chatter": [],
        "backend": "local",
        "updated_at": _now(),
    }


def load_memory() -> dict:
    if MEMORY_PATH.exists():
        return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    mem = default_memory()
    seed_from_synthetic_slack(mem)
    save_memory(mem)
    return mem


def save_memory(mem: dict) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    mem["updated_at"] = _now()
    MEMORY_PATH.write_text(json.dumps(mem, indent=2), encoding="utf-8")


def seed_from_synthetic_slack(mem: dict | None = None) -> dict:
    """Ingest simulated #politics / #video / #print chatter as desk context."""
    mem = mem or load_memory()
    users = {u["id"]: u for u in json.loads((SLACK / "users.json").read_text(encoding="utf-8"))}
    chatter = mem.setdefault("channel_chatter", [])
    seen = {(c.get("channel"), c.get("ts")) for c in chatter}
    for channel_dir in sorted(p for p in SLACK.iterdir() if p.is_dir()):
        for day in sorted(channel_dir.glob("*.json")):
            for msg in json.loads(day.read_text(encoding="utf-8")):
                key = (channel_dir.name, msg.get("ts"))
                if key in seen:
                    continue
                uid = msg.get("user", "")
                chatter.append(
                    {
                        "channel": channel_dir.name,
                        "user": users.get(uid, {}).get("name", uid),
                        "text": msg.get("text", ""),
                        "ts": msg.get("ts"),
                    }
                )
                seen.add(key)
                # Grow aliases from chat text
                text = msg.get("text", "")
                if re.search(r"flaco|eagle-?owl|peeping owl|central park owl", text, re.I):
                    aliases = mem["tickets"][FLACO_TICKET].setdefault("aliases", [])
                    for a in re.findall(
                        r"Flaco|Central Park owl|NYC peeping owl|Eurasian eagle-owl|eagle owl",
                        text,
                        flags=re.I,
                    ):
                        if a not in aliases:
                            aliases.append(a)
                    chans = mem["tickets"][FLACO_TICKET].setdefault("channels", [])
                    if channel_dir.name not in chans:
                        chans.append(channel_dir.name)
                if re.search(r"mona\s*lisa", text, re.I):
                    aliases = mem["tickets"][MONA_TICKET].setdefault("aliases", [])
                    if "Mona Lisa" not in aliases:
                        aliases.append("Mona Lisa")
                    chans = mem["tickets"][MONA_TICKET].setdefault("channels", [])
                    if channel_dir.name not in chans:
                        chans.append(channel_dir.name)
    mem["backend"] = mem.get("backend") or "local"
    save_memory(mem)
    return mem


def _score_ticket(query: str, ticket_id: str, ticket: dict) -> int:
    q = query.lower()
    score = 0
    for alias in ticket.get("aliases") or []:
        a = alias.lower()
        if a and a in q:
            score += 5 + min(len(a), 20)
        elif any(tok and tok in q for tok in re.split(r"\W+", a) if len(tok) > 3):
            score += 2
    for ch in ticket.get("channels") or []:
        if f"#{ch}" in q or ch in q:
            score += 1
    for note in ticket.get("notes") or []:
        for tok in re.split(r"\W+", note.lower()):
            if len(tok) > 4 and tok in q:
                score += 1
    for row in ticket.get("rejects") or []:
        if row.get("ticket", "").lower() in q:
            score += 1
    # filename-ish tokens
    if ticket_id == FLACO_TICKET and any(k in q for k in ("owl", "flaco", "eagle", "windowsill")):
        score += 3
    if ticket_id == MONA_TICKET and any(k in q for k in ("mona", "lisa", "davinci", "portrait")):
        score += 3
    return score


def recall(query: str, limit: int = 3) -> list[dict]:
    """
    What does the desk already know that matches this query / filename / chatter?

    Prefer local Qdrant vector search when available (sponsor-aligned).
    Optional real Cognee when COGNEE_ENABLED=1.
    Always falls back to alias scoring.
    """
    if os.getenv("COGNEE_ENABLED", "").strip() in {"1", "true", "True"}:
        try:
            return _recall_cognee(query, limit=limit)
        except Exception as e:
            local = _recall_vector_or_alias(query, limit=limit)
            for row in local:
                row["cognee_error"] = str(e)
            return local
    return _recall_vector_or_alias(query, limit=limit)


def _recall_vector_or_alias(query: str, limit: int = 3) -> list[dict]:
    use_vector = os.getenv("VECTOR_MEMORY", "1").strip() not in {"0", "false", "False"}
    if use_vector:
        try:
            from vector_memory import search_memory

            hits = search_memory(query, limit=max(limit, 5))
            if hits:
                # Collapse to ticket-level results
                by_ticket: dict[str, dict] = {}
                for h in hits:
                    tid = h.get("ticket") or "UNKNOWN"
                    if tid not in by_ticket or h.get("score", 0) > by_ticket[tid].get("score", 0):
                        by_ticket[tid] = {
                            "ticket": h.get("ticket"),
                            "title": h.get("title"),
                            "score": round(float(h.get("score", 0)) * 100),
                            "aliases": h.get("aliases") or [],
                            "channels": [f"#{c}" for c in str(h.get("channel") or "").split(",") if c],
                            "rejects": [],
                            "backend": "qdrant_local",
                            "summary": (h.get("text") or "")[:240],
                            "kind": h.get("kind"),
                        }
                # Attach reject rules from JSON desk file
                mem = load_memory()
                ranked = []
                for tid, row in by_ticket.items():
                    if tid in mem.get("tickets", {}):
                        t = mem["tickets"][tid]
                        row["title"] = row.get("title") or t.get("title")
                        row["aliases"] = row.get("aliases") or (t.get("aliases") or [])[:8]
                        row["channels"] = row.get("channels") or [f"#{c}" for c in t.get("channels") or []]
                        row["rejects"] = t.get("rejects") or []
                    if row.get("ticket"):
                        ranked.append(row)
                ranked.sort(key=lambda r: r["score"], reverse=True)
                if ranked:
                    return ranked[:limit]
        except Exception as e:
            alias_hits = _recall_local(query, limit=limit)
            for row in alias_hits:
                row["vector_error"] = str(e)
            return alias_hits
    return _recall_local(query, limit=limit)


def _recall_local(query: str, limit: int = 3) -> list[dict]:
    mem = load_memory()
    ranked = []
    for tid, ticket in mem.get("tickets", {}).items():
        score = _score_ticket(query, tid, ticket)
        # Channel chatter boost
        for c in mem.get("channel_chatter") or []:
            if score and any(
                a.lower() in (c.get("text") or "").lower()
                for a in (ticket.get("aliases") or [])[:8]
                if len(a) > 3
            ):
                # already related; small bonus if chatter mentions query tokens
                if any(tok in (c.get("text") or "").lower() for tok in re.split(r"\W+", query.lower()) if len(tok) > 4):
                    score += 1
                    break
        if score > 0:
            ranked.append(
                {
                    "ticket": tid,
                    "title": ticket.get("title"),
                    "score": score,
                    "aliases": ticket.get("aliases", [])[:8],
                    "channels": [f"#{c}" for c in ticket.get("channels") or []],
                    "rejects": ticket.get("rejects") or [],
                    "backend": "local",
                    "summary": (
                        f"{tid}: {ticket.get('title')} | "
                        f"aliases={', '.join((ticket.get('aliases') or [])[:5])} | "
                        f"channels={', '.join('#' + c for c in (ticket.get('channels') or []))}"
                    ),
                }
            )
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked[:limit]


def _recall_cognee(query: str, limit: int = 3) -> list[dict]:
    """Optional path: real Cognee search (embeddings → Qdrant/LanceDB)."""
    import asyncio

    async def _run() -> list[dict]:
        # Community Qdrant adapter must register before any cognee call
        if os.getenv("VECTOR_DB_PROVIDER", "").lower() == "qdrant":
            from cognee_community_vector_adapter_qdrant import register

            register()

        import cognee
        from cognee.api.v1.search import SearchType

        results = await cognee.search(
            query_text=query,
            query_type=SearchType.CHUNKS,
        )
        out = []
        for i, r in enumerate(results[:limit]):
            text = r if isinstance(r, str) else str(r)
            ticket = FLACO_TICKET if re.search(r"flaco|owl|TICKET-FLACO", text, re.I) else None
            if re.search(r"mona|ART-MONA", text, re.I):
                ticket = MONA_TICKET
            out.append(
                {
                    "ticket": ticket,
                    "title": None,
                    "score": limit - i,
                    "aliases": [],
                    "channels": [],
                    "rejects": [],
                    "backend": "cognee",
                    "summary": text[:400],
                }
            )
        return out or _recall_local(query, limit=limit)

    return asyncio.run(_run())


def infer_news_source(filename: str) -> dict:
    """
    Same Flaco story, different outlet/episode → one parent ticket + a source intake id.
    (Entity merge stays on TICKET-FLACO-01; we still mint a source slip for provenance.)
    """
    name = filename.lower()
    if any(k in name for k in ("fire_escape", "fire-escape", "independent", "uws")):
        return {
            "source_id": "SOURCE-INDEPENDENT-FIRE-ESCAPE",
            "outlet": "The Independent / Manhattan bird alert (fire escape)",
            "episode": "UWS fire-escape sighting — same Flaco story, new angle/outlet",
        }
    if any(k in name for k in ("windowsill", "inside edition", "peeping", "g-iz4d54szw")):
        return {
            "source_id": "SOURCE-INSIDE-EDITION-WINDOWSILL",
            "outlet": "Inside Edition-style windowsill peeping",
            "episode": "Windowsill angle — same Flaco story",
        }
    if "eagle sighting" in name or "glgfq" in name or "glgfq" in name.replace("_", ""):
        return {
            "source_id": "SOURCE-SLACK-EAGLE-SIGHTING",
            "outlet": "Slack / social upload",
            "episode": "Mislabelled ‘eagle’ social clip — same Flaco story",
        }
    if "mona" in name or "lisa" in name:
        return {
            "source_id": "SOURCE-MONA-DISTRACTOR",
            "outlet": "Art / distractor intake",
            "episode": "Not Flaco",
        }
    if "snowy" in name or "not_flaco" in name:
        return {
            "source_id": "SOURCE-SNOWY-OWL-OTHER",
            "outlet": "Other owl species (snowy)",
            "episode": "Different bird — must not merge into Flaco",
        }
    return {
        "source_id": "SOURCE-UNKNOWN-INTAKE",
        "outlet": "Unlabelled upload",
        "episode": "New intake — classify against existing tickets",
    }


def remember_attachment(
    ticket_id: str,
    *,
    source: str,
    indexed_asset_id: str | None = None,
    reason: str | None = None,
    source_meta: dict | None = None,
) -> dict:
    mem = load_memory()
    ticket = mem["tickets"].setdefault(
        ticket_id,
        {"aliases": [], "channels": [], "attachments": [], "rejects": [], "notes": [], "sources": []},
    )
    meta = source_meta or infer_news_source(source)
    entry = {
        "source": source,
        "indexed_asset_id": indexed_asset_id,
        "reason": reason,
        "at": _now(),
        **meta,
    }
    ticket.setdefault("attachments", []).append(entry)
    sources = ticket.setdefault("sources", [])
    if meta.get("source_id") and meta["source_id"] not in {s.get("source_id") for s in sources}:
        sources.append(meta)
    save_memory(mem)
    return meta


def remember_reject(
    from_ticket: str,
    to_ticket: str,
    *,
    source: str,
    reason: str,
) -> None:
    mem = load_memory()
    ticket = mem["tickets"].setdefault(from_ticket, {"aliases": [], "channels": [], "attachments": [], "rejects": [], "notes": []})
    ticket.setdefault("rejects", []).append(
        {"ticket": to_ticket, "source": source, "reason": reason, "at": _now()}
    )
    save_memory(mem)


def format_memory_for_slack(hits: list[dict]) -> str:
    if not hits:
        return "_Desk memory: nothing prior on this story._"
    top = hits[0]
    lines = [
        f"*Desk memory* (`{top.get('backend', 'local')}`): `{top.get('ticket')}` — {top.get('title') or 'match'}",
        f"_Aliases: {', '.join(top.get('aliases') or []) or 'n/a'}_",
        f"_Channels: {', '.join(top.get('channels') or []) or 'n/a'}_",
    ]
    rejects = top.get("rejects") or []
    if rejects:
        r0 = rejects[0]
        lines.append(f"_Prior reject rule: do not merge `{r0.get('ticket')}` — {r0.get('reason')}_")
    return "\n".join(lines)


def sync_to_cognee_if_enabled() -> str:
    """One-shot: push local desk facts into Cognee for embedding/Qdrant search."""
    if os.getenv("COGNEE_ENABLED", "").strip() not in {"1", "true", "True"}:
        return "skipped: set COGNEE_ENABLED=1"
    import asyncio

    async def _run() -> str:
        if os.getenv("VECTOR_DB_PROVIDER", "").lower() == "qdrant":
            from cognee_community_vector_adapter_qdrant import register

            register()
        import cognee

        mem = load_memory()
        docs = []
        for tid, t in mem.get("tickets", {}).items():
            docs.append(
                f"Ticket {tid}: {t.get('title')}. "
                f"Aliases: {', '.join(t.get('aliases') or [])}. "
                f"Channels: {', '.join(t.get('channels') or [])}. "
                f"Notes: {' '.join(t.get('notes') or [])}. "
                f"Rejects: {json.dumps(t.get('rejects') or [])}."
            )
        for c in mem.get("channel_chatter") or []:
            docs.append(f"Slack #{c.get('channel')} @{c.get('user')}: {c.get('text')}")
        for d in docs:
            await cognee.add(d)
        await cognee.cognify()
        mem["backend"] = "cognee"
        save_memory(mem)
        return f"synced {len(docs)} docs to Cognee"

    return asyncio.run(_run())


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "sync":
        print(sync_to_cognee_if_enabled())
    elif len(sys.argv) > 1:
        print(json.dumps(recall(" ".join(sys.argv[1:])), indent=2))
    else:
        seed_from_synthetic_slack()
        print(json.dumps(recall("eagle sighting windowsill footage"), indent=2))
