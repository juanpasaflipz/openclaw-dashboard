"""
Web Browsing Routes — AI-driven web research pipeline.
"""
from flask import jsonify, request, session
from models import db, UserModelConfig, WebBrowsingResult
from llm_service import LLMService
import requests as http_requests
import json
import re


def register_web_browsing_routes(app):

    @app.route('/api/browse/research', methods=['POST'])
    def research():
        """Full AI research pipeline: generate queries -> search -> fetch -> synthesize."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json() or {}
        question = (data.get('question') or '').strip()
        if not question:
            return jsonify({'error': 'Research question is required'}), 400

        # Load model config
        config = UserModelConfig.query.filter_by(user_id=user_id, feature_slot='web_browsing').first()
        if not config:
            return jsonify({'error': 'No model configured for web browsing. Please configure a model first.'}), 400

        try:
            # Step 1: Generate search queries
            query_prompt = [
                {'role': 'system', 'content': 'You generate web search queries. Return a JSON array of 2-3 search query strings. Only return the JSON array, nothing else.'},
                {'role': 'user', 'content': f'Generate search queries to research: {question}'},
            ]
            query_result = LLMService.call(
                config.provider, config.model, config.api_key, query_prompt,
                config.endpoint_url, {'max_tokens': 200, 'temperature': 0.3, **(config.extra_config or {})}
            )

            # Parse search queries
            queries = _parse_json_array(query_result['content'])
            if not queries:
                queries = [question]

            # Step 2: Search via DuckDuckGo HTML
            all_urls = []
            for q in queries[:3]:
                urls = _duckduckgo_search(q, max_results=3)
                all_urls.extend(urls)

            # Deduplicate
            seen = set()
            unique_urls = []
            for u in all_urls:
                if u['url'] not in seen:
                    seen.add(u['url'])
                    unique_urls.append(u)
            unique_urls = unique_urls[:6]

            # Step 3: Fetch and extract content
            page_contents = []
            for url_info in unique_urls:
                content = _fetch_and_extract(url_info['url'])
                if content:
                    page_contents.append({
                        'url': url_info['url'],
                        'title': url_info.get('title', ''),
                        'content': content[:2000],
                    })

            # Step 4: Synthesize with AI
            context_text = ''
            for i, page in enumerate(page_contents, 1):
                context_text += f'\n--- Source {i}: {page["title"]} ({page["url"]}) ---\n{page["content"]}\n'

            synth_prompt = [
                {'role': 'system', 'content': 'You are a research assistant. Synthesize the provided web sources into a clear, comprehensive answer. Cite sources using [Source N] notation.'},
                {'role': 'user', 'content': f'Research question: {question}\n\nSources:{context_text}\n\nProvide a comprehensive answer with source citations.'},
            ]
            synth_result = LLMService.call(
                config.provider, config.model, config.api_key, synth_prompt,
                config.endpoint_url, {'max_tokens': 1500, 'temperature': 0.5, **(config.extra_config or {})}
            )

            # Save result
            browse_result = WebBrowsingResult(
                user_id=user_id,
                query=question,
                urls_fetched=[{'url': p['url'], 'title': p['title']} for p in page_contents],
                extracted_content=context_text[:5000],
                ai_summary=synth_result['content'],
            )
            db.session.add(browse_result)
            db.session.commit()

            return jsonify({
                'success': True,
                'summary': synth_result['content'],
                'sources': [{'url': p['url'], 'title': p['title']} for p in page_contents],
                'queries_used': queries,
                'result_id': browse_result.id,
            })

        except Exception as e:
            print(f"Research failed: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/browse/fetch', methods=['POST'])
    def fetch_url():
        """Fetch and extract content from a specific URL."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json() or {}
        url = (data.get('url') or '').strip()
        if not url:
            return jsonify({'error': 'URL is required'}), 400

        try:
            content = _fetch_and_extract(url)
            if not content:
                return jsonify({'error': 'Could not extract content from URL'}), 400

            return jsonify({
                'success': True,
                'url': url,
                'content': content[:5000],
                'content_length': len(content),
            })
        except Exception as e:
            print(f"Fetch failed: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/browse/history', methods=['GET'])
    def browse_history():
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        results = WebBrowsingResult.query.filter_by(user_id=user_id)\
            .order_by(WebBrowsingResult.created_at.desc()).limit(20).all()
        return jsonify({'results': [r.to_dict() for r in results]})


def _parse_json_array(text):
    """Try to extract a JSON array from LLM response text."""
    try:
        match = re.search(r'\[.*?\]', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except (json.JSONDecodeError, AttributeError):
        pass
    return []


def _duckduckgo_search(query, max_results=3):
    """Search DuckDuckGo HTML and extract result URLs."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        resp = http_requests.get(
            'https://html.duckduckgo.com/html/',
            params={'q': query},
            headers=headers,
            timeout=5,
        )
        if not resp.ok:
            return []

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, 'html.parser')
        results = []
        for result in soup.select('.result__a')[:max_results]:
            href = result.get('href', '')
            title = result.get_text(strip=True)
            # DuckDuckGo wraps URLs in a redirect
            if 'uddg=' in href:
                from urllib.parse import unquote, parse_qs, urlparse
                parsed = urlparse(href)
                qs = parse_qs(parsed.query)
                actual_url = unquote(qs.get('uddg', [href])[0])
                results.append({'url': actual_url, 'title': title})
            elif href.startswith('http'):
                results.append({'url': href, 'title': title})

        return results
    except Exception:
        return []


def _fetch_and_extract(url):
    """Fetch a URL and extract readable text content."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        resp = http_requests.get(url, headers=headers, timeout=5)
        if not resp.ok:
            return None

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Remove nav, footer, script, style, aside elements
        for tag in soup(['nav', 'footer', 'script', 'style', 'aside', 'header', 'noscript', 'iframe']):
            tag.decompose()

        text = soup.get_text(separator='\n', strip=True)
        # Clean up excessive whitespace
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return '\n'.join(lines)
    except Exception:
        return None
