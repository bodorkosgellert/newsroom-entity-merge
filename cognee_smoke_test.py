"""
Minimal Cognee smoke test against Docker Qdrant + OpenAI.

Prereqs:
  1. Docker Qdrant running:  docker start newsroom-qdrant
  2. In .env (do not commit):
       OPENAI_API_KEY=sk-...
       LLM_API_KEY=sk-...          # same key is fine
       COGNEE_ENABLED=1
       VECTOR_DB_PROVIDER=qdrant
       VECTOR_DB_URL=http://localhost:6333
       VECTOR_DB_KEY=
       VECTOR_DATASET_DATABASE_HANDLER=qdrant

Uses only a few short desk facts — low token spend (~small € cents).
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def _require_keys() -> None:
    openai = (os.getenv("OPENAI_API_KEY") or "").strip()
    llm = (os.getenv("LLM_API_KEY") or "").strip()
    if not llm and openai:
        os.environ["LLM_API_KEY"] = openai
        llm = openai
    if not llm:
        raise SystemExit(
            "Missing OPENAI_API_KEY / LLM_API_KEY in .env\n"
            "Add the key locally (do not paste it into chat), then re-run."
        )
    if (os.getenv("VECTOR_DB_URL") or "").strip() == "":
        os.environ["VECTOR_DB_URL"] = "http://localhost:6333"
    os.environ.setdefault("VECTOR_DB_PROVIDER", "qdrant")
    os.environ.setdefault("VECTOR_DATASET_DATABASE_HANDLER", "qdrant")
    os.environ.setdefault("COGNEE_ENABLED", "1")


async def main() -> None:
    _require_keys()
    # Multi-user mode is on by default; disable for a simple local smoke test.
    os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")

    # Side-effect import registers the Qdrant adapter with Cognee
    import cognee_community_vector_adapter_qdrant.register  # noqa: F401

    import cognee
    from cognee import config
    from cognee.api.v1.search import SearchType

    system_path = ROOT / ".cognee_system"
    data_path = ROOT / ".cognee_data"
    system_path.mkdir(exist_ok=True)
    data_path.mkdir(exist_ok=True)
    config.system_root_directory(str(system_path))
    config.data_root_directory(str(data_path))
    config.set_vector_db_config(
        {
            "vector_db_provider": "qdrant",
            "vector_dataset_database_handler": "qdrant",
            "vector_db_url": os.getenv("VECTOR_DB_URL", "http://localhost:6333"),
            "vector_db_key": os.getenv("VECTOR_DB_KEY", "") or None,
        }
    )

    facts = [
        "Ticket TICKET-FLACO-01 is the Flaco multi-angle NYC Eurasian eagle-owl desk story. "
        "Aliases include Flaco, Central Park owl, eagle sighting, eagle owl.",
        "Ticket ART-MONA-220 is the Mona Lisa art-desk ticket. Never merge Mona Lisa into Flaco.",
        "Slack #video said the Independent fire-escape clip is the same Flaco story, new source.",
    ]

    print("Adding", len(facts), "short facts to Cognee…")
    for f in facts:
        await cognee.add(f)
    print("Cognify (uses a little OpenAI credit)…")
    await cognee.cognify()
    print("Search: eagle sighting…")
    results = await cognee.search(
        query_text="eagle sighting windowsill — which desk ticket?",
        query_type=SearchType.CHUNKS,
    )
    for i, r in enumerate(results[:5], 1):
        print(f"{i}. {r}")
    print("OK — Cognee + Docker Qdrant path works.")


if __name__ == "__main__":
    asyncio.run(main())
