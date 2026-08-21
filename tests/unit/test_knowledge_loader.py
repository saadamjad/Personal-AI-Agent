from app.knowledge.loader import knowledge_loaded, load_all_documents, render_full_knowledge_text


def test_knowledge_documents_load() -> None:
    docs = load_all_documents()
    names = {d.name for d in docs}
    assert "profile" in names
    assert "career_timeline" in names
    assert "education" in names
    assert "projects" in names
    assert "skills" in names


def test_knowledge_loaded_is_true() -> None:
    assert knowledge_loaded() is True


def test_render_full_knowledge_text_includes_key_facts() -> None:
    text = render_full_knowledge_text().lower()
    assert "saad" in text
    assert "washmen" in text
    assert "react native" in text
