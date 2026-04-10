from fastapi import APIRouter

from app.modules.keyword_corpus.endpoints import (
    categories,
    content_strategies,
    corpus_templates,
    global_corpus,
    knowledge_base_files,
    knowledge_bases,
    metadata,
    node_pending_audits,
    nodes,
    stats,
    visualization,
)

external_router = APIRouter()
external_router.include_router(categories.router)
external_router.include_router(content_strategies.router)
external_router.include_router(corpus_templates.router)
external_router.include_router(global_corpus.router)
external_router.include_router(metadata.router)
external_router.include_router(node_pending_audits.router)
external_router.include_router(nodes.router)
external_router.include_router(stats.router)
external_router.include_router(visualization.router)

knowledge_router = APIRouter()
knowledge_router.include_router(knowledge_bases.router)
knowledge_router.include_router(knowledge_base_files.router)

internal_router = APIRouter()
internal_router.include_router(categories.router)
internal_router.include_router(content_strategies.router)
internal_router.include_router(corpus_templates.router)
internal_router.include_router(global_corpus.router)
internal_router.include_router(metadata.router)
internal_router.include_router(node_pending_audits.router)
internal_router.include_router(nodes.router)
internal_router.include_router(stats.router)
internal_router.include_router(visualization.router)
internal_router.include_router(knowledge_bases.router)
internal_router.include_router(knowledge_base_files.router)
