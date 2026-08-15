"""
Local “Cognee-shaped” memory + Qdrant vectors (no Docker, $0 API credit).

Plain picture:
  • Cognee’s job  → decide WHAT to remember (tickets, aliases, Slack lines) and
                     ask an embedding model to turn that text into a list of numbers.
  • Qdrant’s job  → store those number-lists and find “nearby” memories on search.
  • Twelve Labs   → separate brain for VIDEO pixels/audio. We keep it separate,
                     then write a short text note of its decision into memory.

This module uses:
  • sentence-transformers (free, on your PC) instead of a paid embedding API
  • qdrant-client path=… (embedded Qdrant on disk — same idea as Docker Qdrant)

When you later install Docker + add LLM_API_KEY, you can swap in real `cognee`
without changing the demo story.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QDRANT_PATH = ROOT / "out" / "qdrant_local"
COLLECTION = "newsroom_desk"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DIM = 384

_model = None
_client = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _get_client():
    global _client
    if _client is None:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qm

        QDRANT_PATH.mkdir(parents=True, exist_ok=True)
        _client = QdrantClient(path=str(QDRANT_PATH))
        names = {c.name for c in _client.get_collections().collections}
        if COLLECTION not in names:
            _client.create_collection(
                collection_name=COLLECTION,
                vectors_config=qm.VectorParams(size=DIM, distance=qm.Distance.COSINE),
            )
    return _client


def embed(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vectors]


def upsert_memories(points: list[dict]) -> int:
    """
    Each point is one memory card, e.g.:
      {id, text, ticket, kind, channel, aliases}
    Qdrant stores: vector = embedding(text), payload = the rest.
    """
    from qdrant_client.http import models as qm

    if not points:
        return 0
    client = _get_client()
    texts = [p["text"] for p in points]
    vectors = embed(texts)
    payload_points = []
    for p, vec in zip(points, vectors):
        payload_points.append(
            qm.PointStruct(
                id=p["id"],
                vector=vec,
                payload={k: v for k, v in p.items() if k != "id"},
            )
        )
    client.upsert(collection_name=COLLECTION, points=payload_points)
    return len(payload_points)


def search_memory(query: str, limit: int = 5) -> list[dict]:
    client = _get_client()
    vector = embed([query])[0]
    # Newer qdrant-client: query_points (search() was removed)
    raw = client.query_points(collection_name=COLLECTION, query=vector, limit=limit)
    out = []
    for h in raw.points:
        row = dict(h.payload or {})
        row["score"] = float(h.score or 0)
        row["point_id"] = h.id
        out.append(row)
    return out


def build_points_from_desk(mem: dict) -> list[dict]:
    """Turn desk tickets / Slack chatter into Qdrant points (entity cards)."""
    points = []
    pid = 1
    for tid, t in (mem.get("tickets") or {}).items():
        aliases = t.get("aliases") or []
        channels = t.get("channels") or []
        text = (
            f"Ticket {tid}: {t.get('title')}. "
            f"Also known as: {', '.join(aliases)}. "
            f"Seen in Slack channels: {', '.join('#' + c for c in channels)}. "
            f"Notes: {' '.join(t.get('notes') or [])}."
        )
        points.append(
            {
                "id": pid,
                "text": text,
                "ticket": tid,
                "kind": "ticket",
                "channel": ",".join(channels),
                "aliases": aliases,
                "title": t.get("title"),
            }
        )
        pid += 1
        for a in aliases:
            points.append(
                {
                    "id": pid,
                    "text": f"Alias '{a}' refers to desk ticket {tid} ({t.get('title')}).",
                    "ticket": tid,
                    "kind": "alias",
                    "channel": "",
                    "aliases": [a],
                    "title": t.get("title"),
                }
            )
            pid += 1
        for r in t.get("rejects") or []:
            points.append(
                {
                    "id": pid,
                    "text": (
                        f"Reject rule for {tid}: do not merge {r.get('ticket')}. "
                        f"Reason: {r.get('reason')}."
                    ),
                    "ticket": tid,
                    "kind": "reject",
                    "channel": "",
                    "aliases": [],
                    "title": t.get("title"),
                }
            )
            pid += 1
    for c in mem.get("channel_chatter") or []:
        points.append(
            {
                "id": pid,
                "text": f"Slack #{c.get('channel')} @{c.get('user')}: {c.get('text')}",
                "ticket": None,
                "kind": "chatter",
                "channel": c.get("channel"),
                "aliases": [],
                "title": None,
            }
        )
        pid += 1
    return points


def remember_vision_decision(
    *,
    filename: str,
    ticket: str | None,
    decision: str,
    reason: str,
    indexed_asset_id: str | None = None,
) -> None:
    """Write Twelve Labs outcome into the same memory (text fact, not video bytes)."""
    from qdrant_client.http import models as qm
    import time

    client = _get_client()
    text = (
        f"Vision routing: file '{filename}' decided as {decision} "
        f"→ ticket {ticket}. Reason: {reason}. "
        f"Twelve Labs indexed_asset_id={indexed_asset_id}."
    )
    vec = embed([text])[0]
    # stable-ish id from time
    point_id = int(time.time() * 1000) % 2_000_000_000
    client.upsert(
        collection_name=COLLECTION,
        points=[
            qm.PointStruct(
                id=point_id,
                vector=vec,
                payload={
                    "text": text,
                    "ticket": ticket,
                    "kind": "vision_decision",
                    "channel": "slack",
                    "aliases": [],
                    "title": filename,
                },
            )
        ],
    )


def export_embedding_map(out_json: Path, queries: list[str] | None = None) -> dict:
    """
    Pull stored points + a few demo queries, project to 2D for the portfolio HTML.
    Uses PCA on the vectors (simple map — not magic, just a sketch of ‘nearness’).
    """
    import numpy as np
    from sklearn.decomposition import PCA

    client = _get_client()
    # scroll all points
    records, _ = client.scroll(collection_name=COLLECTION, with_vectors=True, with_payload=True, limit=500)
    rows = []
    vectors = []
    for r in records:
        payload = r.payload or {}
        rows.append(
            {
                "id": r.id,
                "kind": payload.get("kind"),
                "ticket": payload.get("ticket"),
                "label": (payload.get("text") or "")[:80],
                "channel": payload.get("channel"),
            }
        )
        vectors.append(r.vector)

    queries = queries or [
        "eagle sighting on social media",
        "Flaco owl windowsill",
        "Mona Lisa painting art desk",
        "random cooking recipe",
    ]
    q_vecs = embed(queries)
    for q, v in zip(queries, q_vecs):
        rows.append({"id": f"q:{q}", "kind": "query", "ticket": None, "label": q, "channel": ""})
        vectors.append(v)

    if len(vectors) < 2:
        data = {"points": [], "note": "not enough vectors"}
        out_json.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data

    X = np.array(vectors, dtype=float)
    xy = PCA(n_components=2, random_state=0).fit_transform(X)
    for i, row in enumerate(rows):
        row["x"] = float(xy[i, 0])
        row["y"] = float(xy[i, 1])

    data = {
        "model": MODEL_NAME,
        "collection": COLLECTION,
        "distance": "cosine",
        "points": rows,
        "caption": (
            "Each dot is a memory card or a search query. "
            "Close dots ≈ similar meaning. Queries near Flaco dots mean the desk would reinforce that ticket."
        ),
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def sync_desk_to_qdrant() -> dict:
    from desk_memory import load_memory, seed_from_synthetic_slack, save_memory

    mem = seed_from_synthetic_slack()
    points = build_points_from_desk(mem)
    # recreate collection cleanly for demo sync
    from qdrant_client.http import models as qm

    client = _get_client()
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=qm.VectorParams(size=DIM, distance=qm.Distance.COSINE),
    )
    n = upsert_memories(points)
    mem["backend"] = "qdrant_local"
    save_memory(mem)
    return {"upserted": n, "collection": COLLECTION, "path": str(QDRANT_PATH)}


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "map":
        out = ROOT / "out" / "embedding_map.json"
        print(json.dumps(export_embedding_map(out), indent=2)[:2000])
    elif len(sys.argv) > 1 and sys.argv[1] == "search":
        q = " ".join(sys.argv[2:]) or "eagle sighting"
        print(json.dumps(search_memory(q), indent=2))
    else:
        print(json.dumps(sync_desk_to_qdrant(), indent=2))
