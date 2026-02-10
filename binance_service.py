"""
Binance crypto trading service layer
Mirrors gmail_routes.py's get_gmail_service() pattern using ccxt
"""
from models import db, Superpower
from datetime import datetime
import json


def get_binance_client(user_id):
    """
    Get authenticated Binance ccxt client for a user.

    Returns:
        (client, None) on success or (None, error_message) on failure
    """
    try:
        import ccxt

        superpower = Superpower.query.filter_by(
            user_id=user_id,
            service_type='binance',
            is_enabled=True
        ).first()

        if not superpower:
            return None, 'Binance not connected'

        if not superpower.access_token_encrypted:
            return None, 'Binance API key missing'

        if not superpower.refresh_token_encrypted:
            return None, 'Binance API secret missing'

        # Parse config
        config = json.loads(superpower.config) if superpower.config else {}

        # Build ccxt client
        # TODO: Decrypt tokens
        exchange_config = {
            'apiKey': superpower.access_token_encrypted,
            'secret': superpower.refresh_token_encrypted,
            'enableRateLimit': True,
        }

        if config.get('testnet'):
            exchange_config['sandbox'] = True

        # Set default market type (spot by default)
        default_type = config.get('default_type', 'spot')
        exchange_config['options'] = {'defaultType': default_type}

        client = ccxt.binance(exchange_config)

        # Update last used
        superpower.last_used = datetime.utcnow()
        superpower.usage_count = (superpower.usage_count or 0) + 1
        db.session.commit()

        return client, None

    except Exception as e:
        return None, str(e)


def validate_binance_keys(api_key, api_secret, testnet=False):
    """
    Test connection with provided Binance API keys.

    Returns:
        (True, account_info) on success or (False, error_message) on failure
    """
    try:
        import ccxt

        exchange_config = {
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
        }

        if testnet:
            exchange_config['sandbox'] = True

        client = ccxt.binance(exchange_config)
        balance = client.fetch_balance()

        return True, {
            'total_assets': len([k for k, v in balance.get('total', {}).items() if v and v > 0]),
            'testnet': testnet
        }

    except Exception as e:
        return False, str(e)


def get_portfolio(user_id):
    """
    Fetch account balances for a user.

    Returns:
        (portfolio_data, None) on success or (None, error_message) on failure
    """
    client, error = get_binance_client(user_id)
    if error:
        return None, error

    try:
        balance = client.fetch_balance()

        # Filter to non-zero holdings
        holdings = []
        for currency, amount in balance.get('total', {}).items():
            if amount and amount > 0:
                holdings.append({
                    'currency': currency,
                    'total': amount,
                    'free': balance.get('free', {}).get(currency, 0),
                    'used': balance.get('used', {}).get(currency, 0),
                })

        return {
            'holdings': holdings,
            'total_assets': len(holdings),
        }, None

    except Exception as e:
        return None, str(e)


def get_price(user_id, symbol):
    """
    Fetch current ticker price for a symbol (e.g., 'BTC/USDT').

    Returns:
        (ticker_data, None) on success or (None, error_message) on failure
    """
    client, error = get_binance_client(user_id)
    if error:
        return None, error

    try:
        ticker = client.fetch_ticker(symbol)

        return {
            'symbol': ticker.get('symbol'),
            'last': ticker.get('last'),
            'bid': ticker.get('bid'),
            'ask': ticker.get('ask'),
            'high': ticker.get('high'),
            'low': ticker.get('low'),
            'volume': ticker.get('baseVolume'),
            'change_percent': ticker.get('percentage'),
            'timestamp': ticker.get('timestamp'),
        }, None

    except Exception as e:
        return None, str(e)


def place_order(user_id, symbol, side, order_type, amount, price=None):
    """
    Place an order on Binance. Only executes if trading_enabled is True.

    Args:
        symbol: e.g. 'BTC/USDT'
        side: 'buy' or 'sell'
        order_type: 'market' or 'limit'
        amount: quantity to trade
        price: required for limit orders

    Returns:
        (order_result, None) on success or (None, error_message) on failure
    """
    if not is_trading_enabled(user_id):
        return None, 'Trading is not enabled. Enable trading in the Binance settings first.'

    client, error = get_binance_client(user_id)
    if error:
        return None, error

    try:
        order = client.create_order(
            symbol=symbol,
            type=order_type,
            side=side,
            amount=amount,
            price=price if order_type == 'limit' else None,
        )

        return {
            'order_id': order.get('id'),
            'symbol': order.get('symbol'),
            'side': order.get('side'),
            'type': order.get('type'),
            'amount': order.get('amount'),
            'price': order.get('price'),
            'filled_qty': order.get('filled'),
            'avg_price': order.get('average'),
            'status': order.get('status'),
            'fees': order.get('fee'),
            'timestamp': order.get('timestamp'),
        }, None

    except Exception as e:
        return None, str(e)


def get_order_status(user_id, symbol, order_id):
    """
    Fetch the status of an existing order.

    Returns:
        (order_data, None) on success or (None, error_message) on failure
    """
    client, error = get_binance_client(user_id)
    if error:
        return None, error

    try:
        order = client.fetch_order(order_id, symbol)

        return {
            'order_id': order.get('id'),
            'symbol': order.get('symbol'),
            'side': order.get('side'),
            'type': order.get('type'),
            'amount': order.get('amount'),
            'price': order.get('price'),
            'filled_qty': order.get('filled'),
            'avg_price': order.get('average'),
            'remaining': order.get('remaining'),
            'status': order.get('status'),
            'fees': order.get('fee'),
            'timestamp': order.get('timestamp'),
        }, None

    except Exception as e:
        return None, str(e)


def is_trading_enabled(user_id):
    """
    Check if trading is enabled for a user's Binance connection.

    Returns:
        True if trading is explicitly enabled, False otherwise (read-only by default)
    """
    superpower = Superpower.query.filter_by(
        user_id=user_id,
        service_type='binance',
        is_enabled=True
    ).first()

    if not superpower or not superpower.config:
        return False

    try:
        config = json.loads(superpower.config)
        return config.get('trading_enabled', False)
    except (json.JSONDecodeError, TypeError):
        return False
