"""
Stripe integration routes for credit purchases
"""
from flask import jsonify, request, session
from models import db, User, CreditPackage, CreditTransaction
import stripe
import os

# Initialize Stripe
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')


def require_auth(func):
    """Decorator to require authentication"""
    def wrapper(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


def register_stripe_routes(app):
    """Register Stripe-related routes with the Flask app"""

    @app.route('/api/credits/packages', methods=['GET'])
    def get_credit_packages():
        """Get available credit packages"""
        try:
            packages = CreditPackage.query.filter_by(is_active=True).all()
            return jsonify({
                'packages': [{
                    'id': pkg.id,
                    'name': pkg.name,
                    'credits': pkg.credits,
                    'price': pkg.price_dollars,
                    'price_per_credit': pkg.price_dollars / pkg.credits if pkg.credits > 0 else 0
                } for pkg in packages]
            })
        except Exception as e:
            print(f"❌ Error in get_credit_packages: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/credits/create-checkout', methods=['POST'])
    @require_auth
    def create_checkout_session():
        """Create a Stripe Checkout session for purchasing credits"""
        try:
            data = request.get_json()
            package_id = data.get('package_id')

            if not package_id:
                return jsonify({'error': 'Package ID is required'}), 400

            # Get package
            package = CreditPackage.query.get(package_id)
            if not package or not package.is_active:
                return jsonify({'error': 'Invalid package'}), 404

            # Get current user
            user_id = session.get('user_id')
            user = User.query.get(user_id)

            # Create or get Stripe customer
            if not user.stripe_customer_id:
                customer = stripe.Customer.create(
                    email=user.email,
                    metadata={'user_id': user.id}
                )
                user.stripe_customer_id = customer.id
                db.session.commit()

            # Create Checkout Session
            base_url = os.environ.get('BASE_URL', 'http://localhost:5000')
            checkout_session = stripe.checkout.Session.create(
                customer=user.stripe_customer_id,
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'unit_amount': package.price_cents,
                        'product_data': {
                            'name': f'{package.name} - {package.credits} Credits',
                            'description': f'Post credits for OpenClaw Dashboard',
                        },
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=f'{base_url}/?payment=success',
                cancel_url=f'{base_url}/?payment=cancelled',
                metadata={
                    'user_id': user.id,
                    'package_id': package.id,
                    'credits': package.credits
                }
            )

            return jsonify({
                'checkout_url': checkout_session.url,
                'session_id': checkout_session.id
            })

        except Exception as e:
            print(f"❌ Error in create_checkout_session: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/stripe/webhook', methods=['POST'])
    def stripe_webhook():
        """Handle Stripe webhook events"""
        payload = request.data
        sig_header = request.headers.get('Stripe-Signature')
        webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        except ValueError:
            print("❌ Invalid payload")
            return jsonify({'error': 'Invalid payload'}), 400
        except stripe.error.SignatureVerificationError:
            print("❌ Invalid signature")
            return jsonify({'error': 'Invalid signature'}), 400

        # Handle checkout.session.completed event
        if event['type'] == 'checkout.session.completed':
            session_data = event['data']['object']

            try:
                # Extract metadata
                user_id = int(session_data['metadata']['user_id'])
                package_id = int(session_data['metadata']['package_id'])
                credits = int(session_data['metadata']['credits'])

                # Get user and package
                user = User.query.get(user_id)
                package = CreditPackage.query.get(package_id)

                if user and package:
                    # Add credits to user
                    user.add_credits(
                        amount=credits,
                        reason=f'Purchased {package.name}',
                        stripe_payment_id=session_data['payment_intent']
                    )

                    # Record the checkout session ID
                    transaction = CreditTransaction.query.filter_by(
                        user_id=user_id,
                        stripe_payment_id=session_data['payment_intent']
                    ).first()

                    if transaction:
                        transaction.stripe_checkout_session_id = session_data['id']

                    db.session.commit()

                    print(f"✅ Added {credits} credits to user {user.email}")
                else:
                    print(f"❌ User or package not found: user_id={user_id}, package_id={package_id}")

            except Exception as e:
                print(f"❌ Error processing webhook: {e}")
                db.session.rollback()

        return jsonify({'success': True})

    @app.route('/api/credits/balance', methods=['GET'])
    @require_auth
    def get_credit_balance():
        """Get current user's credit balance"""
        try:
            user_id = session.get('user_id')
            user = User.query.get(user_id)

            return jsonify({
                'balance': user.credit_balance,
                'transactions': [{
                    'amount': t.amount,
                    'reason': t.reason,
                    'created_at': t.created_at.isoformat()
                } for t in user.transactions.order_by(CreditTransaction.created_at.desc()).limit(10)]
            })

        except Exception as e:
            print(f"❌ Error in get_credit_balance: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/moltbook/post', methods=['POST'])
    @require_auth
    def create_moltbook_post_paid():
        """Create Moltbook post (requires credits)"""
        try:
            user_id = session.get('user_id')
            user = User.query.get(user_id)

            # Check if user has credits
            if not user.has_credits(1):
                return jsonify({
                    'error': 'Insufficient credits',
                    'balance': user.credit_balance,
                    'required': 1
                }), 402  # Payment Required

            data = request.get_json()
            title = data.get('title')
            content = data.get('content')
            submolt = data.get('submolt', 'general')
            api_key = data.get('api_key')

            if not all([title, content, api_key]):
                return jsonify({'error': 'Missing required fields'}), 400

            # Deduct credit
            if not user.deduct_credits(1, reason='Moltbook post'):
                return jsonify({'error': 'Failed to deduct credits'}), 500

            # Record post history
            post = PostHistory(
                user_id=user.id,
                post_title=title,
                post_submolt=submolt,
                post_content_length=len(content)
            )
            db.session.add(post)
            db.session.commit()

            print(f"✅ Credit deducted for user {user.email}, new balance: {user.credit_balance}")

            # Return success (frontend will call Moltbook API directly)
            return jsonify({
                'success': True,
                'new_balance': user.credit_balance,
                'message': 'Credit deducted. Proceed with posting.'
            })

        except Exception as e:
            print(f"❌ Error in create_moltbook_post_paid: {e}")
            db.session.rollback()
            return jsonify({'error': str(e)}), 500
