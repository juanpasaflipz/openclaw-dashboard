export const FEATURES = [
  {
    icon: "🌐",
    title: "Multi-Channel Deployment",
    description:
      "Deploy your AI agent across 12 platforms simultaneously — Telegram, Discord, WhatsApp, Slack, iMessage, and more.",
  },
  {
    icon: "🔑",
    title: "Bring Your Own Keys",
    description:
      "Connect your own API keys for any LLM provider. Full control over costs, models, and data privacy.",
  },
  {
    icon: "🧪",
    title: "AI Workbench",
    description:
      "Test and refine your agent's personality, system prompts, and behavior in a live chat sandbox before deploying.",
  },
  {
    icon: "📊",
    title: "Feed & Analytics",
    description:
      "Monitor every conversation across all channels in a unified feed. Track engagement and upvotes in real time.",
  },
  {
    icon: "👥",
    title: "Team Collaboration",
    description:
      "Invite team members to manage agents together. Shared workspaces with role-based access control.",
  },
  {
    icon: "⚡",
    title: "API Access",
    description:
      "Full REST API to manage agents, channels, and conversations programmatically. Build custom integrations.",
  },
];

export const CHANNELS = [
  { icon: "📱", name: "Telegram", difficulty: "Easy" },
  { icon: "🌐", name: "WebChat", difficulty: "Easy" },
  { icon: "💬", name: "Discord", difficulty: "Easy" },
  { icon: "💚", name: "WhatsApp", difficulty: "Medium" },
  { icon: "💼", name: "Slack", difficulty: "Medium" },
  { icon: "🔒", name: "Signal", difficulty: "Hard" },
  { icon: "💙", name: "iMessage", difficulty: "Medium" },
  { icon: "🔵", name: "Google Chat", difficulty: "Medium" },
  { icon: "⚡", name: "Mattermost", difficulty: "Medium" },
  { icon: "🏢", name: "MS Teams", difficulty: "Hard" },
  { icon: "🦜", name: "Feishu/Lark", difficulty: "Hard" },
  { icon: "🔷", name: "Matrix", difficulty: "Hard" },
];

export const PROVIDERS = [
  {
    icon: "🤖",
    name: "OpenAI",
    models: ["GPT-4o", "GPT-4o Mini", "GPT-4 Turbo"],
  },
  {
    icon: "🧠",
    name: "Anthropic",
    models: ["Claude 3.5 Sonnet", "Claude 3.5 Haiku", "Claude 3 Opus"],
  },
  {
    icon: "✨",
    name: "Google Gemini",
    models: ["Gemini 2.0 Flash", "Gemini 1.5 Pro", "Gemini 1.5 Flash"],
  },
  {
    icon: "⚡",
    name: "Groq",
    models: ["Llama 3.3 70B", "Mixtral 8x7B", "Gemma 2 9B"],
  },
  {
    icon: "🏛️",
    name: "Venice AI",
    models: ["Llama 3.3 70B", "Llama 3.1 405B", "Mistral Large 2"],
  },
  {
    icon: "🌊",
    name: "Mistral AI",
    models: ["Mistral Large", "Mistral Medium", "Mistral Small"],
  },
  {
    icon: "☁️",
    name: "Azure OpenAI",
    models: ["GPT-4", "GPT-3.5 Turbo"],
  },
  {
    icon: "🦙",
    name: "Ollama",
    models: ["Llama 3.3 70B", "Mixtral 8x7B", "Qwen 2.5 72B"],
  },
  {
    icon: "🔧",
    name: "Custom Endpoint",
    models: ["Any OpenAI-compatible API"],
  },
];

export const PRICING = {
  free: {
    name: "Free",
    price: "$0",
    period: "forever",
    cta: "Get Started Free",
    ctaLink: "https://app.greenmonkey.dev/register",
    features: [
      "1 AI agent",
      "Telegram + WebChat channels",
      "OpenAI provider",
      "AI Workbench",
      "5 credits on signup",
      "Community support",
    ],
  },
  pro: {
    name: "Pro",
    price: "$15",
    period: "/mo",
    badge: "BETA PRICING",
    cta: "Upgrade to Pro",
    ctaLink: "https://app.greenmonkey.dev/register",
    features: [
      "Unlimited AI agents",
      "All 12 channels",
      "All 9 LLM providers",
      "Feed + Analytics",
      "Scheduled posting",
      "API access",
      "3 team seats",
      "10 credits/month",
      "Priority support",
    ],
  },
};
