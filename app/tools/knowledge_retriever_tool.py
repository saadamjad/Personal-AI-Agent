from crewai.tools import tool

from app.knowledge.loader import load_all_documents


@tool("search_knowledge_base")
def search_knowledge_base(query: str) -> str:
    """Searches the personal/professional knowledge base (profile, career
    history, education, projects, skills) and returns the documents relevant
    to the query. Always use this before answering a factual question about
    the person this agent represents — never answer from memory alone.

    Args:
        query: A short description of what the user is asking about,
            e.g. "education", "React Native experience", "contact info".
    """
    docs = load_all_documents()
    if not docs:
        return "No knowledge base documents are loaded."

    query_terms = [t for t in query.lower().split() if len(t) > 2]
    if not query_terms:
        matches = docs
    else:
        matches = [d for d in docs if any(t in d.content.lower() for t in query_terms)]
        if not matches:
            # Fall back to everything rather than returning nothing — a missed
            # keyword match must never cause the agent to say "I don't know"
            # about something that's actually in the knowledge base.
            matches = docs

    return "\n\n".join(f"## {d.name}\n\n{d.content.strip()}" for d in matches)
