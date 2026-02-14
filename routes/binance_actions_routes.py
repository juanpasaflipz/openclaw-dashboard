"""
Binance agent actions - Trade proposals via approval queue
Mirrors agent_actions_routes.py pattern for Gmail
"""
from flask import jsonify, request, session
from models import db, User, Agent, AgentAction, Superpower
from binance_service import get_portfolio, get_price, is_trading_enabled
from datetime import datetime
import json
import os


def get_anthropic_client():
    """Get Anthropic client (lazy initialization)"""
    try:
        import anthropic
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            return None, "ANTHROPIC_API_KEY not configured"

        try:
            client = anthropic.Anthropic(api_key=api_key)
        except TypeError:
            client = anthropic.Client(api_key=api_key)

        return client, None
    except ImportError:
        return None, "anthropic package not installed"
    except Exception as e:
        return None, f"Anthropic client error: {str(e)}"


def register_binance_actions_routes(app):
    """Register Binance agent action routes"""

    @app.route('/api/agent-actions/propose-trade', methods=['POST'])
    def propose_trade():
        """Create a trade proposal that goes through the approval queue"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']
        user = User.query.get(user_id)

        if not user:
            return jsonify({'error': 'User not found'}), 404

        try:
            data = request.json
            symbol = data.get('symbol')
            side = data.get('side')  # 'buy' or 'sell'
            order_type = data.get('order_type', 'market')
            amount = data.get('amount')
            price = data.get('price')  # Required for limit orders
            reasoning = data.get('reasoning', '')

            # Validate required fields
            if not symbol or not side or not amount:
                return jsonify({'error': 'symbol, side, and amount are required'}), 400

            if side not in ('buy', 'sell'):
                return jsonify({'error': 'side must be "buy" or "sell"'}), 400

            if order_type not in ('market', 'limit'):
                return jsonify({'error': 'order_type must be "market" or "limit"'}), 400

            if order_type == 'limit' and not price:
                return jsonify({'error': 'price is required for limit orders'}), 400

            # Check that Binance is connected
            superpower = Superpower.query.filter_by(
                user_id=user_id,
                service_type='binance',
                is_enabled=True
            ).first()

            if not superpower:
                return jsonify({'error': 'Binance not connected'}), 400

            # Check trading is enabled
            if not is_trading_enabled(user_id):
                return jsonify({'error': 'Trading is not enabled. Enable trading in Binance settings first.'}), 400

            # Check trade limit
            config = json.loads(superpower.config) if superpower.config else {}
            trade_limit_usd = config.get('trade_limit_usd', 100)

            # Estimate trade value for limit check
            estimated_value = float(amount) * float(price) if price else None
            if estimated_value and estimated_value > trade_limit_usd:
                return jsonify({
                    'error': f'Trade value (${estimated_value:.2f}) exceeds limit (${trade_limit_usd:.2f}). Increase your trade limit in settings.'
                }), 400

            # Get agent
            agent = user.get_primary_agent()

            # Create pending action
            action = AgentAction(
                user_id=user_id,
                agent_id=agent.id if agent else None,
                action_type='place_order',
                service_type='binance',
                status='pending',
                action_data=json.dumps({
                    'symbol': symbol,
                    'side': side,
                    'order_type': order_type,
                    'amount': float(amount),
                    'price': float(price) if price else None,
                }),
                ai_reasoning=reasoning or f"Proposed {side} {amount} {symbol} ({order_type})",
                ai_confidence=0.7,
            )

            db.session.add(action)
            db.session.commit()

            return jsonify({
                'success': True,
                'action_id': action.id,
                'message': f'Trade proposal created! Review and approve to execute the {side} order.',
            })

        except Exception as e:
            print(f"Error proposing trade: {str(e)}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/agent-actions/analyze-portfolio', methods=['POST'])
    def analyze_portfolio():
        """AI analyzes portfolio and returns suggestions (no action created)"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']
        user = User.query.get(user_id)

        if not user:
            return jsonify({'error': 'User not found'}), 404

        try:
            # Get portfolio
            portfolio, error = get_portfolio(user_id)
            if error:
                return jsonify({'error': error}), 400

            if not portfolio.get('holdings'):
                return jsonify({
                    'success': True,
                    'analysis': 'Your portfolio is empty. Fund your account to get started.',
                    'suggestions': [],
                })

            # Get prices for context
            prices = {}
            for holding in portfolio['holdings']:
                currency = holding['currency']
                if currency != 'USDT' and currency != 'USD':
                    ticker, _ = get_price(user_id, f"{currency}/USDT")
                    if ticker:
                        prices[currency] = ticker.get('last')

            # Use Claude to analyze portfolio
            analysis_prompt = f"""Analyze this crypto portfolio and provide insights:

Holdings:
{json.dumps(portfolio['holdings'], indent=2)}

Current Prices (USD):
{json.dumps(prices, indent=2)}

Provide:
1. A brief portfolio summary
2. Risk assessment (concentration, volatility)
3. Suggestions for improvement (diversification, rebalancing)

Format your response as JSON with keys: summary, risk_level, risk_notes (array), suggestions (array of objects with action and reasoning)"""

            client, error = get_anthropic_client()
            if error:
                return jsonify({'error': f'AI not configured: {error}'}), 500

            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": analysis_prompt
                }]
            )

            ai_response = response.content[0].text

            # Parse AI response
            try:
                import re
                json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group())
                else:
                    analysis = {
                        'summary': ai_response,
                        'risk_level': 'unknown',
                        'risk_notes': [],
                        'suggestions': [],
                    }
            except (json.JSONDecodeError, ValueError):
                analysis = {
                    'summary': ai_response,
                    'risk_level': 'unknown',
                    'risk_notes': [],
                    'suggestions': [],
                }

            return jsonify({
                'success': True,
                'analysis': analysis.get('summary', ai_response),
                'risk_level': analysis.get('risk_level', 'unknown'),
                'risk_notes': analysis.get('risk_notes', []),
                'suggestions': analysis.get('suggestions', []),
                'portfolio': portfolio,
            })

        except Exception as e:
            print(f"Error analyzing portfolio: {str(e)}")
            return jsonify({'error': 'An internal error occurred'}), 500
