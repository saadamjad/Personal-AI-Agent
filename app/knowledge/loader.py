from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

KNOWLEDGE_DIR = Path(__file__).parent


@dataclass(frozen=True)
class KnowledgeDocument:
    name: str
    content: str


def _load_markdown_docs() -> list[KnowledgeDocument]:
    docs = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        docs.append(KnowledgeDocument(name=path.stem, content=path.read_text(encoding="utf-8")))
    return docs


def _load_yaml_as_text(path: Path) -> str:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _load_yaml_docs() -> list[KnowledgeDocument]:
    docs = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.yaml")):
        docs.append(KnowledgeDocument(name=path.stem, content=_load_yaml_as_text(path)))
    return docs


@lru_cache
def load_all_documents() -> list[KnowledgeDocument]:
    return _load_markdown_docs() + _load_yaml_docs()


def knowledge_loaded() -> bool:
    return len(load_all_documents()) > 0


def render_full_knowledge_text() -> str:
    """Concatenates every knowledge document into one text block.

    The knowledge base is small enough (a handful of short files) that full
    inclusion beats chunked retrieval — no vector search needed at this scale.
    """
    sections = []
    for doc in load_all_documents():
        sections.append(f"## {doc.name}\n\n{doc.content.strip()}")
    return "\n\n".join(sections)
