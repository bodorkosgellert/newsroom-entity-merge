"""Search the Flaco Twelve Labs index and print clip timestamps."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "out" / "twelvelabs_flaco_state.json"


def main() -> None:
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("TWELVELABS_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("TWELVELABS_API_KEY missing")

    query = " ".join(sys.argv[1:]).strip() or "owl perched on windowsill looking into apartment"
    index_id = os.getenv("TWELVELABS_INDEX_ID", "").strip()
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        index_id = index_id or state.get("index_id", "")
    if not index_id:
        raise SystemExit("No TWELVELABS_INDEX_ID — run index_flaco.py first")

    from twelvelabs import TwelveLabs

    client = TwelveLabs(api_key=api_key)
    print(f"Index: {index_id}")
    print(f"Query: {query}\n")
    results = client.search.query(
        index_id=index_id,
        query_text=query,
        search_options=["visual", "audio"],
    )
    for i, clip in enumerate(results):
        vid = getattr(clip, "video_id", None) or getattr(clip, "id", None)
        start = getattr(clip, "start", None)
        end = getattr(clip, "end", None)
        score = getattr(clip, "score", None) or getattr(clip, "rank", None)
        print(f"{i+1}. video={vid}  {start}s–{end}s  score/rank={score}")


if __name__ == "__main__":
    main()
