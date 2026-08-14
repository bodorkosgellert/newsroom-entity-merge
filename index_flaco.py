"""
Download (optional) + index Flaco clips into Twelve Labs.
Uses current SDK: indexes + assets + indexed_assets (not the old task.create API).
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
CLIPS_DIR = ROOT / "data" / "clips" / "flaco"
STATE_PATH = ROOT / "out" / "twelvelabs_flaco_state.json"


def load_env() -> str:
    load_dotenv(ROOT / ".env")
    key = os.getenv("TWELVELABS_API_KEY", "").strip()
    if not key:
        raise SystemExit("TWELVELABS_API_KEY missing in .env")
    return key


def wait_asset_ready(client, asset_id: str, timeout_s: int = 600) -> None:
    start = time.time()
    while True:
        asset = client.assets.retrieve(asset_id)
        status = getattr(asset, "status", None) or (asset.get("status") if isinstance(asset, dict) else None)
        print(f"  asset {asset_id}: {status}")
        if status == "ready":
            return
        if status in {"failed", "error"}:
            raise RuntimeError(f"Asset failed: {asset_id} status={status}")
        if time.time() - start > timeout_s:
            raise TimeoutError(f"Asset not ready after {timeout_s}s: {asset_id}")
        time.sleep(5)


def wait_indexed_ready(client, index_id: str, indexed_asset_id: str, timeout_s: int = 900) -> None:
    start = time.time()
    while True:
        item = client.indexes.indexed_assets.retrieve(index_id, indexed_asset_id)
        status = getattr(item, "status", None) or (item.get("status") if isinstance(item, dict) else None)
        print(f"  indexed {indexed_asset_id}: {status}")
        if status == "ready":
            return
        if status in {"failed", "error"}:
            raise RuntimeError(f"Indexing failed: {indexed_asset_id} status={status}")
        if time.time() - start > timeout_s:
            raise TimeoutError(f"Index not ready after {timeout_s}s: {indexed_asset_id}")
        time.sleep(8)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-id", default=os.getenv("TWELVELABS_INDEX_ID", "").strip())
    parser.add_argument("--name", default=f"flaco-angles-{int(time.time())}")
    args = parser.parse_args()

    api_key = load_env()
    from twelvelabs import TwelveLabs

    client = TwelveLabs(api_key=api_key)
    files = sorted(CLIPS_DIR.glob("*.mp4")) + sorted(CLIPS_DIR.glob("*.webm")) + sorted(CLIPS_DIR.glob("*.mkv"))
    if not files:
        raise SystemExit(f"No videos in {CLIPS_DIR}. Run yt-dlp first.")

    index_id = args.index_id
    if not index_id:
        print(f"Creating index: {args.name}")
        index = client.indexes.create(
            index_name=args.name,
            models=[{"model_name": "marengo3.0", "model_options": ["visual", "audio"]}],
        )
        index_id = index.id
        print(f"Index id: {index_id}")
    else:
        print(f"Using existing index: {index_id}")

    uploaded = []
    for path in files:
        print(f"Uploading {path.name} ...")
        with path.open("rb") as fh:
            asset = client.assets.create(method="direct", file=fh)
        asset_id = asset.id
        wait_asset_ready(client, asset_id)
        indexed = client.indexes.indexed_assets.create(index_id=index_id, asset_id=asset_id)
        indexed_id = indexed.id
        wait_indexed_ready(client, index_id, indexed_id)
        uploaded.append(
            {
                "file": path.name,
                "asset_id": asset_id,
                "indexed_asset_id": indexed_id,
            }
        )
        print(f"  ready: {path.name}")

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state = {"index_id": index_id, "videos": uploaded}
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

    # Persist index id into .env if empty
    env_path = ROOT / ".env"
    text = env_path.read_text(encoding="utf-8")
    if "TWELVELABS_INDEX_ID=\n" in text or text.strip().endswith("TWELVELABS_INDEX_ID="):
        text = text.replace("TWELVELABS_INDEX_ID=", f"TWELVELABS_INDEX_ID={index_id}", 1)
        env_path.write_text(text, encoding="utf-8")

    print("\nDone.")
    print(f"Index: {index_id}")
    print(f"State: {STATE_PATH}")
    print('Try: python search_flaco.py "owl on apartment windowsill"')


if __name__ == "__main__":
    main()
