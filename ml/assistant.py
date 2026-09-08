"""
ml/assistant.py
AI Recruiter Assistant (#13)

RAG pipeline:
1. Index candidate profiles, job descriptions, client history into LlamaIndex
2. On each user query, retrieve relevant documents
3. Feed retrieved context + query to Llama 3 via Ollama
4. Return answer with source citations

Usage:
    from ml.assistant import ask, build_index, stream_answer

    build_index()  # run once or nightly

    answer = ask("Which candidates are available for a Python role in New York?")
    # {"answer": "...", "sources": [...], "confidence": "high"}

    for chunk in stream_answer("What is John Smith's visa status?"):
        print(chunk, end="")
"""
import logging
import os
from pathlib import Path
from typing import Generator, Optional

from data.logger import get_logger
from ml.performance import timed
from dotenv import load_dotenv
load_dotenv()
logger = get_logger("ml.assistant")

INDEX_STORAGE_DIR = Path("data/index")
INDEX_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# ── System prompt ─────────────────────────────────────────────────────────────

ASSISTANT_SYSTEM = """You are an AI assistant for a staffing intelligence platform.
You help recruiters by answering questions about:
- Candidate availability, skills, visa status, and experience
- Open job requirements and client preferences
- Placement history and submission outcomes
- Rate guidance and market information
- Compliance and visa expiry risks

Always be concise, factual, and cite the source of your information.
If you don't have enough information to answer confidently, say so clearly.
Never make up candidate names, rates, or visa information."""


# ── Document builders ─────────────────────────────────────────────────────────

def _build_candidate_documents() -> list:
    """Build LlamaIndex documents from candidate records."""
    from llama_index.core import Document
    from db.queries import get_candidates

    candidates = get_candidates()
    documents = []

    for _, row in candidates.iterrows():
        skills_str = ", ".join(row.get("skills") or [])
        text = f"""CANDIDATE PROFILE
Name: {row.get('name', 'Unknown')}
Email: {row.get('email', 'N/A')}
Visa Status: {row.get('visa_status', 'unknown')}
Location: {row.get('location', 'N/A')}
Years of Experience: {row.get('yoe', 0)}
Desired Rate: ${row.get('rate', 0)}/hr
Skills: {skills_str}
Active Contractor: {'Yes' if row.get('is_active_contractor') else 'No'}
Attrition Risk: {row.get('attrition_risk_score', 'N/A')}
"""
        doc = Document(
            text=text,
            metadata={
                "type":         "candidate",
                "candidate_id": int(row.get("id", 0)),
                "name":         str(row.get("name", "")),
                "visa":         str(row.get("visa_status", "")),
                "location":     str(row.get("location", "")),
            },
            doc_id=f"candidate_{row.get('id')}",
        )
        documents.append(doc)

    logger.info(f"Built {len(documents)} candidate documents")
    return documents


def _build_job_documents() -> list:
    """Build LlamaIndex documents from open job records."""
    from llama_index.core import Document
    from db.queries import get_open_jobs

    jobs = get_open_jobs()
    documents = []

    for _, row in jobs.iterrows():
        skills_str = ", ".join(row.get("required_skills") or [])
        text = f"""JOB OPENING
Title: {row.get('title', 'N/A')}
Client ID: {row.get('client_id', 'N/A')}
Location: {row.get('location', 'N/A')}
Remote OK: {'Yes' if row.get('remote_ok') else 'No'}
Required Skills: {skills_str}
Rate Range: ${row.get('rate_min', 0)}–${row.get('rate_max', 0)}/hr
Min Experience: {row.get('min_yoe', 0)} years
Status: {row.get('status', 'open')}
"""
        doc = Document(
            text=text,
            metadata={
                "type":     "job",
                "job_id":   int(row.get("id", 0)),
                "title":    str(row.get("title", "")),
                "location": str(row.get("location", "")),
            },
            doc_id=f"job_{row.get('id')}",
        )
        documents.append(doc)

    logger.info(f"Built {len(documents)} job documents")
    return documents


def _build_client_documents() -> list:
    """Build LlamaIndex documents from client records."""
    from llama_index.core import Document
    from db.queries import get_clients

    clients = get_clients()
    documents = []

    for _, row in clients.iterrows():
        text = f"""CLIENT PROFILE
Name: {row.get('name', 'N/A')}
Industry: {row.get('industry', 'N/A')}
Status: {row.get('status', 'active')}
Active Requisitions: {row.get('req_volume', 0)}
Average Margin: {row.get('margin_pct', 0):.1f}%
Contact: {row.get('contact_name', 'N/A')} ({row.get('contact_email', 'N/A')})
"""
        doc = Document(
            text=text,
            metadata={
                "type":      "client",
                "client_id": int(row.get("id", 0)),
                "name":      str(row.get("name", "")),
            },
            doc_id=f"client_{row.get('id')}",
        )
        documents.append(doc)

    logger.info(f"Built {len(documents)} client documents")
    return documents


