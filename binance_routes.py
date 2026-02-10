"""
Binance integration routes - Connect, portfolio, prices, and trading controls
"""
from flask import jsonify, request, session
from models import db, Superpower
from binance_service import (
    validate_binance_keys, get_portfolio, get_price,
    get_order_status, is_trading_enabled, get_binance_client
)
from datetime import datetime
import json


def register_binance_routes(app):
    """Register Binance-specific routes"""

    @app.route('/api/binance/connect', methods=['POST'])
    def connect_binance():
        """Connect Binance with API key + secret (not OAuth)"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            data = request.get_json()
            api_key = data.get('api_key', '').strip()
            api_secret = data.get('api_secret', '').strip()
            testnet = data.get('testnet', False)

            if not api_key or not api_secret:
                return jsonify({'error': 'API key and secret are required'}), 400

            # Validate keys by testing connection
            valid, result = validate_binance_keys(api_key, api_secret, testnet)
            if not valid:
                return jsonify({'error': f'Invalid Binance credentials: {result}'}), 400

            # Check for existing Binance superpower
            superpower = Superpower.query.filter_by(
                user_id=user_id,
                service_type='binance'
            ).first()

            config = json.dumps({
                'testnet': testnet,
                'trading_enabled': False,  # Read-only by default
                'default_type': 'spot',
                'trade_limit_usd': 100,
            })

            if superpower:
                # Update existing
                superpower.access_token_encrypted = api_key  # TODO: Encrypt
                superpower.refresh_token_encrypted = api_secret  # TODO: Encrypt
                superpower.config = config
                superpower.is_enabled = True
                superpower.connected_at = datetime.utcnow()
                superpower.last_error = None
            else:
                # Create new
                superpower = Superpower(
                    user_id=user_id,
                    service_type='binance',
                    service_name='Binance',
                    category='do',
                    is_enabled=True,
                    connected_at=datetime.utcnow(),
                    access_token_encrypted=api_key,  # TODO: Encrypt
                    refresh_token_encrypted=api_secret,  # TODO: Encrypt
                    config=config,
                    usage_count=0,
                )
                db.session.add(superpower)

            db.session.commit()

            print(f"Binance connected for user {user_id} (testnet={testnet})")

            return jsonify({
                'success': True,
                'message': f'Binance {"testnet " if testnet else ""}connected successfully!',
                'total_assets': result.get('total_assets', 0),
            })

        except Exception as e:
            print(f"Error connecting Binance: {e}")
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/binance/disconnect', methods=['POST'])
    def disconnect_binance():
        """Disconnect Binance superpower"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            superpower = Superpower.query.filter_by(
                user_id=user_id,
                service_type='binance'
            ).first()

            if not superpower:
                return jsonify({'error': 'Binance not connected'}), 404

            db.session.delete(superpower)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Binance disconnected'
            })

        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/binance/portfolio', methods=['GET'])
    def binance_portfolio():
        """Get portfolio holdings (read-only, no approval needed)"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            portfolio, error = get_portfolio(user_id)
            if error:
                return jsonify({'error': error}), 400

            return jsonify({
                'success': True,
                'portfolio': portfolio,
            })

        except Exception as e:
            print(f"Error fetching portfolio: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/binance/price/<symbol>', methods=['GET'])
    def binance_price(symbol):
        """Get current price for a symbol (read-only)"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            # Convert URL-safe symbol (BTC-USDT) to ccxt format (BTC/USDT)
            symbol = symbol.replace('-', '/')

            ticker, error = get_price(user_id, symbol)
            if error:
                return jsonify({'error': error}), 400

            return jsonify({
                'success': True,
                'ticker': ticker,
            })

        except Exception as e:
            print(f"Error fetching price: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/binance/prices', methods=['GET'])
    def binance_prices():
        """Get prices for major trading pairs (read-only)"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            client, error = get_binance_client(user_id)
            if error:
                return jsonify({'error': error}), 400

            major_pairs = [
                'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT',
                'XRP/USDT', 'ADA/USDT', 'DOGE/USDT', 'DOT/USDT',
            ]

            tickers = []
            for symbol in major_pairs:
                try:
                    ticker = client.fetch_ticker(symbol)
                    tickers.append({
                        'symbol': ticker.get('symbol'),
                        'last': ticker.get('last'),
                        'change_percent': ticker.get('percentage'),
                        'high': ticker.get('high'),
                        'low': ticker.get('low'),
                        'volume': ticker.get('baseVolume'),
                    })
                except Exception:
                    pass  # Skip unavailable pairs

            return jsonify({
                'success': True,
                'tickers': tickers,
            })

        except Exception as e:
            print(f"Error fetching prices: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/binance/order/<symbol>/<order_id>', methods=['GET'])
    def binance_order(symbol, order_id):
        """Get order status (read-only)"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            symbol = symbol.replace('-', '/')

            order, error = get_order_status(user_id, symbol, order_id)
            if error:
                return jsonify({'error': error}), 400

            return jsonify({
                'success': True,
                'order': order,
            })

        except Exception as e:
            print(f"Error fetching order: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/binance/enable-trading', methods=['POST'])
    def enable_trading():
        """Explicitly opt in to trading (sets trading_enabled = True)"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            superpower = Superpower.query.filter_by(
                user_id=user_id,
                service_type='binance',
                is_enabled=True
            ).first()

            if not superpower:
                return jsonify({'error': 'Binance not connected'}), 400

            config = json.loads(superpower.config) if superpower.config else {}
            config['trading_enabled'] = True
            superpower.config = json.dumps(config)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Trading enabled. All trades still require approval.',
            })

        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/binance/disable-trading', methods=['POST'])
    def disable_trading():
        """Disable trading (back to read-only mode)"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            superpower = Superpower.query.filter_by(
                user_id=user_id,
                service_type='binance',
                is_enabled=True
            ).first()

            if not superpower:
                return jsonify({'error': 'Binance not connected'}), 400

            config = json.loads(superpower.config) if superpower.config else {}
            config['trading_enabled'] = False
            superpower.config = json.dumps(config)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Trading disabled. Read-only mode active.',
            })

        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500
