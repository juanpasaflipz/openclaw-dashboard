"""
Stripe integration routes for credit purchases and subscriptions
"""
from flask import jsonify, request, session
from models import db, User, CreditPackage, CreditTransaction, PostHistory, SubscriptionPlan
from datetime import datetime, timedelta
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
                # Check if this is a subscription or one-time payment
                if session_data.get('mode') == 'subscription':
                    # Handle subscription checkout
                    user_id = int(session_data['metadata']['user_id'])
                    plan_id = int(session_data['metadata']['plan_id'])
                    tier = session_data['metadata']['tier']

                    user = User.query.get(user_id)
                    plan = SubscriptionPlan.query.get(plan_id)

                    if user and plan:
                        # Subscription will be activated by customer.subscription.created event
                        print(f"✅ Subscription checkout completed for user {user.email}, tier: {tier}")
                    else:
                        print(f"❌ User or plan not found: user_id={user_id}, plan_id={plan_id}")

                else:
                    # Handle one-time credit purchase
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
                print(f"❌ Error processing checkout.session.completed: {e}")
                db.session.rollback()

        # Handle subscription created
        elif event['type'] == 'customer.subscription.created':
            subscription = event['data']['object']
            try:
                # Find user by Stripe customer ID
                customer_id = subscription['customer']
                user = User.query.filter_by(stripe_customer_id=customer_id).first()

                if user:
                    # Get plan tier from metadata or subscription items
                    subscription_id = subscription['id']
                    tier = subscription.get('metadata', {}).get('tier', 'starter')

                    # Activate subscription
                    user.stripe_subscription_id = subscription_id
                    user.subscription_tier = tier
                    user.subscription_status = 'active'
                    user.subscription_started_at = datetime.fromtimestamp(subscription['current_period_start'])
                    user.subscription_expires_at = datetime.fromtimestamp(subscription['current_period_end'])

                    db.session.commit()
                    print(f"✅ Activated {tier} subscription for user {user.email}")
                else:
                    print(f"❌ User not found for customer_id: {customer_id}")

            except Exception as e:
                print(f"❌ Error processing customer.subscription.created: {e}")
                db.session.rollback()

        # Handle subscription updated
        elif event['type'] == 'customer.subscription.updated':
            subscription = event['data']['object']
            try:
                # Find user by subscription ID
                subscription_id = subscription['id']
                user = User.query.filter_by(stripe_subscription_id=subscription_id).first()

                if user:
                    # Update subscription status
                    status_map = {
                        'active': 'active',
                        'past_due': 'past_due',
                        'canceled': 'cancelled',
                        'unpaid': 'inactive',
                        'incomplete': 'inactive',
                        'incomplete_expired': 'inactive',
                        'trialing': 'active',
                        'paused': 'inactive'
                    }

                    stripe_status = subscription['status']
                    user.subscription_status = status_map.get(stripe_status, 'inactive')
                    user.subscription_expires_at = datetime.fromtimestamp(subscription['current_period_end'])

                    # Handle tier changes (if metadata was updated)
                    if 'tier' in subscription.get('metadata', {}):
                        user.subscription_tier = subscription['metadata']['tier']

                    db.session.commit()
                    print(f"✅ Updated subscription for user {user.email}: status={user.subscription_status}")
                else:
                    print(f"❌ User not found for subscription_id: {subscription_id}")

            except Exception as e:
                print(f"❌ Error processing customer.subscription.updated: {e}")
                db.session.rollback()

        # Handle subscription deleted (cancelled)
        elif event['type'] == 'customer.subscription.deleted':
            subscription = event['data']['object']
            try:
                # Find user by subscription ID
                subscription_id = subscription['id']
                user = User.query.filter_by(stripe_subscription_id=subscription_id).first()

                if user:
                    # Cancel subscription
                    user.subscription_status = 'cancelled'
                    user.subscription_tier = 'free'
                    user.subscription_expires_at = datetime.utcnow()

                    db.session.commit()
                    print(f"✅ Cancelled subscription for user {user.email}")
                else:
                    print(f"❌ User not found for subscription_id: {subscription_id}")

            except Exception as e:
                print(f"❌ Error processing customer.subscription.deleted: {e}")
                db.session.rollback()

        # Handle successful payment (subscription renewal)
        elif event['type'] == 'invoice.payment_succeeded':
            invoice = event['data']['object']
            try:
                # Only process subscription invoices (not one-time payments)
                if invoice.get('subscription'):
                    subscription_id = invoice['subscription']
                    user = User.query.filter_by(stripe_subscription_id=subscription_id).first()

                    if user:
                        # Renew subscription
                        user.subscription_status = 'active'
                        user.subscription_expires_at = datetime.fromtimestamp(invoice['period_end'])

                        db.session.commit()
                        print(f"✅ Renewed subscription for user {user.email}")
                    else:
                        print(f"❌ User not found for subscription_id: {subscription_id}")

            except Exception as e:
                print(f"❌ Error processing invoice.payment_succeeded: {e}")
                db.session.rollback()

        # Handle failed payment
        elif event['type'] == 'invoice.payment_failed':
            invoice = event['data']['object']
            try:
                if invoice.get('subscription'):
                    subscription_id = invoice['subscription']
                    user = User.query.filter_by(stripe_subscription_id=subscription_id).first()

                    if user:
                        # Mark subscription as past_due
                        user.subscription_status = 'past_due'

                        db.session.commit()
                        print(f"⚠️ Payment failed for user {user.email}, marked as past_due")
                    else:
                        print(f"❌ User not found for subscription_id: {subscription_id}")

            except Exception as e:
                print(f"❌ Error processing invoice.payment_failed: {e}")
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

            # Check rate limit: 30 minutes between posts (SKIP for Premium users!)
            if not user.has_unlimited_posts():
                last_post = PostHistory.query.filter_by(user_id=user.id).order_by(PostHistory.created_at.desc()).first()
                if last_post:
                    time_since_last_post = datetime.utcnow() - last_post.created_at
                    if time_since_last_post < timedelta(minutes=30):
                        minutes_remaining = 30 - int(time_since_last_post.total_seconds() / 60)
                        return jsonify({
                            'error': 'Rate limit exceeded',
                            'message': f'Please wait {minutes_remaining} more minutes before posting again. Note: Moltbook has a 30-minute rate limit for all users.',
                            'cooldown_minutes': minutes_remaining,
                            'upgrade_available': False
                        }), 429  # Too Many Requests
            else:
                print(f"✨ Premium user {user.email} - no rate limit!")

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

    # ==================== SUBSCRIPTION ENDPOINTS ====================

    @app.route('/api/subscriptions/plans', methods=['GET'])
    def get_subscription_plans():
        """Get available subscription plans"""
        try:
            plans = SubscriptionPlan.query.filter_by(is_active=True).all()
            return jsonify({
                'plans': [{
                    'id': plan.id,
                    'tier': plan.tier,
                    'name': plan.name,
                    'price': plan.price_monthly_dollars,
                    'features': {
                        'unlimited_posts': plan.unlimited_posts,
                        'max_agents': plan.max_agents,
                        'scheduled_posting': plan.scheduled_posting,
                        'analytics': plan.analytics,
                        'api_access': plan.api_access,
                        'team_members': plan.team_members,
                        'priority_support': plan.priority_support
                    }
                } for plan in plans]
            })
        except Exception as e:
            print(f"❌ Error in get_subscription_plans: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/subscriptions/create-checkout', methods=['POST'])
    @require_auth
    def create_subscription_checkout():
        """Create a Stripe Checkout session for subscription"""
        try:
            data = request.get_json()
            plan_id = data.get('plan_id')

            if not plan_id:
                return jsonify({'error': 'Plan ID is required'}), 400

            # Get plan
            plan = SubscriptionPlan.query.get(plan_id)
            if not plan or not plan.is_active:
                return jsonify({'error': 'Invalid plan'}), 404

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

            # Create Checkout Session for subscription
            base_url = os.environ.get('BASE_URL', 'http://localhost:5000')
            checkout_session = stripe.checkout.Session.create(
                customer=user.stripe_customer_id,
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'unit_amount': plan.price_monthly_cents,
                        'recurring': {
                            'interval': 'month'
                        },
                        'product_data': {
                            'name': f'{plan.name}',
                            'description': f'OpenClaw Dashboard - {plan.tier.title()} Tier',
                        },
                    },
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=f'{base_url}/?subscription=success',
                cancel_url=f'{base_url}/?subscription=cancelled',
                metadata={
                    'user_id': user.id,
                    'plan_id': plan.id,
                    'tier': plan.tier
                }
            )

            return jsonify({
                'checkout_url': checkout_session.url,
                'session_id': checkout_session.id
            })

        except Exception as e:
            print(f"❌ Error in create_subscription_checkout: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/subscriptions/portal', methods=['POST'])
    @require_auth
    def create_customer_portal():
        """Create Stripe Customer Portal session for managing subscription"""
        try:
            user_id = session.get('user_id')
            user = User.query.get(user_id)

            if not user.stripe_customer_id:
                return jsonify({'error': 'No subscription to manage'}), 404

            base_url = os.environ.get('BASE_URL', 'http://localhost:5000')
            portal_session = stripe.billing_portal.Session.create(
                customer=user.stripe_customer_id,
                return_url=f'{base_url}/',
            )

            return jsonify({'portal_url': portal_session.url})

        except Exception as e:
            print(f"❌ Error in create_customer_portal: {e}")
            return jsonify({'error': str(e)}), 500
