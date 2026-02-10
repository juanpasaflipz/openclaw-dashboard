"""
Tests for Stripe webhook handlers
"""
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from models import User, CreditPackage, CreditTransaction, SubscriptionPlan, db


@pytest.fixture
def credit_package(app, db_session):
    """Create a test credit package"""
    package = CreditPackage(
        name='Starter Pack',
        credits=50,
        price_dollars=10.00,
        price_cents=1000,
        stripe_price_id='price_test_starter',
        is_active=True
    )
    db_session.add(package)
    db_session.commit()
    return package


@pytest.fixture
def subscription_plan(app, db_session):
    """Create a test subscription plan"""
    plan = SubscriptionPlan(
        tier='starter',
        name='Starter Plan',
        price_monthly=29,
        price_cents_monthly=2900,
        stripe_price_id='price_test_starter_sub',
        features_json='{"agents": 3, "posts": "unlimited"}',
        is_active=True
    )
    db_session.add(plan)
    db_session.commit()
    return plan


@pytest.mark.stripe
class TestStripeCheckoutWebhook:
    """Tests for checkout.session.completed webhook"""

    @patch('stripe.Webhook.construct_event')
    def test_credit_purchase_webhook(self, mock_construct, client, user, credit_package, app):
        """Test webhook for one-time credit purchase"""
        with app.app_context():
            # Create mock Stripe event
            event = {
                'type': 'checkout.session.completed',
                'data': {
                    'object': {
                        'id': 'cs_test_123',
                        'mode': 'payment',
                        'payment_intent': 'pi_test_123',
                        'metadata': {
                            'user_id': str(user.id),
                            'package_id': str(credit_package.id),
                            'credits': str(credit_package.credits)
                        }
                    }
                }
            }
            mock_construct.return_value = event

            # Send webhook
            response = client.post(
                '/api/stripe/webhook',
                data=json.dumps(event),
                headers={'Stripe-Signature': 'test_signature'}
            )

            assert response.status_code == 200

            # Verify credits were added
            db_session = db.session
            db_session.refresh(user)
            assert user.credit_balance >= credit_package.credits

            # Verify transaction was recorded
            transaction = CreditTransaction.query.filter_by(
                user_id=user.id,
                stripe_payment_id='pi_test_123'
            ).first()
            assert transaction is not None
            assert transaction.amount == credit_package.credits

    @patch('stripe.Webhook.construct_event')
    def test_subscription_checkout_webhook(self, mock_construct, client, user, subscription_plan, app):
        """Test webhook for subscription checkout"""
        with app.app_context():
            event = {
                'type': 'checkout.session.completed',
                'data': {
                    'object': {
                        'id': 'cs_test_sub_123',
                        'mode': 'subscription',
                        'metadata': {
                            'user_id': str(user.id),
                            'plan_id': str(subscription_plan.id),
                            'tier': subscription_plan.tier
                        }
                    }
                }
            }
            mock_construct.return_value = event

            response = client.post(
                '/api/stripe/webhook',
                data=json.dumps(event),
                headers={'Stripe-Signature': 'test_signature'}
            )

            assert response.status_code == 200
            # Subscription activation happens in customer.subscription.created

    @patch('stripe.Webhook.construct_event')
    def test_webhook_invalid_signature(self, mock_construct, client):
        """Test webhook with invalid signature"""
        import stripe
        mock_construct.side_effect = stripe.error.SignatureVerificationError('Invalid signature', 'sig')

        response = client.post(
            '/api/stripe/webhook',
            data=json.dumps({'type': 'test'}),
            headers={'Stripe-Signature': 'invalid'}
        )

        assert response.status_code == 400
        data = response.get_json()
        assert 'Invalid signature' in data['error']


