"""
Memory Routes — API endpoints for semantic memory management + cron indexing.
"""
from flask import jsonify, request, session
from models import db, MemoryEmbedding, ChatConversation
from datetime import datetime, timedelta
import os


def register_memory_routes(app):

    @app.route('/api/memories', methods=['GET'])
    def list_memories():
        """List user's stored memories (paginated)."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)
        source_type = request.args.get('source_type')

        query = MemoryEmbedding.query.filter_by(user_id=user_id)
        if source_type:
            query = query.filter_by(source_type=source_type)

        memories = query.order_by(MemoryEmbedding.created_at.desc())\
            .paginate(page=page, per_page=per_page, error_out=False)

        return jsonify({
            'memories': [m.to_dict() for m in memories.items],
            'total': memories.total,
            'page': page,
            'pages': memories.pages,
        })

    @app.route('/api/memories/<int:memory_id>', methods=['DELETE'])
    def delete_memory(memory_id):
        """Delete a specific memory."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        mem = MemoryEmbedding.query.filter_by(id=memory_id, user_id=user_id).first()
        if not mem:
            return jsonify({'error': 'Memory not found'}), 404

        db.session.delete(mem)
        db.session.commit()
        return jsonify({'success': True})

    @app.route('/api/memories/search', methods=['POST'])
    def search_memories_endpoint():
        """Search memories by semantic similarity."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json() or {}
        query = (data.get('query') or '').strip()
        if not query:
            return jsonify({'error': 'query is required'}), 400

        from memory_service import search_memories
        results = search_memories(user_id, query, limit=data.get('limit', 10))
        return jsonify({'results': results})

    @app.route('/api/memories/index', methods=['POST'])
    def index_memories_cron():
        """Cron endpoint: index recent conversations into semantic memory.

        Protected by CRON_SECRET to prevent unauthorized access.
        """
        # Verify cron secret
        cron_secret = os.environ.get('CRON_SECRET')
        auth_header = request.headers.get('Authorization', '')
        if cron_secret and not auth_header.endswith(cron_secret):
            return jsonify({'error': 'Unauthorized'}), 401

        from memory_service import index_conversation

        # Find conversations updated in the last 12 hours that haven't been indexed
        cutoff = datetime.utcnow() - timedelta(hours=12)
        conversations = ChatConversation.query.filter(
            ChatConversation.updated_at >= cutoff,
        ).all()

        indexed = 0
        errors = 0
        for conv in conversations:
            try:
                if index_conversation(conv.user_id, conv.conversation_id):
                    indexed += 1
            except Exception as e:
                errors += 1
                print(f"Memory indexing error for {conv.conversation_id}: {e}")

        return jsonify({
            'success': True,
            'indexed': indexed,
            'errors': errors,
            'checked': len(conversations),
        })
