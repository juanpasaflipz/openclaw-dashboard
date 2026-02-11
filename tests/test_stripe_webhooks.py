"""
Tests for Stripe webhook handlers
"""
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from models import User, CreditPackage, CreditTransaction, SubscriptionPlan, db


@pytest.fixture
def credit_package(app):
    """Create a test credit package"""
    package = CreditPackage(
        name='Starter Pack',
        credits=50,
        price_cents=1000,
        stripe_price_id='price_test_starter',
        is_active=True
    )
    db.session.add(package)
    db.session.commit()
    return package


@pytest.fixture
def subscription_plan(app):
    """Create a test subscription plan"""
    plan = SubscriptionPlan(
        tier='starter',
        name='Starter Plan',
        price_monthly_cents=2900,
        stripe_price_id='price_test_starter_sub',
        is_active=True
    )
    db.session.add(plan)
    db.session.commit()
    return plan


@pytest.mark.stripe
class TestStripeCheckoutWebhook:
    """Tests for checkout.session.completed webhook"""

    @patch('stripe.Webhook.construct_event')
    def test_credit_purchase_webhook(self, mock_construct, client, user, credit_package, app):
        """Test webhook for one-time credit purchase"""
        user_id = user.id
        package_id = credit_package.id
        package_credits = credit_package.credits

        event = {
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'id': 'cs_test_123',
                    'mode': 'payment',
                    'payment_intent': 'pi_test_123',
                    'metadata': {
                        'user_id': str(user_id),
                        'package_id': str(package_id),
                        'credits': str(package_credits)
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

        # Re-query from DB after request
        u = User.query.get(user_id)
        assert u.credit_balance >= package_credits

        transaction = CreditTransaction.query.filter_by(
            user_id=user_id,
            stripe_payment_id='pi_test_123'
        ).first()
        assert transaction is not None
        assert transaction.amount == package_credits

    @patch('stripe.Webhook.construct_event')
    def test_subscription_checkout_webhook(self, mock_construct, client, user, subscription_plan, app):
        """Test webhook for subscription checkout"""
        user_id = user.id
        plan_id = subscription_plan.id
        plan_tier = subscription_plan.tier

        event = {
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'id': 'cs_test_sub_123',
                    'mode': 'subscription',
                    'metadata': {
                        'user_id': str(user_id),
                        'plan_id': str(plan_id),
                        'tier': plan_tier
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
        user_id = user.id
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

        # Re-query from DB
        u = User.query.get(user_id)
        assert u.stripe_subscription_id == 'sub_test_123'
        assert u.subscription_tier == 'pro'
        assert u.subscription_status == 'active'
        assert u.subscription_started_at is not None
        assert u.subscription_expires_at is not None

    @patch('stripe.Webhook.construct_event')
    def test_subscription_updated(self, mock_construct, client, premium_user, app):
        """Test customer.subscription.updated webhook"""
        user_id = premium_user.id
        sub_id = premium_user.stripe_subscription_id
        future_time = int((datetime.utcnow() + timedelta(days=60)).timestamp())

        event = {
            'type': 'customer.subscription.updated',
            'data': {
                'object': {
                    'id': sub_id,
                    'status': 'active',
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

        u = User.query.get(user_id)
        assert u.subscription_tier == 'pro'
        assert u.subscription_status == 'active'

    @patch('stripe.Webhook.construct_event')
    def test_subscription_updated_to_past_due(self, mock_construct, client, premium_user, app):
        """Test subscription status changed to past_due"""
        user_id = premium_user.id
        sub_id = premium_user.stripe_subscription_id
        future_time = int((datetime.utcnow() + timedelta(days=30)).timestamp())

        event = {
            'type': 'customer.subscription.updated',
            'data': {
                'object': {
                    'id': sub_id,
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

        u = User.query.get(user_id)
        assert u.subscription_status == 'past_due'

    @patch('stripe.Webhook.construct_event')
    def test_subscription_deleted(self, mock_construct, client, premium_user, app):
        """Test customer.subscription.deleted webhook"""
        user_id = premium_user.id
        sub_id = premium_user.stripe_subscription_id

        event = {
            'type': 'customer.subscription.deleted',
            'data': {
                'object': {
                    'id': sub_id,
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

        u = User.query.get(user_id)
        assert u.subscription_status == 'cancelled'
        assert u.subscription_tier == 'free'


@pytest.mark.stripe
class TestInvoiceWebhooks:
    """Tests for invoice-related webhooks"""

    @patch('stripe.Webhook.construct_event')
    def test_invoice_payment_succeeded(self, mock_construct, client, premium_user, app):
        """Test invoice.payment_succeeded webhook (subscription renewal)"""
        user_id = premium_user.id
        sub_id = premium_user.stripe_subscription_id
        future_time = int((datetime.utcnow() + timedelta(days=30)).timestamp())

        event = {
            'type': 'invoice.payment_succeeded',
            'data': {
                'object': {
                    'subscription': sub_id,
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

        u = User.query.get(user_id)
        assert u.subscription_status == 'active'
        assert u.subscription_expires_at is not None

    @patch('stripe.Webhook.construct_event')
    def test_invoice_payment_failed(self, mock_construct, client, premium_user, app):
        """Test invoice.payment_failed webhook"""
        user_id = premium_user.id
        sub_id = premium_user.stripe_subscription_id

        event = {
            'type': 'invoice.payment_failed',
            'data': {
                'object': {
                    'subscription': sub_id
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

        u = User.query.get(user_id)
        assert u.subscription_status == 'past_due'

    @patch('stripe.Webhook.construct_event')
    def test_invoice_without_subscription_ignored(self, mock_construct, client, user, app):
        """Test that non-subscription invoices are ignored"""
        user_id = user.id
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

        u = User.query.get(user_id)
        assert u.credit_balance == initial_balance


@pytest.mark.stripe
@pytest.mark.integration
class TestCreditSystemIntegration:
    """Integration tests for credit system"""

    def test_user_credit_methods(self, app, user):
        """Test User model credit management methods"""
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