@pytest.mark.stripe
class TestSubscriptionWebhooks:
    """Tests for subscription lifecycle webhooks"""

    @patch('stripe.Webhook.construct_event')
    def test_subscription_created(self, mock_construct, client, user, app):
        """Test customer.subscription.created webhook"""
        with app.app_context():
            # Update user with Stripe customer ID
            user.stripe_customer_id = 'cus_test_123'
            db.session.commit()

            current_time = int(datetime.utcnow().timestamp())
            future_time = int((datetime.utcnow() + timedelta(days=30)).timestamp())

            event = {
                'type': 'customer.subscription.created',
                'data': {
                    'object': {
                        'id': 'sub_test_123',
                        'customer': 'cus_test_123',
                        'status': 'active',
                        'current_period_start': current_time,
                        'current_period_end': future_time,
                        'metadata': {
                            'tier': 'pro'
                        }
                    }
                }
            }
            mock_construct.return_value = event

            response = client.post(
                '/api/stripe/webhook',
                data=json.dumps(event),
                headers={'Stripe-Signature': 'test_signature'}
            )

            assert response.status_code == 200

            # Verify subscription was activated
            db.session.refresh(user)
            assert user.stripe_subscription_id == 'sub_test_123'
            assert user.subscription_tier == 'pro'
            assert user.subscription_status == 'active'
            assert user.subscription_started_at is not None
            assert user.subscription_expires_at is not None

    @patch('stripe.Webhook.construct_event')
    def test_subscription_updated(self, mock_construct, client, premium_user, app):
        """Test customer.subscription.updated webhook"""
        with app.app_context():
            future_time = int((datetime.utcnow() + timedelta(days=60)).timestamp())

            event = {
                'type': 'customer.subscription.updated',
                'data': {
                    'object': {
                        'id': premium_user.stripe_subscription_id,
                        'status': 'active',
                        'current_period_end': future_time,
                        'metadata': {
                            'tier': 'pro'  # Upgraded tier
                        }
                    }
                }
            }
            mock_construct.return_value = event

            response = client.post(
                '/api/stripe/webhook',
                data=json.dumps(event),
                headers={'Stripe-Signature': 'test_signature'}
            )

            assert response.status_code == 200

            # Verify subscription was updated
            db.session.refresh(premium_user)
            assert premium_user.subscription_tier == 'pro'
            assert premium_user.subscription_status == 'active'

    @patch('stripe.Webhook.construct_event')
    def test_subscription_updated_to_past_due(self, mock_construct, client, premium_user, app):
        """Test subscription status changed to past_due"""
        with app.app_context():
            future_time = int((datetime.utcnow() + timedelta(days=30)).timestamp())

            event = {
                'type': 'customer.subscription.updated',
                'data': {
                    'object': {
                        'id': premium_user.stripe_subscription_id,
                        'status': 'past_due',
                        'current_period_end': future_time,
                        'metadata': {}
                    }
                }
            }
            mock_construct.return_value = event

            response = client.post(
                '/api/stripe/webhook',
                data=json.dumps(event),
                headers={'Stripe-Signature': 'test_signature'}
            )

            assert response.status_code == 200

            # Verify subscription status was updated
            db.session.refresh(premium_user)
            assert premium_user.subscription_status == 'past_due'

    @patch('stripe.Webhook.construct_event')
    def test_subscription_deleted(self, mock_construct, client, premium_user, app):
        """Test customer.subscription.deleted webhook"""
        with app.app_context():
            event = {
                'type': 'customer.subscription.deleted',
                'data': {
                    'object': {
                        'id': premium_user.stripe_subscription_id,
                        'status': 'canceled'
                    }
                }
            }
            mock_construct.return_value = event

            response = client.post(
                '/api/stripe/webhook',
                data=json.dumps(event),
                headers={'Stripe-Signature': 'test_signature'}
            )

            assert response.status_code == 200

            # Verify subscription was cancelled
            db.session.refresh(premium_user)
            assert premium_user.subscription_status == 'cancelled'
            assert premium_user.subscription_tier == 'free'


