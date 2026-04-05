from __future__ import annotations

import json
from pathlib import Path
import sys
import uuid


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import settings
from app.database import ArticleRepository
from app.schemas import SourceHealthResponse
from app.services.ingestion import IngestionService
from app.services.llm import LLMService
from app.services.vector_store import VectorStore
from app.sources.registry import build_sources


def main() -> None:
    repository = ArticleRepository(settings.db_path)
    repository.init_database()
    vector_store = VectorStore(settings=settings, repository=repository)
    llm_service = LLMService(settings)
    ingestion_service = IngestionService(
        settings=settings,
        repository=repository,
        vector_store=vector_store,
        llm_service=llm_service,
        sources=build_sources(settings),
    )
    request_id = f"cli-ingest-{uuid.uuid4().hex[:12]}"
    result = ingestion_service.ingest(request_id=request_id)
    health_items = repository.list_source_health(stale_after_hours=settings.source_health_stale_hours)
    health_summary = SourceHealthResponse(
        items=health_items,
        healthy_count=sum(1 for item in health_items if item.status == "ok" and not item.stale),
        failing_count=sum(1 for item in health_items if item.status == "error"),
        stale_count=sum(1 for item in health_items if item.stale),
    )
    print(json.dumps({**result, "request_id": request_id, "source_health": health_summary.model_dump(mode="json")}, indent=2))


if __name__ == "__main__":
    main()