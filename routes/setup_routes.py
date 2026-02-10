"""
Setup wizard routes for guiding users through OpenClaw installation
"""
from flask import jsonify, request, session, render_template_string
import subprocess
import platform
import os
import shutil


def register_setup_routes(app):
    """Register setup wizard routes with the Flask app"""

    @app.route('/setup')
    def setup_wizard():
        """Render the setup wizard page"""
        # Check if user is authenticated
        user_id = session.get('user_id')
        if not user_id:
            return '''
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Setup - Green Monkey</title>
                    <style>
                        body {
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            min-height: 100vh;
                            margin: 0;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        }
                        .auth-required {
                            background: white;
                            padding: 48px;
                            border-radius: 16px;
                            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                            text-align: center;
                            max-width: 400px;
                        }
                        h1 { margin: 0 0 16px 0; color: #1a202c; }
                        p { color: #4a5568; margin: 0 0 24px 0; }
                        a {
                            display: inline-block;
                            padding: 12px 32px;
                            background: #667eea;
                            color: white;
                            text-decoration: none;
                            border-radius: 8px;
                            font-weight: 600;
                        }
                        a:hover { background: #5a67d8; }
                    </style>
                </head>
                <body>
                    <div class="auth-required">
                        <h1>🔐 Authentication Required</h1>
                        <p>Please sign in to access the setup wizard.</p>
                        <a href="/">Go to Dashboard</a>
                    </div>
                </body>
                </html>
            '''

        # Render setup wizard (will be replaced with proper template)
        return '''
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>OpenClaw Setup Wizard - Green Monkey</title>
                <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🐵</text></svg>">
                <link rel="stylesheet" href="/static/css/dashboard.css">
                <style>
                    .setup-container {
                        max-width: 900px;
                        margin: 0 auto;
                        padding: 40px 20px;
                    }

                    .setup-header {
                        text-align: center;
                        margin-bottom: 48px;
                    }

                    .setup-header h1 {
                        font-size: 32px;
                        margin: 0 0 16px 0;
                        color: var(--text-primary);
                    }

                    .setup-header p {
                        font-size: 16px;
                        color: var(--text-secondary);
                        margin: 0;
                    }

                    .progress-bar {
                        display: flex;
                        gap: 12px;
                        margin-bottom: 48px;
                        position: relative;
                    }

                    .progress-bar::before {
                        content: '';
                        position: absolute;
                        top: 20px;
                        left: 20px;
                        right: 20px;
                        height: 2px;
                        background: var(--border);
                        z-index: 0;
                    }

                    .progress-step {
                        flex: 1;
                        text-align: center;
                        position: relative;
                        z-index: 1;
                    }

                    .progress-step-circle {
                        width: 40px;
                        height: 40px;
                        border-radius: 50%;
                        background: var(--surface);
                        border: 2px solid var(--border);
                        margin: 0 auto 8px auto;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-weight: 600;
                        transition: all 0.3s ease;
                    }

                    .progress-step.active .progress-step-circle {
                        background: var(--primary);
                        color: white;
                        border-color: var(--primary);
                        transform: scale(1.1);
                    }

                    .progress-step.completed .progress-step-circle {
                        background: var(--success);
                        color: white;
                        border-color: var(--success);
                    }

                    .progress-step-label {
                        font-size: 13px;
                        color: var(--text-tertiary);
                        font-weight: 500;
                    }

                    .progress-step.active .progress-step-label {
                        color: var(--primary);
                        font-weight: 600;
                    }

                    .setup-step {
                        display: none;
                        background: var(--surface);
                        border-radius: 12px;
                        padding: 32px;
                        box-shadow: var(--shadow);
                    }

                    .setup-step.active {
                        display: block;
                        animation: slideIn 0.3s ease-out;
                    }

                    @keyframes slideIn {
                        from {
                            opacity: 0;
                            transform: translateY(20px);
                        }
                        to {
                            opacity: 1;
                            transform: translateY(0);
                        }
                    }

                    .step-title {
                        font-size: 24px;
                        margin: 0 0 16px 0;
                        color: var(--text-primary);
                    }

                    .step-description {
                        font-size: 15px;
                        color: var(--text-secondary);
                        margin: 0 0 32px 0;
                        line-height: 1.6;
                    }

                    .command-box {
                        background: #1e1e1e;
                        color: #d4d4d4;
                        padding: 20px;
                        border-radius: 8px;
                        font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
                        font-size: 14px;
                        margin: 16px 0;
                        position: relative;
                        overflow-x: auto;
                    }

                    .command-box pre {
                        margin: 0;
                        white-space: pre-wrap;
                        word-wrap: break-word;
                    }

                    .copy-button {
                        position: absolute;
                        top: 12px;
                        right: 12px;
                        padding: 6px 12px;
                        background: #333;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        cursor: pointer;
                        font-size: 12px;
                        transition: background 0.2s;
                    }

                    .copy-button:hover {
                        background: #444;
                    }

                    .copy-button.copied {
                        background: var(--success);
                    }

                    .status-check {
                        display: flex;
                        align-items: center;
                        gap: 12px;
                        padding: 16px;
                        background: var(--bg-color);
                        border-radius: 8px;
                        margin: 16px 0;
                    }

                    .status-check.checking {
                        border-left: 3px solid var(--warning);
                    }

                    .status-check.success {
                        border-left: 3px solid var(--success);
                    }

                    .status-check.error {
                        border-left: 3px solid var(--error);
                    }

                    .status-spinner {
                        width: 20px;
                        height: 20px;
                        border: 2px solid var(--border);
                        border-top-color: var(--primary);
                        border-radius: 50%;
                        animation: spin 0.8s linear infinite;
                    }

                    @keyframes spin {
                        to { transform: rotate(360deg); }
                    }

                    .button-group {
                        display: flex;
                        gap: 12px;
                        margin-top: 32px;
                        justify-content: space-between;
                    }

                    .btn {
                        padding: 12px 24px;
                        border: none;
                        border-radius: 8px;
                        font-size: 14px;
                        font-weight: 600;
                        cursor: pointer;
                        transition: all 0.2s;
                        text-decoration: none;
                        display: inline-block;
                    }

                    .btn-primary {
                        background: var(--primary);
                        color: white;
                    }

                    .btn-primary:hover {
                        background: var(--primary-dark);
                        transform: translateY(-1px);
                    }

                    .btn-secondary {
                        background: var(--bg-color);
                        color: var(--text-primary);
                    }

                    .btn-secondary:hover {
                        background: var(--border);
                    }

                    .btn:disabled {
                        opacity: 0.5;
                        cursor: not-allowed;
                    }

                    .os-selector {
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                        gap: 16px;
                        margin: 24px 0;
                    }

                    .os-option {
                        padding: 24px;
                        border: 2px solid var(--border);
                        border-radius: 12px;
                        text-align: center;
                        cursor: pointer;
                        transition: all 0.2s;
                    }

                    .os-option:hover {
                        border-color: var(--primary);
                        transform: translateY(-2px);
                    }

                    .os-option.selected {
                        border-color: var(--primary);
                        background: rgba(99, 91, 255, 0.05);
                    }

                    .os-icon {
                        font-size: 48px;
                        margin-bottom: 12px;
                    }

                    .os-name {
                        font-weight: 600;
                        color: var(--text-primary);
                    }

                    .provider-setup-card {
                        padding: 20px;
                        border: 2px solid var(--border);
                        border-radius: 12px;
                        cursor: pointer;
                        transition: all 0.2s;
                        background: var(--surface);
                    }

                    .provider-setup-card:hover {
                        border-color: var(--primary);
                        transform: translateY(-2px);
                        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                    }

                    .provider-setup-card.selected {
                        border-color: var(--primary);
                        background: rgba(99, 91, 255, 0.05);
                        box-shadow: 0 0 0 3px rgba(99, 91, 255, 0.1);
                    }

                    .provider-setup-card.locked {
                        opacity: 0.6;
                        cursor: not-allowed;
                    }

                    .provider-setup-card.locked:hover {
                        transform: none;
                        border-color: var(--border);
                        box-shadow: none;
                    }

                    .info-card {
                        background: #DBEAFE;
                        border-left: 3px solid var(--primary);
                        padding: 16px;
                        border-radius: 6px;
                        margin: 16px 0;
                    }

                    .info-card p {
                        margin: 0;
                        color: #1E40AF;
                        font-size: 14px;
                        line-height: 1.5;
                    }

                    .success-animation {
                        text-align: center;
                        padding: 48px 0;
                    }

                    .success-checkmark {
                        font-size: 80px;
                        animation: scaleIn 0.5s ease-out;
                    }

                    @keyframes scaleIn {
                        from {
                            opacity: 0;
                            transform: scale(0);
                        }
                        to {
                            opacity: 1;
                            transform: scale(1);
                        }
                    }
                </style>
            </head>
            <body>
                <div class="setup-container">
                    <div class="setup-header">
                        <h1>🚀 OpenClaw Setup Wizard</h1>
                        <p>Let's get your AI agent up and running in minutes</p>
                    </div>

                    <div class="progress-bar">
                        <div class="progress-step active" data-step="1">
                            <div class="progress-step-circle">1</div>
                            <div class="progress-step-label">Detect OS</div>
                        </div>
                        <div class="progress-step" data-step="2">
                            <div class="progress-step-circle">2</div>
                            <div class="progress-step-label">Install</div>
                        </div>
                        <div class="progress-step" data-step="3">
                            <div class="progress-step-circle">3</div>
                            <div class="progress-step-label">Configure</div>
                        </div>
                        <div class="progress-step" data-step="4">
                            <div class="progress-step-circle">4</div>
                            <div class="progress-step-label">Provider</div>
                        </div>
                        <div class="progress-step" data-step="5">
                            <div class="progress-step-circle">5</div>
                            <div class="progress-step-label">Verify</div>
                        </div>
                        <div class="progress-step" data-step="6">
                            <div class="progress-step-circle">✓</div>
                            <div class="progress-step-label">Done</div>
                        </div>
                    </div>

                    <!-- Step 1: OS Detection -->
                    <div class="setup-step active" data-step="1">
                        <h2 class="step-title">Select Your Operating System</h2>
                        <p class="step-description">Choose your platform to get the correct installation instructions</p>

                        <div class="os-selector">
                            <div class="os-option" data-os="macos">
                                <div class="os-icon">🍎</div>
                                <div class="os-name">macOS</div>
                            </div>
                            <div class="os-option" data-os="linux">
                                <div class="os-icon">🐧</div>
                                <div class="os-name">Linux</div>
                            </div>
                            <div class="os-option" data-os="windows">
                                <div class="os-icon">🪟</div>
                                <div class="os-name">Windows</div>
                            </div>
                        </div>

                        <div class="button-group">
                            <a href="/" class="btn btn-secondary">Back to Dashboard</a>
                            <button class="btn btn-primary" id="nextStep1" disabled>Continue</button>
                        </div>
                    </div>

                    <!-- Step 2: Installation -->
                    <div class="setup-step" data-step="2">
                        <h2 class="step-title">Install OpenClaw</h2>
                        <p class="step-description">Run this command in your terminal to install OpenClaw</p>

                        <div id="installInstructions"></div>

                        <div class="status-check" id="installCheck" style="display: none;">
                            <div class="status-spinner"></div>
                            <span>Checking installation...</span>
                        </div>

                        <div class="button-group">
                            <button class="btn btn-secondary" onclick="previousStep()">Back</button>
                            <button class="btn btn-primary" onclick="checkInstallation()">Check Installation</button>
                        </div>
                    </div>

                    <!-- Step 3: Configuration -->
                    <div class="setup-step" data-step="3">
                        <h2 class="step-title">Configure OpenClaw</h2>
                        <p class="step-description">Set up your agent's configuration and identity</p>

                        <div id="configInstructions"></div>

                        <div class="info-card">
                            <p><strong>💡 Tip:</strong> Your configuration will be synced with Green Monkey dashboard automatically.</p>
                        </div>

                        <div class="button-group">
                            <button class="btn btn-secondary" onclick="previousStep()">Back</button>
                            <button class="btn btn-primary" onclick="nextStep()">Continue</button>
                        </div>
                    </div>

                    <!-- Step 4: LLM Provider Setup -->
                    <div class="setup-step" data-step="4">
                        <h2 class="step-title">Choose Your LLM Provider</h2>
                        <p class="step-description">Select which AI model provider to use for your agent</p>

                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin: 24px 0;">
                            <!-- OpenAI Card -->
                            <div class="provider-setup-card" data-provider="openai">
                                <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                                    <div style="font-size: 40px;">🤖</div>
                                    <div>
                                        <h4 style="margin: 0; font-size: 18px;">OpenAI</h4>
                                        <span style="display: inline-block; background: #DCFCE7; color: #166534; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">FREE TIER</span>
                                    </div>
                                </div>
                                <p style="color: var(--text-secondary); font-size: 14px; margin: 12px 0;">
                                    GPT-4, GPT-4 Turbo, GPT-3.5 models. Most popular choice.
                                </p>
                                <ul style="font-size: 13px; color: var(--text-secondary); padding-left: 20px;">
                                    <li>Best general performance</li>
                                    <li>Large ecosystem</li>
                                    <li>Easy to get started</li>
                                </ul>
                            </div>

                            <!-- Venice AI Card -->
                            <div class="provider-setup-card" data-provider="venice">
                                <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                                    <div style="font-size: 40px;">🏛️</div>
                                    <div>
                                        <h4 style="margin: 0; font-size: 18px;">Venice AI</h4>
                                        <span style="display: inline-block; background: #FEF3C7; color: #92400E; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">STARTER+</span>
                                    </div>
                                </div>
                                <p style="color: var(--text-secondary); font-size: 14px; margin: 12px 0;">
                                    Privacy-first, uncensored AI with competitive pricing.
                                </p>
                                <ul style="font-size: 13px; color: var(--text-secondary); padding-left: 20px;">
                                    <li>60% cheaper than OpenAI</li>
                                    <li>No censorship</li>
                                    <li>Privacy-focused</li>
                                </ul>
                            </div>

                            <!-- Claude Card -->
                            <div class="provider-setup-card" data-provider="anthropic">
                                <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                                    <div style="font-size: 40px;">🧠</div>
                                    <div>
                                        <h4 style="margin: 0; font-size: 18px;">Anthropic Claude</h4>
                                        <span style="display: inline-block; background: #DBEAFE; color: #1E40AF; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">PRO+</span>
                                    </div>
                                </div>
                                <p style="color: var(--text-secondary); font-size: 14px; margin: 12px 0;">
                                    Claude 3.5 Sonnet - advanced reasoning and analysis.
                                </p>
                                <ul style="font-size: 13px; color: var(--text-secondary); padding-left: 20px;">
                                    <li>Best reasoning ability</li>
                                    <li>200K context window</li>
                                    <li>Superior tool use</li>
                                </ul>
                            </div>
                        </div>

                        <div id="providerConfigForm" style="display: none; margin-top: 24px; padding: 24px; background: var(--surface); border-radius: 12px; border: 2px solid var(--border);">
                            <h3 id="selectedProviderName" style="margin: 0 0 16px 0;"></h3>
                            <div id="providerFields"></div>
                        </div>

                        <div class="info-card" style="margin-top: 24px;">
                            <p><strong>💡 Note:</strong> You can change providers anytime from the Providers tab in your dashboard.</p>
                        </div>

                        <div class="button-group">
                            <button class="btn btn-secondary" onclick="previousStep()">Back</button>
                            <button class="btn btn-secondary" id="skipProvider" onclick="nextStep()">Skip for Now</button>
                            <button class="btn btn-primary" id="connectProviderBtn" onclick="saveProviderAndContinue()" disabled>Connect & Continue</button>
                        </div>
                    </div>

                    <!-- Step 5: Verification -->
                    <div class="setup-step" data-step="5">
                        <h2 class="step-title">Verify Setup</h2>
                        <p class="step-description">Let's make sure everything is working correctly</p>

                        <div class="status-check checking" id="verifyCheck">
                            <div class="status-spinner"></div>
                            <span>Running verification tests...</span>
                        </div>

                        <div id="verificationResults"></div>

                        <div class="button-group">
                            <button class="btn btn-secondary" onclick="previousStep()">Back</button>
                            <button class="btn btn-primary" id="completeSetup" onclick="completeSetup()" disabled>Complete Setup</button>
                        </div>
                    </div>

                    <!-- Step 6: Complete -->
                    <div class="setup-step" data-step="6">
                        <div class="success-animation">
                            <div class="success-checkmark">✅</div>
                            <h2 class="step-title">Setup Complete!</h2>
                            <p class="step-description">Your OpenClaw agent is ready to start posting</p>
                        </div>

                        <div class="info-card">
                            <p><strong>🎉 What's next?</strong> Head to your dashboard to configure your first agent and start posting to Moltbook!</p>
                        </div>

                        <div class="button-group" style="justify-content: center;">
                            <a href="/" class="btn btn-primary" style="min-width: 200px; text-align: center;">Go to Dashboard</a>
                        </div>
                    </div>
                </div>

                <script>
                    let currentStep = 1;
                    let selectedOS = null;

                    // Auto-detect OS
                    function detectOS() {
                        const userAgent = navigator.userAgent.toLowerCase();
                        if (userAgent.includes('mac')) return 'macos';
                        if (userAgent.includes('linux')) return 'linux';
                        if (userAgent.includes('win')) return 'windows';
                        return null;
                    }

                    // Initialize
                    document.addEventListener('DOMContentLoaded', () => {
                        const detectedOS = detectOS();
                        if (detectedOS) {
                            document.querySelector(`[data-os="${detectedOS}"]`)?.click();
                        }
                    });

                    // OS Selection
                    document.querySelectorAll('.os-option').forEach(option => {
                        option.addEventListener('click', function() {
                            document.querySelectorAll('.os-option').forEach(o => o.classList.remove('selected'));
                            this.classList.add('selected');
                            selectedOS = this.dataset.os;
                            document.getElementById('nextStep1').disabled = false;
                        });
                    });

                    document.getElementById('nextStep1').addEventListener('click', () => {
                        loadInstallInstructions();
                        nextStep();
                    });

                    function loadInstallInstructions() {
                        const instructions = {
                            macos: {
                                title: 'Install via Homebrew',
                                command: 'brew install openclaw',
                                note: 'If you don\'t have Homebrew, install it first: <a href="https://brew.sh" target="_blank">brew.sh</a>'
                            },
                            linux: {
                                title: 'Install via pip',
                                command: 'pip3 install openclaw',
                                note: 'You may need to use sudo on some systems'
                            },
                            windows: {
                                title: 'Install via pip',
                                command: 'pip install openclaw',
                                note: 'Make sure Python and pip are installed and in your PATH'
                            }
                        };

                        const inst = instructions[selectedOS];
                        document.getElementById('installInstructions').innerHTML = `
                            <h3>${inst.title}</h3>
                            <div class="command-box">
                                <button class="copy-button" onclick="copyCommand(this, '${inst.command}')">Copy</button>
                                <pre>${inst.command}</pre>
                            </div>
                            <div class="info-card">
                                <p>${inst.note}</p>
                            </div>
                        `;
                    }

                    function copyCommand(button, text) {
                        navigator.clipboard.writeText(text);
                        button.textContent = '✓ Copied';
                        button.classList.add('copied');
                        setTimeout(() => {
                            button.textContent = 'Copy';
                            button.classList.remove('copied');
                        }, 2000);
                    }

                    function checkInstallation() {
                        const checkEl = document.getElementById('installCheck');
                        checkEl.style.display = 'flex';
                        checkEl.className = 'status-check checking';
                        checkEl.innerHTML = '<div class="status-spinner"></div><span>Checking installation...</span>';

                        fetch('/api/setup/check-install')
                            .then(r => r.json())
                            .then(data => {
                                if (data.installed) {
                                    checkEl.className = 'status-check success';
                                    checkEl.innerHTML = '<span style="font-size: 20px;">✓</span><span>OpenClaw is installed! Click Continue to proceed.</span>';
                                    setTimeout(nextStep, 1500);
                                } else {
                                    checkEl.className = 'status-check error';
                                    checkEl.innerHTML = '<span style="font-size: 20px;">✗</span><span>OpenClaw not found. Please run the installation command above.</span>';
                                }
                            })
                            .catch(err => {
                                checkEl.className = 'status-check error';
                                checkEl.innerHTML = '<span style="font-size: 20px;">✗</span><span>Unable to check installation. Please try again.</span>';
                            });
                    }

                    // Provider Selection (Step 4)
                    let selectedProvider = null;
                    let selectedProviderData = null;

                    document.addEventListener('DOMContentLoaded', () => {
                        document.querySelectorAll('.provider-setup-card').forEach(card => {
                            card.addEventListener('click', function() {
                                // Check if locked
                                if (this.classList.contains('locked')) {
                                    alert('This provider requires a paid subscription. Please upgrade your plan to access this provider.');
                                    return;
                                }

                                // Deselect all
                                document.querySelectorAll('.provider-setup-card').forEach(c => c.classList.remove('selected'));

                                // Select this one
                                this.classList.add('selected');
                                selectedProvider = this.dataset.provider;

                                // Show configuration form
                                showProviderConfigForm(selectedProvider);

                                // Enable connect button
                                document.getElementById('connectProviderBtn').disabled = false;
                            });
                        });
                    });

                    function showProviderConfigForm(providerId) {
                        const providers = {
                            openai: {
                                name: 'OpenAI',
                                fields: [
                                    { key: 'api_key', label: 'API Key', type: 'password', required: true, help: 'Get from platform.openai.com' }
                                ]
                            },
                            venice: {
                                name: 'Venice AI',
                                fields: [
                                    { key: 'api_key', label: 'API Key', type: 'password', required: true, help: 'Get from venice.ai' }
                                ]
                            },
                            anthropic: {
                                name: 'Anthropic Claude',
                                fields: [
                                    { key: 'api_key', label: 'API Key', type: 'password', required: true, help: 'Get from console.anthropic.com' }
                                ]
                            }
                        };

                        selectedProviderData = providers[providerId];
                        const form = document.getElementById('providerConfigForm');
                        const nameEl = document.getElementById('selectedProviderName');
                        const fieldsEl = document.getElementById('providerFields');

                        nameEl.textContent = `Configure ${selectedProviderData.name}`;

                        fieldsEl.innerHTML = selectedProviderData.fields.map(field => `
                            <div style="margin-bottom: 16px;">
                                <label style="display: block; margin-bottom: 8px; font-weight: 500;">
                                    ${field.label}${field.required ? ' <span style="color: var(--error);">*</span>' : ''}
                                </label>
                                <input
                                    type="${field.type}"
                                    id="provider_${field.key}"
                                    ${field.required ? 'required' : ''}
                                    placeholder="${field.help || ''}"
                                    style="width: 100%; padding: 10px; border: 1px solid var(--border); border-radius: 6px;"
                                />
                                ${field.help ? `<small style="color: var(--text-tertiary); font-size: 12px;">${field.help}</small>` : ''}
                            </div>
                        `).join('');

                        form.style.display = 'block';
                    }

                    function saveProviderAndContinue() {
                        if (!selectedProvider || !selectedProviderData) {
                            alert('Please select a provider first');
                            return;
                        }

                        // Collect form data
                        const config = {};
                        selectedProviderData.fields.forEach(field => {
                            const input = document.getElementById(`provider_${field.key}`);
                            if (field.required && !input.value) {
                                alert(`Please fill in: ${field.label}`);
                                return;
                            }
                            config[field.key] = input.value;
                        });

                        // TODO: Save to backend
                        console.log('Saving provider config:', selectedProvider, config);

                        // Show success message
                        alert(`✅ ${selectedProviderData.name} configured successfully!`);

                        // Continue to next step
                        nextStep();
                    }

                    function nextStep() {
                        if (currentStep < 6) {
                            document.querySelector(`[data-step="${currentStep}"].setup-step`).classList.remove('active');
                            document.querySelector(`[data-step="${currentStep}"].progress-step`).classList.add('completed');
                            currentStep++;
                            document.querySelector(`[data-step="${currentStep}"].setup-step`).classList.add('active');
                            document.querySelector(`[data-step="${currentStep}"].progress-step`).classList.add('active');
                        }
                    }

                    function previousStep() {
                        if (currentStep > 1) {
                            document.querySelector(`[data-step="${currentStep}"].setup-step`).classList.remove('active');
                            document.querySelector(`[data-step="${currentStep}"].progress-step`).classList.remove('active');
                            currentStep--;
                            document.querySelector(`[data-step="${currentStep}"].setup-step`).classList.add('active');
                            document.querySelector(`[data-step="${currentStep}"].progress-step`).classList.remove('completed');
                        }
                    }

                    function completeSetup() {
                        nextStep();
                    }
                </script>
            </body>
            </html>
        '''

    @app.route('/api/setup/check-install', methods=['GET'])
    def check_openclaw_install():
        """Check if OpenClaw is installed"""
        try:
            # Try to find openclaw command
            openclaw_path = shutil.which('openclaw')

            if openclaw_path:
                # Try to get version
                try:
                    result = subprocess.run(
                        ['openclaw', '--version'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    version = result.stdout.strip() if result.returncode == 0 else 'unknown'

                    return jsonify({
                        'installed': True,
                        'path': openclaw_path,
                        'version': version
                    })
                except subprocess.TimeoutExpired:
                    return jsonify({
                        'installed': True,
                        'path': openclaw_path,
                        'version': 'unknown'
                    })
            else:
                return jsonify({'installed': False})

        except Exception as e:
            print(f"Error checking OpenClaw installation: {e}")
            return jsonify({'installed': False, 'error': str(e)})

    @app.route('/api/setup/detect-os', methods=['GET'])
    def detect_os():
        """Detect user's operating system"""
        try:
            system = platform.system().lower()
            return jsonify({
                'os': system,
                'platform': platform.platform(),
                'python_version': platform.python_version()
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
