"""Upload Mona Lisa distractor into the existing Flaco Twelve Labs index."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
MONA = ROOT / "data" / "clips" / "distractors" / "mona-lisa-effect.mp4"
STATE_PATH = ROOT / "out" / "twelvelabs_flaco_state.json"


def wait_asset_ready(client, asset_id: str, timeout_s: int = 600) -> None:
    start = time.time()
    while True:
        asset = client.assets.retrieve(asset_id)
        status = getattr(asset, "status", None)
        print(f"  asset {asset_id}: {status}")
        if status == "ready":
            return
        if status in {"failed", "error"}:
            raise RuntimeError(f"Asset failed: {status}")
        if time.time() - start > timeout_s:
            raise TimeoutError("asset timeout")
        time.sleep(5)


def wait_indexed_ready(client, index_id: str, indexed_asset_id: str, timeout_s: int = 900) -> None:
    start = time.time()
    while True:
        item = client.indexes.indexed_assets.retrieve(index_id, indexed_asset_id)
        status = getattr(item, "status", None)
        print(f"  indexed {indexed_asset_id}: {status}")
        if status == "ready":
            return
        if status in {"failed", "error"}:
            raise RuntimeError(f"Index failed: {status}")
        if time.time() - start > timeout_s:
            raise TimeoutError("index timeout")
        time.sleep(8)


def main() -> None:
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("TWELVELABS_API_KEY", "").strip()
    index_id = os.getenv("TWELVELABS_INDEX_ID", "").strip()
    if not api_key or not index_id:
        raise SystemExit("Need TWELVELABS_API_KEY and TWELVELABS_INDEX_ID in .env")
    if not MONA.exists():
        raise SystemExit(f"Missing {MONA}")

    from twelvelabs import TwelveLabs

    client = TwelveLabs(api_key=api_key)
    print(f"Uploading distractor {MONA.name} -> index {index_id}")
    with MONA.open("rb") as fh:
        asset = client.assets.create(method="direct", file=fh)
    wait_asset_ready(client, asset.id)
    indexed = client.indexes.indexed_assets.create(index_id=index_id, asset_id=asset.id)
    wait_indexed_ready(client, index_id, indexed.id)

    state = {"index_id": index_id, "videos": []}
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    state.setdefault("distractors", [])
    state["distractors"].append(
        {"file": MONA.name, "asset_id": asset.id, "indexed_asset_id": indexed.id, "label": "mona-lisa"}
    )
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print("Mona Lisa distractor indexed.")


if __name__ == "__main__":
    main()