@pytest.mark.stripe
class TestInvoiceWebhooks:
    """Tests for invoice-related webhooks"""

    @patch('stripe.Webhook.construct_event')
    def test_invoice_payment_succeeded(self, mock_construct, client, premium_user, app):
        """Test invoice.payment_succeeded webhook (subscription renewal)"""
        with app.app_context():
            future_time = int((datetime.utcnow() + timedelta(days=30)).timestamp())

            event = {
                'type': 'invoice.payment_succeeded',
                'data': {
                    'object': {
                        'subscription': premium_user.stripe_subscription_id,
                        'period_end': future_time
                    }
                }
            }
            mock_construct.return_value = event

            response = client.post(
                '/api/stripe/webhook',
                data=json.dumps(event),
                headers={'Stripe-Signature': 'test_signature'}
            )

            assert response.status_code == 200

            # Verify subscription was renewed
            db.session.refresh(premium_user)
            assert premium_user.subscription_status == 'active'
            assert premium_user.subscription_expires_at is not None

    @patch('stripe.Webhook.construct_event')
    def test_invoice_payment_failed(self, mock_construct, client, premium_user, app):
        """Test invoice.payment_failed webhook"""
        with app.app_context():
            event = {
                'type': 'invoice.payment_failed',
                'data': {
                    'object': {
                        'subscription': premium_user.stripe_subscription_id
                    }
                }
            }
            mock_construct.return_value = event

            response = client.post(
                '/api/stripe/webhook',
                data=json.dumps(event),
                headers={'Stripe-Signature': 'test_signature'}
            )

            assert response.status_code == 200

            # Verify subscription was marked past_due
            db.session.refresh(premium_user)
            assert premium_user.subscription_status == 'past_due'

    @patch('stripe.Webhook.construct_event')
    def test_invoice_without_subscription_ignored(self, mock_construct, client, user, app):
        """Test that non-subscription invoices are ignored"""
        with app.app_context():
            initial_balance = user.credit_balance

            event = {
                'type': 'invoice.payment_succeeded',
                'data': {
                    'object': {
                        'subscription': None,  # Not a subscription invoice
                        'period_end': int(datetime.utcnow().timestamp())
                    }
                }
            }
            mock_construct.return_value = event

            response = client.post(
                '/api/stripe/webhook',
                data=json.dumps(event),
                headers={'Stripe-Signature': 'test_signature'}
            )

            assert response.status_code == 200

            # Verify user wasn't affected
            db.session.refresh(user)
            assert user.credit_balance == initial_balance


@pytest.mark.stripe
@pytest.mark.integration
class TestCreditSystemIntegration:
    """Integration tests for credit system"""

    def test_user_credit_methods(self, app, user):
        """Test User model credit management methods"""
        with app.app_context():
            # Test has_credits
            user.credit_balance = 10
            assert user.has_credits(5) is True
            assert user.has_credits(15) is False

            # Test add_credits
            initial_balance = user.credit_balance
            user.add_credits(20, 'test_purchase')
            db.session.commit()

            assert user.credit_balance == initial_balance + 20

            # Verify transaction was recorded
            transaction = CreditTransaction.query.filter_by(
                user_id=user.id,
                transaction_type='credit',
                reason='test_purchase'
            ).first()
            assert transaction is not None
            assert transaction.amount == 20

            # Test deduct_credits
            initial_balance = user.credit_balance
            success = user.deduct_credits(5, 'test_post')
            db.session.commit()

            assert success is True
            assert user.credit_balance == initial_balance - 5

            # Verify debit transaction was recorded
            transaction = CreditTransaction.query.filter_by(
                user_id=user.id,
                transaction_type='debit',
                reason='test_post'
            ).first()
            assert transaction is not None
            assert transaction.amount == -5

            # Test insufficient credits
            user.credit_balance = 2
            success = user.deduct_credits(5)
            assert success is False
            assert user.credit_balance == 2  # Balance unchanged
