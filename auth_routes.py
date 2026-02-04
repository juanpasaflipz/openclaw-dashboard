"""
Authentication routes for magic link email-based auth
"""
from flask import jsonify, request, session, url_for
from models import db, User, MagicLink
from datetime import datetime
import os


def send_magic_link_email(email, magic_link_url):
    """
    Send magic link email to user via SendGrid
    Falls back to console logging if SendGrid is not configured
    """
    sendgrid_api_key = os.environ.get('SENDGRID_API_KEY')

    # If SendGrid is configured, send real email
    if sendgrid_api_key:
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail

            # Get verified sender email from env, or use default
            from_email = os.environ.get('SENDGRID_FROM_EMAIL', 'noreply@openclaw.app')

            message = Mail(
                from_email=from_email,
                to_emails=email,
                subject='🦞 Your OpenClaw Dashboard Login Link',
                html_content=f'''
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #6366f1;">🦞 Sign in to OpenClaw Dashboard</h2>
                        <p>Click the button below to sign in to your account:</p>
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{magic_link_url}"
                               style="background: #6366f1; color: white; padding: 12px 24px;
                                      text-decoration: none; border-radius: 8px; display: inline-block;">
                                Sign In to Dashboard
                            </a>
                        </div>
                        <p style="color: #666; font-size: 14px;">
                            This link expires in 15 minutes.<br>
                            If you didn't request this, you can safely ignore this email.
                        </p>
                        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                        <p style="color: #999; font-size: 12px;">
                            OpenClaw Dashboard - AI Agent Configuration<br>
                            <a href="{magic_link_url}" style="color: #6366f1;">Click here if the button doesn't work</a>
                        </p>
                    </div>
                '''
            )

            sg = SendGridAPIClient(sendgrid_api_key)
            response = sg.send(message)

            print(f"✅ Email sent to {email} (Status: {response.status_code})")
            return True

        except Exception as e:
            print(f"❌ SendGrid error: {e}")
            print(f"📧 Falling back to console logging for {email}")
            # Fall through to console logging

    # Development mode: Print to console
    print("=" * 60)
    print("📧 MAGIC LINK EMAIL (Development Mode)")
    print("=" * 60)
    print(f"To: {email}")
    print(f"Magic Link: {magic_link_url}")
    print("=" * 60)
    print("💡 Add SENDGRID_API_KEY to environment to send real emails")
    print("=" * 60)

    return True


def register_auth_routes(app):
    """Register authentication routes with the Flask app"""

    @app.route('/api/auth/request-magic-link', methods=['POST'])
    def request_magic_link():
        """Request a magic link for email-based authentication"""
        try:
            data = request.get_json()
            email = data.get('email', '').strip().lower()

            if not email:
                return jsonify({'error': 'Email is required'}), 400

            # Basic email validation
            if '@' not in email or '.' not in email.split('@')[1]:
                return jsonify({'error': 'Invalid email address'}), 400

            # Find or create user
            user = User.query.filter_by(email=email).first()
            if not user:
                user = User(email=email)
                # Give 5 free credits for new users
                user.credit_balance = 5
                db.session.add(user)
                db.session.commit()
                print(f"✅ New user created: {email} (5 free credits)")

            # Create magic link
            magic_link = MagicLink.create_for_user(user.id, expires_in_minutes=15)
            magic_link.ip_address = request.remote_addr
            db.session.commit()

            # Generate magic link URL
            # In production, use your actual domain
            base_url = os.environ.get('BASE_URL', 'http://localhost:5000')
            magic_link_url = f"{base_url}/api/auth/verify?token={magic_link.token}"

            # Send email
            send_magic_link_email(email, magic_link_url)

            return jsonify({
                'success': True,
                'message': 'Magic link sent! Check your email (or console in development).',
                'dev_link': magic_link_url if app.debug else None  # Only show in debug mode
            })

        except Exception as e:
            print(f"❌ Error in request_magic_link: {e}")
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/auth/verify', methods=['GET'])
    def verify_magic_link():
        """Verify magic link token and create session"""
        try:
            token = request.args.get('token')

            if not token:
                return jsonify({'error': 'Token is required'}), 400

            # Find magic link
            magic_link = MagicLink.query.filter_by(token=token).first()

            if not magic_link:
                return jsonify({'error': 'Invalid magic link'}), 404

            if not magic_link.is_valid():
                return jsonify({'error': 'Magic link expired or already used'}), 400

            # Mark as used
            magic_link.mark_as_used()

            # Update user's last login
            user = magic_link.user
            user.last_login = datetime.utcnow()

            # Create session
            session['user_id'] = user.id
            session['email'] = user.email

            db.session.commit()

            print(f"✅ User logged in: {user.email}")

            # Redirect to dashboard
            return '''
            <html>
                <head><title>Login Successful</title></head>
                <body style="font-family: system-ui; text-align: center; padding: 50px;">
                    <h1>✅ Login Successful!</h1>
                    <p>You can close this tab and return to the dashboard.</p>
                    <script>
                        // Try to close the tab or redirect
                        setTimeout(() => {
                            window.location.href = '/';
                        }, 2000);
                    </script>
                </body>
            </html>
            '''

        except Exception as e:
            print(f"❌ Error in verify_magic_link: {e}")
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/auth/me', methods=['GET'])
    def get_current_user():
        """Get current authenticated user info"""
        try:
            user_id = session.get('user_id')

            if not user_id:
                return jsonify({'authenticated': False}), 401

            user = User.query.get(user_id)

            if not user:
                session.clear()
                return jsonify({'authenticated': False}), 401

            return jsonify({
                'authenticated': True,
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'credit_balance': user.credit_balance,
                    'created_at': user.created_at.isoformat(),
                    'stripe_customer_id': user.stripe_customer_id,
                    'subscription_tier': user.subscription_tier,
                    'subscription_status': user.subscription_status,
                    'subscription_expires_at': user.subscription_expires_at.isoformat() if user.subscription_expires_at else None
                }
            })

        except Exception as e:
            print(f"❌ Error in get_current_user: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/auth/logout', methods=['POST'])
    def logout():
        """Logout current user"""
        try:
            session.clear()
            return jsonify({'success': True, 'message': 'Logged out successfully'})
        except Exception as e:
            print(f"❌ Error in logout: {e}")
            return jsonify({'error': str(e)}), 500
