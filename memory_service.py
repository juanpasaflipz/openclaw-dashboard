"""
Semantic Memory Service — embedding + vector search for cross-conversation recall.

Uses OpenAI text-embedding-3-small (1536 dims) for embeddings.
Stores vectors in PostgreSQL via pgvector extension.
Falls back to JSON text storage + cosine similarity in Python when pgvector is unavailable.
"""
import json
import os
import math
from datetime import datetime
from models import db, MemoryEmbedding, UserModelConfig


EMBEDDING_MODEL = 'text-embedding-3-small'
EMBEDDING_DIMS = 1536
SIMILARITY_THRESHOLD = 0.7


def _get_openai_api_key(user_id=None):
    """Get OpenAI API key from user config or environment."""
    if user_id:
        config = UserModelConfig.query.filter_by(user_id=user_id, feature_slot='chatbot').first()
        if config and config.provider == 'openai' and config.api_key:
            return config.api_key
        # Try any OpenAI config for this user
        config = UserModelConfig.query.filter_by(user_id=user_id, provider='openai').first()
        if config and config.api_key:
            return config.api_key
    return os.environ.get('OPENAI_API_KEY')


def embed_text(text, user_id=None):
    """Generate an embedding vector for text using OpenAI text-embedding-3-small.

    Returns a list of floats (1536 dims) or None on failure.
    """
    import requests as http_requests

    api_key = _get_openai_api_key(user_id)
    if not api_key:
        return None

    try:
        resp = http_requests.post(
            'https://api.openai.com/v1/embeddings',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': EMBEDDING_MODEL,
                'input': text[:8000],  # Truncate to fit model limits
            },
            timeout=15,
        )
        if resp.ok:
            return resp.json()['data'][0]['embedding']
        print(f"Embedding API error: {resp.status_code} {resp.text[:200]}")
        return None
    except Exception as e:
        print(f"Embedding error: {e}")
        return None


def _cosine_similarity(a, b):
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def store_memory(user_id, content, source_type='conversation', source_id=None):
    """Embed text and store in MemoryEmbedding table.

    Args:
        user_id: Owner user ID
        content: Text to embed and store
        source_type: 'conversation', 'soul', 'manual'
        source_id: Reference ID (e.g. conversation_id)
    """
    embedding = embed_text(content, user_id=user_id)
    embedding_json = json.dumps(embedding) if embedding else None

    mem = MemoryEmbedding(
        user_id=user_id,
        content=content,
        embedding=embedding_json,
        source_type=source_type,
        source_id=source_id,
    )
    db.session.add(mem)
    db.session.commit()
    return mem


def search_memories(user_id, query, limit=5):
    """Search user's memories by semantic similarity.

    Embeds the query, then finds top-k similar memories.
    Uses Python-based cosine similarity (pgvector query can be added later
    for better performance at scale).

    Returns list of dicts: [{content, source_type, similarity, created_at}]
    """
    query_embedding = embed_text(query, user_id=user_id)
    if not query_embedding:
        # Fallback: return recent memories without ranking
        memories = MemoryEmbedding.query.filter_by(user_id=user_id)\
            .order_by(MemoryEmbedding.created_at.desc())\
            .limit(limit).all()
        return [{'content': m.content, 'source_type': m.source_type,
                 'similarity': None, 'created_at': m.created_at.isoformat() if m.created_at else None}
                for m in memories]

    # Load all user memories that have embeddings
    memories = MemoryEmbedding.query.filter_by(user_id=user_id)\
        .filter(MemoryEmbedding.embedding.isnot(None))\
        .all()

    # Score and rank by cosine similarity
    scored = []
    for mem in memories:
        try:
            mem_embedding = json.loads(mem.embedding)
        except (json.JSONDecodeError, TypeError):
            continue
        sim = _cosine_similarity(query_embedding, mem_embedding)
        if sim >= SIMILARITY_THRESHOLD:
            scored.append((sim, mem))

    # Sort by similarity descending
    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            'content': mem.content,
            'source_type': mem.source_type,
            'similarity': round(sim, 4),
            'created_at': mem.created_at.isoformat() if mem.created_at else None,
        }
        for sim, mem in scored[:limit]
    ]


def index_conversation(user_id, conversation_id):
    """Summarize a conversation into key facts and store as memories.

    This is called by the cron endpoint to index completed conversations.
    """
    from models import ChatMessage

    # Check if already indexed
    existing = MemoryEmbedding.query.filter_by(
        user_id=user_id, source_type='conversation', source_id=conversation_id
    ).first()
    if existing:
        return False  # Already indexed

    # Get conversation messages
    messages = ChatMessage.query.filter_by(conversation_id=conversation_id)\
        .filter(ChatMessage.role.in_(['user', 'assistant']))\
        .order_by(ChatMessage.created_at.asc())\
        .all()

    if len(messages) < 2:
        return False  # Too short to index

    # Build a summary of the conversation (take first and last messages, limited)
    texts = []
    for msg in messages[:20]:  # Limit to first 20 messages
        role = 'User' if msg.role == 'user' else 'Assistant'
        texts.append(f'{role}: {msg.content[:500]}')

    conversation_text = '\n'.join(texts)

    # Store as a single memory with conversation context
    summary = f'Conversation summary (ID: {conversation_id[:8]}):\n{conversation_text[:2000]}'
    store_memory(user_id, summary, source_type='conversation', source_id=conversation_id)
    return True