# ── Index management ──────────────────────────────────────────────────────────

_index = None


@timed("build_index")
def build_index(force: bool = False) -> object:
    """
    Build or load the LlamaIndex vector index from DB data.

    Args:
        force: if True, rebuild even if index already exists

    Returns:
        LlamaIndex VectorStoreIndex
    """
    global _index
    from llama_index.core import (
        VectorStoreIndex, StorageContext, load_index_from_storage, Settings
    )
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    from llama_index.llms.ollama import Ollama

    # Configure LlamaIndex to use local models
    Settings.embed_model = HuggingFaceEmbedding(model_name="all-MiniLM-L6-v2")
    Settings.llm = Ollama(model=os.getenv("OLLAMA_MODEL", "llama3"),
                          base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                          request_timeout=120.0)

    index_path = INDEX_STORAGE_DIR / "docstore.json"

    if index_path.exists() and not force:
        logger.info("Loading existing index from disk")
        try:
            storage_context = StorageContext.from_defaults(persist_dir=str(INDEX_STORAGE_DIR))
            _index = load_index_from_storage(storage_context)
            logger.info("Index loaded from disk")
            return _index
        except Exception as e:
            logger.warning(f"Failed to load index: {e} — rebuilding")

    logger.info("Building RAG index from DB data...")

    # Build all documents
    documents = (
        _build_candidate_documents() +
        _build_job_documents() +
        _build_client_documents()
    )

    if not documents:
        logger.warning("No documents found — index will be empty")
        return None

    # Build index
    _index = VectorStoreIndex.from_documents(
        documents,
        show_progress=True,
    )
    _index.storage_context.persist(persist_dir=str(INDEX_STORAGE_DIR))
    logger.info(f"Index built with {len(documents)} documents and saved to disk")
    return _index


def _get_index():
    global _index
    if _index is None:
        _index = build_index()
    return _index


# ── Query engine ──────────────────────────────────────────────────────────────

@timed("ask_assistant")
def ask(
    question: str,
    top_k: int = 5,
) -> dict:
    """
    Ask the assistant a question and get an answer with citations.

    Args:
        question: natural language question from recruiter
        top_k:    number of documents to retrieve

    Returns:
        {
          "answer":     "John Smith is available, H1B visa, Python+AWS...",
          "sources":    [{"type": "candidate", "name": "John Smith", ...}],
          "confidence": "high" | "medium" | "low"
        }
    """
    index = _get_index()
    if index is None:
        return {
            "answer":     "Index not available. Please rebuild the index first.",
            "sources":    [],
            "confidence": "low",
        }

    query_engine = index.as_query_engine(
        similarity_top_k=top_k,
        response_mode="compact",
    )

    try:
        response = query_engine.query(question)
        answer   = str(response)

        # Extract source metadata
        sources = []
        if hasattr(response, "source_nodes"):
            for node in response.source_nodes:
                meta = node.node.metadata or {}
                sources.append({
                    "type":  meta.get("type", "unknown"),
                    "id":    meta.get("candidate_id") or meta.get("job_id") or meta.get("client_id"),
                    "name":  meta.get("name") or meta.get("title", ""),
                    "score": round(node.score or 0, 3),
                })

        confidence = "high" if sources and sources[0]["score"] > 0.7 else \
                     "medium" if sources else "low"

        return {"answer": answer, "sources": sources, "confidence": confidence}

    except Exception as e:
        logger.error(f"Assistant query failed: {e}")
        return {
            "answer":     f"I encountered an error: {e}",
            "sources":    [],
            "confidence": "low",
        }


def stream_answer(
    question: str,
    history: Optional[list[dict]] = None,
) -> Generator[str, None, None]:
    """
    Stream an answer from the assistant for the Streamlit chat UI.

    Args:
        question: current user question
        history:  prior conversation messages

    Yields:
        String chunks
    """
    from ml.llm_client import stream_chat

    # Get relevant context from index
    index = _get_index()
    context = ""
    sources = []

    if index:
        try:
            retriever = index.as_retriever(similarity_top_k=5)
            nodes = retriever.retrieve(question)
            context_parts = [n.node.get_content() for n in nodes]
            context = "\n\n---\n\n".join(context_parts[:3])
            sources = [n.node.metadata.get("name", "") for n in nodes if n.node.metadata]
        except Exception as e:
            logger.warning(f"Retrieval failed: {e}")

    # Build augmented prompt
    if context:
        prompt = f"""Based on the following information from our staffing database:

{context}

Answer this question: {question}

Be specific and cite the candidates/jobs/clients mentioned above."""
    else:
        prompt = question

    yield from stream_chat(prompt, system=ASSISTANT_SYSTEM, history=history)

    if sources:
        yield f"\n\n📎 *Sources: {', '.join(s for s in sources if s)}*"
