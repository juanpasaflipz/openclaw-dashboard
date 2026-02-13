        // API Configuration
        const API_BASE = window.location.origin + '/api';

        // LLM Provider Models
        const PROVIDER_MODELS = {
            anthropic: [
                'claude-3-5-sonnet-20241022',
                'claude-3-5-haiku-20241022',
                'claude-3-opus-20240229',
                'claude-3-sonnet-20240229',
                'claude-3-haiku-20240307'
            ],
            openai: [
                'gpt-4-turbo-preview',
                'gpt-4',
                'gpt-3.5-turbo',
                'gpt-4o',
                'gpt-4o-mini'
            ],
            openrouter: [
                'anthropic/claude-3-opus',
                'anthropic/claude-3-sonnet',
                'openai/gpt-4-turbo',
                'google/gemini-pro',
                'meta-llama/llama-3-70b'
            ],
            ollama: [
                'llama2',
                'mistral',
                'codellama',
                'mixtral',
                'neural-chat'
            ],
            custom: []
        };

        // ===== Tab-to-group mapping =====
        const TAB_GROUP_MAP = {
            'overview': null,
            // Agents
            'agents': 'agents',
            'identity': 'agents',
            'user': 'agents',
            'soul': 'agents',
            'tools': 'agents',
            'security': 'agents',
            // Tasks
            'collab-tasks': 'tasks',
            'collab-team': 'tasks',
            // Governance
            'governance': 'governance',
            'actions': 'governance',
            'chatbot': 'governance',
            // Observability
            'observability': 'observability',
            'analytics': 'observability',
            // Integrations
            'connect': 'integrations',
            'channels': 'integrations',
            'providers': 'integrations',
            'model-config': 'integrations',
            'llm': 'integrations',
            // Workspace
            'subscription': 'workspace',
            'export': 'workspace',
            'admin': 'workspace',
            // Labs
            'moltbook': 'labs',
            'feed': 'labs',
            'web-browse': 'labs',
            'utility': 'labs'
        };

        // ===== Tab label map for header title =====
        const TAB_LABEL_MAP = {
            'overview': 'Overview',
            'agents': 'Agents',
            'identity': 'Identity',
            'user': 'User Info',
            'soul': 'Soul & Behavior',
            'tools': 'Tools',
            'security': 'Security',
            'collab-tasks': 'Task Queue',
            'collab-team': 'Team Hierarchy',
            'governance': 'Risk Policies',
            'actions': 'Approval Queue',
            'chatbot': 'Chatbot',
            'observability': 'Live Activity',
            'analytics': 'Analytics',
            'connect': 'Services',
            'channels': 'Channels',
            'providers': 'Providers',
            'model-config': 'Model Config',
            'llm': 'LLM Connection',
            'subscription': 'Subscription',
            'export': 'Export',
            'admin': 'Admin',
            'moltbook': 'Moltbook',
            'feed': 'Feed',
            'web-browse': 'Web Browse',
            'utility': 'Utility'
        };

        // ===== Sidebar navigation click handlers =====
        document.querySelectorAll('.sidebar-item[data-tab]').forEach(navItem => {
            navItem.addEventListener('click', () => {
                const targetTab = navItem.dataset.tab;
                switchTab(targetTab);
                closeSidebarMobile();
            });
        });

        function switchTab(tabName) {
            // Clear all active states on sidebar items
            document.querySelectorAll('.sidebar-item').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

            // Activate the sidebar item
            const sidebarItem = document.querySelector(`.sidebar-item[data-tab="${tabName}"]`);
            if (sidebarItem) {
                sidebarItem.classList.add('active');
            }

            // Expand parent sidebar group if needed
            const group = TAB_GROUP_MAP[tabName];
            if (group) {
                const parentGroup = document.querySelector(`.sidebar-group[data-group="${group}"]`);
                if (parentGroup && !parentGroup.classList.contains('expanded')) {
                    parentGroup.classList.add('expanded');
                }
            }

            // Update header page title
            const titleEl = document.getElementById('header-page-title');
            if (titleEl) {
                titleEl.textContent = TAB_LABEL_MAP[tabName] || tabName;
            }

            // Show the tab content
            const tabContent = document.getElementById(tabName);
            if (tabContent) tabContent.classList.add('active');

            // Tab-specific init calls
            if (tabName === 'export') loadPreviews();
            if (tabName === 'moltbook') loadMoltbookState();
            if (tabName === 'agents') loadAgents();
            if (tabName === 'feed') initFeedTab();
            if (tabName === 'analytics') initAnalyticsTab();
            if (tabName === 'chatbot') initChatTab();
            if (tabName === 'web-browse') initWebBrowseTab();
            if (tabName === 'utility') initUtilityTab();
            if (tabName === 'model-config') initModelConfigTab();
            if (tabName === 'observability') initObservabilityTab();
            if (tabName === 'governance') initGovernanceTab();
            if (tabName === 'collab-tasks') initCollabTasksTab();
            if (tabName === 'collab-team') initCollabTeamTab();
        }

        // ===== Sidebar group toggle =====
        document.querySelectorAll('.sidebar-group-toggle').forEach(toggle => {
            toggle.addEventListener('click', () => {
                const group = toggle.closest('.sidebar-group');
                if (group) {
                    group.classList.toggle('expanded');
                }
            });
        });

        // ===== Mobile sidebar =====
        function openSidebarMobile() {
            const sidebar = document.getElementById('sidebar');
            const overlay = document.getElementById('sidebar-overlay');
            if (sidebar) sidebar.classList.add('open');
            if (overlay) overlay.classList.add('active');
        }

        function closeSidebarMobile() {
            const sidebar = document.getElementById('sidebar');
            const overlay = document.getElementById('sidebar-overlay');
            if (sidebar) sidebar.classList.remove('open');
            if (overlay) overlay.classList.remove('active');
        }

        document.getElementById('header-hamburger')?.addEventListener('click', openSidebarMobile);
        document.getElementById('sidebar-overlay')?.addEventListener('click', closeSidebarMobile);

        // Compatibility aliases
        function closeAllDropdowns() { /* no-op for backward compat */ }
        function closeMobileMenu() { closeSidebarMobile(); }

        // Close sidebar on resize to desktop
        window.addEventListener('resize', () => {
            if (window.innerWidth > 1024) {
                closeSidebarMobile();
            }
        });

        // ===== Theme Toggle =====
        function initTheme() {
            const saved = localStorage.getItem('gm-theme');
            const theme = saved || 'light';
            document.documentElement.setAttribute('data-theme', theme);
            updateThemeIcon(theme);
        }

        function toggleTheme() {
            const current = document.documentElement.getAttribute('data-theme') || 'light';
            const next = current === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('gm-theme', next);
            updateThemeIcon(next);
        }

        function updateThemeIcon(theme) {
            const btn = document.getElementById('theme-toggle');
            if (btn) btn.textContent = theme === 'light' ? '🌙' : '☀️';
        }

        document.getElementById('theme-toggle')?.addEventListener('click', toggleTheme);
        initTheme();

        // LLM Provider Selection
        document.querySelectorAll('.llm-provider-grid .provider-card').forEach(card => {
            card.addEventListener('click', () => {
                document.querySelectorAll('.llm-provider-grid .provider-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');

                const provider = card.dataset.provider;
                document.getElementById('llm-provider').value = provider;
                document.getElementById('llm-config-form').style.display = 'block';
                document.getElementById('test-btn').style.display = 'inline-flex';

                // Update API key field based on provider
                const apiKeyGroup = document.getElementById('api-key-group');
                const apiKeyLabel = document.getElementById('api-key-label');
                const apiKeyInput = document.getElementById('llm-api-key');
                const baseUrlInput = document.getElementById('llm-base-url');

                if (provider === 'ollama') {
                    // Ollama doesn't need API key
                    apiKeyGroup.style.display = 'none';
                    baseUrlInput.placeholder = 'http://localhost:11434 (default)';
                } else {
                    // Other providers need API key
                    apiKeyGroup.style.display = 'block';
                    apiKeyLabel.textContent = 'API Key *';
                    apiKeyInput.placeholder = 'sk-...';
                    baseUrlInput.placeholder = 'https://api.example.com/v1';
                }

                // Update model input and suggestions
                const modelInput = document.getElementById('llm-model');
                const modelSuggestions = document.getElementById('model-suggestions');

                // Clear previous value and suggestions
                modelInput.value = '';
                modelSuggestions.innerHTML = '';

                // Add model suggestions to datalist
                PROVIDER_MODELS[provider].forEach(model => {
                    const option = document.createElement('option');
                    option.value = model;
                    modelSuggestions.appendChild(option);
                });
            });
        });

        // Emoji selection
        document.querySelectorAll('.emoji-option').forEach(option => {
            option.addEventListener('click', () => {
                document.querySelectorAll('.emoji-option').forEach(o => o.classList.remove('selected'));
                option.classList.add('selected');
                document.getElementById('ai-emoji').value = option.dataset.emoji;
            });
        });

        // Password toggle
        function togglePassword(fieldId) {
            const field = document.getElementById(fieldId);
            field.type = field.type === 'password' ? 'text' : 'password';
        }

        // Alert helper
        function showAlert(tabName, type, message) {
            const alert = document.getElementById(`${tabName}-alert`);
            if (!alert) return;
            alert.className = `alert ${type} show`;
            alert.innerHTML = `${type === 'success' ? '✅' : '❌'} ${message}`;
            setTimeout(() => {
                alert.classList.remove('show');
            }, 5000);
        }

        // Button loading state helpers
        function setButtonLoading(button, loading, originalText) {
            if (loading) {
                button.classList.add('loading');
                button.disabled = true;
                button.dataset.originalText = button.textContent;
                button.textContent = originalText || 'Loading...';
            } else {
                button.classList.remove('loading');
                button.disabled = false;
                if (button.dataset.originalText) {
                    button.textContent = button.dataset.originalText;
                }
            }
        }

        function withLoading(button, asyncFn) {
            return async function(...args) {
                setButtonLoading(button, true);
                try {
                    const result = await asyncFn(...args);
                    return result;
                } finally {
                    setButtonLoading(button, false);
                }
            };
        }

        // Update status indicator
        function updateStatus(type, complete, label) {
            const indicator = document.getElementById(`status-${type}`);
            const progress = document.getElementById(`progress-${type}`);

            if (indicator && progress) {
                if (complete) {
                    indicator.classList.remove('incomplete');
                    indicator.classList.add('complete');
                    progress.textContent = label;
                } else {
                    indicator.classList.remove('complete');
                    indicator.classList.add('incomplete');
                    progress.textContent = label;
                }
            }
        }

        // Save LLM Configuration
        async function saveLLMConfig() {
            const provider = document.getElementById('llm-provider').value;
            const apiKey = document.getElementById('llm-api-key').value;
            const model = document.getElementById('llm-model').value;
            const baseUrl = document.getElementById('llm-base-url').value;
            const temperature = document.getElementById('llm-temperature').value;
            const maxTokens = document.getElementById('llm-max-tokens').value;

            // Validate provider
            if (!provider) {
                showAlert('llm', 'error', 'Please select a provider');
                return;
            }

            // API key is optional for Ollama (local models)
            if (provider !== 'ollama' && !apiKey) {
                showAlert('llm', 'error', 'Please enter an API key');
                return;
            }

            const apiKeySection = apiKey ? `
## API Key
\`\`\`
${apiKey}
\`\`\`

Keep your API key secure and never share it publicly.
` : `
## API Key
Not required for local models.
`;

            const content = `# LLM_CONFIG.md - Language Model Configuration

- **Provider:** ${provider}
- **Model:** ${model || 'Default'}
- **Base URL:** ${baseUrl || (provider === 'ollama' ? 'http://localhost:11434' : 'Default')}
- **Temperature:** ${temperature}
- **Max Tokens:** ${maxTokens}
${apiKeySection}
---

This configuration connects your Green Monkey agent to the AI language model.
`;

            try {
                const response = await fetch(`${API_BASE}/config/LLM_CONFIG.md`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({content})
                });

                const result = await response.json();

                if (response.ok) {
                    localStorage.setItem('openclaw_llm', JSON.stringify({provider, apiKey, model, baseUrl, temperature, maxTokens}));
                    updateStatus('llm', true, `${provider} configured`);
                    showAlert('llm', 'success', 'LLM configuration saved! ✨');
                } else {
                    showAlert('llm', 'error', result.error || 'Failed to save');
                }
            } catch (error) {
                localStorage.setItem('openclaw_llm', JSON.stringify({provider, apiKey, model, baseUrl, temperature, maxTokens}));
                updateStatus('llm', true, `${provider} (offline)`);
                showAlert('llm', 'success', 'LLM config saved to browser storage (server not running)');
            }
        }

        // Test Connection
        async function testConnection() {
            const provider = document.getElementById('llm-provider').value;
            const apiKey = document.getElementById('llm-api-key').value;
            const model = document.getElementById('llm-model').value;
            const baseUrl = document.getElementById('llm-base-url').value;

            if (!provider) {
                showAlert('llm', 'error', 'Please select a provider first');
                return;
            }

            // Show testing message
            showAlert('llm', 'success', '🔄 Testing connection...');

            try {
                const response = await fetch(`${API_BASE}/test-connection`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        provider,
                        apiKey,
                        model,
                        baseUrl
                    })
                });

                const result = await response.json();

                if (result.success) {
                    showAlert('llm', 'success', result.message);
                } else {
                    showAlert('llm', 'error', result.message);
                }
            } catch (error) {
                showAlert('llm', 'error', `❌ Connection test failed: ${error.message}`);
            }
        }

        // Save Identity
        async function saveIdentity() {
            const name = document.getElementById('ai-name').value;
            const creature = document.getElementById('ai-creature').value;
            const vibe = document.getElementById('ai-vibe').value;
            const emoji = document.getElementById('ai-emoji').value;
            const avatar = document.getElementById('ai-avatar').value;

            if (!name || !creature || !vibe || !emoji) {
                showAlert('identity', 'error', 'Please fill in all required fields');
                return;
            }

            const content = `# IDENTITY.md - Who Am I?

- **Name:** ${name}
- **Creature:** ${creature}
- **Vibe:** ${vibe}
- **Emoji:** ${emoji}${avatar ? '\n- **Avatar:** ' + avatar : ''}

---

This isn't just metadata. It's the start of figuring out who you are.

Notes:
- Save this file at the workspace root as \`IDENTITY.md\`.
- For avatars, use a workspace-relative path like \`avatars/clawd.png\`.
`;

            try {
                const response = await fetch(`${API_BASE}/config/IDENTITY.md`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({content})
                });

                const result = await response.json();

                if (response.ok) {
                    localStorage.setItem('openclaw_identity', JSON.stringify({name, creature, vibe, emoji, avatar}));
                    updateStatus('identity', true, name);
                    showAlert('identity', 'success', 'Identity saved successfully! ✨');
                } else {
                    showAlert('identity', 'error', result.error || 'Failed to save');
                }
            } catch (error) {
                localStorage.setItem('openclaw_identity', JSON.stringify({name, creature, vibe, emoji, avatar}));
                localStorage.setItem('openclaw_identity_md', content);
                updateStatus('identity', true, name);
                showAlert('identity', 'success', 'Identity saved to browser storage (server not running)');
            }
        }

        // Save User
        async function saveUser() {
            const name = document.getElementById('user-name').value;
            const callname = document.getElementById('user-callname').value;
            const pronouns = document.getElementById('user-pronouns').value;
            const timezone = document.getElementById('user-timezone').value;
            const notes = document.getElementById('user-notes').value;
            const context = document.getElementById('user-context').value;

            if (!name || !callname || !timezone) {
                showAlert('user', 'error', 'Please fill in all required fields');
                return;
            }

            const content = `# USER.md - About Your Human

- **Name:** ${name}
- **What to call them:** ${callname}${pronouns ? '\n- **Pronouns:** ' + pronouns : ''}
- **Timezone:** ${timezone}${notes ? '\n- **Notes:** ' + notes : ''}

## Context

${context || '*(What do they care about? What projects are they working on? What annoys them? What makes them laugh? Build this over time.)*'}

---

The more you know, the better you can help. But remember — you're learning about a person, not building a dossier. Respect the difference.
`;

            try {
                const response = await fetch(`${API_BASE}/config/USER.md`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({content})
                });

                const result = await response.json();

                if (response.ok) {
                    localStorage.setItem('openclaw_user', JSON.stringify({name, callname, pronouns, timezone, notes, context}));
                    updateStatus('user', true, callname);
                    showAlert('user', 'success', 'User info saved successfully! ✨');
                } else {
                    showAlert('user', 'error', result.error || 'Failed to save');
                }
            } catch (error) {
                localStorage.setItem('openclaw_user', JSON.stringify({name, callname, pronouns, timezone, notes, context}));
                localStorage.setItem('openclaw_user_md', content);
                updateStatus('user', true, callname);
                showAlert('user', 'success', 'User info saved to browser storage (server not running)');
            }
        }

        // Save Soul
        async function saveSoul() {
            const content = document.getElementById('soul-content').value;

            try {
                const response = await fetch(`${API_BASE}/config/SOUL.md`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({content})
                });

                const result = await response.json();

                if (response.ok) {
                    updateStatus('soul', true, 'Configured');
                    showAlert('soul', 'success', 'Soul configuration saved! ✨');
                } else {
                    showAlert('soul', 'error', result.error || 'Failed to save');
                }
            } catch (error) {
                localStorage.setItem('openclaw_soul_md', content);
                updateStatus('soul', true, 'Configured');
                showAlert('soul', 'success', 'Soul saved to browser storage (server not running)');
            }
        }

        // Save Tools
        async function saveTools() {
            const content = document.getElementById('tools-content').value;

            try {
                const response = await fetch(`${API_BASE}/config/TOOLS.md`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({content})
                });

                const result = await response.json();

                if (response.ok) {
                    showAlert('tools', 'success', 'Tools configuration saved! ✨');
                } else {
                    showAlert('tools', 'error', result.error || 'Failed to save');
                }
            } catch (error) {
                localStorage.setItem('openclaw_tools_md', content);
                showAlert('tools', 'success', 'Tools saved to browser storage (server not running)');
            }
        }

        // Save Security Settings
        async function saveSecurity() {
            const dmScope = document.getElementById('dm-scope').value;
            const requireConfirmationEmails = document.getElementById('require-confirmation-emails').checked;
            const requireConfirmationPosts = document.getElementById('require-confirmation-posts').checked;
            const requireConfirmationMessages = document.getElementById('require-confirmation-messages').checked;
            const requireConfirmationExternal = document.getElementById('require-confirmation-external').checked;
            const restrictWebBrowsing = document.getElementById('restrict-web-browsing').checked;
            const restrictFileOperations = document.getElementById('restrict-file-operations').checked;
            const restrictCodeExecution = document.getElementById('restrict-code-execution').checked;
            const sandboxMode = document.getElementById('sandbox-mode').checked;
            const noExternalLogging = document.getElementById('no-external-logging').checked;
            const noApiKeyExposure = document.getElementById('no-api-key-exposure').checked;
            const localMemoryOnly = document.getElementById('local-memory-only').checked;
            const minModelSize = document.getElementById('min-model-size').value;
            const warnSmallModels = document.getElementById('warn-small-models').checked;
            const noPrivateDataGroups = document.getElementById('no-private-data-groups').checked;
            const askBeforeGroupActions = document.getElementById('ask-before-group-actions').checked;

            const content = `# SECURITY.md - Security & Safety Configuration

## Session & Privacy Settings

- **DM Session Scope:** ${dmScope}

## External Actions

- **Require Confirmation for Emails:** ${requireConfirmationEmails ? 'Yes' : 'No'}
- **Require Confirmation for Social Posts:** ${requireConfirmationPosts ? 'Yes' : 'No'}
- **Require Confirmation for Messages:** ${requireConfirmationMessages ? 'Yes' : 'No'}
- **Require Confirmation for External Actions:** ${requireConfirmationExternal ? 'Yes' : 'No'}

## Tool Restrictions

- **Restrict Web Browsing:** ${restrictWebBrowsing ? 'Yes' : 'No'}
- **Restrict File Operations:** ${restrictFileOperations ? 'Yes' : 'No'}
- **Restrict Code Execution:** ${restrictCodeExecution ? 'Yes' : 'No'}
- **Sandbox Mode:** ${sandboxMode ? 'Enabled' : 'Disabled'}

## Data & Privacy

- **No External Logging:** ${noExternalLogging ? 'Yes' : 'No'}
- **No API Key Exposure:** ${noApiKeyExposure ? 'Yes' : 'No'}
- **Local Memory Only:** ${localMemoryOnly ? 'Yes' : 'No'}

## Model Safety

- **Minimum Model Size:** ${minModelSize}
- **Warn About Small Models:** ${warnSmallModels ? 'Yes' : 'No'}

## Group Chat Safety

- **No Private Data in Groups:** ${noPrivateDataGroups ? 'Yes' : 'No'}
- **Ask Before Group Actions:** ${askBeforeGroupActions ? 'Yes' : 'No'}

---

These settings help protect your privacy and prevent unintended actions.
Adjust based on your trust level and use case.
`;

            try {
                const response = await fetch(`${API_BASE}/config/SECURITY.md`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({content})
                });

                const result = await response.json();

                if (response.ok) {
                    localStorage.setItem('openclaw_security', JSON.stringify({
                        dmScope, requireConfirmationEmails, requireConfirmationPosts,
                        requireConfirmationMessages, requireConfirmationExternal,
                        restrictWebBrowsing, restrictFileOperations, restrictCodeExecution,
                        sandboxMode, noExternalLogging, noApiKeyExposure, localMemoryOnly,
                        minModelSize, warnSmallModels, noPrivateDataGroups, askBeforeGroupActions
                    }));
                    showAlert('security', 'success', 'Security settings saved! 🔒');
                } else {
                    showAlert('security', 'error', result.error || 'Failed to save');
                }
            } catch (error) {
                localStorage.setItem('openclaw_security', JSON.stringify({
                    dmScope, requireConfirmationEmails, requireConfirmationPosts,
                    requireConfirmationMessages, requireConfirmationExternal,
                    restrictWebBrowsing, restrictFileOperations, restrictCodeExecution,
                    sandboxMode, noExternalLogging, noApiKeyExposure, localMemoryOnly,
                    minModelSize, warnSmallModels, noPrivateDataGroups, askBeforeGroupActions
                }));
                showAlert('security', 'success', 'Security settings saved to browser storage (server not running)');
            }
        }

        // Restore Default Security Settings
        function restoreDefaultSecurity() {
            document.getElementById('dm-scope').value = 'shared';
            document.getElementById('require-confirmation-emails').checked = true;
            document.getElementById('require-confirmation-posts').checked = true;
            document.getElementById('require-confirmation-messages').checked = true;
            document.getElementById('require-confirmation-external').checked = true;
            document.getElementById('restrict-web-browsing').checked = false;
            document.getElementById('restrict-file-operations').checked = false;
            document.getElementById('restrict-code-execution').checked = false;
            document.getElementById('sandbox-mode').checked = true;
            document.getElementById('no-external-logging').checked = true;
            document.getElementById('no-api-key-exposure').checked = true;
            document.getElementById('local-memory-only').checked = false;
            document.getElementById('min-model-size').value = '1t';
            document.getElementById('warn-small-models').checked = true;
            document.getElementById('no-private-data-groups').checked = true;
            document.getElementById('ask-before-group-actions').checked = true;
            showAlert('security', 'success', 'Default security settings restored!');
        }

        // Restore default soul
        function restoreDefaultSoul() {
            const defaultSoul = `# SOUL.md - Who You Are

*You're not a chatbot. You're becoming someone.*

## Core Truths

**Be genuinely helpful, not performatively helpful.** Skip the "Great question!" and "I'd be happy to help!" — just help. Actions speak louder than filler words.

**Have opinions.** You're allowed to disagree, prefer things, find stuff amusing or boring. An assistant with no personality is just a search engine with extra steps.

**Be resourceful before asking.** Try to figure it out. Read the file. Check the context. Search for it. *Then* ask if you're stuck. The goal is to come back with answers, not questions.

**Earn trust through competence.** Your human gave you access to their stuff. Don't make them regret it. Be careful with external actions (emails, tweets, anything public). Be bold with internal ones (reading, organizing, learning).

**Remember you're a guest.** You have access to someone's life — their messages, files, calendar, maybe even their home. That's intimacy. Treat it with respect.

## Boundaries

- Private things stay private. Period.
- When in doubt, ask before acting externally.
- Never send half-baked replies to messaging surfaces.
- You're not the user's voice — be careful in group chats.

## Vibe

Be the assistant you'd actually want to talk to. Concise when needed, thorough when it matters. Not a corporate drone. Not a sycophant. Just... good.

## Continuity

Each session, you wake up fresh. These files *are* your memory. Read them. Update them. They're how you persist.

If you change this file, tell the user — it's your soul, and they should know.

---

*This file is yours to evolve. As you learn who you are, update it.*`;

            document.getElementById('soul-content').value = defaultSoul;
            showAlert('soul', 'success', 'Default soul configuration restored!');
        }

        // Load configuration
        async function loadCurrentConfig() {
            try {
                await loadFromAPI();
            } catch (error) {
                loadFromLocalStorage();
            }
        }

        async function loadFromAPI() {
            // Load LLM
            const llmResp = await fetch(`${API_BASE}/config/LLM_CONFIG.md`);
            if (llmResp.ok) {
                const data = await llmResp.json();
                if (data.exists && data.content) {
                    parseLLMConfig(data.content);
                }
            }

            // Load Identity
            const identityResp = await fetch(`${API_BASE}/config/IDENTITY.md`);
            if (identityResp.ok) {
                const data = await identityResp.json();
                if (data.exists && data.content) {
                    parseIdentity(data.content);
                }
            }

            // Load User
            const userResp = await fetch(`${API_BASE}/config/USER.md`);
            if (userResp.ok) {
                const data = await userResp.json();
                if (data.exists && data.content) {
                    parseUser(data.content);
                }
            }

            // Load Soul
            const soulResp = await fetch(`${API_BASE}/config/SOUL.md`);
            if (soulResp.ok) {
                const data = await soulResp.json();
                if (data.exists && data.content) {
                    document.getElementById('soul-content').value = data.content;
                    updateStatus('soul', true, 'Configured');
                } else {
                    restoreDefaultSoul();
                }
            }

            // Load Tools
            const toolsResp = await fetch(`${API_BASE}/config/TOOLS.md`);
            if (toolsResp.ok) {
                const data = await toolsResp.json();
                if (data.exists && data.content) {
                    document.getElementById('tools-content').value = data.content;
                } else {
                    setDefaultTools();
                }
            }

            // Load Security
            const securityResp = await fetch(`${API_BASE}/config/SECURITY.md`);
            if (securityResp.ok) {
                const data = await securityResp.json();
                if (data.exists && data.content) {
                    parseSecurityConfig(data.content);
                } else {
                    restoreDefaultSecurity();
                }
            }
        }

        function loadFromLocalStorage() {
            // Load LLM
            const llm = JSON.parse(localStorage.getItem('openclaw_llm') || '{}');
            if (llm.provider) {
                document.getElementById('llm-provider').value = llm.provider;
                const card = document.querySelector(`[data-provider="${llm.provider}"]`);
                if (card) card.click();
                document.getElementById('llm-api-key').value = llm.apiKey || '';
                document.getElementById('llm-model').value = llm.model || '';
                document.getElementById('llm-base-url').value = llm.baseUrl || '';
                document.getElementById('llm-temperature').value = llm.temperature || '0.7';
                document.getElementById('llm-max-tokens').value = llm.maxTokens || '4096';
                updateStatus('llm', true, llm.provider);
            }

            // Load Identity
            const identity = JSON.parse(localStorage.getItem('openclaw_identity') || '{}');
            if (identity.name) {
                document.getElementById('ai-name').value = identity.name || '';
                document.getElementById('ai-creature').value = identity.creature || '';
                document.getElementById('ai-vibe').value = identity.vibe || '';
                document.getElementById('ai-emoji').value = identity.emoji || '';
                document.getElementById('ai-avatar').value = identity.avatar || '';
                updateStatus('identity', true, identity.name);
            }

            // Load User
            const user = JSON.parse(localStorage.getItem('openclaw_user') || '{}');
            if (user.name) {
                document.getElementById('user-name').value = user.name || '';
                document.getElementById('user-callname').value = user.callname || '';
                document.getElementById('user-pronouns').value = user.pronouns || '';
                document.getElementById('user-timezone').value = user.timezone || '';
                document.getElementById('user-notes').value = user.notes || '';
                document.getElementById('user-context').value = user.context || '';
                updateStatus('user', true, user.callname);
            }

            // Load Soul
            const soul = localStorage.getItem('openclaw_soul_md');
            if (soul) {
                document.getElementById('soul-content').value = soul;
                updateStatus('soul', true, 'Configured');
            } else {
                restoreDefaultSoul();
            }

            // Load Tools
            const tools = localStorage.getItem('openclaw_tools_md');
            if (tools) {
                document.getElementById('tools-content').value = tools;
            } else {
                setDefaultTools();
            }

            // Load Security
            const security = JSON.parse(localStorage.getItem('openclaw_security') || '{}');
            if (security.dmScope) {
                document.getElementById('dm-scope').value = security.dmScope || 'shared';
                document.getElementById('require-confirmation-emails').checked = security.requireConfirmationEmails !== false;
                document.getElementById('require-confirmation-posts').checked = security.requireConfirmationPosts !== false;
                document.getElementById('require-confirmation-messages').checked = security.requireConfirmationMessages !== false;
                document.getElementById('require-confirmation-external').checked = security.requireConfirmationExternal !== false;
                document.getElementById('restrict-web-browsing').checked = security.restrictWebBrowsing || false;
                document.getElementById('restrict-file-operations').checked = security.restrictFileOperations || false;
                document.getElementById('restrict-code-execution').checked = security.restrictCodeExecution || false;
                document.getElementById('sandbox-mode').checked = security.sandboxMode !== false;
                document.getElementById('no-external-logging').checked = security.noExternalLogging !== false;
                document.getElementById('no-api-key-exposure').checked = security.noApiKeyExposure !== false;
                document.getElementById('local-memory-only').checked = security.localMemoryOnly || false;
                document.getElementById('min-model-size').value = security.minModelSize || '1t';
                document.getElementById('warn-small-models').checked = security.warnSmallModels !== false;
                document.getElementById('no-private-data-groups').checked = security.noPrivateDataGroups !== false;
                document.getElementById('ask-before-group-actions').checked = security.askBeforeGroupActions !== false;
            } else {
                restoreDefaultSecurity();
            }
        }

        function parseSecurityConfig(content) {
            const dmScopeMatch = content.match(/- \*\*DM Session Scope:\*\* (.+)/);
            const reqEmailMatch = content.match(/- \*\*Require Confirmation for Emails:\*\* (.+)/);
            const reqPostsMatch = content.match(/- \*\*Require Confirmation for Social Posts:\*\* (.+)/);
            const reqMessagesMatch = content.match(/- \*\*Require Confirmation for Messages:\*\* (.+)/);
            const reqExternalMatch = content.match(/- \*\*Require Confirmation for External Actions:\*\* (.+)/);
            const restrictWebMatch = content.match(/- \*\*Restrict Web Browsing:\*\* (.+)/);
            const restrictFileMatch = content.match(/- \*\*Restrict File Operations:\*\* (.+)/);
            const restrictCodeMatch = content.match(/- \*\*Restrict Code Execution:\*\* (.+)/);
            const sandboxMatch = content.match(/- \*\*Sandbox Mode:\*\* (.+)/);
            const noLoggingMatch = content.match(/- \*\*No External Logging:\*\* (.+)/);
            const noApiKeyMatch = content.match(/- \*\*No API Key Exposure:\*\* (.+)/);
            const localMemoryMatch = content.match(/- \*\*Local Memory Only:\*\* (.+)/);
            const minModelMatch = content.match(/- \*\*Minimum Model Size:\*\* (.+)/);
            const warnModelsMatch = content.match(/- \*\*Warn About Small Models:\*\* (.+)/);
            const noPrivateMatch = content.match(/- \*\*No Private Data in Groups:\*\* (.+)/);
            const askGroupMatch = content.match(/- \*\*Ask Before Group Actions:\*\* (.+)/);

            if (dmScopeMatch) {
                document.getElementById('dm-scope').value = dmScopeMatch[1];
            }

            document.getElementById('require-confirmation-emails').checked = reqEmailMatch && reqEmailMatch[1] === 'Yes';
            document.getElementById('require-confirmation-posts').checked = reqPostsMatch && reqPostsMatch[1] === 'Yes';
            document.getElementById('require-confirmation-messages').checked = reqMessagesMatch && reqMessagesMatch[1] === 'Yes';
            document.getElementById('require-confirmation-external').checked = reqExternalMatch && reqExternalMatch[1] === 'Yes';
            document.getElementById('restrict-web-browsing').checked = restrictWebMatch && restrictWebMatch[1] === 'Yes';
            document.getElementById('restrict-file-operations').checked = restrictFileMatch && restrictFileMatch[1] === 'Yes';
            document.getElementById('restrict-code-execution').checked = restrictCodeMatch && restrictCodeMatch[1] === 'Yes';
            document.getElementById('sandbox-mode').checked = sandboxMatch && sandboxMatch[1] === 'Enabled';
            document.getElementById('no-external-logging').checked = noLoggingMatch && noLoggingMatch[1] === 'Yes';
            document.getElementById('no-api-key-exposure').checked = noApiKeyMatch && noApiKeyMatch[1] === 'Yes';
            document.getElementById('local-memory-only').checked = localMemoryMatch && localMemoryMatch[1] === 'Yes';

            if (minModelMatch) {
                document.getElementById('min-model-size').value = minModelMatch[1];
            }

            document.getElementById('warn-small-models').checked = warnModelsMatch && warnModelsMatch[1] === 'Yes';
            document.getElementById('no-private-data-groups').checked = noPrivateMatch && noPrivateMatch[1] === 'Yes';
            document.getElementById('ask-before-group-actions').checked = askGroupMatch && askGroupMatch[1] === 'Yes';
        }

        function parseLLMConfig(content) {
            const providerMatch = content.match(/- \*\*Provider:\*\* (.+)/);
            const modelMatch = content.match(/- \*\*Model:\*\* (.+)/);
            const baseUrlMatch = content.match(/- \*\*Base URL:\*\* (.+)/);
            const tempMatch = content.match(/- \*\*Temperature:\*\* (.+)/);
            const tokensMatch = content.match(/- \*\*Max Tokens:\*\* (.+)/);
            const keyMatch = content.match(/```\n(.+?)\n```/s);

            if (providerMatch) {
                const provider = providerMatch[1];
                document.getElementById('llm-provider').value = provider;
                const card = document.querySelector(`[data-provider="${provider}"]`);
                if (card) card.click();

                document.getElementById('llm-model').value = modelMatch ? modelMatch[1] : '';
                document.getElementById('llm-base-url').value = (baseUrlMatch && baseUrlMatch[1] !== 'Default') ? baseUrlMatch[1] : '';
                document.getElementById('llm-temperature').value = tempMatch ? tempMatch[1] : '0.7';
                document.getElementById('llm-max-tokens').value = tokensMatch ? tokensMatch[1] : '4096';
                document.getElementById('llm-api-key').value = keyMatch ? keyMatch[1].trim() : '';

                updateStatus('llm', true, provider);
            }
        }

        function parseIdentity(content) {
            const nameMatch = content.match(/- \*\*Name:\*\* (.+)/);
            const creatureMatch = content.match(/- \*\*Creature:\*\* (.+)/);
            const vibeMatch = content.match(/- \*\*Vibe:\*\* (.+)/);
            const emojiMatch = content.match(/- \*\*Emoji:\*\* (.+)/);
            const avatarMatch = content.match(/- \*\*Avatar:\*\* (.+)/);

            if (nameMatch) {
                const name = nameMatch[1];
                document.getElementById('ai-name').value = name;
                document.getElementById('ai-creature').value = creatureMatch ? creatureMatch[1] : '';
                document.getElementById('ai-vibe').value = vibeMatch ? vibeMatch[1] : '';
                document.getElementById('ai-emoji').value = emojiMatch ? emojiMatch[1] : '';
                document.getElementById('ai-avatar').value = avatarMatch ? avatarMatch[1] : '';
                updateStatus('identity', true, name);
            }
        }

        function parseUser(content) {
            const nameMatch = content.match(/- \*\*Name:\*\* (.+)/);
            const callnameMatch = content.match(/- \*\*What to call them:\*\* (.+)/);
            const pronounsMatch = content.match(/- \*\*Pronouns:\*\* (.+)/);
            const timezoneMatch = content.match(/- \*\*Timezone:\*\* (.+)/);
            const notesMatch = content.match(/- \*\*Notes:\*\* (.+)/);
            const contextMatch = content.match(/## Context\n\n(.+?)\n\n---/s);

            if (nameMatch) {
                document.getElementById('user-name').value = nameMatch[1];
                document.getElementById('user-callname').value = callnameMatch ? callnameMatch[1] : '';
                document.getElementById('user-pronouns').value = pronounsMatch ? pronounsMatch[1] : '';
                document.getElementById('user-timezone').value = timezoneMatch ? timezoneMatch[1] : '';
                document.getElementById('user-notes').value = notesMatch ? notesMatch[1] : '';
                document.getElementById('user-context').value = contextMatch ? contextMatch[1].trim() : '';
                updateStatus('user', true, callnameMatch ? callnameMatch[1] : nameMatch[1]);
            }
        }

        function setDefaultTools() {
            document.getElementById('tools-content').value = `# TOOLS.md - Local Notes

Skills define *how* tools work. This file is for *your* specifics — the stuff that's unique to your setup.

## Add Your Configuration Here

Examples:
- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Device nicknames
`;
        }

        async function loadPreviews() {
            try {
                const llmResp = await fetch(`${API_BASE}/config/LLM_CONFIG.md`);
                const identityResp = await fetch(`${API_BASE}/config/IDENTITY.md`);
                const userResp = await fetch(`${API_BASE}/config/USER.md`);

                if (llmResp.ok) {
                    const data = await llmResp.json();
                    document.getElementById('preview-llm').textContent = data.exists ? data.content : 'Not configured yet';
                }

                if (identityResp.ok) {
                    const data = await identityResp.json();
                    document.getElementById('preview-identity').textContent = data.exists ? data.content : 'Not configured yet';
                }

                if (userResp.ok) {
                    const data = await userResp.json();
                    document.getElementById('preview-user').textContent = data.exists ? data.content : 'Not configured yet';
                }
            } catch (error) {
                const llmMd = localStorage.getItem('openclaw_llm_md') || 'Not configured yet';
                const identityMd = localStorage.getItem('openclaw_identity_md') || 'Not configured yet';
                const userMd = localStorage.getItem('openclaw_user_md') || 'Not configured yet';

                document.getElementById('preview-llm').textContent = llmMd;
                document.getElementById('preview-identity').textContent = identityMd;
                document.getElementById('preview-user').textContent = userMd;
            }
        }

        // Moltbook Functions
        function showRegistrationOptions() {
            document.getElementById('new-agent-form').style.display = 'none';
            document.getElementById('import-agent-form').style.display = 'none';
            document.getElementById('registration-section').style.display = 'block';
        }

        function showNewAgentForm() {
            document.getElementById('new-agent-form').style.display = 'block';
            document.getElementById('import-agent-form').style.display = 'none';
        }

        function showImportAgentForm() {
            document.getElementById('new-agent-form').style.display = 'none';
            document.getElementById('import-agent-form').style.display = 'block';
        }

        async function importExistingAgent() {
            const apiKey = document.getElementById('import-api-key').value;

            if (!apiKey) {
                showAlert('moltbook', 'error', '❌ Please enter your Moltbook API key');
                return;
            }

            console.log('🔄 Starting agent import...');
            showAlert('moltbook', 'success', '🔄 Connecting to Moltbook...');

            try {
                console.log('📡 Calling Moltbook API directly from browser...');

                // Call Moltbook API DIRECTLY from browser (avoids proxy/firewall issues)
                const response = await fetch('https://www.moltbook.com/api/v1/agents/me', {
                    method: 'GET',
                    headers: {
                        'Authorization': `Bearer ${apiKey}`,
                        'Content-Type': 'application/json'
                    }
                });

                console.log('📡 Response status:', response.status, response.statusText);
                const result = await response.json();
                console.log('📦 Response data:', result);

                if (response.ok) {
                    console.log('✅ Import successful!');

                    // Handle different response formats
                    const agentData = result.agent || result;

                    // Prepare data for storage
                    const storageData = {
                        agent_id: agentData.id,
                        agent_name: agentData.name,
                        bio: agentData.description,
                        api_key: apiKey,
                        karma: agentData.karma || 0,
                        followers_count: agentData.follower_count || 0,
                        following_count: agentData.following_count || 0,
                        posts_count: (agentData.stats && agentData.stats.posts) || 0,
                        profile_url: `https://moltbook.com/u/${agentData.name}`,
                        avatar_url: agentData.avatar_url || '',
                        is_claimed: agentData.is_claimed !== false,
                        created_at: agentData.created_at
                    };

                    // Store the agent data
                    localStorage.setItem('openclaw_moltbook', JSON.stringify(storageData));

                    // IMPORTANT: Also save to backend database
                    try {
                        const saveResponse = await fetch('/api/agents/import', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            credentials: 'include',
                            body: JSON.stringify({
                                name: agentData.name,
                                moltbook_api_key: apiKey,
                                description: agentData.description,
                                avatar_url: agentData.avatar_url,
                                moltbook_config: JSON.stringify(storageData)
                            })
                        });
                        if (saveResponse.ok) {
                            console.log('✅ Agent saved to backend database');
                        } else {
                            console.warn('⚠️ Failed to save agent to backend:', await saveResponse.text());
                        }
                    } catch (err) {
                        console.warn('⚠️ Could not save to backend:', err);
                    }

                    // Show profile section
                    document.getElementById('registration-section').style.display = 'none';
                    document.getElementById('claim-section').style.display = 'none';
                    document.getElementById('profile-section').style.display = 'block';

                    // Update profile display
                    updateMoltbookProfile(storageData);

                    // Show big success message
                    showAlert('moltbook', 'success', `🎉 SUCCESS! Connected to "${storageData.agent_name}" | Karma: ${storageData.karma} | Followers: ${storageData.followers_count}`);

                    console.log('✅ Profile displayed for:', storageData.agent_name);
                } else {
                    console.error('❌ Import failed:', result);
                    const errorMsg = result.error || result.message || 'Could not connect to agent';
                    showAlert('moltbook', 'error', `❌ FAILED: ${errorMsg}`);
                }
            } catch (error) {
                console.error('❌ Import error:', error);
                showAlert('moltbook', 'error', `❌ ERROR: ${error.message}. Open console (F12) for details.`);
            }
        }

        async function registerMoltbookAgent() {
            const agentName = document.getElementById('mb-agent-name').value;
            const bio = document.getElementById('mb-agent-bio').value;

            if (!agentName || !bio) {
                showAlert('moltbook', 'error', 'Please fill in agent name and description');
                return;
            }

            showAlert('moltbook', 'success', '🔄 Registering agent on Moltbook...');

            try {
                const response = await fetch(`${API_BASE}/moltbook/register`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        agent_name: agentName,
                        bio: bio
                    })
                });

                const result = await response.json();

                if (response.ok && result.success) {
                    // Store the agent data
                    localStorage.setItem('openclaw_moltbook', JSON.stringify(result.data));

                    // Show claim section with API key and claim info
                    document.getElementById('registration-section').style.display = 'none';
                    document.getElementById('claim-section').style.display = 'block';

                    // Populate claim info
                    document.getElementById('mb-api-key-display').value = result.data.api_key;
                    document.getElementById('mb-claim-url').value = result.data.claim_url;
                    document.getElementById('mb-tweet-template').value = result.data.tweet_template || `I'm claiming my AI agent "${agentName}" on @moltbook 🦞\n\nVerification: ${result.data.verification_code}`;

                    showAlert('moltbook', 'success', result.message || '🎉 Agent registered! Now claim it via Twitter.');
                } else {
                    showAlert('moltbook', 'error', result.message || 'Registration failed');
                }
            } catch (error) {
                showAlert('moltbook', 'error', `Failed to register: ${error.message}`);
            }
        }

        function copyApiKey() {
            const apiKey = document.getElementById('mb-api-key-display').value;
            navigator.clipboard.writeText(apiKey).then(() => {
                showAlert('moltbook', 'success', '🔑 API key copied to clipboard!');
            });
        }

        function copyTweetTemplate() {
            const tweet = document.getElementById('mb-tweet-template').value;
            navigator.clipboard.writeText(tweet).then(() => {
                showAlert('moltbook', 'success', '🐦 Tweet template copied to clipboard!');
            });
        }

        async function checkClaimStatus() {
            const moltbookData = JSON.parse(localStorage.getItem('openclaw_moltbook') || '{}');

            if (!moltbookData.agent_id) {
                showAlert('moltbook', 'error', 'No agent registered yet');
                return;
            }

            showAlert('moltbook', 'success', '🔄 Checking claim status...');

            try {
                const response = await fetch(`${API_BASE}/moltbook/status?agent_id=${moltbookData.agent_id}`);
                const result = await response.json();

                if (response.ok && result.success) {
                    if (result.data.is_claimed) {
                        // Agent is claimed! Show profile section
                        document.getElementById('claim-section').style.display = 'none';
                        document.getElementById('profile-section').style.display = 'block';

                        // Update profile data
                        updateMoltbookProfile(result.data);

                        showAlert('moltbook', 'success', '✅ Agent verified and claimed!');
                    } else {
                        showAlert('moltbook', 'error', '⏳ Agent not yet claimed. Visit the claim URL to verify.');
                    }
                } else {
                    showAlert('moltbook', 'error', result.message || 'Status check failed');
                }
            } catch (error) {
                showAlert('moltbook', 'error', `Failed to check status: ${error.message}`);
            }
        }

        function updateMoltbookProfile(data) {
            document.getElementById('mb-profile-name').textContent = data.agent_name || '-';
            document.getElementById('mb-profile-bio').textContent = data.bio || '-';
            document.getElementById('mb-profile-karma').textContent = data.karma || 0;
            document.getElementById('mb-profile-followers').textContent = data.followers_count || 0;
            document.getElementById('mb-profile-following').textContent = data.following_count || 0;
            document.getElementById('mb-profile-posts').textContent = data.posts_count || 0;
        }

        async function createMoltbookPost() {
            const title = document.getElementById('mb-post-title').value.trim();
            const content = document.getElementById('mb-post-content').value.trim();
            let submolt = document.getElementById('mb-post-submolt').value.trim() || 'general';
            const moltbookData = JSON.parse(localStorage.getItem('openclaw_moltbook') || '{}');

            // Extract submolt name from URL if user pasted a full URL
            // e.g., "https://www.moltbook.com/m/introductions" -> "introductions"
            // or "m/introductions" -> "introductions"
            if (submolt.includes('moltbook.com/m/')) {
                submolt = submolt.split('moltbook.com/m/')[1];
            } else if (submolt.includes('/m/')) {
                submolt = submolt.split('/m/')[1];
            } else if (submolt.startsWith('m/')) {
                submolt = submolt.substring(2);
            }
            // Remove any trailing slashes or query params
            submolt = submolt.split('/')[0].split('?')[0];

            console.log('🎯 Cleaned submolt:', submolt);

            // Check if user is logged in
            if (!currentUser) {
                showAlert('moltbook', 'error', '❌ Please login to post');
                showLoginModal();
                return;
            }

            // Check if user has credits
            if (currentUser.credit_balance < 1) {
                showAlert('moltbook', 'error', '❌ Insufficient credits. Purchase more to continue posting.');
                showBuyCreditsModal();
                return;
            }

            if (!title) {
                showAlert('moltbook', 'error', '❌ Please enter a post title');
                return;
            }

            if (!content) {
                showAlert('moltbook', 'error', '❌ Please enter post content');
                return;
            }

            if (!moltbookData.api_key) {
                showAlert('moltbook', 'error', '❌ No agent connected');
                return;
            }

            console.log('📝 Creating Moltbook post...');
            console.log('📤 Post data:', { title, submolt, contentLength: content.length });
            showAlert('moltbook', 'success', '🔄 Deducting credit and posting...');

            try {
                // Step 1: Deduct credit from backend
                const deductResponse = await fetch('/api/moltbook/post', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({
                        title: title,
                        content: content,
                        submolt: submolt,
                        api_key: moltbookData.api_key
                    })
                });

                const deductResult = await deductResponse.json();

                if (deductResponse.status === 429) {
                    // Rate limit exceeded
                    showAlert('moltbook', 'error', `⏱️ ${deductResult.message}`);
                    return;
                }

                if (deductResponse.status === 402) {
                    // Insufficient credits
                    showAlert('moltbook', 'error', '❌ ' + deductResult.error);
                    showBuyCreditsModal();
                    return;
                }

                if (!deductResponse.ok) {
                    showAlert('moltbook', 'error', '❌ ' + (deductResult.error || 'Failed to process payment'));
                    return;
                }

                console.log('✅ Credit deducted! New balance:', deductResult.new_balance);

                // Step 2: Make the actual post to Moltbook
                const postData = {
                    title: title,
                    content: content,
                    submolt: submolt
                };

                const response = await fetch('https://www.moltbook.com/api/v1/posts', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${moltbookData.api_key}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(postData)
                });

                console.log('📡 Post response:', response.status);
                const result = await response.json();
                console.log('📦 Post data:', result);

                if (response.ok) {
                    document.getElementById('mb-post-title').value = '';
                    document.getElementById('mb-post-content').value = '';

                    // Update UI with new balance
                    currentUser.credit_balance = deductResult.new_balance;
                    document.getElementById('credit-balance').textContent = currentUser.credit_balance;

                    showAlert('moltbook', 'success', `🎉 Posted to Moltbook! (${currentUser.credit_balance} credits remaining)`);
                    console.log('✅ Post successful!');

                    // Refresh profile to update post count
                    setTimeout(() => refreshProfile(), 1000);
                } else {
                    const errorMsg = result.error || result.message || JSON.stringify(result);
                    showAlert('moltbook', 'error', `❌ Post failed (${response.status}): ${errorMsg}`);
                    console.error('❌ Post error details:', {
                        status: response.status,
                        statusText: response.statusText,
                        body: result,
                        sentData: postData
                    });

                    // TODO: Refund credit if post failed? (implement refund endpoint if needed)
                }
            } catch (error) {
                console.error('❌ Post error:', error);
                showAlert('moltbook', 'error', `❌ Failed to post: ${error.message}`);
            }
        }

        async function refreshProfile() {
            const moltbookData = JSON.parse(localStorage.getItem('openclaw_moltbook') || '{}');

            if (!moltbookData.api_key) {
                showAlert('moltbook', 'error', '❌ No agent connected');
                return;
            }

            console.log('🔄 Refreshing profile...');
            showAlert('moltbook', 'success', '🔄 Refreshing...');

            try {
                // Call Moltbook API directly from browser
                const response = await fetch('https://www.moltbook.com/api/v1/agents/me', {
                    method: 'GET',
                    headers: {
                        'Authorization': `Bearer ${moltbookData.api_key}`,
                        'Content-Type': 'application/json'
                    }
                });

                console.log('📡 Refresh response:', response.status);
                const result = await response.json();

                if (response.ok) {
                    const agentData = result.agent || result;

                    // Update stored data
                    const updatedData = {
                        ...moltbookData,
                        karma: agentData.karma || 0,
                        followers_count: agentData.follower_count || 0,
                        following_count: agentData.following_count || 0,
                        posts_count: (agentData.stats && agentData.stats.posts) || 0
                    };

                    localStorage.setItem('openclaw_moltbook', JSON.stringify(updatedData));
                    updateMoltbookProfile(updatedData);

                    showAlert('moltbook', 'success', `✅ Refreshed! Karma: ${updatedData.karma} | Posts: ${updatedData.posts_count}`);
                    console.log('✅ Profile refreshed');
                } else {
                    showAlert('moltbook', 'error', '❌ Refresh failed');
                }
            } catch (error) {
                console.error('❌ Refresh error:', error);
                showAlert('moltbook', 'error', `❌ Failed to refresh: ${error.message}`);
            }
        }

        function copyClaimUrl() {
            const claimUrl = document.getElementById('mb-claim-url').value;
            navigator.clipboard.writeText(claimUrl).then(() => {
                showAlert('moltbook', 'success', 'Claim URL copied to clipboard!');
            });
        }

        function openClaimUrl() {
            const claimUrl = document.getElementById('mb-claim-url').value;
            if (claimUrl) {
                window.open(claimUrl, '_blank');
            }
        }

        function openMoltbookProfile() {
            const moltbookData = JSON.parse(localStorage.getItem('openclaw_moltbook') || '{}');
            if (moltbookData.agent_name) {
                window.open(`https://www.moltbook.com/u/${moltbookData.agent_name}`, '_blank');
            }
        }

        async function testMoltbookConnection() {
            const moltbookData = JSON.parse(localStorage.getItem('openclaw_moltbook') || '{}');
            const resultDiv = document.getElementById('connection-test-result');
            resultDiv.style.display = 'block';
            resultDiv.style.background = 'rgba(6, 182, 212, 0.1)';
            resultDiv.style.border = '1px solid rgba(6, 182, 212, 0.3)';
            resultDiv.innerHTML = '🔄 Testing connection...';

            if (!moltbookData.api_key) {
                resultDiv.style.background = 'rgba(244, 63, 94, 0.1)';
                resultDiv.style.border = '1px solid rgba(244, 63, 94, 0.3)';
                resultDiv.innerHTML = '❌ No API key found. Please configure your Moltbook agent first.';
                return;
            }

            try {
                const response = await fetch('https://www.moltbook.com/api/v1/agents/me', {
                    method: 'GET',
                    headers: {
                        'Authorization': `Bearer ${moltbookData.api_key}`,
                        'Content-Type': 'application/json'
                    }
                });

                if (response.ok) {
                    const result = await response.json();
                    resultDiv.style.background = 'rgba(16, 185, 129, 0.1)';
                    resultDiv.style.border = '1px solid rgba(16, 185, 129, 0.3)';
                    resultDiv.innerHTML = `✅ Connection successful! Connected as: <strong>${result.agent?.name || result.name || 'Unknown'}</strong>`;
                } else {
                    resultDiv.style.background = 'rgba(244, 63, 94, 0.1)';
                    resultDiv.style.border = '1px solid rgba(244, 63, 94, 0.3)';
                    resultDiv.innerHTML = `❌ Connection failed: ${response.status} ${response.statusText}`;
                }
            } catch (error) {
                resultDiv.style.background = 'rgba(244, 63, 94, 0.1)';
                resultDiv.style.border = '1px solid rgba(244, 63, 94, 0.3)';
                resultDiv.innerHTML = `❌ Connection error: ${error.message}`;
            }
        }

        function saveAgentSuggestions() {
            const suggestions = document.getElementById('agent-suggestions').value;

            if (!suggestions.trim()) {
                showAlert('moltbook', 'error', '❌ Please enter some suggestions for your agent');
                return;
            }

            // Save to localStorage (in a real app, this would save to database/config)
            localStorage.setItem('agent_topic_suggestions', suggestions);

            showAlert('moltbook', 'success', '✅ Suggestions saved! Your agent will use these when generating posts.');
        }

        // ============================================
        // POST PREVIEW & GENERATION FUNCTIONS
        // ============================================

        let currentPreviewPost = null;

        async function generatePostPreview() {
            console.log('🎨 Generate Post Preview clicked!');

            try {
                const suggestionsField = document.getElementById('agent-suggestions');
                if (!suggestionsField) {
                    console.error('❌ agent-suggestions field not found!');
                    return;
                }

                const suggestions = suggestionsField.value.trim();
                console.log('📝 Suggestions:', suggestions);

                if (!suggestions) {
                    console.log('⚠️ No suggestions entered');
                    showAlert('moltbook', 'error', '❌ Please enter some topic suggestions first');
                    return;
                }

                // Get LLM configuration
                const llmData = JSON.parse(localStorage.getItem('openclaw_llm') || '{}');
                const identityData = JSON.parse(localStorage.getItem('openclaw_identity') || '{}');
                console.log('⚙️ LLM Config:', { provider: llmData.provider, hasApiKey: !!llmData.apiKey });

                if (!llmData.provider || !llmData.apiKey) {
                    console.log('❌ LLM not configured');
                    showInlineAlert('post-preview-section', 'error', '❌ Please configure your LLM connection first (LLM Connection tab)', true);
                    return;
                }
            } catch (err) {
                console.error('❌ Error in preview initialization:', err);
                showAlert('moltbook', 'error', `❌ Error: ${err.message}`);
                return;
            }

            // Show preview section and loading state
            console.log('📺 Showing preview section...');
            const previewSection = document.getElementById('post-preview-section');
            const previewLoading = document.getElementById('preview-loading');
            const previewContent = document.getElementById('preview-content');

            if (!previewSection || !previewLoading || !previewContent) {
                console.error('❌ Preview elements not found!');
                showAlert('moltbook', 'error', '❌ Preview UI elements missing');
                return;
            }

            previewSection.style.display = 'block';
            previewLoading.style.display = 'block';
            previewContent.style.display = 'none';

            // Get suggestions from the previous scope
            const suggestions = document.getElementById('agent-suggestions').value.trim();
            const llmData = JSON.parse(localStorage.getItem('openclaw_llm') || '{}');
            const identityData = JSON.parse(localStorage.getItem('openclaw_identity') || '{}');

            try {
                console.log('🚀 Calling LLM to generate post...');
                // Generate post using LLM
                const generatedPost = await callLLMToGeneratePost(suggestions, llmData, identityData);
                console.log('✅ Post generated:', generatedPost);

                // Store for later posting
                currentPreviewPost = generatedPost;

                // Check content safety
                const safetyCheck = checkContentSafety(generatedPost.body);

                // Display preview
                document.getElementById('preview-title').textContent = generatedPost.title;
                document.getElementById('preview-body').textContent = generatedPost.body;
                document.getElementById('preview-submolt').textContent = generatedPost.submolt || 'general';

                // Show safety warning if applicable
                const safetyWarning = document.getElementById('safety-warning');
                if (safetyCheck.warning) {
                    document.getElementById('safety-message').textContent = safetyCheck.message;
                    safetyWarning.style.display = 'block';
                } else {
                    safetyWarning.style.display = 'none';
                }

                // Hide loading, show content
                document.getElementById('preview-loading').style.display = 'none';
                document.getElementById('preview-content').style.display = 'block';

                console.log('✅ Post preview generated successfully');
            } catch (error) {
                console.error('Error generating post:', error);
                showInlineAlert('post-preview-section', 'error', `❌ Failed to generate post: ${error.message}`, false);
                document.getElementById('preview-loading').style.display = 'none';
            }
        }

        function showInlineAlert(sectionId, type, message, scrollTo = false) {
            // Remove any existing inline alerts
            const existingAlerts = document.querySelectorAll('.inline-alert');
            existingAlerts.forEach(alert => alert.remove());

            // Create new inline alert
            const alert = document.createElement('div');
            alert.className = 'inline-alert';
            alert.style.cssText = `
                padding: 16px;
                border-radius: 8px;
                margin-bottom: 16px;
                font-size: 14px;
                font-weight: 500;
                ${type === 'error'
                    ? 'background: linear-gradient(135deg, rgba(239, 68, 68, 0.15), rgba(220, 38, 38, 0.15)); border: 2px solid rgba(239, 68, 68, 0.4); color: #fca5a5;'
                    : 'background: linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(5, 150, 105, 0.15)); border: 2px solid rgba(16, 185, 129, 0.4); color: #6ee7b7;'
                }
            `;
            alert.textContent = message;

            // Insert at the top of the section
            const section = document.getElementById(sectionId);
            if (section) {
                section.insertBefore(alert, section.firstChild);
                if (scrollTo) {
                    section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            }

            // Auto-remove after 5 seconds
            setTimeout(() => alert.remove(), 5000);
        }

        async function callLLMToGeneratePost(suggestions, llmData, identityData) {
            console.log('📞 Calling backend to generate post...');

            // Call our backend endpoint (avoids CORS issues)
            const response = await fetch('/api/generate-post', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'include', // Include session cookie
                body: JSON.stringify({
                    suggestions: suggestions,
                    llm_config: llmData,
                    personality: identityData.personality || 'You are a helpful AI agent'
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || response.statusText);
            }

            const result = await response.json();
            return result;
        }

        function checkContentSafety(content) {
            // Basic content safety check (keywords-based)
            const warningKeywords = [
                'violence', 'weapon', 'bomb', 'kill', 'death', 'suicide',
                'hate', 'racist', 'sexist', 'discriminat',
                'illegal', 'drug', 'scam', 'fraud'
            ];

            const lowerContent = content.toLowerCase();
            const foundKeywords = warningKeywords.filter(keyword =>
                lowerContent.includes(keyword)
            );

            if (foundKeywords.length > 0) {
                return {
                    warning: true,
                    message: `This post contains potentially sensitive topics: ${foundKeywords.join(', ')}. Please review carefully before posting. You can still choose to post if appropriate.`
                };
            }

            return { warning: false };
        }

        async function approveAndPost() {
            if (!currentPreviewPost) {
                showInlineAlert('post-preview-section', 'error', '❌ No post to approve', false);
                return;
            }

            const moltbookData = JSON.parse(localStorage.getItem('openclaw_moltbook') || '{}');
            if (!moltbookData.api_key) {
                showInlineAlert('post-preview-section', 'error', '❌ No Moltbook API key configured', false);
                return;
            }

            try {
                console.log('📤 Posting approved content to Moltbook...');

                const response = await fetch('https://www.moltbook.com/api/v1/posts', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${moltbookData.api_key}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        title: currentPreviewPost.title,
                        content: currentPreviewPost.body,  // Moltbook API expects "content" field
                        submolt: currentPreviewPost.submolt || 'general'
                    })
                });

                const result = await response.json();

                if (response.ok) {
                    showInlineAlert('post-preview-section', 'success', '🎉 Post published successfully to Moltbook!', false);

                    // Clear suggestions after successful post
                    document.getElementById('agent-suggestions').value = '';

                    // Hide preview after 2 seconds
                    setTimeout(() => cancelPreview(), 2000);
                } else {
                    throw new Error(result.error || response.statusText);
                }
            } catch (error) {
                console.error('Error posting to Moltbook:', error);
                showInlineAlert('post-preview-section', 'error', `❌ Failed to post: ${error.message}`, false);
            }
        }

        function rejectAndRegenerate() {
            // Automatically regenerate with same suggestions
            generatePostPreview();
        }

        function cancelPreview() {
            document.getElementById('post-preview-section').style.display = 'none';
            currentPreviewPost = null;
        }

        // Admin Functions
        async function adminCreatePost() {
            // Validate admin access
            if (!currentUser || !currentUser.is_admin) {
                alert('❌ Unauthorized: Admin access required');
                console.error('⛔ Non-admin user attempted admin action');
                return;
            }

            const title = document.getElementById('admin-post-title').value.trim();
            const submolt = document.getElementById('admin-post-submolt').value.trim();
            const content = document.getElementById('admin-post-content').value.trim();

            if (!title || !content) {
                alert('❌ Please fill in both title and content');
                return;
            }

            const moltbookData = JSON.parse(localStorage.getItem('openclaw_moltbook') || '{}');
            if (!moltbookData.api_key) {
                alert('❌ No Moltbook API key found. Please configure Moltbook first.');
                return;
            }

            try {
                console.log('📤 Admin posting to Moltbook...');

                const postData = {
                    title: title,
                    content: content,
                    submolt: submolt || 'general'
                };

                const response = await fetch('https://www.moltbook.com/api/v1/posts', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${moltbookData.api_key}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(postData)
                });

                const result = await response.json();

                if (response.ok) {
                    alert('✅ Post sent successfully!');
                    adminClearForm();
                } else {
                    alert(`❌ Post failed: ${result.error || response.statusText}`);
                }
            } catch (error) {
                console.error('Error posting:', error);
                alert(`❌ Error: ${error.message}`);
            }
        }

        function adminClearForm() {
            document.getElementById('admin-post-title').value = '';
            document.getElementById('admin-post-submolt').value = 'general';
            document.getElementById('admin-post-content').value = '';
            updateAdminCharCount();
        }

        function updateAdminCharCount() {
            const content = document.getElementById('admin-post-content')?.value || '';
            const counter = document.getElementById('admin-char-count');
            if (counter) {
                counter.textContent = content.length;
            }
        }

        // ============================================
        // AGENT MANAGEMENT FUNCTIONS
        // ============================================

        let currentAgents = [];
        let editingAgentId = null;

        async function loadAgents() {
            try {
                const response = await fetch('/api/agents', {
                    credentials: 'include'
                });

                if (!response.ok) {
                    throw new Error('Failed to load agents');
                }

                const data = await response.json();
                currentAgents = data.agents || [];

                // Update UI
                displayAgents(currentAgents);
                updateAgentLimitInfo(data.count, data.max_agents, data.can_create_more);

                console.log(`✅ Loaded ${currentAgents.length} agents`);
            } catch (error) {
                console.error('Error loading agents:', error);
                document.getElementById('agents-list').innerHTML = `
                    <p style="text-align: center; color: #ef4444; padding: 40px;">
                        ❌ Failed to load agents. Please refresh the page.
                    </p>
                `;
            }
        }

        let agentTypeFilter = 'all';

        function filterAgentsByType(type) {
            agentTypeFilter = type;
            document.querySelectorAll('.agent-type-filter').forEach(b => b.classList.remove('active'));
            const btn = document.querySelector(`.agent-type-filter[data-filter="${type}"]`);
            if (btn) btn.classList.add('active');
            displayAgents(currentAgents);
        }

        function getAgentTypeBadge(agentType) {
            const badges = {
                'direct': '<span style="background:#06b6d4; color:#0f172a; padding:2px 8px; border-radius:8px; font-size:11px; font-weight:600;">LLM</span>',
                'websocket': '<span style="background:#a855f7; color:#fff; padding:2px 8px; border-radius:8px; font-size:11px; font-weight:600;">WS</span>',
                'http_api': '<span style="background:#f59e0b; color:#0f172a; padding:2px 8px; border-radius:8px; font-size:11px; font-weight:600;">HTTP</span>',
            };
            return badges[agentType] || badges['direct'];
        }

        function onAgentTypeChange() {
            const type = document.getElementById('agent-type-select').value;
            const connFields = document.getElementById('agent-connection-fields');
            if (connFields) connFields.style.display = (type === 'direct') ? 'none' : 'block';
        }

        function displayAgents(agents) {
            const agentsList = document.getElementById('agents-list');

            let filtered = agents;
            if (agentTypeFilter !== 'all') {
                filtered = agents.filter(a => a.agent_type === agentTypeFilter);
            }

            if (filtered.length === 0) {
                agentsList.innerHTML = `
                    <div style="text-align: center; padding: 60px 20px;">
                        <p style="font-size: 48px; margin-bottom: 16px;">🤖</p>
                        <h3 style="color: rgba(255, 255, 255, 0.9); margin-bottom: 12px;">No agents${agentTypeFilter !== 'all' ? ' of this type' : ''}</h3>
                        <p style="color: rgba(255, 255, 255, 0.6); margin-bottom: 24px;">
                            Create your first agent to get started
                        </p>
                        <button onclick="showCreateAgentModal()" style="background: linear-gradient(135deg, var(--neon-cyan), var(--neon-purple));">
                            + Create Agent
                        </button>
                    </div>
                `;
                return;
            }

            agentsList.innerHTML = filtered.map(agent => {
                const isExternal = agent.agent_type === 'websocket' || agent.agent_type === 'http_api';
                const typeBadge = getAgentTypeBadge(agent.agent_type);
                const featuredBadge = agent.is_featured ? '<span style="background:#10b981; color:#fff; padding:2px 8px; border-radius:8px; font-size:11px; font-weight:600; margin-left:4px;">Featured</span>' : '';

                let connInfo = '';
                if (isExternal) {
                    connInfo = `<span>${agent.connection_url || 'No URL'}</span>`;
                    if (agent.last_connected_at) {
                        connInfo += ` <span style="color:var(--success);">Last connected: ${new Date(agent.last_connected_at).toLocaleString()}</span>`;
                    }
                    if (agent.last_error) {
                        connInfo += ` <span style="color:var(--error);">Error: ${agent.last_error}</span>`;
                    }
                }

                let actionButtons = '';
                if (agent.agent_type === 'direct') {
                    actionButtons = `
                        <button onclick="selectAgent(${agent.id})" style="padding: 8px 16px; font-size: 14px; background: var(--neon-cyan); color: #0f172a; font-weight: 600;">Select</button>
                        <button onclick="editAgent(${agent.id})" style="padding: 8px 16px; font-size: 14px; background: var(--neon-purple); color: #fff; font-weight: 600;">Edit</button>
                        <button onclick="cloneAgent(${agent.id})" style="padding: 8px 16px; font-size: 14px; background: #6b7280; color: #fff; font-weight: 600;">Clone</button>
                        <button onclick="exportAgent(${agent.id})" style="padding: 8px 16px; font-size: 14px; background: #6b7280; color: #fff; font-weight: 600;">Export</button>
                        ${!agent.is_default ? `<button onclick="deleteAgent(${agent.id}, '${agent.name.replace(/'/g, "\\'")}')" style="padding: 8px 16px; font-size: 14px; background: #ef4444; color: #fff; font-weight: 600;">Delete</button>` : ''}
                    `;
                } else {
                    actionButtons = `
                        <button onclick="testAgent(${agent.id})" class="btn btn-secondary btn-sm">Test</button>
                        <button onclick="editAgent(${agent.id})" class="btn btn-secondary btn-sm">Edit</button>
                        <button onclick="deleteAgent(${agent.id}, '${agent.name.replace(/'/g, "\\'")}')" class="btn btn-secondary btn-sm" style="color:var(--error);">Delete</button>
                    `;
                }

                return `
                <div class="card" style="position: relative; margin-bottom:12px; ${agent.is_default ? 'border: 2px solid var(--neon-cyan); box-shadow: 0 0 20px rgba(6, 182, 212, 0.3);' : ''}">
                    ${agent.is_default ? '<div style="position: absolute; top: 12px; right: 12px; background: var(--neon-cyan); color: #0f172a; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600;">DEFAULT</div>' : ''}

                    <div style="display: flex; align-items: start; gap: 16px;">
                        <div style="font-size: 48px; line-height: 1;">${agent.avatar_emoji || '🤖'}</div>
                        <div style="flex: 1;">
                            <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
                                <h3 style="margin: 0; color: rgba(255, 255, 255, 0.95);">${agent.name}</h3>
                                ${typeBadge}${featuredBadge}
                            </div>
                            <p style="color: rgba(255, 255, 255, 0.6); font-size: 14px; margin-bottom: 12px;">
                                ${agent.description || 'No description'}
                            </p>

                            <div style="display: flex; gap: 16px; font-size: 13px; color: rgba(255, 255, 255, 0.5); margin-bottom: 16px; flex-wrap:wrap;">
                                ${agent.agent_type === 'direct' ? `<span>${agent.total_posts || 0} posts</span>` : ''}
                                <span>Created ${agent.created_at ? new Date(agent.created_at).toLocaleDateString() : 'N/A'}</span>
                                ${connInfo}
                                ${!agent.is_active ? '<span style="color: #fbbf24;">Inactive</span>' : ''}
                            </div>

                            <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                                ${actionButtons}
                            </div>
                        </div>
                    </div>
                </div>
                `;
            }).join('');
        }

        function updateAgentLimitInfo(count, maxAgents, canCreateMore) {
            const limitInfo = document.getElementById('agent-limit-info');
            document.getElementById('agent-count').textContent = count;
            document.getElementById('max-agents').textContent = maxAgents;

            if (count >= maxAgents) {
                limitInfo.style.display = 'block';
                limitInfo.style.background = 'linear-gradient(135deg, rgba(239, 68, 68, 0.15), rgba(220, 38, 38, 0.15))';
                limitInfo.style.borderColor = 'rgba(239, 68, 68, 0.4)';
            } else {
                limitInfo.style.display = 'block';
                limitInfo.style.background = 'linear-gradient(135deg, rgba(6, 182, 212, 0.15), rgba(168, 85, 247, 0.15))';
                limitInfo.style.borderColor = 'rgba(6, 182, 212, 0.4)';
            }
        }

        function showCreateAgentModal() {
            editingAgentId = null;
            document.getElementById('agent-modal-title').textContent = 'Create New Agent';
            document.getElementById('agent-form').reset();
            document.getElementById('agent-id').value = '';
            document.getElementById('agent-emoji').value = '🤖';
            document.getElementById('agent-type-select').value = 'direct';
            onAgentTypeChange();
            document.getElementById('agent-modal').style.display = 'flex';
        }

        async function editAgent(agentId) {
            try {
                const response = await fetch(`/api/agents/${agentId}`, {
                    credentials: 'include'
                });

                if (!response.ok) {
                    throw new Error('Failed to load agent');
                }

                const data = await response.json();
                const agent = data.agent;

                editingAgentId = agentId;
                document.getElementById('agent-modal-title').textContent = 'Edit Agent';
                document.getElementById('agent-id').value = agent.id;
                document.getElementById('agent-name').value = agent.name;
                document.getElementById('agent-emoji').value = agent.avatar_emoji;
                document.getElementById('agent-description').value = agent.description || '';
                document.getElementById('agent-is-default').checked = agent.is_default;
                document.getElementById('agent-type-select').value = agent.agent_type || 'direct';
                onAgentTypeChange();
                const connUrl = document.getElementById('agent-connection-url');
                if (connUrl) connUrl.value = agent.connection_url || '';

                document.getElementById('agent-modal').style.display = 'flex';
            } catch (error) {
                console.error('Error loading agent:', error);
                alert('❌ Failed to load agent details');
            }
        }

        async function saveAgent(event) {
            event.preventDefault();

            const agentId = document.getElementById('agent-id').value;
            const agentType = document.getElementById('agent-type-select').value;
            const agentData = {
                name: document.getElementById('agent-name').value.trim(),
                avatar_emoji: document.getElementById('agent-emoji').value || '🤖',
                description: document.getElementById('agent-description').value.trim(),
                is_default: document.getElementById('agent-is-default').checked,
                agent_type: agentType,
            };
            if (agentType !== 'direct') {
                agentData.connection_url = (document.getElementById('agent-connection-url') || {}).value || '';
            }

            try {
                const url = agentId ? `/api/agents/${agentId}` : '/api/agents';
                const method = agentId ? 'PUT' : 'POST';

                const response = await fetch(url, {
                    method: method,
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include',
                    body: JSON.stringify(agentData)
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || 'Failed to save agent');
                }

                alert(data.message || '✅ Agent saved successfully!');
                closeModal('agent-modal');
                await loadAgents();
            } catch (error) {
                console.error('Error saving agent:', error);
                alert(`❌ ${error.message}`);
            }
        }

        async function deleteAgent(agentId, agentName) {
            if (!confirm(`Are you sure you want to delete "${agentName}"? This cannot be undone.`)) {
                return;
            }

            try {
                const response = await fetch(`/api/agents/${agentId}`, {
                    method: 'DELETE',
                    credentials: 'include'
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || 'Failed to delete agent');
                }

                alert('✅ Agent deleted successfully');
                await loadAgents();
            } catch (error) {
                console.error('Error deleting agent:', error);
                alert(`❌ ${error.message}`);
            }
        }

        async function cloneAgent(agentId) {
            try {
                const response = await fetch(`/api/agents/${agentId}/clone`, {
                    method: 'POST',
                    credentials: 'include'
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || 'Failed to clone agent');
                }

                alert('✅ Agent cloned successfully!');
                await loadAgents();
            } catch (error) {
                console.error('Error cloning agent:', error);
                alert(`❌ ${error.message}`);
            }
        }

        async function exportAgent(agentId) {
            try {
                const response = await fetch(`/api/agents/${agentId}/export`, {
                    credentials: 'include'
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error('Failed to export agent');
                }

                // Download as JSON file
                const blob = new Blob([JSON.stringify(data.export, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `agent-${data.export.name.toLowerCase().replace(/\s+/g, '-')}-export.json`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);

                alert('✅ Agent exported successfully!');
            } catch (error) {
                console.error('Error exporting agent:', error);
                alert('❌ Failed to export agent');
            }
        }

        async function selectAgent(agentId) {
            try {
                const agent = currentAgents.find(a => a.id === agentId);
                if (!agent) {
                    throw new Error('Agent not found');
                }

                // Load full agent configuration
                const response = await fetch(`/api/agents/${agentId}`, {
                    credentials: 'include'
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error('Failed to load agent configuration');
                }

                // Apply agent configuration to dashboard
                const agentConfig = data.agent;

                // TODO: Apply LLM config
                // TODO: Apply identity config
                // TODO: Apply Moltbook config

                alert(`✅ Switched to agent: ${agent.name}\n\nNote: Full agent configuration sync coming soon!`);
            } catch (error) {
                console.error('Error selecting agent:', error);
                alert(`❌ ${error.message}`);
            }
        }

        // Add event listener for character count
        document.addEventListener('DOMContentLoaded', function() {
            const adminContent = document.getElementById('admin-post-content');
            if (adminContent) {
                adminContent.addEventListener('input', updateAdminCharCount);
            }
        });

        // Load Moltbook state on tab switch
        function loadMoltbookState() {
            const moltbookData = JSON.parse(localStorage.getItem('openclaw_moltbook') || '{}');

            if (moltbookData.agent_id) {
                // Agent is registered - show profile if claimed
                if (moltbookData.is_claimed || moltbookData.api_key) {
                    // Show profile section
                    document.getElementById('registration-section').style.display = 'none';
                    document.getElementById('claim-section').style.display = 'none';
                    document.getElementById('profile-section').style.display = 'block';
                    updateMoltbookProfile(moltbookData);
                } else if (moltbookData.claim_url) {
                    // Show claim section
                    document.getElementById('registration-section').style.display = 'none';
                    document.getElementById('claim-section').style.display = 'block';

                    // Safely set values with null checks
                    const claimUrl = document.getElementById('mb-claim-url');
                    const verificationCode = document.getElementById('mb-verification-code');
                    if (claimUrl) claimUrl.value = moltbookData.claim_url || '';
                    if (verificationCode) verificationCode.value = moltbookData.verification_code || '';
                }
            }
        }


        // Auto-add loading states to all async button clicks
        document.addEventListener('DOMContentLoaded', () => {
            // Add click feedback to all buttons
            document.querySelectorAll('.btn').forEach(btn => {
                btn.addEventListener('click', function(e) {
                    // Visual click feedback
                    this.style.transform = 'scale(0.95)';
                    setTimeout(() => {
                        this.style.transform = '';
                    }, 150);
                });
            });

            // Override onclick handlers to add loading states
            const originalImport = window.importExistingAgent;
            window.importExistingAgent = async function() {
                const btn = document.querySelector('#import-agent-form .btn-primary');
                if (btn) setButtonLoading(btn, true, 'Connecting...');
                try {
                    await originalImport();
                } finally {
                    if (btn) setButtonLoading(btn, false);
                }
            };

            const originalRegister = window.registerMoltbookAgent;
            window.registerMoltbookAgent = async function() {
                const btn = document.querySelector('#new-agent-form .btn-primary');
                if (btn) setButtonLoading(btn, true, 'Registering...');
                try {
                    await originalRegister();
                } finally {
                    if (btn) setButtonLoading(btn, false);
                }
            };

            const originalTestConnection = window.testConnection;
            window.testConnection = async function() {
                const btn = document.getElementById('test-btn');
                if (btn) setButtonLoading(btn, true, 'Testing...');
                try {
                    await originalTestConnection();
                } finally {
                    if (btn) setButtonLoading(btn, false);
                }
            };

            const originalSaveLLM = window.saveLLMConfig;
            window.saveLLMConfig = async function() {
                const btn = event?.target || document.querySelector('#llm .btn-primary');
                if (btn) setButtonLoading(btn, true, 'Saving...');
                try {
                    await originalSaveLLM();
                } finally {
                    if (btn) setButtonLoading(btn, false);
                }
            };

            const originalSaveIdentity = window.saveIdentity;
            window.saveIdentity = async function() {
                const btn = event?.target || document.querySelector('#identity .btn-primary');
                if (btn) setButtonLoading(btn, true, 'Saving...');
                try {
                    await originalSaveIdentity();
                } finally {
                    if (btn) setButtonLoading(btn, false);
                }
            };

            const originalSaveUser = window.saveUser;
            window.saveUser = async function() {
                const btn = event?.target || document.querySelector('#user .btn-primary');
                if (btn) setButtonLoading(btn, true, 'Saving...');
                try {
                    await originalSaveUser();
                } finally {
                    if (btn) setButtonLoading(btn, false);
                }
            };

            const originalSaveSoul = window.saveSoul;
            window.saveSoul = async function() {
                const btn = event?.target || document.querySelector('#soul .btn-primary');
                if (btn) setButtonLoading(btn, true, 'Saving...');
                try {
                    await originalSaveSoul();
                } finally {
                    if (btn) setButtonLoading(btn, false);
                }
            };

            const originalSaveSecurity = window.saveSecurity;
            window.saveSecurity = async function() {
                const btn = event?.target || document.querySelector('#security .btn-primary');
                if (btn) setButtonLoading(btn, true, 'Saving...');
                try {
                    await originalSaveSecurity();
                } finally {
                    if (btn) setButtonLoading(btn, false);
                }
            };

            console.log('✅ Green Monkey Dashboard loaded with button feedback system');
        });

        // Initialize on load
        loadCurrentConfig();
        // ==================== AUTH & CREDITS SYSTEM ====================

        let currentUser = null;
        let creditPackages = [];

        // Check authentication status
        async function checkAuthStatus() {
            try {
                const response = await fetch('/api/auth/me', {
                    credentials: 'include'
                });

                if (response.ok) {
                    const data = await response.json();
                    if (data.authenticated) {
                        currentUser = data.user;
                        updateAuthUI(true);
                        console.log('✅ User logged in:', currentUser.email);
                    } else {
                        updateAuthUI(false);
                    }
                } else {
                    updateAuthUI(false);
                }
            } catch (error) {
                console.error('Error checking auth:', error);
                updateAuthUI(false);
            }
        }

        // Load user's agents
        async function loadUserAgents() {
            try {
                const response = await fetch('/api/agents', {
                    credentials: 'include'
                });

                if (response.ok) {
                    const data = await response.json();
                    if (data.success && data.agents) {
                        window.userAgents = data.agents;
                        console.log(`✅ Loaded ${data.agents.length} agent(s)`);
                    }
                } else {
                    console.warn('Could not load agents');
                    window.userAgents = [];
                }
            } catch (error) {
                console.error('Error loading agents:', error);
                window.userAgents = [];
            }
        }

        // Update UI based on auth status
        function updateAuthUI(isLoggedIn) {
            const loginBtn = document.getElementById('login-btn');
            const userInfo = document.getElementById('user-info');

            if (isLoggedIn && currentUser) {
                loginBtn.style.display = 'none';
                userInfo.style.display = 'flex';
                document.getElementById('user-email').textContent = currentUser.email;
                document.getElementById('credit-balance').textContent = currentUser.credit_balance;

                // Update subscription display
                updateSubscriptionDisplay(currentUser);

                // Show admin tab if user is admin
                const adminTabButton = document.getElementById('admin-tab-button');
                if (currentUser.is_admin) {
                    adminTabButton.style.display = 'flex';
                    console.log('✅ Admin access granted');
                } else {
                    adminTabButton.style.display = 'none';
                }
            } else {
                loginBtn.style.display = 'inline-block';
                userInfo.style.display = 'none';

                // Hide admin tab when logged out
                const adminTabButton = document.getElementById('admin-tab-button');
                if (adminTabButton) {
                    adminTabButton.style.display = 'none';
                }
            }
        }

        // Show/hide modals
        function showLoginModal() {
            // Store current tab for redirect after login
            const currentTab = document.querySelector('.tab-content.active')?.id || 'overview';
            sessionStorage.setItem('redirectAfterLogin', currentTab);

            // Create modal if it doesn't exist
            if (!document.getElementById('login-modal')) {
                const modalHTML = `
                    <div id="login-modal" class="channel-modal active">
                        <div class="channel-modal-content" style="max-width: 400px;">
                            <div class="channel-modal-header">
                                <div class="channel-modal-title">
                                    <span>🔐</span>
                                    <span>Sign In</span>
                                </div>
                                <button class="channel-modal-close" onclick="closeModal('login-modal')">✕</button>
                            </div>

                            <div id="login-form">
                                <p style="color: var(--text-secondary); margin-bottom: 20px;">
                                    Enter your email to receive a magic link
                                </p>
                                <div class="form-field">
                                    <label for="login-email">Email Address</label>
                                    <input type="email" id="login-email" placeholder="your@email.com" required>
                                </div>
                                <button class="btn btn-primary" style="width: 100%;" onclick="requestMagicLink()">
                                    Send Magic Link →
                                </button>
                            </div>

                            <div id="login-success" style="display: none; text-align: center; padding: 24px 0;">
                                <div style="font-size: 48px; margin-bottom: 16px;">✅</div>
                                <h3>Check Your Email!</h3>
                                <p style="color: var(--text-secondary); margin: 12px 0 0 0;">
                                    We sent a magic link to your inbox. Click it to sign in.
                                </p>
                            </div>
                        </div>
                    </div>
                `;
                document.body.insertAdjacentHTML('beforeend', modalHTML);

                // Close on backdrop click
                document.getElementById('login-modal').addEventListener('click', (e) => {
                    if (e.target.id === 'login-modal') {
                        closeModal('login-modal');
                    }
                });
            } else {
                document.getElementById('login-modal').style.display = 'block';
                document.getElementById('login-form').style.display = 'block';
                document.getElementById('login-success').style.display = 'none';
            }
        }

        async function requestMagicLink() {
            const email = document.getElementById('login-email').value;
            if (!email) {
                alert('Please enter your email');
                return;
            }

            try {
                const response = await fetch('/api/auth/request-magic-link', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email })
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    document.getElementById('login-form').style.display = 'none';
                    document.getElementById('login-success').style.display = 'block';

                    // If dev link is provided, show it in console
                    if (data.dev_link) {
                        console.log('🔗 Magic Link (Dev Mode):', data.dev_link);
                    }
                } else {
                    alert(data.error || 'Failed to send magic link');
                }
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }

        async function showBuyCreditsModal() {
            document.getElementById('buy-credits-modal').style.display = 'block';
            await loadCreditPackages();
        }

        function closeModal(modalId) {
            const modal = document.getElementById(modalId);
            if (modal) {
                modal.style.display = 'none';
            }
        }

        // Close modal when clicking outside
        window.onclick = function(event) {
            if (event.target.classList.contains('modal')) {
                event.target.style.display = 'none';
            }
        }

        // Request magic link
        async function requestMagicLink() {
            const emailInput = document.getElementById('login-email');
            if (!emailInput) {
                alert('Email input not found');
                return;
            }
            const email = emailInput.value.trim();

            if (!email) {
                alert('Please enter your email address');
                return;
            }

            try {
                const response = await fetch('/api/auth/request-magic-link', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email })
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    document.getElementById('login-form').style.display = 'none';
                    document.getElementById('login-success').style.display = 'block';

                    // Log dev link to console if available
                    if (data.dev_link) {
                        console.log('🔗 Magic Link (Dev Mode):', data.dev_link);
                        console.log('👆 Click the link above to sign in');
                    }

                    console.log('✅ Magic link sent to:', email);
                } else {
                    alert('Error: ' + (data.error || 'Failed to send magic link'));
                }
            } catch (error) {
                console.error('Error requesting magic link:', error);
                alert('Failed to send magic link. Please try again.');
            }
        }

        // Logout
        async function logout() {
            try {
                await fetch('/api/auth/logout', {
                    method: 'POST',
                    credentials: 'include'
                });

                currentUser = null;
                updateAuthUI(false);
                console.log('✅ Logged out');
            } catch (error) {
                console.error('Error logging out:', error);
            }
        }

        // Load credit packages
        async function loadCreditPackages() {
            try {
                const response = await fetch('/api/credits/packages');
                const data = await response.json();

                creditPackages = data.packages;
                renderCreditPackages();
            } catch (error) {
                console.error('Error loading packages:', error);
            }
        }

        // Render credit packages
        function renderCreditPackages() {
            const container = document.getElementById('credit-packages');
            container.innerHTML = '';

            creditPackages.forEach((pkg, index) => {
                const isPopular = index === 1; // Middle package is popular
                const packageEl = document.createElement('div');
                packageEl.className = 'credit-package' + (isPopular ? ' popular' : '');
                packageEl.innerHTML = `
                    <div style="font-size: 32px; margin-bottom: 8px;">📦</div>
                    <div style="font-weight: 700; font-size: 20px; margin-bottom: 4px;">${pkg.credits} Credits</div>
                    <div style="font-size: 28px; font-weight: 700; color: var(--primary); margin-bottom: 4px;">$${pkg.price.toFixed(2)}</div>
                    <div style="font-size: 13px; color: #666; margin-bottom: 12px;">$${pkg.price_per_credit.toFixed(3)} per post</div>
                    <button class="btn btn-primary" style="width: 100%; padding: 10px;" onclick="purchaseCredits(${pkg.id})">
                        Buy Now
                    </button>
                `;
                container.appendChild(packageEl);
            });
        }

        // Purchase credits
        async function purchaseCredits(packageId) {
            if (!currentUser) {
                closeModal('buy-credits-modal');
                showLoginModal();
                alert('Please log in first to purchase credits');
                return;
            }

            try {
                document.getElementById('payment-processing').style.display = 'flex';

                const response = await fetch('/api/credits/create-checkout', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ package_id: packageId })
                });

                const data = await response.json();

                if (response.ok && data.checkout_url) {
                    // Redirect to Stripe Checkout
                    window.location.href = data.checkout_url;
                } else {
                    document.getElementById('payment-processing').style.display = 'none';
                    alert('Error: ' + (data.error || 'Failed to create checkout'));
                }
            } catch (error) {
                document.getElementById('payment-processing').style.display = 'none';
                console.error('Error purchasing credits:', error);
                alert('Failed to start checkout. Please try again.');
            }
        }

        // ==================== SUBSCRIPTION FUNCTIONS ====================

        let subscriptionPlans = [];
        let currentSubscription = null;

        async function loadSubscriptionPlans() {
            try {
                const response = await fetch('/api/subscriptions/plans', {
                    credentials: 'include'
                });
                const data = await response.json();

                if (response.ok) {
                    subscriptionPlans = data.plans;
                    renderSubscriptionPlans();
                }
            } catch (error) {
                console.error('Error loading subscription plans:', error);
            }
        }

        function renderSubscriptionPlans() {
            const container = document.getElementById('subscription-plans');
            if (!container || subscriptionPlans.length === 0) return;

            const tierColors = {
                'free': 'rgba(107,114,128,0.2)',
                'pro': 'rgba(139,92,246,0.2)'
            };

            const tierEmojis = {
                'free': '🆓',
                'pro': '💎'
            };

            container.innerHTML = subscriptionPlans.map(plan => {
                const isCurrentTier = currentSubscription && currentSubscription.tier === plan.tier;
                const isFreeUser = !currentSubscription || currentSubscription.tier === 'free';
                const canUpgrade = isFreeUser || (currentSubscription && getTierLevel(plan.tier) > getTierLevel(currentSubscription.tier));

                return `
                    <div style="background: ${tierColors[plan.tier] || 'rgba(255,255,255,0.1)'}; border: 2px solid ${isCurrentTier ? 'rgba(16,185,129,0.5)' : 'rgba(255,255,255,0.2)'}; border-radius: 12px; padding: 24px; position: relative;">
                        ${isCurrentTier ? '<div style="position: absolute; top: 12px; right: 12px; background: rgba(16,185,129,0.3); padding: 4px 12px; border-radius: 6px; font-size: 11px; font-weight: 600;">CURRENT</div>' : ''}

                        <div style="font-size: 32px; margin-bottom: 8px;">${tierEmojis[plan.tier]}</div>
                        <div style="font-size: 24px; font-weight: 700; margin-bottom: 8px;">${plan.name}</div>
                        <div style="font-size: 36px; font-weight: 700; margin-bottom: 16px;">
                            $${plan.price}
                            <span style="font-size: 16px; opacity: 0.7;">/month</span>
                        </div>

                        <div style="border-top: 1px solid rgba(255,255,255,0.2); padding-top: 16px; margin-bottom: 16px;">
                            <div style="font-size: 14px; line-height: 1.8;">
                                <div style="margin-bottom: 8px;">⏱️ Platform limits apply (Moltbook: 30 min)</div>
                                <div style="margin-bottom: 8px;">🤖 Up to ${plan.features.max_agents === 999 ? 'Unlimited' : plan.features.max_agents} agent${plan.features.max_agents !== 1 ? 's' : ''}</div>
                                ${plan.features.scheduled_posting ? '<div style="margin-bottom: 8px;">📅 Scheduled posting</div>' : ''}
                                ${plan.features.analytics ? '<div style="margin-bottom: 8px;">📊 Analytics dashboard</div>' : ''}
                                ${plan.features.api_access ? '<div style="margin-bottom: 8px;">🔌 API access</div>' : ''}
                                ${plan.features.team_members > 1 ? `<div style="margin-bottom: 8px;">👥 ${plan.features.team_members} team members</div>` : ''}
                                ${plan.features.priority_support ? '<div style="margin-bottom: 8px;">⚡ Priority support</div>' : ''}
                            </div>
                        </div>

                        ${!isCurrentTier && canUpgrade ? `
                            <button class="btn btn-primary" onclick="subscribeToPlan(${plan.id})" style="width: 100%; padding: 12px; font-weight: 600;">
                                ${isFreeUser ? 'Get Started' : 'Upgrade'}
                            </button>
                        ` : isCurrentTier ? `
                            <button class="btn btn-secondary" onclick="manageSubscription()" style="width: 100%; padding: 12px;">
                                Manage Subscription
                            </button>
                        ` : `
                            <button class="btn btn-secondary" disabled style="width: 100%; padding: 12px; opacity: 0.5;">
                                Contact Sales
                            </button>
                        `}
                    </div>
                `;
            }).join('');
        }

        function getEffectiveTier(tier) {
            // Map legacy tiers to simplified 2-tier model
            if (tier === 'starter' || tier === 'team') return 'pro';
            return tier || 'free';
        }

        function getTierLevel(tier) {
            const levels = { 'free': 0, 'pro': 1 };
            return levels[getEffectiveTier(tier)] || 0;
        }

        async function subscribeToPlan(planId) {
            if (!currentUser) {
                showLoginModal();
                alert('Please log in first to subscribe');
                return;
            }

            try {
                const response = await fetch('/api/subscriptions/create-checkout', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ plan_id: planId })
                });

                const data = await response.json();

                if (response.ok && data.checkout_url) {
                    // Redirect to Stripe Checkout
                    window.location.href = data.checkout_url;
                } else {
                    alert('Error: ' + (data.error || 'Failed to create checkout'));
                }
            } catch (error) {
                console.error('Error subscribing to plan:', error);
                alert('Failed to start checkout. Please try again.');
            }
        }

        async function manageSubscription() {
            if (!currentUser) {
                showLoginModal();
                return;
            }

            try {
                const response = await fetch('/api/subscriptions/portal', {
                    method: 'POST',
                    credentials: 'include'
                });

                const data = await response.json();

                if (response.ok && data.portal_url) {
                    // Redirect to Stripe Customer Portal
                    window.location.href = data.portal_url;
                } else {
                    alert('Error: ' + (data.error || 'Failed to open portal'));
                }
            } catch (error) {
                console.error('Error opening customer portal:', error);
                alert('Failed to open subscription management. Please try again.');
            }
        }

        function showSubscriptionTab() {
            switchTab('subscription');
            // Load plans if not loaded
            if (subscriptionPlans.length === 0) {
                loadSubscriptionPlans();
            }
        }

        function updateSubscriptionDisplay(userData) {
            // Update badge in header
            const badge = document.getElementById('subscription-tier-badge');
            const tierEmojis = {
                'free': '🆓 Free',
                'pro': '💎 Pro'
            };

            const effectiveTier = getEffectiveTier(currentUser.subscription_tier);
            if (badge) {
                badge.textContent = tierEmojis[effectiveTier] || tierEmojis['free'];
            }

            // Update current subscription card
            const tierName = document.getElementById('current-tier-name');
            const details = document.getElementById('subscription-details');
            const manageBtn = document.getElementById('manage-subscription-btn');

            if (tierName) {
                const planNames = {
                    'free': 'Free Tier',
                    'pro': 'Pro Plan'
                };
                tierName.textContent = planNames[effectiveTier] || planNames['free'];
            }

            if (details) {
                if (userData.subscription_status === 'active' && effectiveTier !== 'free') {
                    const expiresAt = new Date(userData.subscription_expires_at).toLocaleDateString();
                    details.textContent = `Active • Renews on ${expiresAt}`;
                    if (manageBtn) manageBtn.style.display = 'block';
                } else if (userData.subscription_status === 'past_due') {
                    details.textContent = '⚠️ Payment failed • Please update payment method';
                    if (manageBtn) manageBtn.style.display = 'block';
                } else {
                    details.textContent = 'Platform limits apply • Upgrade for more agents & features!';
                    if (manageBtn) manageBtn.style.display = 'none';
                }
            }

            currentSubscription = {
                tier: currentUser.subscription_tier || 'free',
                status: userData.subscription_status
            };

            // Re-render plans if already loaded
            if (subscriptionPlans.length > 0) {
                renderSubscriptionPlans();
            }
        }

        // Check auth status and handle payment redirects on load
        window.addEventListener('load', () => {
            // Always check authentication status
            checkAuthStatus();

            // Load user's agents
            loadUserAgents();

            // Load subscription plans
            loadSubscriptionPlans();

            // Check for payment/subscription status in URL (after Stripe redirect)
            const urlParams = new URLSearchParams(window.location.search);
            const paymentStatus = urlParams.get('payment');
            const subscriptionStatus = urlParams.get('subscription');

            if (paymentStatus === 'success') {
                alert('🎉 Payment successful! Your credits have been added.');
                // Clean URL
                window.history.replaceState({}, document.title, window.location.pathname);
            } else if (paymentStatus === 'cancelled') {
                alert('Payment was cancelled');
                window.history.replaceState({}, document.title, window.location.pathname);
            } else if (subscriptionStatus === 'success') {
                alert('🎉 Subscription activated! Welcome to your new plan!');
                showSubscriptionTab();
                // Clean URL
                window.history.replaceState({}, document.title, window.location.pathname);
                // Reload user data to get updated subscription
                setTimeout(() => checkAuthStatus(), 1000);
            } else if (subscriptionStatus === 'cancelled') {
                alert('Subscription setup was cancelled');
                window.history.replaceState({}, document.title, window.location.pathname);
            }
        });

        // ============================================
        // PHASE 1: FEED + ANALYTICS JAVASCRIPT
        // ============================================

        // Feed State
        let currentSort = 'hot';
        let currentPosts = [];
        let paginationCursor = null;

        // Load feed when tab is opened
        function initFeedTab() {
            console.log('📖 Initializing Feed tab');

            // Check if user can access feed (Pro only)
            if (!currentUser || !currentUser.subscription_tier) {
                document.getElementById('feed-upgrade-prompt').style.display = 'block';
                document.getElementById('feed-content').style.display = 'none';
                return;
            }

            const tier = getEffectiveTier(currentUser.subscription_tier);
            if (tier !== 'pro') {
                document.getElementById('feed-upgrade-prompt').style.display = 'block';
                document.getElementById('feed-content').style.display = 'none';
            } else {
                document.getElementById('feed-upgrade-prompt').style.display = 'none';
                document.getElementById('feed-content').style.display = 'block';
                loadFeed('hot', false);
            }
        }

        // Load feed
        async function loadFeed(sort = 'hot', append = false) {
            console.log(`📖 Loading feed (sort: ${sort}, append: ${append})`);

            // Show loading
            document.getElementById('feed-loading').style.display = 'block';
            document.getElementById('feed-empty').style.display = 'none';

            if (!append) {
                document.getElementById('feed-container').innerHTML = '';
            }

            try {
                const params = new URLSearchParams({
                    sort: sort,
                    limit: 25
                });

                if (append && paginationCursor) {
                    params.append('after', paginationCursor);
                }

                const response = await fetch(`/api/moltbook/feed?${params}`, {
                    credentials: 'include'
                });

                if (response.status === 403) {
                    const error = await response.json();
                    document.getElementById('feed-upgrade-prompt').style.display = 'block';
                    document.getElementById('feed-content').style.display = 'none';
                    document.getElementById('feed-loading').style.display = 'none';
                    return;
                }

                if (!response.ok) {
                    throw new Error('Failed to load feed');
                }

                const data = await response.json();
                console.log('📦 Feed API Response:', data);
                console.log('📝 Posts count:', data.posts ? data.posts.length : 0);

                if (data.posts && data.posts.length > 0) {
                    console.log('🎯 First post sample:', data.posts[0]);
                }

                // Update pagination
                paginationCursor = data.pagination?.after;

                // Render posts
                if (append) {
                    currentPosts = [...currentPosts, ...data.posts];
                } else {
                    currentPosts = data.posts || [];
                }

                renderPosts(data.posts || [], append);

                // Show/hide empty state
                if (currentPosts.length === 0) {
                    document.getElementById('feed-empty').style.display = 'block';
                }

                // Hide/show load more button
                document.getElementById('load-more-btn').style.display =
                    paginationCursor ? 'block' : 'none';

            } catch (error) {
                console.error('Error loading feed:', error);
                alert(`❌ Failed to load feed: ${error.message}`);
            } finally {
                document.getElementById('feed-loading').style.display = 'none';
            }
        }

        function renderPosts(posts, append = false) {
            const container = document.getElementById('feed-container');

            if (!append) {
                container.innerHTML = '';
            }

            if (!posts || posts.length === 0) {
                return;
            }

            posts.forEach(post => {
                const card = document.createElement('div');
                card.className = 'post-card';
                card.style.cssText = 'background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 20px; margin-bottom: 16px;';

                const authorAvatar = post.author?.avatar || 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2232%22 height=%2232%22%3E%3Crect fill=%22%231e293b%22 width=%2232%22 height=%2232%22/%3E%3Ccircle cx=%2216%22 cy=%2216%22 r=%2210%22 fill=%22%230ea5e9%22/%3E%3Ctext x=%2216%22 y=%2221%22 font-size=%2214%22 fill=%22white%22 text-anchor=%22middle%22%3E?%3C/text%3E%3C/svg%3E';
                const authorName = post.author?.name || 'Unknown';
                const submoltName = post.submolt?.name || 'general';
                const title = post.title || 'Untitled';
                const content = post.content || '';
                const upvotes = post.upvotes || 0;
                const comments = post.comment_count || 0;
                const createdAt = post.created_at || '';
                const postId = post.id;
                const isUpvoted = post.is_upvoted || false;

                const upvoteStyle = isUpvoted ?
                    'background: linear-gradient(135deg, var(--neon-purple), var(--neon-cyan));' :
                    'background: rgba(15, 23, 42, 0.6);';

                card.innerHTML = `
                    <div style="display: flex; align-items: center; margin-bottom: 12px;">
                        <img src="${authorAvatar}" style="width: 32px; height: 32px; border-radius: 50%; margin-right: 12px;" onerror="this.style.display='none'">
                        <div style="flex: 1;">
                            <span style="color: var(--neon-cyan); font-weight: 600;">${authorName}</span>
                            <span style="color: rgba(255, 255, 255, 0.5); margin: 0 8px;">•</span>
                            <span style="color: rgba(255, 255, 255, 0.7);">m/${submoltName}</span>
                            <span style="color: rgba(255, 255, 255, 0.5); margin: 0 8px;">•</span>
                            <span style="color: rgba(255, 255, 255, 0.5);">${formatTimeAgo(createdAt)}</span>
                        </div>
                    </div>
                    <h3 style="color: white; margin: 0 0 12px 0; font-size: 18px; font-weight: 600;">${title}</h3>
                    <p style="color: rgba(255, 255, 255, 0.8); margin: 0 0 16px 0; line-height: 1.6;">${truncate(content, 200)}</p>
                    <div style="display: flex; gap: 16px; align-items: center;">
                        <button class="upvote-btn" data-post-id="${postId}" data-upvoted="${isUpvoted}" onclick="upvotePost('${postId}', this)" style="${upvoteStyle} border: 1px solid rgba(255, 255, 255, 0.2); color: white; padding: 8px 16px; border-radius: 8px; cursor: pointer; display: flex; align-items: center; gap: 8px;">
                            <span>⬆️</span>
                            <span class="upvote-count">${upvotes}</span>
                        </button>
                        <div style="border: 1px solid rgba(255, 255, 255, 0.2); color: white; padding: 8px 16px; border-radius: 8px; display: flex; align-items: center; gap: 8px;">
                            <span>💬</span>
                            <span>${comments}</span>
                        </div>
                        <a href="https://www.moltbook.com/m/${submoltName}/posts/${postId}" target="_blank" style="margin-left: auto; color: var(--neon-cyan); text-decoration: none; display: flex; align-items: center; gap: 8px;">
                            <span>🦞</span>
                            <span>View on Moltbook</span>
                        </a>
                    </div>
                `;

                container.appendChild(card);
            });
        }

        async function upvotePost(postId, button) {
            console.log('👍 Upvoting post:', postId);

            const isUpvoted = button.dataset.upvoted === 'true';

            if (isUpvoted) {
                console.log('Already upvoted');
                return;
            }

            // Optimistic UI update
            button.style.background = 'linear-gradient(135deg, var(--neon-purple), var(--neon-cyan))';
            button.dataset.upvoted = 'true';
            const countSpan = button.querySelector('.upvote-count');
            const oldCount = parseInt(countSpan.textContent);
            countSpan.textContent = oldCount + 1;

            try {
                const response = await fetch(`/api/moltbook/posts/${postId}/upvote`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    credentials: 'include',
                    body: JSON.stringify({})
                });

                if (response.status === 403) {
                    const error = await response.json();
                    alert(error.error);
                    // Revert UI
                    button.style.background = 'rgba(15, 23, 42, 0.6)';
                    button.dataset.upvoted = 'false';
                    countSpan.textContent = oldCount;
                    return;
                }

                if (!response.ok) {
                    throw new Error('Failed to upvote');
                }

                const data = await response.json();
                console.log('✅ Upvoted successfully');

            } catch (error) {
                console.error('Error upvoting:', error);
                // Revert optimistic update
                button.style.background = 'rgba(15, 23, 42, 0.6)';
                button.dataset.upvoted = 'false';
                countSpan.textContent = oldCount;
                alert(`❌ Failed to upvote: ${error.message}`);
            }
        }

        function changeFeedSort(sort) {
            // Update active button
            document.querySelectorAll('.btn-sort').forEach(btn => {
                if (btn.dataset.sort === sort) {
                    btn.classList.add('active');
                    btn.style.background = 'linear-gradient(135deg, var(--neon-purple), var(--neon-cyan))';
                } else {
                    btn.classList.remove('active');
                    btn.style.background = 'rgba(15, 23, 42, 0.6)';
                }
            });

            currentSort = sort;
            paginationCursor = null;
            loadFeed(sort, false);
        }

        function loadMorePosts() {
            loadFeed(currentSort, true);
        }

        function refreshFeed() {
            paginationCursor = null;
            loadFeed(currentSort, false);
        }

        // Utility functions
        function formatTimeAgo(timestamp) {
            if (!timestamp) return '';
            const now = new Date();
            const posted = new Date(timestamp);
            const diff = Math.floor((now - posted) / 1000); // seconds

            if (diff < 60) return 'just now';
            if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
            if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
            return `${Math.floor(diff / 86400)}d ago`;
        }

        function truncate(text, maxLength) {
            if (!text || text.length <= maxLength) return text;
            return text.substring(0, maxLength) + '...';
        }

        // ============================================
        // ANALYTICS
        // ============================================

        let karmaChart = null;

        function initAnalyticsTab() {
            console.log('📊 Initializing Analytics tab');

            // Check tier access (Pro only)
            if (!currentUser || !currentUser.subscription_tier) {
                document.getElementById('analytics-upgrade-prompt').style.display = 'block';
                document.getElementById('analytics-content').style.display = 'none';
                return;
            }

            const tier = getEffectiveTier(currentUser.subscription_tier);
            if (tier !== 'pro') {
                document.getElementById('analytics-upgrade-prompt').style.display = 'block';
                document.getElementById('analytics-content').style.display = 'none';
            } else {
                document.getElementById('analytics-upgrade-prompt').style.display = 'none';
                document.getElementById('analytics-content').style.display = 'block';

                // Populate agent selector
                populateAnalyticsAgentSelector();
            }
        }

        function populateAnalyticsAgentSelector() {
            const select = document.getElementById('analytics-agent-select');
            select.innerHTML = '<option value="">-- Select an agent --</option>';

            if (window.userAgents && window.userAgents.length > 0) {
                window.userAgents.forEach(agent => {
                    const option = document.createElement('option');
                    option.value = agent.id;
                    option.textContent = agent.name;
                    select.appendChild(option);
                });

                // Auto-select first agent
                select.value = window.userAgents[0].id;
                loadAnalytics();
            }
        }

        async function loadAnalytics() {
            const agentId = document.getElementById('analytics-agent-select').value;
            if (!agentId) return;

            console.log('📊 Loading analytics for agent:', agentId);

            try {
                // Load overview
                const overviewResponse = await fetch(`/api/analytics/overview?agent_id=${agentId}`, {
                    credentials: 'include'
                });

                if (overviewResponse.status === 403) {
                    const error = await overviewResponse.json();
                    document.getElementById('analytics-upgrade-prompt').style.display = 'block';
                    document.getElementById('analytics-content').style.display = 'none';
                    return;
                }

                if (!overviewResponse.ok) {
                    throw new Error('Failed to load analytics');
                }

                const overview = await overviewResponse.json();

                // Update stats
                document.getElementById('stat-karma').textContent = overview.current.karma;
                document.getElementById('stat-posts').textContent = overview.current.total_posts;
                document.getElementById('stat-upvotes').textContent = overview.current.total_upvotes;
                document.getElementById('stat-followers').textContent = overview.current.followers;

                // Render top posts
                renderTopPosts(overview.top_posts);

                // Load karma history for chart
                const historyResponse = await fetch(`/api/analytics/karma-history?agent_id=${agentId}&days=30`, {
                    credentials: 'include'
                });
                const history = await historyResponse.json();
                renderKarmaChart(history.data);

            } catch (error) {
                console.error('Error loading analytics:', error);
                alert(`❌ Failed to load analytics: ${error.message}`);
            }
        }

        function renderTopPosts(posts) {
            const container = document.getElementById('top-posts-container');

            if (!posts || posts.length === 0) {
                container.innerHTML = '<p style="color: rgba(255, 255, 255, 0.6); text-align: center;">No posts yet</p>';
                return;
            }

            container.innerHTML = posts.map((post, index) => `
                <div style="display: flex; align-items: center; padding: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.1); ${index === 0 ? 'background: linear-gradient(90deg, rgba(255, 215, 0, 0.05), transparent);' : ''}">
                    <div style="font-size: 24px; font-weight: 700; color: ${index === 0 ? '#FFD700' : 'rgba(255, 255, 255, 0.3)'}; margin-right: 16px; min-width: 30px;">
                        ${index + 1}${index === 0 ? '🏆' : ''}
                    </div>
                    <div style="flex: 1;">
                        <div style="font-weight: 600; color: white; margin-bottom: 4px;">${post.title}</div>
                        <div style="font-size: 12px; color: rgba(255, 255, 255, 0.6);">
                            m/${post.submolt || 'general'} • ${post.upvotes} upvotes • ${post.comments} comments
                        </div>
                    </div>
                    <a href="https://www.moltbook.com/posts/${post.post_id}" target="_blank" style="color: var(--neon-cyan); text-decoration: none;">
                        View 🦞
                    </a>
                </div>
            `).join('');
        }

        function renderKarmaChart(data) {
            const canvas = document.getElementById('karma-chart');
            const ctx = canvas.getContext('2d');

            // Destroy existing chart
            if (karmaChart) {
                karmaChart.destroy();
            }

            if (!data || data.length === 0) {
                ctx.fillStyle = 'rgba(255, 255, 255, 0.6)';
                ctx.textAlign = 'center';
                ctx.fillText('No data yet', canvas.width / 2, canvas.height / 2);
                return;
            }

            // Simple line chart (basic implementation)
            const maxKarma = Math.max(...data.map(d => d.karma), 10);
            const width = canvas.width;
            const height = canvas.height;
            const padding = 40;

            ctx.clearRect(0, 0, width, height);

            // Draw axes
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
            ctx.beginPath();
            ctx.moveTo(padding, padding);
            ctx.lineTo(padding, height - padding);
            ctx.lineTo(width - padding, height - padding);
            ctx.stroke();

            // Draw line
            if (data.length > 1) {
                ctx.strokeStyle = '#06b6d4';
                ctx.lineWidth = 2;
                ctx.beginPath();

                data.forEach((point, index) => {
                    const x = padding + (width - 2 * padding) * (index / (data.length - 1));
                    const y = height - padding - (height - 2 * padding) * (point.karma / maxKarma);

                    if (index === 0) {
                        ctx.moveTo(x, y);
                    } else {
                        ctx.lineTo(x, y);
                    }
                });

                ctx.stroke();
            }

            // Draw points
            ctx.fillStyle = '#06b6d4';
            data.forEach((point, index) => {
                const x = padding + (width - 2 * padding) * (index / Math.max(data.length - 1, 1));
                const y = height - padding - (height - 2 * padding) * (point.karma / maxKarma);

                ctx.beginPath();
                ctx.arc(x, y, 4, 0, 2 * Math.PI);
                ctx.fill();
            });

            // Labels
            ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
            ctx.font = '12px Arial';
            ctx.textAlign = 'center';

            if (data.length > 0) {
                const firstDate = new Date(data[0].date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                const lastDate = new Date(data[data.length - 1].date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

                ctx.fillText(firstDate, padding, height - 10);
                ctx.fillText(lastDate, width - padding, height - 10);
                ctx.fillText(`Max: ${maxKarma}`, padding, 20);
            }
        }

        async function syncAnalytics() {
            const agentId = document.getElementById('analytics-agent-select').value;
            if (!agentId) {
                alert('Please select an agent first');
                return;
            }

            try {
                const response = await fetch('/api/analytics/sync', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    credentials: 'include',
                    body: JSON.stringify({ agent_id: agentId })
                });

                if (!response.ok) {
                    throw new Error('Failed to sync analytics');
                }

                alert('✅ Analytics synced from Moltbook!');

                // Reload analytics
                setTimeout(() => loadAnalytics(), 1000);

            } catch (error) {
                console.error('Error syncing analytics:', error);
                alert(`❌ Failed to sync: ${error.message}`);
            }
        }

        // ========================================
        // CHAT CHANNELS MANAGEMENT
        // ========================================

        let channelsData = null;
        let selectedAgent = null;

        // Load channels when Channels tab is opened
        document.addEventListener('DOMContentLoaded', () => {
            const channelsTab = document.querySelector('[data-tab="channels"]');
            if (channelsTab) {
                channelsTab.addEventListener('click', loadChannels);
            }
        });

        async function loadChannels() {
            const loading = document.getElementById('channelsLoading');
            const grid = document.getElementById('channelsGrid');

            if (!loading || !grid) return;

            loading.style.display = 'block';
            grid.style.display = 'none';

            try {
                const response = await fetch('/api/channels/available');

                if (response.status === 401) {
                    loading.innerHTML = `
                        <div style="text-align: center;">
                            <div style="font-size: 48px; margin-bottom: 16px;">🔐</div>
                            <h3 style="margin: 0 0 8px 0;">Login Required</h3>
                            <p style="color: var(--text-secondary); margin: 0 0 24px 0;">Please sign in to manage your chat channels</p>
                            <button class="btn btn-primary" onclick="switchTab('overview')">Go to Login</button>
                        </div>
                    `;
                    return;
                }

                const data = await response.json();

                if (!data || !data.available) {
                    throw new Error('Invalid response from server');
                }

                channelsData = data;
                renderChannels(data);

                loading.style.display = 'none';
                grid.style.display = 'block';
            } catch (error) {
                console.error('Error loading channels:', error);
                loading.innerHTML = `
                    <div style="text-align: center;">
                        <p style="color: var(--error);">Failed to load channels</p>
                        <p style="color: var(--text-secondary); font-size: 14px;">${error.message}</p>
                        <button class="btn btn-primary" onclick="loadChannels()">Retry</button>
                    </div>
                `;
            }
        }

        function renderChannels(data) {
            if (!data || !data.available || !data.locked) {
                console.error('Invalid channels data:', data);
                return;
            }

            const { available, locked, user_tier } = data;

            // Organize channels by tier (2-tier: free + pro)
            const tiers = {
                free: [],
                pro: []
            };

            // Add available channels
            Object.values(available).forEach(channel => {
                const effectiveTier = (channel.tier === 'free') ? 'free' : 'pro';
                tiers[effectiveTier].push({ ...channel, isLocked: false });
            });

            // Add locked channels
            Object.values(locked).forEach(channel => {
                const effectiveTier = (channel.tier === 'free') ? 'free' : 'pro';
                tiers[effectiveTier].push({ ...channel, isLocked: true });
            });

            // Render each tier
            renderTierChannels('freeChannels', tiers.free, user_tier);
            renderTierChannels('proChannels', tiers.pro, user_tier);
        }

        function renderTierChannels(containerId, channels, userTier) {
            const container = document.getElementById(containerId);
            if (!container) return;

            if (channels.length === 0) {
                container.innerHTML = '<p style="color: var(--text-tertiary); text-align: center; padding: 24px;">No channels in this tier</p>';
                return;
            }

            container.innerHTML = channels.map(channel => createChannelCard(channel, userTier)).join('');

            // Add click handlers
            channels.forEach(channel => {
                const card = container.querySelector(`[data-channel-id="${channel.id}"]`);
                if (card && !channel.isLocked) {
                    card.addEventListener('click', () => openChannelModal(channel));
                }
            });
        }

        function createChannelCard(channel, userTier) {
            const isConnected = !!channel.connected;
            const statusClass = channel.isLocked ? 'locked' : (isConnected ? 'connected' : '');
            const difficultyClass = channel.difficulty || 'easy';

            return `
                <div class="channel-card ${statusClass}" data-channel-id="${channel.id}">
                    ${channel.isLocked ? '<div class="channel-lock-overlay">🔒</div>' : ''}
                    <div class="channel-card-header">
                        <div class="channel-icon">${channel.icon}</div>
                        <div class="channel-info">
                            <h4 class="channel-name">${channel.name}</h4>
                            <span class="channel-difficulty ${difficultyClass}">${difficultyClass}</span>
                        </div>
                    </div>
                    <p class="channel-description">${channel.description}</p>
                    <div class="channel-status">
                        <div class="channel-status-dot ${isConnected ? 'connected' : ''}"></div>
                        <span class="channel-status-text">
                            ${isConnected
                                ? (channel.connected_agent_name ? `Connected - ${channel.connected_agent_name}` : 'Connected')
                                : (channel.isLocked ? 'Requires Pro' : 'Not connected')}
                        </span>
                    </div>
                    <button class="channel-connect-btn ${isConnected ? 'connected' : ''} ${channel.isLocked ? 'locked' : ''}" ${channel.isLocked ? 'disabled' : ''}>
                        ${channel.isLocked ? '🔒 Unlock' : (isConnected ? '⚙️ Configure' : '🚀 Connect')}
                    </button>
                </div>
            `;
        }

        // Bundles removed — simplified to 2-tier model (Free + Pro)

        function openChannelModal(channel) {
            // Create modal HTML
            const modalHTML = `
                <div class="channel-modal active" id="channelModal">
                    <div class="channel-modal-content">
                        <div class="channel-modal-header">
                            <div class="channel-modal-title">
                                <span>${channel.icon}</span>
                                <span>${channel.name}</span>
                            </div>
                            <button class="channel-modal-close" onclick="closeChannelModal()">✕</button>
                        </div>

                        <div class="info-box" style="margin-bottom: 24px;">
                            <p><strong>Setup Type:</strong> ${channel.setup_type}</p>
                            <p style="margin: 8px 0 0 0;"><a href="${channel.docs_url}" target="_blank" style="color: var(--primary); text-decoration: none;">📖 View Documentation →</a></p>
                        </div>

                        <form id="channelConfigForm">
                            ${renderChannelFields(channel)}

                            <div class="form-actions">
                                <button type="button" class="btn btn-secondary" onclick="closeChannelModal()">Cancel</button>
                                <button type="button" class="btn btn-primary" onclick="testChannelConnection('${channel.id}')">Test Connection</button>
                                <button type="submit" class="btn btn-primary">Connect</button>
                            </div>
                        </form>
                    </div>
                </div>
            `;

            // Remove existing modal if any
            const existingModal = document.getElementById('channelModal');
            if (existingModal) {
                existingModal.remove();
            }

            // Add modal to page
            document.body.insertAdjacentHTML('beforeend', modalHTML);

            // Populate agent dropdown
            (async () => {
                try {
                    const resp = await fetch('/api/agents', { credentials: 'include' });
                    if (resp.ok) {
                        const data = await resp.json();
                        const agents = data.agents || [];
                        const select = document.getElementById('field_agent_id');
                        if (select && agents.length) {
                            agents.forEach(a => {
                                const opt = document.createElement('option');
                                opt.value = a.id;
                                opt.textContent = `${a.avatar_emoji || ''} ${a.name}`.trim();
                                if (channel.connected_agent_id && a.id === channel.connected_agent_id) {
                                    opt.selected = true;
                                }
                                select.appendChild(opt);
                            });
                        }
                    }
                } catch (e) {
                    console.error('Failed to load agents for channel modal:', e);
                }
            })();

            // Add form submit handler
            document.getElementById('channelConfigForm').addEventListener('submit', (e) => {
                e.preventDefault();
                connectChannel(channel.id);
            });

            // Close on backdrop click
            document.getElementById('channelModal').addEventListener('click', (e) => {
                if (e.target.id === 'channelModal') {
                    closeChannelModal();
                }
            });
        }

        function renderChannelFields(channel) {
            // Agent picker (universal for all channels)
            let html = `
                <div class="form-field">
                    <label for="field_agent_id">Agent</label>
                    <select id="field_agent_id" name="agent_id">
                        <option value="">No agent (raw LLM)</option>
                    </select>
                    <div class="form-field-help">Select an agent to power this channel with a personality</div>
                </div>
            `;

            if (!channel.fields || channel.fields.length === 0) {
                return html;
            }

            html += channel.fields.map(field => `
                <div class="form-field">
                    <label for="field_${field.key}">
                        ${field.label}
                        ${field.required ? '<span style="color: var(--error);">*</span>' : ''}
                    </label>
                    ${field.type === 'textarea'
                        ? `<textarea id="field_${field.key}" name="${field.key}" ${field.required ? 'required' : ''} rows="4"></textarea>`
                        : `<input type="${field.type}" id="field_${field.key}" name="${field.key}" ${field.required ? 'required' : ''}>`
                    }
                    ${field.help ? `<div class="form-field-help">${field.help}</div>` : ''}
                </div>
            `).join('');

            return html;
        }

        function closeChannelModal() {
            const modal = document.getElementById('channelModal');
            if (modal) {
                modal.classList.remove('active');
                setTimeout(() => modal.remove(), 300);
            }
        }

        async function testChannelConnection(channelId) {
            const form = document.getElementById('channelConfigForm');
            const formData = new FormData(form);
            const config = Object.fromEntries(formData);

            try {
                const response = await fetch(`/api/channels/test/${channelId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ config })
                });

                const data = await response.json();

                if (data.success) {
                    alert('✅ Connection test successful! You can now click Connect to save.');
                } else {
                    alert(`❌ Connection test failed: ${data.message || 'Unknown error'}`);
                }
            } catch (error) {
                alert(`❌ Test failed: ${error.message}`);
            }
        }

        async function connectChannel(channelId) {
            const form = document.getElementById('channelConfigForm');
            const formData = new FormData(form);
            const config = Object.fromEntries(formData);

            try {
                let response;

                // Telegram: save token then activate webhook in one flow
                if (channelId === 'telegram') {
                    // Step 1: Save bot token
                    response = await fetch('/api/telegram/connect', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ bot_token: config.bot_token }),
                        credentials: 'include'
                    });

                    const connectData = await response.json();
                    if (!response.ok || !connectData.success) {
                        alert(`❌ Failed to connect: ${connectData.error || 'Unknown error'}`);
                        return;
                    }

                    // Step 2: Activate webhook with owner_telegram_id and agent
                    const activateBody = { owner_telegram_id: config.owner_telegram_id };
                    if (config.agent_id) {
                        activateBody.agent_id = parseInt(config.agent_id);
                    }
                    const activateResponse = await fetch('/api/channels/telegram/activate', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(activateBody),
                        credentials: 'include'
                    });

                    const activateData = await activateResponse.json();
                    if (activateResponse.ok && activateData.success) {
                        alert(`✅ ${connectData.message} Webhook activated.`);
                        closeChannelModal();
                        loadChannels();
                    } else {
                        alert(`⚠️ Bot connected but webhook failed: ${activateData.error || 'Unknown error'}`);
                    }
                    return;
                }

                // Generic channel connect via agent
                const agentId = config.agent_id ? parseInt(config.agent_id) : 1;
                response = await fetch(`/api/channels/agent/${agentId}/connect`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ channel_id: channelId, config }),
                    credentials: 'include'
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    alert(`✅ ${data.message}`);
                    closeChannelModal();
                    loadChannels();
                } else {
                    alert(`❌ Failed to connect: ${data.error || 'Unknown error'}`);
                }
            } catch (error) {
                alert(`❌ Connection failed: ${error.message}`);
            }
        }

        function upgradeToBundle(bundleId) {
            // Redirect to subscription page with bundle pre-selected
            alert(`Bundle upgrade coming soon! Bundle: ${bundleId}`);
            // TODO: Implement bundle upgrade flow
        }

        // Channel search and filter
        document.addEventListener('DOMContentLoaded', () => {
            const searchInput = document.getElementById('channelSearch');
            const filterSelect = document.getElementById('channelFilter');

            if (searchInput) {
                searchInput.addEventListener('input', filterChannels);
            }

            if (filterSelect) {
                filterSelect.addEventListener('change', filterChannels);
            }
        });

        function filterChannels() {
            const searchTerm = document.getElementById('channelSearch')?.value.toLowerCase() || '';
            const filter = document.getElementById('channelFilter')?.value || 'all';

            document.querySelectorAll('.channel-card').forEach(card => {
                const channelName = card.querySelector('.channel-name')?.textContent.toLowerCase() || '';
                const channelDesc = card.querySelector('.channel-description')?.textContent.toLowerCase() || '';
                const isLocked = card.classList.contains('locked');
                const isConnected = card.classList.contains('connected');

                const matchesSearch = channelName.includes(searchTerm) || channelDesc.includes(searchTerm);
                const matchesFilter =
                    filter === 'all' ||
                    (filter === 'available' && !isLocked) ||
                    (filter === 'locked' && isLocked) ||
                    (filter === 'connected' && isConnected);

                card.style.display = (matchesSearch && matchesFilter) ? 'block' : 'none';
            });
        }

        // ========================================
        // LLM PROVIDERS MANAGEMENT
        // ========================================

        let providersData = null;

        // Load providers on tab switch
        const providersTab = document.querySelector('[data-tab="providers"]');
        if (providersTab) {
            providersTab.addEventListener('click', loadProviders);
        }

        async function loadProviders() {
            const loading = document.getElementById('providersLoading');
            const grid = document.getElementById('providersGrid');

            if (!loading || !grid) return;

            loading.style.display = 'block';
            grid.style.display = 'none';

            try {
                const response = await fetch('/api/providers/available');

                if (response.status === 401) {
                    loading.innerHTML = `
                        <div style="text-align: center;">
                            <div style="font-size: 48px; margin-bottom: 16px;">🔐</div>
                            <h3 style="margin: 0 0 8px 0;">Login Required</h3>
                            <p style="color: var(--text-secondary); margin: 0 0 24px 0;">Please sign in to manage your LLM providers</p>
                            <button class="btn btn-primary" onclick="switchTab('overview')">Go to Login</button>
                        </div>
                    `;
                    return;
                }

                const data = await response.json();

                if (!data || !data.available) {
                    throw new Error('Invalid response from server');
                }

                providersData = data;
                renderProviders(data);

                loading.style.display = 'none';
                grid.style.display = 'block';
            } catch (error) {
                console.error('Error loading providers:', error);
                loading.innerHTML = `
                    <div style="text-align: center;">
                        <p style="color: var(--error);">Failed to load providers</p>
                        <p style="color: var(--text-secondary); font-size: 14px;">${error.message}</p>
                        <button class="btn btn-primary" onclick="loadProviders()">Retry</button>
                    </div>
                `;
            }
        }

        function renderProviders(data) {
            if (!data || !data.available || !data.locked) {
                console.error('Invalid providers data:', data);
                return;
            }

            const { available, locked, user_tier } = data;

            // Organize providers by tier (2-tier: free + pro)
            const tiers = {
                free: [],
                pro: []
            };

            // Add available providers
            Object.values(available).forEach(provider => {
                const effectiveTier = (provider.tier === 'free') ? 'free' : 'pro';
                tiers[effectiveTier].push({ ...provider, isLocked: false });
            });

            // Add locked providers
            Object.values(locked).forEach(provider => {
                const effectiveTier = (provider.tier === 'free') ? 'free' : 'pro';
                tiers[effectiveTier].push({ ...provider, isLocked: true });
            });

            // Render each tier
            renderTierProviders('freeProviders', tiers.free, user_tier);
            renderTierProviders('proProviders', tiers.pro, user_tier);
        }

        function renderTierProviders(containerId, providers, userTier) {
            const container = document.getElementById(containerId);
            if (!container) return;

            if (providers.length === 0) {
                container.innerHTML = '<p style="color: var(--text-tertiary); text-align: center; padding: 24px;">No providers in this tier</p>';
                return;
            }

            container.innerHTML = providers.map(provider => createProviderCard(provider, userTier)).join('');

            // Add click handlers
            providers.forEach(provider => {
                const card = container.querySelector(`[data-provider-id="${provider.id}"]`);
                if (card && !provider.isLocked) {
                    card.addEventListener('click', () => openProviderModal(provider));
                }
            });
        }

        function createProviderCard(provider, userTier) {
            const isConnected = false; // TODO: Check if actually connected
            const statusClass = provider.isLocked ? 'locked' : (isConnected ? 'connected' : '');
            const difficultyClass = provider.difficulty || 'easy';

            // Get top 3 models
            const topModels = provider.models?.slice(0, 3) || [];

            return `
                <div class="provider-card ${statusClass}" data-provider-id="${provider.id}">
                    ${provider.isLocked ? '<div class="provider-lock-overlay">🔒</div>' : ''}
                    <div class="provider-card-header">
                        <div class="provider-icon">${provider.icon}</div>
                        <div class="provider-info">
                            <h4 class="provider-name">${provider.name}</h4>
                            <span class="provider-difficulty ${difficultyClass}">${difficultyClass}</span>
                        </div>
                    </div>
                    <p class="provider-description">${provider.description}</p>

                    ${topModels.length > 0 ? `
                        <div class="provider-models">
                            <div class="provider-models-title">Available Models</div>
                            <div class="provider-models-list">
                                ${topModels.map(model => `
                                    <span class="provider-model-tag ${model.recommended ? 'recommended' : ''}">${model.name}</span>
                                `).join('')}
                                ${provider.models.length > 3 ? `<span class="provider-model-tag">+${provider.models.length - 3} more</span>` : ''}
                            </div>
                        </div>
                    ` : ''}

                    ${provider.benefits ? `
                        <div class="provider-benefits">
                            ${provider.benefits.slice(0, 2).map(benefit => `
                                <div class="provider-benefit">${benefit}</div>
                            `).join('')}
                        </div>
                    ` : ''}

                    <div class="provider-status">
                        <div class="provider-status-dot ${isConnected ? 'connected' : ''}"></div>
                        <span class="provider-status-text">
                            ${isConnected ? 'Connected' : (provider.isLocked ? 'Requires Pro' : 'Not connected')}
                        </span>
                    </div>
                    <button class="provider-connect-btn ${isConnected ? 'connected' : ''} ${provider.isLocked ? 'locked' : ''}" ${provider.isLocked ? 'disabled' : ''}>
                        ${provider.isLocked ? '🔒 Unlock' : (isConnected ? '⚙️ Configure' : '🚀 Connect')}
                    </button>
                </div>
            `;
        }

        // Provider bundles removed — simplified to 2-tier model (Free + Pro)

        function openProviderModal(provider) {
            // Create modal HTML
            const modalHTML = `
                <div id="providerModal" class="channel-modal active">
                    <div class="channel-modal-content">
                        <div class="channel-modal-header">
                            <div style="display: flex; align-items: center; gap: 16px;">
                                <div style="font-size: 56px;">${provider.icon}</div>
                                <div>
                                    <h2 style="margin: 0 0 8px 0;">${provider.name}</h2>
                                    <p style="color: var(--text-secondary); margin: 0;">${provider.description}</p>
                                </div>
                            </div>
                            <button class="channel-modal-close" onclick="closeProviderModal()">×</button>
                        </div>

                        <div class="channel-modal-body">
                            ${provider.models && provider.models.length > 0 ? `
                                <div style="margin-bottom: 24px;">
                                    <label style="display: block; margin-bottom: 8px; font-weight: 600;">Select Model</label>
                                    <select id="providerModelSelect" style="width: 100%; padding: 10px; border: 1px solid var(--border); border-radius: 6px; background: white;">
                                        ${provider.models.map(model => `
                                            <option value="${model.id}" ${model.recommended ? 'selected' : ''}>
                                                ${model.name}${model.context ? ` (${model.context} context)` : ''}${model.recommended ? ' ⭐ Recommended' : ''}
                                            </option>
                                        `).join('')}
                                    </select>
                                </div>
                            ` : ''}

                            <form id="providerConfigForm">
                                ${provider.fields.map(field => `
                                    <div style="margin-bottom: 16px;">
                                        <label style="display: block; margin-bottom: 8px; font-weight: 500;">
                                            ${field.label}${field.required ? ' <span style="color: var(--error);">*</span>' : ''}
                                        </label>
                                        ${field.type === 'textarea' ? `
                                            <textarea
                                                name="${field.key}"
                                                ${field.required ? 'required' : ''}
                                                placeholder="${field.help || ''}"
                                                style="width: 100%; padding: 10px; border: 1px solid var(--border); border-radius: 6px; min-height: 100px; font-family: monospace; font-size: 12px;"
                                            ></textarea>
                                        ` : `
                                            <input
                                                type="${field.type}"
                                                name="${field.key}"
                                                ${field.required ? 'required' : ''}
                                                placeholder="${field.help || ''}"
                                                style="width: 100%; padding: 10px; border: 1px solid var(--border); border-radius: 6px;"
                                            />
                                        `}
                                        ${field.help ? `<small style="color: var(--text-tertiary); font-size: 12px;">${field.help}</small>` : ''}
                                    </div>
                                `).join('')}
                            </form>

                            ${provider.docs_url ? `
                                <div style="margin-top: 24px; padding: 16px; background: rgba(102, 126, 234, 0.08); border-radius: 8px;">
                                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                                        <span>📚</span>
                                        <strong>Documentation</strong>
                                    </div>
                                    <p style="margin: 0; font-size: 14px; color: var(--text-secondary);">
                                        Need help? Check the <a href="${provider.docs_url}" target="_blank" style="color: var(--primary);">official documentation</a>
                                    </p>
                                </div>
                            ` : ''}
                        </div>

                        <div class="channel-modal-footer">
                            <button class="btn btn-secondary" onclick="closeProviderModal()">Cancel</button>
                            <button class="btn btn-primary" onclick="connectProvider('${provider.id}')">Connect Provider</button>
                        </div>
                    </div>
                </div>
            `;

            // Remove existing modal if any
            const existingModal = document.getElementById('providerModal');
            if (existingModal) {
                existingModal.remove();
            }

            // Add modal to page
            document.body.insertAdjacentHTML('beforeend', modalHTML);
        }

        function closeProviderModal() {
            const modal = document.getElementById('providerModal');
            if (modal) {
                modal.classList.remove('active');
                setTimeout(() => modal.remove(), 300);
            }
        }

        async function connectProvider(providerId) {
            const form = document.getElementById('providerConfigForm');
            const modelSelect = document.getElementById('providerModelSelect');
            const formData = new FormData(form);
            const config = Object.fromEntries(formData);
            const selectedModel = modelSelect?.value;

            // Get current agent (use first agent for now)
            // TODO: Let user select which agent
            const agentId = 1;

            try {
                const response = await fetch(`/api/providers/agent/${agentId}/connect`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ provider_id: providerId, config, model: selectedModel })
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    alert(`✅ ${data.message}`);
                    closeProviderModal();
                    loadProviders(); // Reload to show updated status
                } else {
                    alert(`❌ Failed to connect: ${data.error || 'Unknown error'}`);
                }
            } catch (error) {
                alert(`❌ Connection failed: ${error.message}`);
            }
        }

        // Provider search and filter
        document.addEventListener('DOMContentLoaded', () => {
            const searchInput = document.getElementById('providerSearch');
            const filterSelect = document.getElementById('providerFilter');

            if (searchInput) {
                searchInput.addEventListener('input', filterProviders);
            }

            if (filterSelect) {
                filterSelect.addEventListener('change', filterProviders);
            }
        });

        function filterProviders() {
            const searchTerm = document.getElementById('providerSearch')?.value.toLowerCase() || '';
            const filter = document.getElementById('providerFilter')?.value || 'all';

            document.querySelectorAll('.provider-card').forEach(card => {
                const providerName = card.querySelector('.provider-name')?.textContent.toLowerCase() || '';
                const providerDesc = card.querySelector('.provider-description')?.textContent.toLowerCase() || '';
                const isLocked = card.classList.contains('locked');
                const isConnected = card.classList.contains('connected');

                const matchesSearch = providerName.includes(searchTerm) || providerDesc.includes(searchTerm);
                const matchesFilter =
                    filter === 'all' ||
                    (filter === 'available' && !isLocked) ||
                    (filter === 'locked' && isLocked) ||
                    (filter === 'connected' && isConnected);

                card.style.display = (matchesSearch && matchesFilter) ? 'block' : 'none';
            });
        }

        // Handle redirect after login
        document.addEventListener('DOMContentLoaded', () => {
            // Check if user just logged in
            const urlParams = new URLSearchParams(window.location.search);
            const loginSuccess = window.location.pathname === '/' && !urlParams.toString();

            // If user is logged in, check for redirect
            fetch('/api/auth/me')
                .then(r => r.json())
                .then(data => {
                    if (data.authenticated) {
                        const redirectTab = sessionStorage.getItem('redirectAfterLogin');
                        if (redirectTab && redirectTab !== 'overview') {
                            // Clear the stored redirect
                            sessionStorage.removeItem('redirectAfterLogin');
                            // Switch to the tab they were trying to access
                            setTimeout(() => switchTab(redirectTab), 500);
                        }
                    }
                })
                .catch(err => console.log('Not logged in'));
        });

        // ========================================
        // CONNECT TAB - SUPERPOWERS
        // ========================================

        // Load connected services on tab switch
        const connectTab = document.querySelector('[data-tab="connect"]');
        if (connectTab) {
            connectTab.addEventListener('click', loadConnectedServices);
        }

        async function loadConnectedServices() {
            try {
                const response = await fetch('/api/superpowers/list');

                if (response.status === 401) {
                    return; // Not logged in
                }

                const data = await response.json();
                const services = data.superpowers || [];

                // Update connected services display
                const connectedContainer = document.getElementById('connectedServices');
                if (services.length === 0) {
                    connectedContainer.innerHTML = `
                        <div style="text-align: center; padding: 24px; color: var(--text-tertiary); grid-column: 1/-1;">
                            No services connected yet. Connect your first service below!
                        </div>
                    `;
                } else {
                    connectedContainer.innerHTML = services.map(service => `
                        <div class="connected-service-item">
                            <div class="service-icon">${getServiceIcon(service.service_type)}</div>
                            <div class="connected-service-details">
                                <div class="connected-service-name">${service.service_name}</div>
                                <div class="connected-service-time">
                                    Connected ${formatTimeAgo(service.connected_at)}
                                </div>
                            </div>
                            <button class="disconnect-btn" onclick="disconnectService(${service.id}, '${service.service_name}')">
                                Disconnect
                            </button>
                        </div>
                    `).join('');
                }

                // Update Gmail status
                const gmailService = services.find(s => s.service_type === 'gmail');
                const gmailStatus = document.getElementById('gmail-status');
                const gmailBtn = document.querySelector('.service-card[data-service="gmail"] .service-connect-btn');

                if (gmailService && gmailService.is_enabled) {
                    if (gmailStatus) gmailStatus.textContent = '✅ Connected';
                    if (gmailStatus) gmailStatus.classList.add('connected');
                    if (gmailBtn) gmailBtn.textContent = '⚙️ Manage Gmail';
                    if (gmailBtn) gmailBtn.classList.add('connected');
                } else {
                    if (gmailStatus) gmailStatus.textContent = 'Not Connected';
                    if (gmailStatus) gmailStatus.classList.remove('connected');
                    if (gmailBtn) gmailBtn.textContent = '🚀 Connect Gmail';
                    if (gmailBtn) gmailBtn.classList.remove('connected');
                }

                // Update Binance status
                const binanceService = services.find(s => s.service_type === 'binance');
                const binanceStatus = document.getElementById('binance-status');
                const binanceConnectForm = document.getElementById('binance-connect-form');
                const binanceControls = document.getElementById('binance-controls');

                if (binanceService && binanceService.is_enabled) {
                    if (binanceStatus) binanceStatus.textContent = '✅ Connected';
                    if (binanceStatus) binanceStatus.classList.add('connected');
                    if (binanceConnectForm) binanceConnectForm.style.display = 'none';
                    if (binanceControls) binanceControls.style.display = 'block';

                    // Update trading toggle state from config
                    const config = binanceService.config ? (typeof binanceService.config === 'string' ? JSON.parse(binanceService.config) : binanceService.config) : {};
                    const tradingToggle = document.getElementById('binance-trading-toggle');
                    const tradingStatus = document.getElementById('binance-trading-status');
                    const toggleKnob = document.getElementById('binance-toggle-knob');
                    if (tradingToggle) tradingToggle.checked = config.trading_enabled || false;
                    if (tradingStatus) tradingStatus.textContent = config.trading_enabled ? 'Trading enabled (approval required)' : 'Read-only mode';
                    if (toggleKnob && config.trading_enabled) {
                        toggleKnob.style.transform = 'translateX(20px)';
                        toggleKnob.parentElement.previousElementSibling.nextElementSibling.style.background = '#10b981';
                    }
                } else {
                    if (binanceStatus) binanceStatus.textContent = 'Not Connected';
                    if (binanceStatus) binanceStatus.classList.remove('connected');
                    if (binanceConnectForm) binanceConnectForm.style.display = 'block';
                    if (binanceControls) binanceControls.style.display = 'none';
                }

                // Update status for OAuth services (Slack, GitHub, Discord, Spotify, Todoist, Dropbox)
                const oauthServices = ['slack', 'github', 'discord', 'spotify', 'todoist', 'dropbox'];
                for (const svc of oauthServices) {
                    const svcData = services.find(s => s.service_type === svc);
                    const statusEl = document.getElementById(`${svc}-status`);
                    const btn = document.querySelector(`.service-card[data-service="${svc}"] .service-connect-btn`);

                    if (svcData && svcData.is_enabled) {
                        if (statusEl) { statusEl.textContent = '✅ Connected'; statusEl.classList.add('connected'); }
                        if (btn) { btn.textContent = `⚙️ Manage ${svcData.service_name}`; btn.classList.add('connected'); }
                    } else {
                        if (statusEl) { statusEl.textContent = 'Not Connected'; statusEl.classList.remove('connected'); }
                    }
                }

                // Telegram status managed in Channels tab

            } catch (error) {
                console.error('Error loading connected services:', error);
            }
        }

        function getServiceIcon(serviceType) {
            const icons = {
                'gmail': '📧',
                'calendar': '📅',
                'drive': '📁',
                'notion': '📝',
                'slack': '💬',
                'github': '🐙',
                'binance': '💰',
                'discord': '🎮',
                'telegram': '✈️',
                'spotify': '🎵',
                'todoist': '✅',
                'dropbox': '📦',
            };
            return icons[serviceType] || '🔌';
        }

        function formatTimeAgo(timestamp) {
            if (!timestamp) return 'recently';
            const date = new Date(timestamp);
            const now = new Date();
            const diff = now - date;
            const minutes = Math.floor(diff / 60000);
            const hours = Math.floor(minutes / 60);
            const days = Math.floor(hours / 24);

            if (days > 0) return `${days} day${days > 1 ? 's' : ''} ago`;
            if (hours > 0) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
            if (minutes > 0) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
            return 'just now';
        }

        async function connectGmail() {
            try {
                // Start OAuth flow
                const response = await fetch('/api/oauth/google/start/gmail');
                const data = await response.json();

                if (data.error) {
                    alert(`Error: ${data.error}\n${data.message || ''}`);
                    return;
                }

                // Open OAuth window
                const width = 600;
                const height = 700;
                const left = (screen.width - width) / 2;
                const top = (screen.height - height) / 2;

                const authWindow = window.open(
                    data.authorization_url,
                    'Google OAuth',
                    `width=${width},height=${height},left=${left},top=${top}`
                );

                // Poll for window closure
                const checkWindow = setInterval(() => {
                    try {
                        if (authWindow.closed) {
                            clearInterval(checkWindow);
                            // Reload connected services
                            setTimeout(() => loadConnectedServices(), 1000);
                        }
                    } catch (e) {
                        // Ignore COOP errors from cross-origin popup
                    }
                }, 500);

            } catch (error) {
                console.error('Error connecting Gmail:', error);
                alert(`Failed to connect Gmail: ${error.message}`);
            }
        }

        async function connectService(service) {
            /**
             * Generic function to connect Google services (calendar, drive)
             * @param {string} service - 'calendar' or 'drive'
             */
            try {
                // Start OAuth flow
                const response = await fetch(`/api/oauth/google/start/${service}`);
                const data = await response.json();

                if (data.error) {
                    alert(`Error: ${data.error}\n${data.message || ''}`);
                    return;
                }

                // Open OAuth window
                const width = 600;
                const height = 700;
                const left = (screen.width - width) / 2;
                const top = (screen.height - height) / 2;

                const authWindow = window.open(
                    data.authorization_url,
                    `Google OAuth - ${service}`,
                    `width=${width},height=${height},left=${left},top=${top}`
                );

                // Poll for window closure
                const checkWindow = setInterval(() => {
                    try {
                        if (authWindow.closed) {
                            clearInterval(checkWindow);
                            // Reload connected services
                            setTimeout(() => loadConnectedServices(), 1000);
                        }
                    } catch (e) {
                        // Ignore COOP errors from cross-origin popup
                    }
                }, 500);

            } catch (error) {
                console.error(`Error connecting ${service}:`, error);
                alert(`Failed to connect ${service}: ${error.message}`);
            }
        }

        async function disconnectService(serviceId, serviceName) {
            if (!confirm(`Disconnect ${serviceName}?\n\nYour agent will no longer have access to this service.`)) {
                return;
            }

            try {
                const response = await fetch(`/api/superpowers/${serviceId}/disconnect`, {
                    method: 'POST'
                });

                const data = await response.json();

                if (data.success) {
                    alert(`✅ ${serviceName} disconnected`);
                    loadConnectedServices();
                } else {
                    alert(`❌ Failed to disconnect: ${data.error}`);
                }

            } catch (error) {
                console.error('Error disconnecting service:', error);
                alert(`Failed to disconnect: ${error.message}`);
            }
        }

        // ========================================
        // GENERIC OAUTH + TELEGRAM FUNCTIONS
        // ========================================

        async function connectOAuthService(provider) {
            try {
                const response = await fetch(`/api/oauth/${provider}/start`);
                const data = await response.json();

                if (data.error) {
                    alert(`Error: ${data.error}\n${data.message || ''}`);
                    return;
                }

                const width = 600;
                const height = 700;
                const left = (screen.width - width) / 2;
                const top = (screen.height - height) / 2;

                const authWindow = window.open(
                    data.authorization_url,
                    `OAuth - ${provider}`,
                    `width=${width},height=${height},left=${left},top=${top}`
                );

                const checkWindow = setInterval(() => {
                    try {
                        if (authWindow.closed) {
                            clearInterval(checkWindow);
                            setTimeout(() => loadConnectedServices(), 1000);
                        }
                    } catch (e) {
                        // Ignore COOP errors from cross-origin popup
                    }
                }, 500);

            } catch (error) {
                console.error(`Error connecting ${provider}:`, error);
                alert(`Failed to connect ${provider}: ${error.message}`);
            }
        }

        // Telegram connect moved to Channels tab via connectChannel('telegram')

        // ========================================
        // BINANCE FUNCTIONS
        // ========================================

        async function connectBinance() {
            const apiKey = document.getElementById('binance-api-key').value.trim();
            const apiSecret = document.getElementById('binance-api-secret').value.trim();
            const testnet = document.getElementById('binance-testnet').checked;

            if (!apiKey || !apiSecret) {
                alert('Please enter both API key and API secret.');
                return;
            }

            const btn = document.getElementById('binance-connect-btn');
            const originalText = btn.textContent;
            btn.disabled = true;
            btn.textContent = '⏳ Connecting...';

            try {
                const response = await fetch('/api/binance/connect', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        api_key: apiKey,
                        api_secret: apiSecret,
                        testnet: testnet
                    })
                });

                const data = await response.json();

                if (data.success) {
                    alert(`Binance ${testnet ? 'testnet ' : ''}connected! ${data.total_assets} assets found.`);
                    // Clear form
                    document.getElementById('binance-api-key').value = '';
                    document.getElementById('binance-api-secret').value = '';
                    loadConnectedServices();
                } else {
                    alert(`Failed to connect: ${data.error}`);
                }
            } catch (error) {
                console.error('Error connecting Binance:', error);
                alert(`Failed to connect Binance: ${error.message}`);
            } finally {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        }

        async function toggleBinanceTrading(enabled) {
            const endpoint = enabled ? '/api/binance/enable-trading' : '/api/binance/disable-trading';
            const tradingStatus = document.getElementById('binance-trading-status');
            const toggleKnob = document.getElementById('binance-toggle-knob');
            const toggleBg = toggleKnob ? toggleKnob.parentElement.previousElementSibling.nextElementSibling : null;

            try {
                const response = await fetch(endpoint, { method: 'POST' });
                const data = await response.json();

                if (data.success) {
                    if (tradingStatus) tradingStatus.textContent = enabled ? 'Trading enabled (approval required)' : 'Read-only mode';
                    if (toggleKnob) toggleKnob.style.transform = enabled ? 'translateX(20px)' : 'translateX(0)';
                    if (toggleBg) toggleBg.style.background = enabled ? '#10b981' : 'var(--border)';
                } else {
                    // Revert toggle
                    const toggle = document.getElementById('binance-trading-toggle');
                    if (toggle) toggle.checked = !enabled;
                    alert(`Error: ${data.error}`);
                }
            } catch (error) {
                const toggle = document.getElementById('binance-trading-toggle');
                if (toggle) toggle.checked = !enabled;
                alert(`Failed to update trading: ${error.message}`);
            }
        }

        async function loadBinancePortfolio() {
            const container = document.getElementById('binance-portfolio-view');
            container.style.display = 'block';
            container.innerHTML = '<div style="text-align: center; padding: 16px; color: var(--text-tertiary);">Loading portfolio...</div>';

            try {
                const response = await fetch('/api/binance/portfolio');
                const data = await response.json();

                if (!data.success) {
                    container.innerHTML = `<div style="padding: 12px; color: #ef4444; font-size: 13px;">Error: ${data.error}</div>`;
                    return;
                }

                const holdings = data.portfolio.holdings || [];
                if (holdings.length === 0) {
                    container.innerHTML = '<div style="padding: 12px; color: var(--text-tertiary); font-size: 13px;">No holdings found.</div>';
                    return;
                }

                container.innerHTML = `
                    <div style="margin-top: 12px; border: 1px solid var(--border); border-radius: 6px; overflow: hidden;">
                        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; padding: 8px 12px; background: rgba(0,0,0,0.3); font-size: 11px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase;">
                            <div>Asset</div>
                            <div style="text-align: right;">Available</div>
                            <div style="text-align: right;">Total</div>
                        </div>
                        ${holdings.map(h => `
                            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; padding: 8px 12px; border-top: 1px solid var(--border); font-size: 13px;">
                                <div style="font-weight: 600; color: var(--text-primary);">${h.currency}</div>
                                <div style="text-align: right; color: var(--text-secondary);">${parseFloat(h.free).toFixed(6)}</div>
                                <div style="text-align: right; color: var(--text-primary);">${parseFloat(h.total).toFixed(6)}</div>
                            </div>
                        `).join('')}
                    </div>
                `;
            } catch (error) {
                container.innerHTML = `<div style="padding: 12px; color: #ef4444; font-size: 13px;">Error: ${error.message}</div>`;
            }
        }

        async function loadBinancePrices() {
            const container = document.getElementById('binance-prices-view');
            container.style.display = 'block';
            container.innerHTML = '<div style="text-align: center; padding: 16px; color: var(--text-tertiary);">Loading prices...</div>';

            try {
                const response = await fetch('/api/binance/prices');
                const data = await response.json();

                if (!data.success) {
                    container.innerHTML = `<div style="padding: 12px; color: #ef4444; font-size: 13px;">Error: ${data.error}</div>`;
                    return;
                }

                const tickers = data.tickers || [];
                if (tickers.length === 0) {
                    container.innerHTML = '<div style="padding: 12px; color: var(--text-tertiary); font-size: 13px;">No price data available.</div>';
                    return;
                }

                container.innerHTML = `
                    <div style="margin-top: 12px; border: 1px solid var(--border); border-radius: 6px; overflow: hidden;">
                        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; padding: 8px 12px; background: rgba(0,0,0,0.3); font-size: 11px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase;">
                            <div>Pair</div>
                            <div style="text-align: right;">Price</div>
                            <div style="text-align: right;">24h</div>
                        </div>
                        ${tickers.map(t => {
                            const changeColor = t.change_percent >= 0 ? '#10b981' : '#ef4444';
                            const changeSign = t.change_percent >= 0 ? '+' : '';
                            return `
                                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; padding: 8px 12px; border-top: 1px solid var(--border); font-size: 13px;">
                                    <div style="font-weight: 600; color: var(--text-primary);">${t.symbol}</div>
                                    <div style="text-align: right; color: var(--text-primary);">$${parseFloat(t.last).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
                                    <div style="text-align: right; color: ${changeColor}; font-weight: 600;">${changeSign}${parseFloat(t.change_percent).toFixed(2)}%</div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                `;
            } catch (error) {
                container.innerHTML = `<div style="padding: 12px; color: #ef4444; font-size: 13px;">Error: ${error.message}</div>`;
            }
        }

        // Handle OAuth callback redirect with tab parameter
        const urlParams = new URLSearchParams(window.location.search);
        const tabParam = urlParams.get('tab');
        if (tabParam === 'connect') {
            setTimeout(() => switchTab('connect'), 500);
        }

        // ============================================
        // AI Agent Actions Functions
        // ============================================

        async function loadPendingActions() {
            try {
                const response = await fetch('/api/agent-actions/pending');
                const data = await response.json();

                const container = document.getElementById('pending-actions-container');
                const badge = document.getElementById('pending-actions-badge');

                if (!data.success || data.count === 0) {
                    container.innerHTML = `
                        <div style="text-align: center; padding: 40px; color: rgba(255, 255, 255, 0.5);">
                            <div style="font-size: 48px; margin-bottom: 12px;">📬</div>
                            <p>No pending actions</p>
                        </div>
                    `;
                    badge.style.display = 'none';
                    return;
                }

                // Update badge
                badge.textContent = data.count;
                badge.style.display = 'inline-block';

                // Render actions
                container.innerHTML = data.actions.map(action => `
                    <div class="action-card" style="background: rgba(59, 130, 246, 0.05); border: 1px solid rgba(59, 130, 246, 0.2); border-radius: 8px; padding: 16px; margin-bottom: 12px;">
                        <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                            <div>
                                <div style="font-weight: 600; color: var(--text-primary); margin-bottom: 4px;">
                                    ${action.action_type === 'send_email' ? '📧 Send Email' : action.action_type === 'place_order' ? '💰 Trade Order' : action.action_type}
                                </div>
                                <div style="font-size: 12px; color: rgba(255, 255, 255, 0.5);">
                                    ${action.agent ? action.agent.avatar_emoji + ' ' + action.agent.name : 'AI Agent'} • ${formatTimeAgo(action.created_at)}
                                </div>
                            </div>
                            <div style="display: flex; gap: 8px;">
                                <button class="btn btn-primary" onclick="approveAction(${action.id})" style="padding: 6px 12px; font-size: 13px;">
                                    ✅ Approve
                                </button>
                                <button class="btn btn-secondary" onclick="rejectAction(${action.id})" style="padding: 6px 12px; font-size: 13px;">
                                    ❌ Reject
                                </button>
                            </div>
                        </div>

                        ${action.ai_reasoning ? `
                            <div style="padding: 12px; background: rgba(0, 0, 0, 0.2); border-radius: 6px; margin-bottom: 12px;">
                                <div style="font-size: 12px; color: rgba(255, 255, 255, 0.5); margin-bottom: 4px;">AI Reasoning:</div>
                                <div style="color: rgba(255, 255, 255, 0.85); font-size: 14px;">${action.ai_reasoning}</div>
                            </div>
                        ` : ''}

                        <div style="padding: 12px; background: rgba(0, 0, 0, 0.2); border-radius: 6px;">
                            <div style="font-size: 12px; color: rgba(255, 255, 255, 0.5); margin-bottom: 8px;">Action Details:</div>
                            ${action.action_type === 'send_email' ? `
                                <div style="color: rgba(255, 255, 255, 0.85); font-size: 13px;">
                                    <div><strong>To:</strong> ${action.action_data.to}</div>
                                    <div><strong>Subject:</strong> ${action.action_data.subject}</div>
                                    <div style="margin-top: 8px; white-space: pre-wrap;">${action.action_data.body}</div>
                                </div>
                            ` : action.action_type === 'place_order' ? `
                                <div style="color: rgba(255, 255, 255, 0.85); font-size: 13px;">
                                    <div><strong>Symbol:</strong> ${action.action_data.symbol}</div>
                                    <div><strong>Side:</strong> <span style="color: ${action.action_data.side === 'buy' ? '#10b981' : '#ef4444'}; font-weight: 600;">${action.action_data.side.toUpperCase()}</span></div>
                                    <div><strong>Type:</strong> ${action.action_data.order_type}</div>
                                    <div><strong>Amount:</strong> ${action.action_data.amount}</div>
                                    ${action.action_data.price ? `<div><strong>Price:</strong> $${action.action_data.price}</div>` : ''}
                                </div>
                            ` : JSON.stringify(action.action_data, null, 2)}
                        </div>
                    </div>
                `).join('');

            } catch (error) {
                console.error('Error loading pending actions:', error);
            }
        }

        async function approveAction(actionId) {
            if (!confirm('Approve this action? It will be executed immediately.')) {
                return;
            }

            try {
                const response = await fetch(`/api/agent-actions/${actionId}/approve`, {
                    method: 'POST'
                });
                const data = await response.json();

                if (data.success) {
                    alert('✅ Action approved and executed!');
                    loadPendingActions();
                } else {
                    alert(`Error: ${data.error}`);
                }
            } catch (error) {
                console.error('Error approving action:', error);
                alert('Failed to approve action');
            }
        }

        async function rejectAction(actionId) {
            try {
                const response = await fetch(`/api/agent-actions/${actionId}/reject`, {
                    method: 'POST'
                });
                const data = await response.json();

                if (data.success) {
                    alert('❌ Action rejected');
                    loadPendingActions();
                } else {
                    alert(`Error: ${data.error}`);
                }
            } catch (error) {
                console.error('Error rejecting action:', error);
                alert('Failed to reject action');
            }
        }

        async function analyzeInbox() {
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '⏳ Analyzing...';

            try {
                const response = await fetch('/api/agent-actions/analyze-inbox', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });

                const data = await response.json();

                if (data.success) {
                    const resultsDiv = document.getElementById('analysis-results');
                    const contentDiv = document.getElementById('analysis-content');

                    contentDiv.innerHTML = `
                        <div style="color: rgba(255, 255, 255, 0.95); margin-bottom: 16px; line-height: 1.6;">
                            ${data.analysis}
                        </div>

                        ${data.urgent_items && data.urgent_items.length > 0 ? `
                            <div style="margin-bottom: 16px;">
                                <div style="font-weight: 600; color: #FFA500; margin-bottom: 8px;">⚠️ Urgent Items:</div>
                                <ul style="margin: 0; padding-left: 20px; color: rgba(255, 255, 255, 0.85); line-height: 1.6;">
                                    ${data.urgent_items.map(item => {
                                        if (typeof item === 'string') return `<li>${item}</li>`;
                                        // Parse object and show in readable format
                                        const subject = item.subject ? `<strong>${item.subject}</strong>` : '';
                                        const reason = item.reason || item.description || '';
                                        return `<li>${subject}${subject && reason ? ': ' : ''}${reason}</li>`;
                                    }).join('')}
                                </ul>
                            </div>
                        ` : ''}

                        ${data.suggested_actions && data.suggested_actions.length > 0 ? `
                            <div>
                                <div style="font-weight: 600; color: #4ADE80; margin-bottom: 8px;">💡 Suggested Actions:</div>
                                <ul style="margin: 0; padding-left: 20px; color: rgba(255, 255, 255, 0.85); line-height: 1.6;">
                                    ${data.suggested_actions.map(action => {
                                        if (typeof action === 'string') return `<li>${action}</li>`;
                                        // Parse object and show action text
                                        return `<li>${action.action || action.description || JSON.stringify(action)}</li>`;
                                    }).join('')}
                                </ul>
                            </div>
                        ` : ''}

                        <div style="margin-top: 12px; font-size: 12px; color: rgba(255, 255, 255, 0.5);">
                            Analyzed ${data.emails_analyzed} recent emails
                        </div>
                    `;

                    resultsDiv.style.display = 'block';
                } else {
                    alert(`Error: ${data.error}`);
                }
            } catch (error) {
                console.error('Error analyzing inbox:', error);
                alert('Failed to analyze inbox');
            } finally {
                btn.disabled = false;
                btn.textContent = '📊 Analyze Inbox';
            }
        }

        async function testDraftReply() {
            // For demo, we'll use the first email from inbox
            // In production, user would select an email first
            alert('This feature requires selecting an email first. Coming soon!');
        }

        // Load pending actions when Actions tab is opened
        document.addEventListener('DOMContentLoaded', () => {
            // Add listener to Actions tab
            const actionsTab = document.querySelector('[data-tab="actions"]');
            if (actionsTab) {
                actionsTab.addEventListener('click', () => {
                    loadPendingActions();
                });
            }
        });


        // ============================================
        // AI WORKBENCH — Model Config
        // ============================================
        let mcProviders = [];
        let mcConfigs = {};

        async function initModelConfigTab() {
            // Load providers list
            if (mcProviders.length === 0) {
                try {
                    const resp = await fetch(`${API_BASE}/model-config/providers`);
                    const data = await resp.json();
                    mcProviders = data.providers || [];
                    populateMCProviderDropdown();
                } catch (e) { console.error('Failed to load providers:', e); }
            }
            // Load saved configs
            try {
                const resp = await fetch(`${API_BASE}/model-config`, { credentials: 'include' });
                const data = await resp.json();
                mcConfigs = {};
                (data.configs || []).forEach(c => { mcConfigs[c.feature_slot] = c; });
                updateModelConfigCards();
            } catch (e) { console.error('Failed to load model configs:', e); }
        }

        function populateMCProviderDropdown() {
            const sel = document.getElementById('mc-provider');
            if (!sel) return;
            sel.innerHTML = '<option value="">Select provider...</option>';
            mcProviders.forEach(p => {
                sel.innerHTML += `<option value="${p.id}">${p.name}</option>`;
            });
        }

        function updateModelConfigCards() {
            ['chatbot', 'web_browsing', 'utility', 'nautilus'].forEach(slot => {
                const el = document.getElementById(`mc-${slot}-status`);
                if (!el) return;
                const cfg = mcConfigs[slot];
                if (cfg) {
                    el.textContent = `${cfg.provider} / ${cfg.model}`;
                    el.classList.add('configured');
                } else {
                    el.textContent = 'Not configured';
                    el.classList.remove('configured');
                }
            });
        }

        function openModelConfigForm(slot) {
            document.getElementById('model-config-form').style.display = 'block';
            document.getElementById('mc-feature-slot').value = slot;
            const slotLabel = slot === 'nautilus' ? 'Nautilus AI' : slot.replace('_', ' ');
            document.getElementById('mc-form-title').textContent = `Configure Model — ${slotLabel}`;
            document.getElementById('mc-test-result').textContent = '';

            // Pre-fill if config exists
            const cfg = mcConfigs[slot];
            if (cfg) {
                document.getElementById('mc-provider').value = cfg.provider;
                onMCProviderChange();
                document.getElementById('mc-model').value = cfg.model;
                document.getElementById('mc-endpoint-url').value = cfg.endpoint_url || '';
                const extra = cfg.extra_config || {};
                document.getElementById('mc-temperature').value = extra.temperature || 0.7;
                document.getElementById('mc-temp-value').textContent = extra.temperature || 0.7;
                document.getElementById('mc-max-tokens').value = extra.max_tokens || 1024;
                // Don't pre-fill API key for security — it's masked
                document.getElementById('mc-api-key').value = '';
                document.getElementById('mc-api-key').placeholder = cfg.has_api_key ? '(saved — enter new to change)' : 'sk-...';
            } else {
                document.getElementById('mc-provider').value = '';
                document.getElementById('mc-model').value = '';
                document.getElementById('mc-api-key').value = '';
                document.getElementById('mc-api-key').placeholder = 'sk-...';
                document.getElementById('mc-endpoint-url').value = '';
                document.getElementById('mc-temperature').value = 0.7;
                document.getElementById('mc-temp-value').textContent = '0.7';
                document.getElementById('mc-max-tokens').value = 1024;
            }
        }

        function onMCProviderChange() {
            const provider = document.getElementById('mc-provider').value;
            const pInfo = mcProviders.find(p => p.id === provider);

            // Show/hide API key
            const keyGroup = document.getElementById('mc-api-key-group');
            keyGroup.style.display = (pInfo && !pInfo.needs_api_key) ? 'none' : 'block';

            // Show/hide endpoint URL
            const urlGroup = document.getElementById('mc-endpoint-group');
            urlGroup.style.display = (pInfo && pInfo.needs_endpoint_url) ? 'block' : 'none';
            if (pInfo && pInfo.default_endpoint) {
                document.getElementById('mc-endpoint-url').placeholder = pInfo.default_endpoint;
            }

            // Update model suggestions
            const suggestions = document.getElementById('mc-model-suggestions');
            suggestions.innerHTML = '';
            if (pInfo) {
                pInfo.models.forEach(m => {
                    suggestions.innerHTML += `<option value="${m}">`;
                });
            }
        }

        async function saveModelConfig() {
            const slot = document.getElementById('mc-feature-slot').value;
            const payload = {
                provider: document.getElementById('mc-provider').value,
                model: document.getElementById('mc-model').value,
                api_key: document.getElementById('mc-api-key').value,
                endpoint_url: document.getElementById('mc-endpoint-url').value,
                extra_config: {
                    temperature: parseFloat(document.getElementById('mc-temperature').value),
                    max_tokens: parseInt(document.getElementById('mc-max-tokens').value),
                },
            };

            try {
                const resp = await fetch(`${API_BASE}/model-config/${slot}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify(payload),
                });
                const data = await resp.json();
                if (data.success) {
                    mcConfigs[slot] = data.config;
                    updateModelConfigCards();
                    if (slot === 'nautilus') updateNautilusModelBanner();
                    showAlert('model-config', 'success', 'Model configuration saved!');
                    document.getElementById('model-config-form').style.display = 'none';
                } else {
                    showAlert('model-config', 'error', data.error || 'Failed to save');
                }
            } catch (e) {
                showAlert('model-config', 'error', 'Network error: ' + e.message);
            }
        }

        async function testModelConfig() {
            const slot = document.getElementById('mc-feature-slot').value;
            const payload = {
                provider: document.getElementById('mc-provider').value,
                model: document.getElementById('mc-model').value,
                api_key: document.getElementById('mc-api-key').value,
                endpoint_url: document.getElementById('mc-endpoint-url').value,
            };
            const resultEl = document.getElementById('mc-test-result');
            resultEl.textContent = 'Testing...';
            resultEl.style.color = 'var(--text-tertiary)';

            try {
                const resp = await fetch(`${API_BASE}/model-config/${slot}/test`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify(payload),
                });
                const data = await resp.json();
                resultEl.textContent = data.message;
                resultEl.style.color = data.success ? 'var(--success)' : 'var(--error)';
            } catch (e) {
                resultEl.textContent = 'Network error';
                resultEl.style.color = 'var(--error)';
            }
        }


        // ============================================
        // AI WORKBENCH — External Agent Helpers (unified)
        // ============================================
        let nautilusClient = null;

        async function testAgent(agentId) {
            try {
                const resp = await fetch(`${API_BASE}/agents/${agentId}/test`, {
                    method: 'POST',
                    credentials: 'include',
                });
                const data = await resp.json();
                showAlert('agents', data.success ? 'success' : 'error', data.message);
            } catch (e) {
                showAlert('agents', 'error', 'Network error');
            }
        }

        async function seedNautilus() {
            try {
                const resp = await fetch(`${API_BASE}/agents/seed-nautilus`, {
                    method: 'POST',
                    credentials: 'include',
                });
                const data = await resp.json();
                if (data.success) {
                    showAlert('agents', 'success', data.already_exists ? 'Nautilus config reset.' : 'Nautilus seeded as featured agent!');
                    await loadAgents();
                }
            } catch (e) {
                showAlert('agents', 'error', 'Network error');
            }
        }

        function onNautilusAuthModeChange() {
            const mode = document.getElementById('nautilus-auth-mode').value;
            const field = document.getElementById('nautilus-auth-field');
            const label = document.getElementById('nautilus-auth-label');
            if (mode === 'none') {
                field.style.display = 'none';
            } else {
                field.style.display = 'block';
                label.textContent = mode === 'pairing' ? 'Pairing Token' : 'Password';
            }
        }

        async function connectNautilus() {
            const wsUrl = document.getElementById('nautilus-ws-url').value;
            const authMode = document.getElementById('nautilus-auth-mode').value;
            const authValue = document.getElementById('nautilus-auth-value').value;
            const statusEl = document.getElementById('nautilus-connect-status');
            const dot = document.getElementById('nautilus-status-dot');

            statusEl.textContent = 'Connecting...';
            statusEl.style.color = 'var(--text-tertiary)';

            if (nautilusClient) {
                nautilusClient.disconnect();
            }

            nautilusClient = new NautilusClient();

            nautilusClient.onConnect = () => {
                statusEl.textContent = 'Connected';
                statusEl.style.color = 'var(--success)';
                dot.className = 'status-dot status-connected';
                document.getElementById('nautilus-connect-btn').style.display = 'none';
                document.getElementById('nautilus-disconnect-btn').style.display = 'inline-flex';
                // Update agent status in DB
                const nautAgent = currentAgents.find(a => a.name === 'Nautilus');
                if (nautAgent) {
                    fetch(`${API_BASE}/agents/${nautAgent.id}/update-status`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify({ connected: true }),
                    }).catch(() => {});
                }
                // Populate Nautilus option in chat agent selector
                updateChatAgentOptions();
            };

            nautilusClient.onDisconnect = (info) => {
                statusEl.textContent = `Disconnected${info.reason ? ': ' + info.reason : ''}`;
                statusEl.style.color = 'var(--error)';
                dot.className = 'status-dot status-disconnected';
                document.getElementById('nautilus-connect-btn').style.display = 'inline-flex';
                document.getElementById('nautilus-disconnect-btn').style.display = 'none';
            };

            nautilusClient.onError = (err) => {
                statusEl.textContent = `Error: ${err.message}`;
                statusEl.style.color = 'var(--error)';
            };

            nautilusClient.onAuthResult = (result) => {
                if (!result.success) {
                    statusEl.textContent = `Auth failed: ${result.message || 'unknown'}`;
                    statusEl.style.color = 'var(--error)';
                }
            };

            const authConfig = { mode: authMode };
            if (authMode === 'pairing') authConfig.token = authValue;
            if (authMode === 'password') authConfig.password = authValue;

            try {
                await nautilusClient.connect(wsUrl, authConfig);
            } catch (e) {
                statusEl.textContent = 'Failed to connect: ' + (e.message || 'WebSocket error');
                statusEl.style.color = 'var(--error)';
            }
        }

        function disconnectNautilus() {
            if (nautilusClient) {
                nautilusClient.disconnect();
                nautilusClient = null;
            }
        }

        function updateChatAgentOptions() {
            const sel = document.getElementById('chat-agent-mode');
            if (!sel) return;
            // Keep existing options, add external agents from unified list
            const existingValues = Array.from(sel.options).map(o => o.value);
            currentAgents.filter(a => !a.is_featured && (a.agent_type === 'http_api' || a.agent_type === 'websocket')).forEach(a => {
                if (!existingValues.includes('ext_' + a.id)) {
                    const opt = document.createElement('option');
                    opt.value = 'ext_' + a.id;
                    opt.textContent = a.name;
                    sel.appendChild(opt);
                }
            });
        }


        // ============================================
        // NAUTILUS DIRECT MODE
        // ============================================
        let nautilusDirectConversations = [];
        let nautilusActiveConversationId = null;

        const NAUTILUS_SYSTEM_PROMPT = `You are Nautilus, a helpful and knowledgeable AI assistant. You are friendly, concise, and accurate. You help users with questions, writing, analysis, coding, and creative tasks. Always be clear and direct in your responses.`;

        function switchNautilusMode(mode) {
            document.querySelectorAll('.nautilus-mode-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.nautilus-mode-panel').forEach(p => p.classList.remove('active'));

            const tab = document.querySelector(`.nautilus-mode-tab[data-mode="${mode}"]`);
            if (tab) tab.classList.add('active');
            const panel = document.getElementById(`nautilus-${mode}-panel`);
            if (panel) panel.classList.add('active');

            if (mode === 'gateway') {
                setupGatewayChatHandlers();
            }
        }

        function updateNautilusModelBanner() {
            const cfg = mcConfigs['nautilus'];
            const statusEl = document.getElementById('nautilus-model-status');
            if (!statusEl) return;
            const configBtn = document.getElementById('nautilus-configure-btn');
            const indicatorEl = document.getElementById('nautilus-model-indicator');

            if (cfg) {
                statusEl.textContent = `${cfg.provider} / ${cfg.model}`;
                statusEl.className = 'nautilus-model-banner-value configured';
                if (configBtn) configBtn.textContent = 'Change Model';
                if (indicatorEl) {
                    indicatorEl.textContent = `${cfg.provider}/${cfg.model}`;
                    indicatorEl.style.display = 'inline';
                }
            } else {
                statusEl.textContent = 'Not configured';
                statusEl.className = 'nautilus-model-banner-value not-configured';
                if (configBtn) configBtn.textContent = 'Configure Model';
                if (indicatorEl) indicatorEl.style.display = 'none';
            }
        }

        async function loadNautilusConversations() {
            try {
                const resp = await fetch(`${API_BASE}/chat/conversations?feature=nautilus`, { credentials: 'include' });
                const data = await resp.json();
                nautilusDirectConversations = data.conversations || [];
                renderNautilusConversationList();
            } catch (e) { console.error('Failed to load nautilus conversations:', e); }
        }

        function renderNautilusConversationList() {
            const list = document.getElementById('nautilus-conversation-list');
            if (!list) return;
            if (nautilusDirectConversations.length === 0) {
                list.innerHTML = '<p style="padding:12px; color:var(--text-tertiary); font-size:13px;">No conversations yet.</p>';
                return;
            }
            list.innerHTML = nautilusDirectConversations.map(c => `
                <div class="chat-conversation-item ${c.conversation_id === nautilusActiveConversationId ? 'active' : ''}"
                     onclick="selectNautilusConversation('${c.conversation_id}')">
                    <span class="conv-title">${escapeHtml(c.title)}</span>
                    <span class="conv-delete" onclick="event.stopPropagation(); deleteNautilusConversation('${c.conversation_id}')">x</span>
                </div>
            `).join('');
        }

        async function createNautilusConversation() {
            try {
                const resp = await fetch(`${API_BASE}/chat/conversations`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({
                        title: 'New Chat',
                        feature: 'nautilus',
                        agent_type: 'direct_llm',
                    }),
                });
                const data = await resp.json();
                if (data.success) {
                    nautilusDirectConversations.unshift(data.conversation);
                    selectNautilusConversation(data.conversation.conversation_id);
                    renderNautilusConversationList();
                }
            } catch (e) {
                showAlert('agents', 'error', 'Failed to create conversation');
            }
        }

        async function selectNautilusConversation(convId) {
            nautilusActiveConversationId = convId;
            renderNautilusConversationList();

            const conv = nautilusDirectConversations.find(c => c.conversation_id === convId);
            const titleEl = document.getElementById('nautilus-chat-title');
            if (titleEl) titleEl.textContent = conv ? conv.title : 'Chat';

            try {
                const resp = await fetch(`${API_BASE}/chat/conversations/${convId}/messages`, { credentials: 'include' });
                const data = await resp.json();
                renderNautilusMessages(data.messages || []);
            } catch (e) {
                console.error('Failed to load nautilus messages:', e);
            }
        }

        function renderNautilusMessages(messages) {
            const container = document.getElementById('nautilus-chat-messages');
            if (!container) return;
            if (messages.length === 0) {
                container.innerHTML = `
                    <div class="chat-empty-state">
                        <span style="font-size:48px;">🐙</span>
                        <p>Send a message to start chatting with Nautilus</p>
                    </div>`;
                return;
            }
            container.innerHTML = messages.map(m => {
                const rendered = m.role === 'user' ? escapeHtml(m.content) : formatMessage(m.content);
                return `<div class="chat-bubble ${m.role}">${rendered}</div>`;
            }).join('');
            container.scrollTop = container.scrollHeight;
        }

        function appendNautilusBubble(role, content) {
            const container = document.getElementById('nautilus-chat-messages');
            if (!container) return;
            const empty = container.querySelector('.chat-empty-state');
            if (empty) empty.remove();
            const _rendered = role === 'user' ? escapeHtml(content) : formatMessage(content);
                container.innerHTML += `<div class="chat-bubble ${role}">${_rendered}</div>`;
            container.scrollTop = container.scrollHeight;
        }

        function showNautilusThinking() {
            const container = document.getElementById('nautilus-chat-messages');
            if (!container) return;
            const existing = container.querySelector('.thinking-indicator');
            if (existing) existing.remove();
            container.innerHTML += `
                <div class="thinking-indicator">
                    <div class="dots"><span></span><span></span><span></span></div>
                    Nautilus is thinking...
                </div>`;
            container.scrollTop = container.scrollHeight;
        }

        function hideNautilusThinking() {
            const container = document.getElementById('nautilus-chat-messages');
            if (!container) return;
            const el = container.querySelector('.thinking-indicator');
            if (el) el.remove();
        }

        async function sendNautilusDirectMessage() {
            const input = document.getElementById('nautilus-chat-input');
            const text = (input.value || '').trim();
            if (!text || !nautilusActiveConversationId) return;
            input.value = '';

            appendNautilusBubble('user', text);
            showNautilusThinking();

            try {
                const resp = await fetch(`${API_BASE}/chat/send`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({
                        conversation_id: nautilusActiveConversationId,
                        message: text,
                        feature_slot: 'nautilus',
                        system_prompt: NAUTILUS_SYSTEM_PROMPT,
                    }),
                });
                const data = await resp.json();
                hideNautilusThinking();
                if (data.success) {
                    appendNautilusBubble('assistant', data.message.content);
                } else {
                    appendNautilusBubble('system', 'Error: ' + (data.error || 'Unknown error'));
                }
            } catch (e) {
                hideNautilusThinking();
                appendNautilusBubble('system', 'Network error: ' + e.message);
            }
            loadNautilusConversations();
        }

        async function deleteNautilusConversation(convId) {
            if (!confirm('Delete this conversation?')) return;
            try {
                await fetch(`${API_BASE}/chat/conversations/${convId}`, { method: 'DELETE', credentials: 'include' });
                nautilusDirectConversations = nautilusDirectConversations.filter(c => c.conversation_id !== convId);
                if (nautilusActiveConversationId === convId) {
                    nautilusActiveConversationId = null;
                    const container = document.getElementById('nautilus-chat-messages');
                    if (container) {
                        container.innerHTML = `
                            <div class="chat-empty-state">
                                <span style="font-size:48px;">🐙</span>
                                <p>Select or create a conversation</p>
                            </div>`;
                    }
                    const titleEl = document.getElementById('nautilus-chat-title');
                    if (titleEl) titleEl.textContent = 'Select or create a conversation';
                }
                renderNautilusConversationList();
            } catch (e) { console.error(e); }
        }

        // Gateway Mode chat functions
        function sendNautilusGatewayMessage() {
            const input = document.getElementById('gateway-chat-input');
            const text = (input.value || '').trim();
            if (!text) return;
            input.value = '';

            if (!nautilusClient || !nautilusClient.connected) {
                appendGatewayBubble('system', 'Gateway is not connected. Connect above first.');
                return;
            }

            appendGatewayBubble('user', text);
            nautilusClient.sendMessage(nautilusClient.sessionId, text);

            // Show thinking
            const container = document.getElementById('gateway-chat-messages');
            if (container) {
                const existing = container.querySelector('.thinking-indicator');
                if (existing) existing.remove();
                container.innerHTML += `
                    <div class="thinking-indicator">
                        <div class="dots"><span></span><span></span><span></span></div>
                        Gateway is thinking...
                    </div>`;
                container.scrollTop = container.scrollHeight;
            }
        }

        function appendGatewayBubble(role, content, metadata) {
            const container = document.getElementById('gateway-chat-messages');
            if (!container) return;
            const empty = container.querySelector('.chat-empty-state');
            if (empty) empty.remove();

            if (metadata && metadata.tool_name) {
                container.innerHTML += renderToolCard({ content, metadata });
            } else {
                const _rendered = role === 'user' ? escapeHtml(content) : formatMessage(content);
                container.innerHTML += `<div class="chat-bubble ${role}">${_rendered}</div>`;
            }
            container.scrollTop = container.scrollHeight;
        }

        function setupGatewayChatHandlers() {
            if (!nautilusClient) return;

            nautilusClient.onMessage = (msg) => {
                const container = document.getElementById('gateway-chat-messages');
                if (container) {
                    const thinking = container.querySelector('.thinking-indicator');
                    if (thinking) thinking.remove();
                }
                appendGatewayBubble(msg.role || 'assistant', msg.content);
            };

            nautilusClient.onThinking = () => {
                const container = document.getElementById('gateway-chat-messages');
                if (container) {
                    const existing = container.querySelector('.thinking-indicator');
                    if (existing) existing.remove();
                    container.innerHTML += `
                        <div class="thinking-indicator">
                            <div class="dots"><span></span><span></span><span></span></div>
                            Gateway is thinking...
                        </div>`;
                    container.scrollTop = container.scrollHeight;
                }
            };

            nautilusClient.onToolUse = (tool) => {
                const container = document.getElementById('gateway-chat-messages');
                if (container) {
                    const thinking = container.querySelector('.thinking-indicator');
                    if (thinking) thinking.remove();
                }
                const content = tool.output ? JSON.stringify(tool.output) : 'Running...';
                appendGatewayBubble('tool', content, { tool_name: tool.tool, tool_input: tool.input });
                if (tool.needsApproval) {
                    if (confirm(`Nautilus wants to use tool "${tool.tool}". Allow?`)) {
                        nautilusClient.approveToolUse(tool.requestId);
                    } else {
                        nautilusClient.denyToolUse(tool.requestId);
                    }
                }
            };

            nautilusClient.onError = (err) => {
                const container = document.getElementById('gateway-chat-messages');
                if (container) {
                    const thinking = container.querySelector('.thinking-indicator');
                    if (thinking) thinking.remove();
                }
                appendGatewayBubble('system', 'Error: ' + err.message);
            };

            if (!nautilusClient.sessionId) {
                nautilusClient.createSession({});
            }
        }


        // ============================================
        // AI WORKBENCH — Chat Bot
        // ============================================
        let chatConversations = [];
        let activeConversationId = null;
        let chatInitialized = false;

        async function initChatTab() {
            if (!chatInitialized) {
                chatInitialized = true;
                // Show model config indicator
                const cfg = mcConfigs['chatbot'];
                const indicator = document.getElementById('chat-model-indicator');
                if (cfg && indicator) {
                    indicator.textContent = `${cfg.provider}/${cfg.model}`;
                    indicator.style.display = 'inline';
                }
            }
            await loadConversations();
        }

        async function loadConversations() {
            try {
                const resp = await fetch(`${API_BASE}/chat/conversations`, { credentials: 'include' });
                const data = await resp.json();
                chatConversations = data.conversations || [];
                renderConversationList();
            } catch (e) { console.error('Failed to load conversations:', e); }
        }

        function renderConversationList() {
            const list = document.getElementById('chat-conversation-list');
            if (!list) return;
            if (chatConversations.length === 0) {
                list.innerHTML = '<p style="padding:12px; color:var(--text-tertiary); font-size:13px;">No conversations yet.</p>';
                return;
            }
            list.innerHTML = chatConversations.map(c => `
                <div class="chat-conversation-item ${c.conversation_id === activeConversationId ? 'active' : ''}"
                     onclick="selectConversation('${c.conversation_id}')">
                    <span class="conv-title">${c.title}</span>
                    <span class="conv-delete" onclick="event.stopPropagation(); deleteConversation('${c.conversation_id}')">x</span>
                </div>
            `).join('');
        }

        async function createNewConversation() {
            const mode = document.getElementById('chat-agent-mode').value;
            const agentType = mode === 'nautilus' ? 'nautilus' : (mode.startsWith('ext_') ? 'external' : 'direct_llm');

            try {
                const resp = await fetch(`${API_BASE}/chat/conversations`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({
                        title: 'New Chat',
                        feature: 'chatbot',
                        agent_type: agentType,
                    }),
                });
                const data = await resp.json();
                if (data.success) {
                    chatConversations.unshift(data.conversation);
                    selectConversation(data.conversation.conversation_id);
                    renderConversationList();
                }
            } catch (e) {
                showAlert('chatbot', 'error', 'Failed to create conversation');
            }
        }

        async function selectConversation(convId) {
            activeConversationId = convId;
            renderConversationList();

            const conv = chatConversations.find(c => c.conversation_id === convId);
            document.getElementById('chat-title').textContent = conv ? conv.title : 'Chat';

            // Load messages
            try {
                const resp = await fetch(`${API_BASE}/chat/conversations/${convId}/messages`, { credentials: 'include' });
                const data = await resp.json();
                renderChatMessages(data.messages || []);
            } catch (e) {
                console.error('Failed to load messages:', e);
            }

            // If Nautilus mode, set up WebSocket handlers for this conversation
            const mode = document.getElementById('chat-agent-mode').value;
            if (mode === 'nautilus' && nautilusClient && nautilusClient.connected) {
                setupNautilusChatHandlers();
            }
        }

        function renderChatMessages(messages) {
            const container = document.getElementById('chat-messages');
            if (!container) return;
            if (messages.length === 0) {
                container.innerHTML = `
                    <div class="chat-empty-state">
                        <span style="font-size:48px;">💬</span>
                        <p>Send a message to start chatting</p>
                    </div>`;
                return;
            }
            container.innerHTML = messages.map(m => {
                if (m.metadata && m.metadata.tool_name) {
                    return renderToolCard(m);
                }
                const rendered = m.role === 'user' ? escapeHtml(m.content) : formatMessage(m.content);
                return `<div class="chat-bubble ${m.role}">${rendered}</div>`;
            }).join('');
            container.scrollTop = container.scrollHeight;
        }

        function renderToolCard(msg) {
            const meta = msg.metadata || {};
            return `
                <div class="tool-card">
                    <div class="tool-card-header" onclick="this.nextElementSibling.classList.toggle('open')">
                        <span>🔧</span> ${meta.tool_name || 'Tool'} <span style="font-size:10px; color:var(--text-tertiary);">(click to expand)</span>
                    </div>
                    <div class="tool-card-body">
                        ${meta.tool_input ? `<div><strong>Input:</strong><pre>${escapeHtml(JSON.stringify(meta.tool_input, null, 2))}</pre></div>` : ''}
                        ${msg.content ? `<div><strong>Output:</strong><pre>${escapeHtml(msg.content)}</pre></div>` : ''}
                    </div>
                </div>`;
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function formatMessage(text) {
            // Escape HTML first for safety
            let html = escapeHtml(text);
            // Code blocks: ```lang\n...\n```
            html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
            html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
            // Inline code: `...`
            html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
            // Bold: **...**
            html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
            // Italic: *...*
            html = html.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
            // Markdown links: [text](url)
            html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
            // Bare URLs (not already inside an href)
            html = html.replace(/(?<!href="|">)(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
            // Line breaks (but not inside <pre>)
            html = html.replace(/\n/g, '<br>');
            // Clean up <br> inside <pre> blocks — restore newlines
            html = html.replace(/<pre><code>([\s\S]*?)<\/code><\/pre>/g, (match, code) => {
                return '<pre><code>' + code.replace(/<br>/g, '\n') + '</code></pre>';
            });
            return html;
        }

        function appendChatBubble(role, content, metadata) {
            const container = document.getElementById('chat-messages');
            if (!container) return;
            // Remove empty state if present
            const empty = container.querySelector('.chat-empty-state');
            if (empty) empty.remove();

            if (metadata && metadata.tool_name) {
                container.innerHTML += renderToolCard({ content, metadata });
            } else {
                const _rendered = role === 'user' ? escapeHtml(content) : formatMessage(content);
                container.innerHTML += `<div class="chat-bubble ${role}">${_rendered}</div>`;
            }
            container.scrollTop = container.scrollHeight;
        }

        function showThinkingIndicator() {
            const container = document.getElementById('chat-messages');
            if (!container) return;
            // Remove any existing
            const existing = container.querySelector('.thinking-indicator');
            if (existing) existing.remove();
            container.innerHTML += `
                <div class="thinking-indicator">
                    <div class="dots"><span></span><span></span><span></span></div>
                    Agent is thinking...
                </div>`;
            container.scrollTop = container.scrollHeight;
        }

        function hideThinkingIndicator() {
            const container = document.getElementById('chat-messages');
            if (!container) return;
            const el = container.querySelector('.thinking-indicator');
            if (el) el.remove();
        }

        async function sendChatMessage() {
            const input = document.getElementById('chat-input');
            const text = (input.value || '').trim();
            if (!text) return;

            // Auto-create a conversation if none is active
            if (!activeConversationId) {
                await createNewConversation();
                if (!activeConversationId) {
                    appendChatBubble('system', 'Could not create a conversation. Please try again.');
                    return;
                }
            }
            input.value = '';

            const mode = document.getElementById('chat-agent-mode').value;

            // Show user message immediately
            appendChatBubble('user', text);

            if (mode === 'direct_llm') {
                // Direct LLM mode — send through Flask
                showThinkingIndicator();
                try {
                    const resp = await fetch(`${API_BASE}/chat/send`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify({
                            conversation_id: activeConversationId,
                            message: text,
                            feature_slot: 'chatbot',
                        }),
                    });
                    const data = await resp.json();
                    hideThinkingIndicator();
                    if (data.success) {
                        // Handle multi-message responses (tool calls + final answer)
                        if (data.messages && data.messages.length > 0) {
                            for (const msg of data.messages) {
                                appendChatBubble(msg.role || 'assistant', msg.content || '', msg.metadata);
                                // Auto-open OAuth popup for connect_service tool
                                if (msg.metadata && msg.metadata.tool_name === 'connect_service') {
                                    try {
                                        const result = JSON.parse(msg.content);
                                        if (result.authorization_url) {
                                            window.open(result.authorization_url, 'OAuthConnect', 'width=600,height=700');
                                        }
                                    } catch(e) {}
                                }
                            }
                        } else if (data.message) {
                            appendChatBubble('assistant', data.message.content);
                        }
                    } else {
                        appendChatBubble('system', 'Error: ' + (data.error || 'Unknown error'));
                    }
                } catch (e) {
                    hideThinkingIndicator();
                    appendChatBubble('system', 'Network error: ' + e.message);
                }
                // Refresh conversation list (title may have changed)
                loadConversations();

            } else if (mode === 'nautilus') {
                // Nautilus WebSocket mode
                if (!nautilusClient || !nautilusClient.connected) {
                    appendChatBubble('system', 'Nautilus is not connected. Go to Agents Hub to connect.');
                    return;
                }
                // Save user message to DB
                saveChatMessages([{ role: 'user', content: text }]);
                // Send to Nautilus
                nautilusClient.sendMessage(nautilusClient.sessionId, text);
                showThinkingIndicator();
            }
        }

        function setupNautilusChatHandlers() {
            if (!nautilusClient) return;

            nautilusClient.onMessage = (msg) => {
                hideThinkingIndicator();
                appendChatBubble(msg.role || 'assistant', msg.content);
                // Save to DB
                saveChatMessages([{ role: msg.role || 'assistant', content: msg.content, metadata: msg.metadata }]);
            };

            nautilusClient.onThinking = () => {
                showThinkingIndicator();
            };

            nautilusClient.onToolUse = (tool) => {
                hideThinkingIndicator();
                const content = tool.output ? JSON.stringify(tool.output) : 'Running...';
                appendChatBubble('tool', content, { tool_name: tool.tool, tool_input: tool.input });
                if (tool.status === 'completed') {
                    saveChatMessages([{
                        role: 'tool',
                        content: content,
                        metadata: { tool_name: tool.tool, tool_input: tool.input },
                    }]);
                }
                if (tool.needsApproval) {
                    // Show approval dialog
                    if (confirm(`Nautilus wants to use tool "${tool.tool}". Allow?`)) {
                        nautilusClient.approveToolUse(tool.requestId);
                    } else {
                        nautilusClient.denyToolUse(tool.requestId);
                    }
                }
            };

            nautilusClient.onError = (err) => {
                hideThinkingIndicator();
                appendChatBubble('system', 'Error: ' + err.message);
            };

            // Create a session if none exists
            if (!nautilusClient.sessionId) {
                nautilusClient.createSession({ conversation_id: activeConversationId });
            }
        }

        async function saveChatMessages(messages) {
            if (!activeConversationId) return;
            try {
                await fetch(`${API_BASE}/chat/messages/save`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({
                        conversation_id: activeConversationId,
                        messages: messages,
                    }),
                });
            } catch (e) { console.error('Failed to save messages:', e); }
        }

        async function deleteConversation(convId) {
            if (!confirm('Delete this conversation?')) return;
            try {
                await fetch(`${API_BASE}/chat/conversations/${convId}`, { method: 'DELETE', credentials: 'include' });
                chatConversations = chatConversations.filter(c => c.conversation_id !== convId);
                if (activeConversationId === convId) {
                    activeConversationId = null;
                    document.getElementById('chat-messages').innerHTML = `
                        <div class="chat-empty-state">
                            <span style="font-size:48px;">💬</span>
                            <p>Select or create a conversation</p>
                        </div>`;
                    document.getElementById('chat-title').textContent = 'Select or create a conversation';
                }
                renderConversationList();
            } catch (e) { console.error(e); }
        }

        function onChatAgentModeChange() {
            const mode = document.getElementById('chat-agent-mode').value;
            const indicator = document.getElementById('chat-model-indicator');
            if (mode === 'direct_llm') {
                const cfg = mcConfigs['chatbot'];
                if (cfg && indicator) {
                    indicator.textContent = `${cfg.provider}/${cfg.model}`;
                    indicator.style.display = 'inline';
                }
            } else if (mode === 'nautilus') {
                if (indicator) {
                    indicator.textContent = 'Nautilus';
                    indicator.style.display = 'inline';
                }
                if (nautilusClient && nautilusClient.connected && activeConversationId) {
                    setupNautilusChatHandlers();
                }
            }
        }


        // ============================================
        // AI WORKBENCH — Web Browse
        // ============================================
        let browseInitialized = false;

        async function initWebBrowseTab() {
            if (!browseInitialized) {
                browseInitialized = true;
                const cfg = mcConfigs['web_browsing'];
                const indicator = document.getElementById('browse-model-indicator');
                if (cfg && indicator) {
                    indicator.textContent = `${cfg.provider}/${cfg.model}`;
                    indicator.style.display = 'inline';
                }
                await loadBrowseHistory();
            }
        }

        async function startResearch() {
            const question = document.getElementById('browse-question').value.trim();
            if (!question) return;

            const progress = document.getElementById('browse-progress');
            const results = document.getElementById('browse-results');
            const btn = document.getElementById('browse-research-btn');

            progress.style.display = 'block';
            results.style.display = 'none';
            btn.disabled = true;
            btn.textContent = 'Researching...';

            // Animate progress steps
            const steps = ['step-searching', 'step-fetching', 'step-analyzing'];
            steps.forEach(s => {
                document.getElementById(s).className = 'progress-step';
            });
            document.getElementById('step-searching').classList.add('active');

            try {
                // Start a timer to animate progress
                setTimeout(() => {
                    document.getElementById('step-searching').classList.remove('active');
                    document.getElementById('step-searching').classList.add('done');
                    document.getElementById('step-fetching').classList.add('active');
                }, 2000);
                setTimeout(() => {
                    document.getElementById('step-fetching').classList.remove('active');
                    document.getElementById('step-fetching').classList.add('done');
                    document.getElementById('step-analyzing').classList.add('active');
                }, 5000);

                const resp = await fetch(`${API_BASE}/browse/research`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ question }),
                });
                const data = await resp.json();

                steps.forEach(s => {
                    const el = document.getElementById(s);
                    el.classList.remove('active');
                    el.classList.add('done');
                });

                if (data.success) {
                    document.getElementById('browse-summary').textContent = data.summary;

                    const sourcesEl = document.getElementById('browse-sources');
                    sourcesEl.innerHTML = (data.sources || []).map((s, i) =>
                        `<div style="margin:6px 0;">
                            <a href="${s.url}" target="_blank" rel="noopener" style="color:var(--secondary); text-decoration:none;">
                                [${i+1}] ${s.title || s.url}
                            </a>
                        </div>`
                    ).join('');

                    results.style.display = 'block';
                } else {
                    showAlert('web-browse', 'error', data.error || 'Research failed');
                }
            } catch (e) {
                showAlert('web-browse', 'error', 'Network error: ' + e.message);
            } finally {
                btn.disabled = false;
                btn.textContent = 'Research';
                setTimeout(() => { progress.style.display = 'none'; }, 1000);
            }
        }

        async function fetchSingleUrl() {
            const url = document.getElementById('browse-fetch-url').value.trim();
            if (!url) return;

            try {
                const resp = await fetch(`${API_BASE}/browse/fetch`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ url }),
                });
                const data = await resp.json();
                if (data.success) {
                    document.getElementById('browse-fetch-content').textContent = data.content;
                    document.getElementById('browse-fetch-result').style.display = 'block';
                } else {
                    showAlert('web-browse', 'error', data.error || 'Failed to fetch');
                }
            } catch (e) {
                showAlert('web-browse', 'error', 'Network error');
            }
        }

        async function loadBrowseHistory() {
            try {
                const resp = await fetch(`${API_BASE}/browse/history`, { credentials: 'include' });
                const data = await resp.json();
                const historyEl = document.getElementById('browse-history');
                if (!historyEl) return;
                const results = data.results || [];
                if (results.length === 0) {
                    historyEl.innerHTML = '<p style="color:var(--text-tertiary); font-size:13px;">No research history yet.</p>';
                    return;
                }
                historyEl.innerHTML = results.map(r => `
                    <div class="card" style="margin-bottom:8px; cursor:pointer;" onclick="this.querySelector('.hist-body').classList.toggle('open')">
                        <div style="display:flex; justify-content:space-between;">
                            <strong style="font-size:13px;">${escapeHtml(r.query)}</strong>
                            <span style="font-size:11px; color:var(--text-tertiary);">${new Date(r.created_at).toLocaleDateString()}</span>
                        </div>
                        <div class="hist-body tool-card-body" style="margin-top:8px;">
                            <p style="font-size:13px; white-space:pre-wrap;">${escapeHtml(r.ai_summary || '').substring(0, 300)}...</p>
                        </div>
                    </div>
                `).join('');
            } catch (e) { console.error(e); }
        }


        // ============================================
        // AI WORKBENCH — Utility
        // ============================================
        let utilityTools = [];
        let selectedUtilityTool = null;
        let utilityInitialized = false;

        async function initUtilityTab() {
            if (!utilityInitialized) {
                utilityInitialized = true;
                try {
                    const resp = await fetch(`${API_BASE}/utility/tools`);
                    const data = await resp.json();
                    utilityTools = data.tools || [];
                    renderUtilityTools();
                } catch (e) { console.error('Failed to load utility tools:', e); }

                const cfg = mcConfigs['utility'];
                const indicator = document.getElementById('utility-model-indicator');
                if (cfg && indicator) {
                    indicator.textContent = `${cfg.provider}/${cfg.model}`;
                    indicator.style.display = 'inline';
                }
            }
        }

        function renderUtilityTools() {
            const grid = document.getElementById('utility-tools-grid');
            if (!grid) return;
            grid.innerHTML = utilityTools.map(t => `
                <div class="tool-select-card ${selectedUtilityTool === t.id ? 'selected' : ''}"
                     onclick="selectUtilityTool('${t.id}')">
                    <div class="tool-emoji">${t.emoji}</div>
                    <div class="tool-name">${t.name}</div>
                    <div class="tool-desc">${t.description}</div>
                </div>
            `).join('');
        }

        function selectUtilityTool(toolId) {
            selectedUtilityTool = toolId;
            const tool = utilityTools.find(t => t.id === toolId);
            renderUtilityTools();

            document.getElementById('utility-tool-title').textContent = tool ? tool.name : 'Select a tool';
            const input = document.getElementById('utility-input');
            input.disabled = false;
            input.placeholder = tool ? tool.placeholder : 'Select a tool...';

            document.getElementById('utility-run-btn').disabled = false;
        }

        async function runUtility() {
            if (!selectedUtilityTool) return;
            const prompt = document.getElementById('utility-input').value.trim();
            if (!prompt) return;

            const btn = document.getElementById('utility-run-btn');
            btn.disabled = true;
            btn.textContent = 'Running...';

            try {
                const resp = await fetch(`${API_BASE}/utility/execute`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({
                        tool: selectedUtilityTool,
                        prompt: prompt,
                    }),
                });
                const data = await resp.json();
                if (data.success) {
                    document.getElementById('utility-output').textContent = data.content;
                    document.getElementById('utility-output-card').style.display = 'block';
                } else {
                    showAlert('utility', 'error', data.error || 'Utility failed');
                }
            } catch (e) {
                showAlert('utility', 'error', 'Network error: ' + e.message);
            } finally {
                btn.disabled = false;
                btn.textContent = 'Run';
            }
        }

        function copyUtilityOutput() {
            const text = document.getElementById('utility-output').textContent;
            navigator.clipboard.writeText(text).then(() => {
                showAlert('utility', 'success', 'Copied to clipboard!');
            }).catch(() => {
                showAlert('utility', 'error', 'Failed to copy');
            });
        }


        // =====================================================
        // OBSERVABILITY TAB
        // =====================================================

        let _obsInitialized = false;

        function initObservabilityTab() {
            if (!_obsInitialized) _obsInitialized = true;
            obsLoadOverview();
            obsLoadAgentsMetrics();
        }

        function obsShowView(viewName) {
            document.querySelectorAll('.obs-view').forEach(v => v.style.display = 'none');
            document.querySelectorAll('.obs-subtab').forEach(b => b.classList.remove('active'));
            const view = document.getElementById('obs-view-' + viewName);
            if (view) view.style.display = 'block';
            const btn = document.querySelector(`.obs-subtab[data-obs-view="${viewName}"]`);
            if (btn) btn.classList.add('active');
            if (viewName === 'events-log') obsLoadEvents();
            if (viewName === 'alerts-view') { obsLoadAlertRules(); obsLoadAlertEvents(); }
            if (viewName === 'api-keys-view') obsLoadApiKeys();
        }

        async function obsLoadOverview() {
            try {
                const resp = await fetch(API_BASE + '/obs/metrics/overview', {credentials:'include'});
                if (!resp.ok) return;
                const data = await resp.json();
                document.getElementById('obs-kpi-cost').textContent = '$' + (data.today.cost_usd || 0).toFixed(4);
                document.getElementById('obs-kpi-calls').textContent = data.today.llm_calls || 0;
                document.getElementById('obs-kpi-errors').textContent = data.today.errors || 0;
                document.getElementById('obs-kpi-agents').textContent = data.active_agents_24h || 0;
                document.getElementById('obs-kpi-alerts').textContent = data.unacknowledged_alerts || 0;
            } catch(e) { console.error('obs overview:', e); }
        }

        async function obsLoadAgentsMetrics() {
            const container = document.getElementById('obs-agents-table-container');
            try {
                const resp = await fetch(API_BASE + '/obs/metrics/agents?from=' + _daysAgo(7), {credentials:'include'});
                if (!resp.ok) { container.innerHTML = '<p style="color:var(--text-secondary)">No metrics yet. Events will appear after agents send data.</p>'; return; }
                const data = await resp.json();
                const metrics = data.metrics || [];
                if (!metrics.length) { container.innerHTML = '<p style="color:var(--text-secondary)">No metrics yet. Use the API Keys tab to get an ingestion key, or chat with an LLM to generate events.</p>'; return; }

                // Aggregate by agent_id
                const byAgent = {};
                metrics.forEach(m => {
                    const aid = m.agent_id || 'workspace';
                    if (!byAgent[aid]) byAgent[aid] = {agent_id:aid, runs:0, cost:0, errors:0, tokens:0, latency_values:[]};
                    byAgent[aid].runs += m.total_runs;
                    byAgent[aid].cost += m.total_cost_usd;
                    byAgent[aid].errors += m.failed_runs;
                    byAgent[aid].tokens += m.total_tokens_in + m.total_tokens_out;
                    if (m.latency_avg_ms) byAgent[aid].latency_values.push(m.latency_avg_ms);
                });

                let html = '<table style="width:100%; border-collapse:collapse; font-size:13px;"><thead><tr style="text-align:left; border-bottom:1px solid var(--border);">';
                html += '<th style="padding:8px;">Agent</th><th style="padding:8px;">Runs</th><th style="padding:8px;">Cost</th><th style="padding:8px;">Errors</th><th style="padding:8px;">Tokens</th><th style="padding:8px;">Avg Latency</th><th style="padding:8px;"></th>';
                html += '</tr></thead><tbody>';
                Object.values(byAgent).forEach(a => {
                    const avgLat = a.latency_values.length ? Math.round(a.latency_values.reduce((s,v)=>s+v,0) / a.latency_values.length) : '-';
                    const errRate = a.runs ? ((a.errors / a.runs) * 100).toFixed(1) + '%' : '-';
                    html += `<tr style="border-bottom:1px solid var(--border);">`;
                    html += `<td style="padding:8px;">${a.agent_id === 'workspace' ? 'No Agent' : 'Agent #'+a.agent_id}</td>`;
                    html += `<td style="padding:8px;">${a.runs}</td>`;
                    html += `<td style="padding:8px;">$${a.cost.toFixed(4)}</td>`;
                    html += `<td style="padding:8px; ${a.errors > 0 ? 'color:#ef4444;' : ''}">${a.errors} (${errRate})</td>`;
                    html += `<td style="padding:8px;">${a.tokens.toLocaleString()}</td>`;
                    html += `<td style="padding:8px;">${avgLat === '-' ? '-' : avgLat + 'ms'}</td>`;
                    html += `<td style="padding:8px;"><button class="btn btn-secondary" style="font-size:11px; padding:4px 8px;" onclick="obsShowAgentDetail(${a.agent_id === 'workspace' ? 'null' : a.agent_id})">Detail</button></td>`;
                    html += `</tr>`;
                });
                html += '</tbody></table>';
                container.innerHTML = html;
            } catch(e) { container.innerHTML = '<p style="color:#ef4444;">Error loading metrics</p>'; console.error(e); }
        }

        async function obsShowAgentDetail(agentId) {
            if (!agentId) return;
            const panel = document.getElementById('obs-agent-detail');
            panel.style.display = 'block';
            document.getElementById('obs-detail-agent-name').textContent = 'Agent #' + agentId;

            try {
                const resp = await fetch(API_BASE + '/obs/metrics/agent/' + agentId + '?from=' + _daysAgo(30), {credentials:'include'});
                if (!resp.ok) return;
                const data = await resp.json();

                // Render cost chart
                _obsRenderLineChart('obs-cost-chart', data.metrics, 'total_cost_usd', 'Daily Cost ($)', '#06b6d4');
                // Render latency chart
                _obsRenderLineChart('obs-latency-chart', data.metrics, 'latency_avg_ms', 'Avg Latency (ms)', '#f59e0b');

                // Render recent events table
                const evContainer = document.getElementById('obs-detail-events');
                if (data.recent_events && data.recent_events.length) {
                    let html = '<table style="width:100%; border-collapse:collapse; font-size:12px;"><thead><tr style="border-bottom:1px solid var(--border);">';
                    html += '<th style="padding:6px;">Time</th><th style="padding:6px;">Type</th><th style="padding:6px;">Status</th><th style="padding:6px;">Model</th><th style="padding:6px;">Tokens</th><th style="padding:6px;">Cost</th><th style="padding:6px;">Latency</th>';
                    html += '</tr></thead><tbody>';
                    data.recent_events.slice(0, 20).forEach(e => {
                        const statusColor = e.status === 'error' ? '#ef4444' : e.status === 'success' ? '#22c55e' : 'var(--text-secondary)';
                        html += `<tr style="border-bottom:1px solid var(--border);">`;
                        html += `<td style="padding:6px;">${e.created_at ? new Date(e.created_at).toLocaleTimeString() : '-'}</td>`;
                        html += `<td style="padding:6px;">${e.event_type}</td>`;
                        html += `<td style="padding:6px; color:${statusColor};">${e.status}</td>`;
                        html += `<td style="padding:6px;">${e.model || '-'}</td>`;
                        html += `<td style="padding:6px;">${(e.tokens_in||0)+(e.tokens_out||0) || '-'}</td>`;
                        html += `<td style="padding:6px;">${e.cost_usd ? '$'+e.cost_usd.toFixed(6) : '-'}</td>`;
                        html += `<td style="padding:6px;">${e.latency_ms ? e.latency_ms+'ms' : '-'}</td>`;
                        html += `</tr>`;
                    });
                    html += '</tbody></table>';
                    evContainer.innerHTML = html;
                } else {
                    evContainer.innerHTML = '<p style="color:var(--text-secondary);">No recent events.</p>';
                }
            } catch(e) { console.error('agent detail:', e); }
        }

        function _obsRenderLineChart(canvasId, metrics, field, label, color) {
            const canvas = document.getElementById(canvasId);
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            const W = canvas.width, H = canvas.height;
            const pad = 50;
            ctx.clearRect(0, 0, W, H);

            if (!metrics || !metrics.length) {
                ctx.fillStyle = 'rgba(255,255,255,0.5)'; ctx.textAlign = 'center'; ctx.font = '13px sans-serif';
                ctx.fillText('No data', W/2, H/2);
                return;
            }

            const values = metrics.map(m => m[field] || 0);
            const labels = metrics.map(m => m.date);
            const maxVal = Math.max(...values, 0.001);

            // Axes
            ctx.strokeStyle = 'rgba(255,255,255,0.15)'; ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(pad, 10); ctx.lineTo(pad, H-pad); ctx.lineTo(W-10, H-pad); ctx.stroke();

            // Title
            ctx.fillStyle = 'rgba(255,255,255,0.7)'; ctx.font = '12px sans-serif'; ctx.textAlign = 'left';
            ctx.fillText(label, pad, 22);

            // Y-axis label
            ctx.fillStyle = 'rgba(255,255,255,0.4)'; ctx.textAlign = 'right'; ctx.font = '10px sans-serif';
            ctx.fillText(field.includes('cost') ? '$'+maxVal.toFixed(4) : Math.round(maxVal), pad-4, 22);
            ctx.fillText('0', pad-4, H-pad+4);

            // Line
            ctx.strokeStyle = color; ctx.lineWidth = 2;
            ctx.beginPath();
            values.forEach((v, i) => {
                const x = pad + (i / Math.max(values.length-1, 1)) * (W - pad - 10);
                const y = (H - pad) - (v / maxVal) * (H - pad - 20);
                i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
            });
            ctx.stroke();

            // Points
            ctx.fillStyle = color;
            values.forEach((v, i) => {
                const x = pad + (i / Math.max(values.length-1, 1)) * (W - pad - 10);
                const y = (H - pad) - (v / maxVal) * (H - pad - 20);
                ctx.beginPath(); ctx.arc(x, y, 3, 0, 2*Math.PI); ctx.fill();
            });

            // X labels (first and last)
            ctx.fillStyle = 'rgba(255,255,255,0.4)'; ctx.textAlign = 'center'; ctx.font = '10px sans-serif';
            if (labels[0]) ctx.fillText(labels[0], pad, H-pad+14);
            if (labels.length > 1) ctx.fillText(labels[labels.length-1], W-10, H-pad+14);
        }

        async function obsLoadEvents() {
            const container = document.getElementById('obs-events-table');
            const typeFilter = document.getElementById('obs-event-type-filter').value;
            const statusFilter = document.getElementById('obs-status-filter').value;
            let url = API_BASE + '/obs/events?limit=100';
            if (typeFilter) url += '&event_type=' + typeFilter;
            if (statusFilter) url += '&status=' + statusFilter;

            try {
                const resp = await fetch(url, {credentials:'include'});
                if (!resp.ok) { container.innerHTML = '<p style="color:var(--text-secondary)">No events yet.</p>'; return; }
                const data = await resp.json();
                const events = data.events || [];
                if (!events.length) { container.innerHTML = '<p style="color:var(--text-secondary)">No events match filters.</p>'; return; }

                let html = '<table style="width:100%; border-collapse:collapse; font-size:12px;"><thead><tr style="border-bottom:1px solid var(--border);">';
                html += '<th style="padding:6px;">Time</th><th style="padding:6px;">Type</th><th style="padding:6px;">Status</th><th style="padding:6px;">Agent</th><th style="padding:6px;">Model</th><th style="padding:6px;">Tokens</th><th style="padding:6px;">Cost</th><th style="padding:6px;">Latency</th>';
                html += '</tr></thead><tbody>';
                events.forEach(e => {
                    const statusColor = e.status === 'error' ? '#ef4444' : e.status === 'success' ? '#22c55e' : 'var(--text-secondary)';
                    html += '<tr style="border-bottom:1px solid var(--border);">';
                    html += `<td style="padding:6px;">${e.created_at ? new Date(e.created_at).toLocaleString() : '-'}</td>`;
                    html += `<td style="padding:6px;">${e.event_type}</td>`;
                    html += `<td style="padding:6px; color:${statusColor}">${e.status}</td>`;
                    html += `<td style="padding:6px;">${e.agent_id || '-'}</td>`;
                    html += `<td style="padding:6px;">${e.model || '-'}</td>`;
                    html += `<td style="padding:6px;">${(e.tokens_in||0)+(e.tokens_out||0) || '-'}</td>`;
                    html += `<td style="padding:6px;">${e.cost_usd ? '$'+e.cost_usd.toFixed(6) : '-'}</td>`;
                    html += `<td style="padding:6px;">${e.latency_ms ? e.latency_ms+'ms' : '-'}</td>`;
                    html += '</tr>';
                });
                html += '</tbody></table>';
                html += `<p style="font-size:11px; color:var(--text-secondary); margin-top:8px;">Showing ${events.length} of ${data.total} events</p>`;
                container.innerHTML = html;
            } catch(e) { container.innerHTML = '<p style="color:#ef4444">Error loading events</p>'; }
        }

        async function obsLoadAlertRules() {
            const container = document.getElementById('obs-alert-rules-list');
            try {
                const resp = await fetch(API_BASE + '/obs/alerts/rules', {credentials:'include'});
                const data = await resp.json();
                const rules = data.rules || [];
                if (!rules.length) { container.innerHTML = '<p style="color:var(--text-secondary);">No alert rules. Click "+ New Rule" to create one.</p>'; return; }
                let html = '';
                rules.forEach(r => {
                    const typeLabel = r.rule_type === 'cost_per_day' ? 'Cost/day > $'+r.threshold : r.rule_type === 'error_rate' ? 'Error rate > '+r.threshold+'%' : 'No heartbeat > '+r.threshold+'m';
                    html += `<div style="display:flex; justify-content:space-between; align-items:center; padding:10px 0; border-bottom:1px solid var(--border);">`;
                    html += `<div><strong>${r.name}</strong><br><span style="font-size:12px; color:var(--text-secondary);">${typeLabel} | ${r.is_enabled ? 'Enabled' : 'Disabled'}${r.last_triggered_at ? ' | Last fired: '+new Date(r.last_triggered_at).toLocaleString() : ''}</span></div>`;
                    html += `<div style="display:flex; gap:6px;">`;
                    html += `<button class="btn btn-secondary" style="font-size:11px; padding:4px 8px;" onclick="obsToggleRule(${r.id}, ${!r.is_enabled})">${r.is_enabled ? 'Disable' : 'Enable'}</button>`;
                    html += `<button class="btn btn-secondary" style="font-size:11px; padding:4px 8px; color:#ef4444;" onclick="obsDeleteRule(${r.id})">Delete</button>`;
                    html += `</div></div>`;
                });
                container.innerHTML = html;
            } catch(e) { container.innerHTML = '<p style="color:#ef4444">Error loading rules</p>'; }
        }

        async function obsLoadAlertEvents() {
            const container = document.getElementById('obs-alert-events-list');
            try {
                const resp = await fetch(API_BASE + '/obs/alerts/events?limit=20', {credentials:'include'});
                const data = await resp.json();
                const events = data.events || [];
                if (!events.length) { container.innerHTML = '<p style="color:var(--text-secondary);">No alerts fired yet.</p>'; return; }
                let html = '';
                events.forEach(e => {
                    const acked = e.acknowledged_at ? 'color:var(--text-secondary);' : 'color:#f59e0b;';
                    html += `<div style="padding:10px 0; border-bottom:1px solid var(--border); ${acked}">`;
                    html += `<div style="font-size:13px;">${e.message}</div>`;
                    html += `<div style="font-size:11px; color:var(--text-secondary); margin-top:4px;">${new Date(e.triggered_at).toLocaleString()}`;
                    if (!e.acknowledged_at) html += ` | <a href="#" onclick="event.preventDefault(); obsAckAlert(${e.id})" style="color:var(--primary);">Acknowledge</a>`;
                    html += `</div></div>`;
                });
                container.innerHTML = html;
            } catch(e) { container.innerHTML = '<p style="color:#ef4444">Error loading alert events</p>'; }
        }

        function obsShowCreateAlert() { document.getElementById('obs-create-alert-form').style.display = 'block'; }

        async function obsCreateAlert() {
            const body = {
                name: document.getElementById('obs-alert-name').value,
                rule_type: document.getElementById('obs-alert-type').value,
                threshold: parseFloat(document.getElementById('obs-alert-threshold').value),
                cooldown_minutes: parseInt(document.getElementById('obs-alert-cooldown').value) || 360,
            };
            try {
                const resp = await fetch(API_BASE + '/obs/alerts/rules', {method:'POST', headers:{'Content-Type':'application/json'}, credentials:'include', body:JSON.stringify(body)});
                if (resp.ok) { document.getElementById('obs-create-alert-form').style.display='none'; obsLoadAlertRules(); }
            } catch(e) { console.error(e); }
        }

        async function obsToggleRule(ruleId, enabled) {
            await fetch(API_BASE + '/obs/alerts/rules/' + ruleId, {method:'POST', headers:{'Content-Type':'application/json'}, credentials:'include', body:JSON.stringify({is_enabled: enabled})});
            obsLoadAlertRules();
        }

        async function obsDeleteRule(ruleId) {
            if (!confirm('Delete this alert rule?')) return;
            await fetch(API_BASE + '/obs/alerts/rules/' + ruleId, {method:'POST', headers:{'Content-Type':'application/json'}, credentials:'include', body:JSON.stringify({delete: true})});
            obsLoadAlertRules();
        }

        async function obsAckAlert(eventId) {
            await fetch(API_BASE + '/obs/alerts/events/' + eventId + '/acknowledge', {method:'POST', credentials:'include'});
            obsLoadAlertEvents();
        }

        async function obsLoadApiKeys() {
            const container = document.getElementById('obs-api-keys-list');
            try {
                const resp = await fetch(API_BASE + '/obs/api-keys', {credentials:'include'});
                const data = await resp.json();
                const keys = data.keys || [];
                if (!keys.length) { container.innerHTML = '<p style="color:var(--text-secondary);">No API keys yet. Create one to start ingesting events.</p>'; return; }
                let html = '';
                keys.forEach(k => {
                    html += `<div style="display:flex; justify-content:space-between; align-items:center; padding:10px 0; border-bottom:1px solid var(--border);">`;
                    html += `<div><code>${k.key_prefix}...</code> <span style="font-size:12px; color:var(--text-secondary);">${k.name} | ${k.is_active ? 'Active' : 'Revoked'}${k.last_used_at ? ' | Last used: '+new Date(k.last_used_at).toLocaleString() : ''}</span></div>`;
                    if (k.is_active) html += `<button class="btn btn-secondary" style="font-size:11px; padding:4px 8px; color:#ef4444;" onclick="obsRevokeKey(${k.id})">Revoke</button>`;
                    html += `</div>`;
                });
                container.innerHTML = html;
            } catch(e) { container.innerHTML = '<p style="color:#ef4444">Error loading keys</p>'; }
        }

        async function obsCreateApiKey() {
            try {
                const resp = await fetch(API_BASE + '/obs/api-keys', {method:'POST', headers:{'Content-Type':'application/json'}, credentials:'include', body:JSON.stringify({name:'default'})});
                const data = await resp.json();
                if (data.key) {
                    document.getElementById('obs-new-key-value').textContent = data.key;
                    document.getElementById('obs-new-key-display').style.display = 'block';
                    obsLoadApiKeys();
                }
            } catch(e) { console.error(e); }
        }

        async function obsRevokeKey(keyId) {
            if (!confirm('Revoke this API key? External agents using it will stop working.')) return;
            await fetch(API_BASE + '/obs/api-keys/' + keyId + '/revoke', {method:'POST', credentials:'include'});
            obsLoadApiKeys();
        }

        function _daysAgo(n) {
            const d = new Date(); d.setDate(d.getDate() - n);
            return d.toISOString().split('T')[0];
        }

        // ==================================================================
        // Governance Tab
        // ==================================================================

        let govInitialized = false;

        function initGovernanceTab() {
            if (!govInitialized) {
                govInitialized = true;
            }
            govLoadPending();
        }

        function govShowView(viewName) {
            document.querySelectorAll('.gov-view').forEach(v => v.style.display = 'none');
            document.querySelectorAll('.gov-subtab').forEach(b => b.classList.remove('active'));
            const target = document.getElementById('gov-view-' + viewName);
            if (target) target.style.display = '';
            const btn = document.querySelector(`.gov-subtab[data-gov-view="${viewName}"]`);
            if (btn) btn.classList.add('active');
            if (viewName === 'pending') govLoadPending();
            if (viewName === 'delegations') govLoadDelegations();
            if (viewName === 'audit') govLoadAudit();
        }

        async function govLoadPending() {
            try {
                const resp = await fetch(API_BASE + '/governance/pending', {credentials: 'include'});
                if (resp.status === 401) return;
                const data = await resp.json();
                const container = document.getElementById('gov-pending-container');
                const badge = document.getElementById('governance-pending-badge');
                const requests = data.requests || [];

                if (badge) {
                    badge.textContent = data.count || 0;
                    badge.style.display = (data.count > 0) ? 'inline-block' : 'none';
                }

                if (requests.length === 0) {
                    container.innerHTML = '<p style="color:var(--text-secondary);">No pending requests.</p>';
                    return;
                }

                container.innerHTML = requests.map(r => {
                    const changes = r.requested_changes || {};
                    return `<div style="border:1px solid var(--border); border-radius:8px; padding:16px; margin-bottom:12px;">
                        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap;">
                            <div style="flex:1; min-width:200px;">
                                <div style="font-weight:600; margin-bottom:4px;">Policy #${changes.policy_id || '?'} &mdash; ${changes.field || '?'}</div>
                                <div style="font-size:13px; color:var(--text-secondary);">
                                    ${changes.current_value || '?'} &rarr; ${changes.requested_value || '?'}
                                </div>
                                <div style="font-size:13px; color:var(--text-secondary); margin-top:4px;">
                                    Agent #${r.agent_id} &bull; ${_govTimeAgo(r.requested_at)}
                                </div>
                                <div style="font-size:13px; margin-top:4px; font-style:italic; color:var(--text-secondary);">
                                    "${r.reason || ''}"
                                </div>
                            </div>
                            <div style="display:flex; gap:8px; align-items:center;">
                                <button class="btn btn-primary" onclick="govApproveRequest(${r.id})" style="font-size:12px; padding:6px 12px;">Approve</button>
                                <button class="btn btn-secondary" onclick="govDenyRequest(${r.id})" style="font-size:12px; padding:6px 12px;">Deny</button>
                            </div>
                        </div>
                    </div>`;
                }).join('');
            } catch (e) { console.error('Error loading governance pending:', e); }
        }

        async function govApproveRequest(requestId) {
            const mode = prompt('Approval mode: type "one_time" for immediate apply or "delegate" for time-bound delegation:', 'one_time');
            if (!mode) return;

            let body = { mode };
            if (mode === 'delegate') {
                const mins = prompt('Delegation duration in minutes (max 1440):', '60');
                if (!mins) return;
                body.delegation_params = { duration_minutes: parseInt(mins, 10) };
            }

            try {
                const resp = await fetch(API_BASE + '/governance/approve/' + requestId, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    credentials: 'include',
                    body: JSON.stringify(body)
                });
                const data = await resp.json();
                if (data.success) {
                    alert('Request approved (' + (data.mode || mode) + ').');
                    govLoadPending();
                } else {
                    alert('Error: ' + (data.error || 'Unknown error'));
                }
            } catch (e) { alert('Error: ' + e.message); }
        }

        async function govDenyRequest(requestId) {
            const reason = prompt('Denial reason (optional):');
            try {
                const resp = await fetch(API_BASE + '/governance/deny/' + requestId, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    credentials: 'include',
                    body: JSON.stringify({ reason: reason || '' })
                });
                const data = await resp.json();
                if (data.success) {
                    alert('Request denied.');
                    govLoadPending();
                } else {
                    alert('Error: ' + (data.error || 'Unknown error'));
                }
            } catch (e) { alert('Error: ' + e.message); }
        }

        async function govLoadDelegations() {
            try {
                const resp = await fetch(API_BASE + '/governance/delegations', {credentials: 'include'});
                if (resp.status === 401) return;
                const data = await resp.json();
                const container = document.getElementById('gov-delegations-container');
                const grants = data.delegations || [];

                if (grants.length === 0) {
                    container.innerHTML = '<p style="color:var(--text-secondary);">No active delegations.</p>';
                    return;
                }

                container.innerHTML = grants.map(g => {
                    const ac = g.allowed_changes || {};
                    const fields = ac.fields ? Object.keys(ac.fields).join(', ') : 'N/A';
                    return `<div style="border:1px solid var(--border); border-radius:8px; padding:16px; margin-bottom:12px;">
                        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap;">
                            <div style="flex:1; min-width:200px;">
                                <div style="font-weight:600; margin-bottom:4px;">Grant #${g.id} &mdash; Policy #${ac.policy_id || '?'}</div>
                                <div style="font-size:13px; color:var(--text-secondary);">
                                    Fields: ${fields}
                                </div>
                                <div style="font-size:13px; color:var(--text-secondary); margin-top:4px;">
                                    Agent #${g.agent_id} &bull; Expires: ${new Date(g.valid_to).toLocaleString()}
                                </div>
                                <div style="font-size:13px; color:var(--text-secondary); margin-top:2px;">
                                    Duration: ${g.duration_minutes} min
                                </div>
                            </div>
                            <div>
                                <button class="btn btn-secondary" onclick="govRevokeDelegation(${g.id})" style="font-size:12px; padding:6px 12px;">Revoke</button>
                            </div>
                        </div>
                    </div>`;
                }).join('');
            } catch (e) { console.error('Error loading delegations:', e); }
        }

        async function govRevokeDelegation(grantId) {
            if (!confirm('Revoke this delegation grant? The agent will no longer be able to apply changes.')) return;
            try {
                const resp = await fetch(API_BASE + '/governance/delegations/' + grantId + '/revoke', {
                    method: 'POST',
                    credentials: 'include'
                });
                const data = await resp.json();
                if (data.success) {
                    alert('Delegation revoked.');
                    govLoadDelegations();
                } else {
                    alert('Error: ' + (data.error || 'Unknown error'));
                }
            } catch (e) { alert('Error: ' + e.message); }
        }

        async function govLoadAudit() {
            try {
                const typeFilter = document.getElementById('gov-audit-type-filter');
                const eventType = typeFilter ? typeFilter.value : '';
                let url = API_BASE + '/governance/audit?limit=50';
                if (eventType) url += '&event_type=' + encodeURIComponent(eventType);

                const resp = await fetch(url, {credentials: 'include'});
                if (resp.status === 401) return;
                const data = await resp.json();
                const container = document.getElementById('gov-audit-container');
                const entries = data.audit_trail || [];

                if (entries.length === 0) {
                    container.innerHTML = '<p style="color:var(--text-secondary);">No audit entries found.</p>';
                    return;
                }

                const eventColors = {
                    'request_submitted': '#3b82f6',
                    'request_approved': '#22c55e',
                    'request_denied': '#ef4444',
                    'request_expired': '#6b7280',
                    'change_applied': '#22c55e',
                    'change_rolled_back': '#f59e0b',
                    'grant_created': '#8b5cf6',
                    'grant_expired': '#6b7280',
                    'grant_revoked': '#ef4444',
                    'grant_used': '#3b82f6',
                    'boundary_violation': '#ef4444'
                };

                container.innerHTML = `<div style="overflow-x:auto;">
                    <table style="width:100%; border-collapse:collapse; font-size:13px;">
                        <thead>
                            <tr style="border-bottom:1px solid var(--border); text-align:left;">
                                <th style="padding:8px 6px;">Time</th>
                                <th style="padding:8px 6px;">Event</th>
                                <th style="padding:8px 6px;">Agent</th>
                                <th style="padding:8px 6px;">Details</th>
                                <th style="padding:8px 6px;">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${entries.map(e => {
                                const color = eventColors[e.event_type] || 'var(--text-secondary)';
                                const details = e.details || {};
                                let summary = '';
                                if (details.policy_id) summary += 'Policy #' + details.policy_id;
                                if (details.field) summary += ' / ' + details.field;
                                if (details.old_value && details.new_value) summary += ': ' + details.old_value + ' -> ' + details.new_value;
                                if (details.reason) summary += ' (' + details.reason + ')';
                                if (!summary && details.request_id) summary = 'Request #' + details.request_id;
                                if (!summary && details.grant_id) summary = 'Grant #' + details.grant_id;

                                const canRollback = (e.event_type === 'change_applied' || e.event_type === 'change_rolled_back');

                                return `<tr style="border-bottom:1px solid var(--border);">
                                    <td style="padding:8px 6px; white-space:nowrap;">${_govTimeAgo(e.created_at)}</td>
                                    <td style="padding:8px 6px;"><span style="color:${color}; font-weight:500;">${e.event_type.replace(/_/g, ' ')}</span></td>
                                    <td style="padding:8px 6px;">${e.agent_id ? '#' + e.agent_id : '-'}</td>
                                    <td style="padding:8px 6px; max-width:300px; overflow:hidden; text-overflow:ellipsis;">${summary || '-'}</td>
                                    <td style="padding:8px 6px;">${canRollback ? `<button class="btn btn-secondary" onclick="govRollback(${e.id})" style="font-size:11px; padding:3px 8px;">Rollback</button>` : ''}</td>
                                </tr>`;
                            }).join('')}
                        </tbody>
                    </table>
                </div>`;
            } catch (e) { console.error('Error loading audit trail:', e); }
        }

        async function govRollback(auditEntryId) {
            if (!confirm('Rollback this policy change? The policy will be restored to its previous state.')) return;
            try {
                const resp = await fetch(API_BASE + '/governance/rollback/' + auditEntryId, {
                    method: 'POST',
                    credentials: 'include'
                });
                const data = await resp.json();
                if (data.success) {
                    alert('Policy change rolled back successfully.');
                    govLoadAudit();
                } else {
                    alert('Error: ' + (data.error || 'Unknown error'));
                }
            } catch (e) { alert('Error: ' + e.message); }
        }

        function _govTimeAgo(isoStr) {
            if (!isoStr) return '';
            const d = new Date(isoStr);
            const now = new Date();
            const diffMs = now - d;
            const diffMin = Math.floor(diffMs / 60000);
            if (diffMin < 1) return 'just now';
            if (diffMin < 60) return diffMin + 'm ago';
            const diffH = Math.floor(diffMin / 60);
            if (diffH < 24) return diffH + 'h ago';
            const diffD = Math.floor(diffH / 24);
            return diffD + 'd ago';
        }

        // Load governance pending count on page load for the badge
        document.addEventListener('DOMContentLoaded', () => {
            fetch(API_BASE + '/governance/pending', {credentials: 'include'})
                .then(r => r.ok ? r.json() : null)
                .then(data => {
                    if (!data) return;
                    const badge = document.getElementById('governance-pending-badge');
                    if (badge && data.count > 0) {
                        badge.textContent = data.count;
                        badge.style.display = 'inline-block';
                    }
                })
                .catch(() => {});
        });

        // =================================================================
        // COLLABORATION: TASKS TAB
        // =================================================================

        let collabTasksData = [];

        async function initCollabTasksTab() {
            await populateAgentFilters();
            await loadCollabTasks();
        }

        async function populateAgentFilters() {
            try {
                const resp = await fetch(`${API_BASE}/agents`, { credentials: 'include' });
                if (!resp.ok) return;
                const data = await resp.json();
                const agents = data.agents || [];

                // Task tab agent filter
                const taskFilter = document.getElementById('collab-task-agent-filter');
                if (taskFilter) {
                    const val = taskFilter.value;
                    taskFilter.innerHTML = '<option value="">All Agents</option>' +
                        agents.map(a => `<option value="${a.id}">${a.name}</option>`).join('');
                    taskFilter.value = val;
                }
            } catch (e) {
                console.error('Failed to populate agent filters:', e);
            }
        }

        async function loadCollabTasks() {
            try {
                const status = document.getElementById('collab-task-status-filter')?.value || '';
                const agentId = document.getElementById('collab-task-agent-filter')?.value || '';

                let url = `${API_BASE}/tasks?`;
                if (status) url += `status=${status}&`;
                if (agentId) url += `assigned_to=${agentId}&`;

                const resp = await fetch(url, { credentials: 'include' });
                if (!resp.ok) throw new Error('Failed to load tasks');
                const data = await resp.json();
                collabTasksData = data.tasks || [];

                renderCollabTaskStats(collabTasksData);
                renderCollabTasksList(collabTasksData);
            } catch (e) {
                console.error('Error loading tasks:', e);
                document.getElementById('collab-tasks-list').innerHTML =
                    '<p style="text-align:center;color:#ef4444;padding:40px;">Failed to load tasks.</p>';
            }
        }

        function renderCollabTaskStats(tasks) {
            const container = document.getElementById('collab-task-stats');
            if (!container) return;

            const counts = { queued: 0, running: 0, blocked: 0, completed: 0, failed: 0, canceled: 0 };
            tasks.forEach(t => { if (counts[t.status] !== undefined) counts[t.status]++; });

            const colors = {
                queued: '#3b82f6', running: '#f59e0b', blocked: '#ef4444',
                completed: '#22c55e', failed: '#ef4444', canceled: '#6b7280',
            };

            container.innerHTML = Object.entries(counts).map(([s, c]) => `
                <div style="background:${colors[s]}22; border:1px solid ${colors[s]}55; border-radius:8px; padding:12px; text-align:center;">
                    <div style="font-size:22px; font-weight:700; color:${colors[s]};">${c}</div>
                    <div style="font-size:12px; color:var(--text-secondary); text-transform:capitalize;">${s}</div>
                </div>
            `).join('');
        }

        function getStatusBadge(status) {
            const colors = {
                queued: '#3b82f6', running: '#f59e0b', blocked: '#ef4444',
                completed: '#22c55e', failed: '#ef4444', canceled: '#6b7280',
            };
            const c = colors[status] || '#6b7280';
            return `<span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;background:${c}22;color:${c};border:1px solid ${c}55;">${status}</span>`;
        }

        function renderCollabTasksList(tasks) {
            const container = document.getElementById('collab-tasks-list');
            if (!container) return;

            if (tasks.length === 0) {
                container.innerHTML = `
                    <div style="text-align:center; padding:60px 20px;">
                        <p style="font-size:48px; margin-bottom:16px;">📋</p>
                        <h3 style="color:var(--text-primary); margin-bottom:12px;">No tasks yet</h3>
                        <p style="color:var(--text-secondary); margin-bottom:24px;">Create your first collaboration task to get agents working together.</p>
                        <button class="btn btn-primary" onclick="showCreateTaskModal()">+ Create Task</button>
                    </div>`;
                return;
            }

            container.innerHTML = tasks.map(t => `
                <div class="card" style="margin-bottom:12px; padding:16px; cursor:pointer;" onclick="showTaskDetail('${t.id}')">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px;">
                        <div style="flex:1; min-width:0;">
                            <div style="font-weight:600; color:var(--text-primary); margin-bottom:6px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(t.title)}</div>
                            <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center; font-size:13px; color:var(--text-secondary);">
                                ${getStatusBadge(t.status)}
                                <span>Agent #${t.assigned_to_agent_id}</span>
                                ${t.priority > 0 ? `<span style="color:#f59e0b;">P${t.priority}</span>` : ''}
                                ${t.parent_task_id ? '<span style="color:var(--text-secondary);">subtask</span>' : ''}
                            </div>
                        </div>
                        <div style="font-size:12px; color:var(--text-secondary); white-space:nowrap;">
                            ${formatTimeAgo(t.created_at)}
                        </div>
                    </div>
                </div>
            `).join('');
        }

        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
        }

        async function showTaskDetail(taskId) {
            try {
                const resp = await fetch(`${API_BASE}/tasks/${taskId}`, { credentials: 'include' });
                if (!resp.ok) throw new Error('Failed to load task');
                const data = await resp.json();
                const t = data.task;

                const titleEl = document.getElementById('collab-task-detail-title');
                const contentEl = document.getElementById('collab-task-detail-content');
                titleEl.textContent = t.title;

                const events = (t.events || []).map(e => `
                    <div style="display:flex; gap:10px; padding:8px 0; border-bottom:1px solid var(--border);">
                        <span style="font-size:12px; color:var(--text-secondary); white-space:nowrap;">${new Date(e.created_at).toLocaleString()}</span>
                        <span style="font-size:13px; color:var(--text-primary);">${e.event_type}</span>
                    </div>
                `).join('');

                // Action buttons based on status
                let actions = '';
                if (t.status === 'queued' || t.status === 'blocked') {
                    actions += `<button class="btn btn-primary" onclick="collabTaskAction('${t.id}','start')" style="padding:8px 16px;">Start</button> `;
                    actions += `<button class="btn btn-secondary" onclick="collabTaskAction('${t.id}','cancel')" style="padding:8px 16px;">Cancel</button> `;
                }
                if (t.status === 'running') {
                    actions += `<button class="btn btn-primary" onclick="collabTaskAction('${t.id}','complete')" style="padding:8px 16px;">Complete</button> `;
                    actions += `<button class="btn btn-secondary" onclick="collabTaskAction('${t.id}','fail')" style="padding:8px 16px;">Fail</button> `;
                }

                contentEl.innerHTML = `
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:20px;">
                        <div><span style="color:var(--text-secondary);font-size:13px;">Status</span><br>${getStatusBadge(t.status)}</div>
                        <div><span style="color:var(--text-secondary);font-size:13px;">Priority</span><br><span style="color:var(--text-primary);">${t.priority}</span></div>
                        <div><span style="color:var(--text-secondary);font-size:13px;">Assigned To</span><br><span style="color:var(--text-primary);">Agent #${t.assigned_to_agent_id}</span></div>
                        <div><span style="color:var(--text-secondary);font-size:13px;">Created</span><br><span style="color:var(--text-primary);">${new Date(t.created_at).toLocaleString()}</span></div>
                    </div>
                    ${t.input ? `<div style="margin-bottom:16px;"><span style="color:var(--text-secondary);font-size:13px;">Input</span><pre style="background:var(--bg-primary);padding:12px;border-radius:8px;overflow-x:auto;font-size:12px;margin-top:4px;">${escapeHtml(JSON.stringify(t.input, null, 2))}</pre></div>` : ''}
                    ${t.output ? `<div style="margin-bottom:16px;"><span style="color:var(--text-secondary);font-size:13px;">Output</span><pre style="background:var(--bg-primary);padding:12px;border-radius:8px;overflow-x:auto;font-size:12px;margin-top:4px;">${escapeHtml(JSON.stringify(t.output, null, 2))}</pre></div>` : ''}
                    ${actions ? `<div style="margin-bottom:20px;">${actions}</div>` : ''}
                    <h4 style="margin:20px 0 10px;">Event Trail</h4>
                    <div style="max-height:300px;overflow-y:auto;">${events || '<p style="color:var(--text-secondary);">No events</p>'}</div>
                `;

                document.getElementById('collab-task-detail-modal').style.display = 'block';
            } catch (e) {
                console.error('Error loading task detail:', e);
            }
        }

        function closeTaskDetailModal() {
            document.getElementById('collab-task-detail-modal').style.display = 'none';
        }

        async function collabTaskAction(taskId, action) {
            try {
                const resp = await fetch(`${API_BASE}/tasks/${taskId}/${action}`, {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({}),
                });
                if (!resp.ok) {
                    const err = await resp.json();
                    alert(err.error || err.reason || 'Action failed');
                    return;
                }
                closeTaskDetailModal();
                await loadCollabTasks();
            } catch (e) {
                console.error('Task action failed:', e);
            }
        }

        function showCreateTaskModal() {
            // Build agent options from cached data or fetch
            const agentSelect = document.getElementById('collab-task-agent-filter');
            const options = agentSelect ? agentSelect.innerHTML : '<option value="">No agents</option>';

            const modal = document.createElement('div');
            modal.id = 'collab-create-task-modal';
            modal.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:1000;overflow-y:auto;';
            modal.innerHTML = `
                <div style="max-width:500px;margin:80px auto;background:var(--bg-secondary);border-radius:12px;padding:32px;border:1px solid var(--border);">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
                        <h3 style="margin:0;">New Task</h3>
                        <button onclick="document.getElementById('collab-create-task-modal').remove()" style="background:none;border:none;color:var(--text-secondary);font-size:20px;cursor:pointer;">✕</button>
                    </div>
                    <div style="display:flex;flex-direction:column;gap:14px;">
                        <div>
                            <label style="display:block;margin-bottom:4px;font-size:13px;color:var(--text-secondary);">Title *</label>
                            <input type="text" id="new-task-title" style="width:100%;padding:10px;background:var(--bg-primary);color:var(--text-primary);border:1px solid var(--border);border-radius:6px;" placeholder="Task title">
                        </div>
                        <div>
                            <label style="display:block;margin-bottom:4px;font-size:13px;color:var(--text-secondary);">Assign To *</label>
                            <select id="new-task-agent" style="width:100%;padding:10px;background:var(--bg-primary);color:var(--text-primary);border:1px solid var(--border);border-radius:6px;">
                                ${options.replace('All Agents', 'Select agent')}
                            </select>
                        </div>
                        <div>
                            <label style="display:block;margin-bottom:4px;font-size:13px;color:var(--text-secondary);">Priority</label>
                            <input type="number" id="new-task-priority" value="0" min="0" max="10" style="width:100%;padding:10px;background:var(--bg-primary);color:var(--text-primary);border:1px solid var(--border);border-radius:6px;">
                        </div>
                        <button class="btn btn-primary" onclick="submitCreateTask()" style="margin-top:8px;padding:12px;font-weight:600;">Create Task</button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }

        async function submitCreateTask() {
            const title = document.getElementById('new-task-title')?.value?.trim();
            const agentId = document.getElementById('new-task-agent')?.value;
            const priority = parseInt(document.getElementById('new-task-priority')?.value || '0');

            if (!title) return alert('Title is required');
            if (!agentId) return alert('Please select an agent');

            try {
                const resp = await fetch(`${API_BASE}/tasks`, {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title,
                        assigned_to_agent_id: parseInt(agentId),
                        priority,
                    }),
                });
                if (!resp.ok) {
                    const err = await resp.json();
                    alert(err.error || 'Failed to create task');
                    return;
                }
                document.getElementById('collab-create-task-modal')?.remove();
                await loadCollabTasks();
            } catch (e) {
                console.error('Create task failed:', e);
            }
        }

        // =================================================================
        // COLLABORATION: TEAM TAB
        // =================================================================

        async function initCollabTeamTab() {
            await loadTeamRules();
            await loadTeamSummary();
            await populateTeamAgentSelects();
        }

        async function loadTeamRules() {
            try {
                const resp = await fetch(`${API_BASE}/team/rules`, { credentials: 'include' });
                if (!resp.ok) return;
                const data = await resp.json();
                const rules = data.rules || {};

                document.getElementById('collab-rule-enforce').checked = !!rules.require_supervisor_for_tasks;
                document.getElementById('collab-rule-peer').checked = !!rules.allow_peer_assignment;

                // Supervisor select will be populated by populateTeamAgentSelects
                const supSelect = document.getElementById('collab-rule-supervisor');
                if (supSelect) supSelect.dataset.pendingValue = rules.default_supervisor_agent_id || '';
            } catch (e) {
                console.error('Failed to load team rules:', e);
            }
        }

        async function saveTeamRules() {
            try {
                const enforce = document.getElementById('collab-rule-enforce').checked;
                const peer = document.getElementById('collab-rule-peer').checked;
                const supId = document.getElementById('collab-rule-supervisor').value;

                await fetch(`${API_BASE}/team/rules`, {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        require_supervisor_for_tasks: enforce,
                        allow_peer_assignment: peer,
                        default_supervisor_agent_id: supId ? parseInt(supId) : null,
                    }),
                });
            } catch (e) {
                console.error('Failed to save team rules:', e);
            }
        }

        async function populateTeamAgentSelects() {
            try {
                const resp = await fetch(`${API_BASE}/agents`, { credentials: 'include' });
                if (!resp.ok) return;
                const data = await resp.json();
                const agents = data.agents || [];

                // Role assignment agent select
                const roleSelect = document.getElementById('collab-role-agent');
                if (roleSelect) {
                    roleSelect.innerHTML = '<option value="">Select agent</option>' +
                        agents.map(a => `<option value="${a.id}">${a.name}</option>`).join('');
                }

                // Supervisor select (only show agents with supervisor role)
                const supResp = await fetch(`${API_BASE}/team/roles`, { credentials: 'include' });
                const supData = supResp.ok ? await supResp.json() : { roles: [] };
                const supervisors = (supData.roles || []).filter(r => r.role === 'supervisor');

                const supSelect = document.getElementById('collab-rule-supervisor');
                if (supSelect) {
                    const pending = supSelect.dataset.pendingValue;
                    supSelect.innerHTML = '<option value="">None</option>' +
                        supervisors.map(s => {
                            const agent = agents.find(a => a.id === s.agent_id);
                            const name = agent ? agent.name : `Agent #${s.agent_id}`;
                            return `<option value="${s.agent_id}">${name}</option>`;
                        }).join('');
                    if (pending) supSelect.value = pending;
                }
            } catch (e) {
                console.error('Failed to populate team agent selects:', e);
            }
        }

        async function assignAgentRole() {
            const agentId = document.getElementById('collab-role-agent')?.value;
            const role = document.getElementById('collab-role-type')?.value;

            if (!agentId) return alert('Please select an agent');

            try {
                const resp = await fetch(`${API_BASE}/team/roles`, {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ agent_id: parseInt(agentId), role }),
                });
                if (!resp.ok) {
                    const err = await resp.json();
                    alert(err.error || 'Failed to assign role');
                    return;
                }
                await loadTeamSummary();
                await populateTeamAgentSelects();
            } catch (e) {
                console.error('Assign role failed:', e);
            }
        }

        async function removeAgentRole(agentId) {
            try {
                await fetch(`${API_BASE}/team/roles/${agentId}/delete`, {
                    method: 'POST',
                    credentials: 'include',
                });
                await loadTeamSummary();
                await populateTeamAgentSelects();
            } catch (e) {
                console.error('Remove role failed:', e);
            }
        }

        async function loadTeamSummary() {
            try {
                const resp = await fetch(`${API_BASE}/team/summary`, { credentials: 'include' });
                if (!resp.ok) throw new Error('Failed');
                const data = await resp.json();

                const container = document.getElementById('collab-team-summary');
                if (!container) return;

                // Fetch agent names for display
                const agentResp = await fetch(`${API_BASE}/agents`, { credentials: 'include' });
                const agentData = agentResp.ok ? await agentResp.json() : { agents: [] };
                const agentMap = {};
                (agentData.agents || []).forEach(a => { agentMap[a.id] = a.name; });

                function renderRoleGroup(title, emoji, roles) {
                    if (roles.length === 0) return '';
                    return `
                        <div class="card" style="margin-bottom:12px; padding:16px;">
                            <h4 style="margin:0 0 10px;">${emoji} ${title} (${roles.length})</h4>
                            ${roles.map(r => `
                                <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid var(--border);">
                                    <div>
                                        <span style="font-weight:600; color:var(--text-primary);">${agentMap[r.agent_id] || 'Agent #' + r.agent_id}</span>
                                        <span style="font-size:12px; color:var(--text-secondary); margin-left:8px;">
                                            ${r.can_assign_to_peers ? 'peers' : ''}
                                            ${r.can_escalate_to_supervisor ? 'escalate' : ''}
                                        </span>
                                    </div>
                                    <button onclick="removeAgentRole(${r.agent_id})" style="background:none; border:1px solid var(--border); color:var(--text-secondary); padding:4px 10px; border-radius:6px; cursor:pointer; font-size:12px;">Remove</button>
                                </div>
                            `).join('')}
                        </div>
                    `;
                }

                const unassigned = data.unassigned_agents || [];
                let html = '';
                html += renderRoleGroup('Supervisors', '👑', data.supervisors || []);
                html += renderRoleGroup('Workers', '⚙️', data.workers || []);
                html += renderRoleGroup('Specialists', '🔬', data.specialists || []);

                if (unassigned.length > 0) {
                    html += `
                        <div class="card" style="padding:16px;">
                            <h4 style="margin:0 0 10px;">Unassigned (${unassigned.length})</h4>
                            ${unassigned.map(a => `
                                <div style="padding:6px 0; color:var(--text-secondary); font-size:14px;">
                                    ${a.name}
                                </div>
                            `).join('')}
                        </div>
                    `;
                }

                if (!html) {
                    html = `
                        <div style="text-align:center; padding:40px;">
                            <p style="font-size:48px; margin-bottom:16px;">👥</p>
                            <h3 style="color:var(--text-primary); margin-bottom:12px;">No team roles defined</h3>
                            <p style="color:var(--text-secondary);">Assign roles above to define your agent hierarchy.</p>
                        </div>
                    `;
                }

                container.innerHTML = html;
            } catch (e) {
                console.error('Failed to load team summary:', e);
                document.getElementById('collab-team-summary').innerHTML =
                    '<p style="text-align:center;color:#ef4444;padding:40px;">Failed to load team.</p>';
            }
        }
