"""Classify a local video against the Flaco vs Mona Lisa Twelve Labs index."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "out" / "twelvelabs_flaco_state.json"
FRAMES = ROOT / "out" / "frames"
FFMPEG = Path(
    os.environ.get(
        "FFMPEG",
        r"C:\Users\galla\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0-full_build\bin\ffmpeg.exe",
    )
)

FLACO_TICKET = "TICKET-FLACO-01"
MONA_TICKET = "ART-MONA-220"


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def known_ids(state: dict) -> tuple[set[str], set[str]]:
    flaco = {v.get("indexed_asset_id") for v in state.get("videos", []) if v.get("indexed_asset_id")}
    mona = {d.get("indexed_asset_id") for d in state.get("distractors", []) if d.get("indexed_asset_id")}
    # search results often return video_id == indexed_asset_id in current API
    return flaco, mona


def extract_poster(video: Path, out_jpg: Path, t: float = 1.0) -> Path:
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(FFMPEG),
        "-y",
        "-ss",
        str(t),
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-q:v",
        "3",
        str(out_jpg),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_jpg


def wait_asset_ready(client, asset_id: str, timeout_s: int = 600) -> None:
    start = time.time()
    while True:
        asset = client.assets.retrieve(asset_id)
        status = getattr(asset, "status", None)
        if status == "ready":
            return
        if status in {"failed", "error"}:
            raise RuntimeError(f"asset {status}")
        if time.time() - start > timeout_s:
            raise TimeoutError("asset timeout")
        time.sleep(4)


def wait_indexed_ready(client, index_id: str, indexed_id: str, timeout_s: int = 900) -> None:
    start = time.time()
    while True:
        item = client.indexes.indexed_assets.retrieve(index_id, indexed_id)
        status = getattr(item, "status", None)
        if status == "ready":
            return
        if status in {"failed", "error"}:
            raise RuntimeError(f"index {status}")
        if time.time() - start > timeout_s:
            raise TimeoutError("index timeout")
        time.sleep(6)


def search(client, index_id: str, query: str, limit: int = 60) -> list[dict]:
    """Paginate search hits. New clips often sit past the top-8 when the index already has strong matches."""
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


def best_rank_for(video_id: str, hits: list[dict]) -> int | None:
    for i, h in enumerate(hits, start=1):
        if h.get("video_id") == video_id:
            return i
    return None


def neighbor_vote(hits: list[dict], flaco_ids: set[str], mona_ids: set[str]) -> tuple[int, int]:
    """Count unique known ticket videos among search hits (fallback if new id is still missing)."""
    seen_f: set[str] = set()
    seen_m: set[str] = set()
    for h in hits:
        vid = h.get("video_id")
        if not vid:
            continue
        if vid in flaco_ids:
            seen_f.add(vid)
        if vid in mona_ids:
            seen_m.add(vid)
    return len(seen_f), len(seen_m)


def classify_video(video_path: Path, progress=print) -> dict:
    """Index video into existing TL index, then see which query ranks it better."""
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("TWELVELABS_API_KEY", "").strip()
    index_id = os.getenv("TWELVELABS_INDEX_ID", "").strip()
    state = load_state()
    index_id = index_id or state.get("index_id", "")
    if not api_key or not index_id:
        raise RuntimeError("TWELVELABS_API_KEY / TWELVELABS_INDEX_ID required")

    from twelvelabs import TwelveLabs

    client = TwelveLabs(api_key=api_key)
    poster = FRAMES / f"{video_path.stem}_poster.jpg"
    try:
        extract_poster(video_path, poster)
        progress(f"poster: {poster.name}")
    except Exception as e:
        progress(f"poster failed: {e}")
        poster = None

    progress("Uploading to Twelve Labs...")
    with video_path.open("rb") as fh:
        asset = client.assets.create(method="direct", file=fh)
    wait_asset_ready(client, asset.id)
    progress("Indexing (this can take ~30-90s)...")
    indexed = client.indexes.indexed_assets.create(index_id=index_id, asset_id=asset.id)
    wait_indexed_ready(client, index_id, indexed.id)
    new_id = indexed.id
    progress(f"indexed as {new_id}")

    # Brief settle so the new asset is searchable (usually immediate once ready).
    time.sleep(3)

    owl_hits = search(
        client,
        index_id,
        "Eurasian eagle owl on apartment windowsill orange eyes Flaco",
        limit=60,
    )
    mona_hits = search(
        client,
        index_id,
        "Mona Lisa painting Leonardo da Vinci portrait face",
        limit=60,
    )
    owl_rank = best_rank_for(new_id, owl_hits)
    mona_rank = best_rank_for(new_id, mona_hits)

    flaco_ids, mona_ids = known_ids(state)
    decision = "unknown"
    ticket = None
    reason = ""

    if owl_rank is not None and (mona_rank is None or owl_rank < mona_rank):
        decision = "flaco"
        ticket = FLACO_TICKET
        reason = f"vision: new clip ranks #{owl_rank} for owl query (mona rank={mona_rank})"
    elif mona_rank is not None and (owl_rank is None or mona_rank < owl_rank):
        decision = "mona"
        ticket = MONA_TICKET
        reason = f"vision: new clip ranks #{mona_rank} for Mona Lisa query (owl rank={owl_rank})"
    else:
        # Neighbor vote: which known ticket's clips dominate each query's hit list.
        owl_f, owl_m = neighbor_vote(owl_hits[:12], flaco_ids, mona_ids)
        mona_f, mona_m = neighbor_vote(mona_hits[:12], flaco_ids, mona_ids)
        if owl_f > owl_m and mona_m >= mona_f:
            if owl_rank is not None:
                decision, ticket = "flaco", FLACO_TICKET
                reason = f"vision+neighbors: owl_rank={owl_rank}, flaco_neighbors={owl_f}"
            elif mona_rank is not None:
                decision, ticket = "mona", MONA_TICKET
                reason = f"vision+neighbors: mona_rank={mona_rank}, mona_neighbors={mona_m}"
        if decision == "unknown":
            name = video_path.name.lower()
            if "mona" in name or "lisa" in name:
                decision, ticket, reason = "mona", MONA_TICKET, "filename heuristic"
            elif any(k in name for k in ("flaco", "owl", "eagle")):
                decision, ticket, reason = "flaco", FLACO_TICKET, "filename heuristic"
            else:
                reason = (
                    f"no clear ranking for new video id "
                    f"(owl_rank={owl_rank}, mona_rank={mona_rank})"
                )

    # Desk memory: aliases / channels / prior rejects (local JSON, or Cognee if enabled)
    from desk_memory import (
        format_memory_for_slack,
        recall,
        remember_attachment,
        remember_reject,
    )

    memory_query = f"{video_path.name} {reason}"
    memory_hits = recall(memory_query)
    if decision == "unknown" and memory_hits and memory_hits[0].get("ticket"):
        # Memory can break ties when vision is inconclusive
        top = memory_hits[0]
        if top["ticket"] == FLACO_TICKET:
            decision, ticket = "flaco", FLACO_TICKET
            reason = f"desk-memory: {top.get('summary')}"
        elif top["ticket"] == MONA_TICKET:
            decision, ticket = "mona", MONA_TICKET
            reason = f"desk-memory: {top.get('summary')}"

    if decision == "flaco" and ticket:
        remember_attachment(
            ticket,
            source=video_path.name,
            indexed_asset_id=new_id,
            reason=reason,
        )
    elif decision == "mona" and ticket:
        remember_attachment(
            ticket,
            source=video_path.name,
            indexed_asset_id=new_id,
            reason=reason,
        )
        remember_reject(
            FLACO_TICKET,
            MONA_TICKET,
            source=video_path.name,
            reason="Mona Lisa distractor — left Flaco unchanged",
        )

    # Also park a text note of the vision decision in the vector memory (Qdrant)
    try:
        from vector_memory import remember_vision_decision

        remember_vision_decision(
            filename=video_path.name,
            ticket=ticket,
            decision=decision,
            reason=reason,
            indexed_asset_id=new_id,
        )
    except Exception:
        pass

    return {
        "decision": decision,
        "ticket": ticket,
        "reason": reason,
        "indexed_asset_id": new_id,
        "asset_id": asset.id,
        "poster": str(poster) if poster else None,
        "owl_rank": owl_rank,
        "mona_rank": mona_rank,
        "owl_hits": owl_hits[:3],
        "mona_hits": mona_hits[:3],
        "desk_memory": memory_hits,
        "desk_memory_slack": format_memory_for_slack(memory_hits),
    }


if __name__ == "__main__":
    import sys

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/clips/distractors/mona-lisa-effect.mp4"
    print(json.dumps(classify_video(path), indent=2))
