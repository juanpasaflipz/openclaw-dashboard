"""
Context Window Guard — token counting and message trimming.

Prevents LLM calls from exceeding model context limits by:
1. Counting tokens per message (tiktoken for OpenAI, char-estimate for others)
2. Trimming oldest non-system messages to stay within budget
3. Reserving 25% of context for response + tools
"""

# Model context limits (max input tokens)
MODEL_CONTEXT_LIMITS = {
    # OpenAI
    'gpt-4o': 128_000,
    'gpt-4o-mini': 128_000,
    'gpt-4-turbo': 128_000,
    'gpt-4': 8_192,
    'gpt-3.5-turbo': 16_385,
    # Anthropic
    'claude-sonnet-4-5-20250929': 200_000,
    'claude-3-5-sonnet-20241022': 200_000,
    'claude-3-5-haiku-20241022': 200_000,
    'claude-3-opus-20240229': 200_000,
    # Google
    'gemini-2.0-flash': 1_048_576,
    'gemini-1.5-pro': 2_097_152,
    'gemini-1.5-flash': 1_048_576,
    # Groq
    'llama-3.3-70b-versatile': 131_072,
    'llama-3.1-8b-instant': 131_072,
    'mixtral-8x7b-32768': 32_768,
    'gemma2-9b-it': 8_192,
    # Mistral
    'mistral-large-latest': 128_000,
    'mistral-medium-latest': 32_000,
    'mistral-small-latest': 32_000,
    'open-mistral-7b': 32_000,
    # xAI
    'grok-4-1-fast-reasoning': 131_072,
    'grok-3-fast': 131_072,
    'grok-3-mini-fast': 131_072,
    'grok-2-latest': 131_072,
    # Together / OpenRouter — use conservative defaults
    'meta-llama/Llama-3.3-70B-Instruct-Turbo': 131_072,
    # Cohere
    'command-r-plus': 128_000,
    'command-r': 128_000,
    'command-light': 4_096,
}

DEFAULT_CONTEXT_LIMIT = 32_000  # Fallback for unknown models
KEEP_RECENT_MESSAGES = 10       # Always keep this many recent messages
MAX_RATIO = 0.75                # Use at most 75% of context for input

# Lazy-loaded tiktoken encoding
_tiktoken_encoding = None


def _get_tiktoken_encoding():
    """Lazy-load tiktoken cl100k_base encoding (used by GPT-4o, GPT-4, etc.)."""
    global _tiktoken_encoding
    if _tiktoken_encoding is None:
        try:
            import tiktoken
            _tiktoken_encoding = tiktoken.get_encoding('cl100k_base')
        except ImportError:
            _tiktoken_encoding = False  # Sentinel: tiktoken not installed
    return _tiktoken_encoding


def _is_openai_model(model):
    """Check if a model uses tiktoken-compatible tokenization."""
    if not model:
        return False
    lower = model.lower()
    return any(lower.startswith(p) for p in ('gpt-', 'o1-', 'o3-'))


def count_tokens(text, model=None):
    """Count tokens in a text string.

    Uses tiktoken for OpenAI models, character-based estimate for others.
    """
    if not text:
        return 0

    if model and _is_openai_model(model):
        enc = _get_tiktoken_encoding()
        if enc and enc is not False:
            return len(enc.encode(text))

    # Char-based estimate: ~4 chars per token (conservative)
    return max(1, len(text) // 4)


def count_message_tokens(messages, model=None):
    """Sum token counts across all messages.

    Each message costs ~4 tokens of overhead (role, separators).
    """
    total = 0
    for msg in messages:
        content = msg.get('content', '')
        if isinstance(content, list):
            # Structured content (Anthropic tool_result blocks, etc.)
            for block in content:
                if isinstance(block, dict):
                    total += count_tokens(block.get('text', '') or block.get('content', '') or str(block), model)
                else:
                    total += count_tokens(str(block), model)
        elif isinstance(content, str):
            total += count_tokens(content, model)
        total += 4  # Per-message overhead
    return total


def get_context_limit(model):
    """Get the context limit for a model."""
    if model in MODEL_CONTEXT_LIMITS:
        return MODEL_CONTEXT_LIMITS[model]

    # Try prefix matching for versioned model names
    lower = model.lower() if model else ''
    for key, limit in MODEL_CONTEXT_LIMITS.items():
        if lower.startswith(key.lower()):
            return limit

    return DEFAULT_CONTEXT_LIMIT


def trim_messages(messages, model=None, max_ratio=MAX_RATIO):
    """Trim messages to fit within the model's context window.

    Strategy:
    - Always keep system prompt (first message if role=system)
    - Always keep the last KEEP_RECENT_MESSAGES messages
    - Drop oldest non-system messages until within budget
    - Budget = context_limit * max_ratio

    Returns the trimmed message list (new list, does not mutate input).
    """
    if not messages:
        return messages

    context_limit = get_context_limit(model)
    budget = int(context_limit * max_ratio)

    # Check if already within budget
    current_tokens = count_message_tokens(messages, model)
    if current_tokens <= budget:
        return messages

    # Separate system prompt from conversation messages
    system_msgs = []
    conv_msgs = []
    for msg in messages:
        if msg.get('role') == 'system' and not conv_msgs:
            system_msgs.append(msg)
        else:
            conv_msgs.append(msg)

    # Tokens used by system prompt (always kept)
    system_tokens = count_message_tokens(system_msgs, model)

    # Tokens available for conversation messages
    conv_budget = budget - system_tokens
    if conv_budget <= 0:
        # System prompt alone exceeds budget — return system + last message only
        return system_msgs + conv_msgs[-1:] if conv_msgs else system_msgs

    # Always keep the last N messages (recent context is most valuable)
    keep_count = min(KEEP_RECENT_MESSAGES, len(conv_msgs))
    recent_msgs = conv_msgs[-keep_count:] if keep_count > 0 else []
    older_msgs = conv_msgs[:-keep_count] if keep_count > 0 and keep_count < len(conv_msgs) else []

    recent_tokens = count_message_tokens(recent_msgs, model)

    if recent_tokens >= conv_budget:
        # Even recent messages exceed budget — keep as many recent as possible
        trimmed_recent = []
        running = 0
        for msg in reversed(recent_msgs):
            msg_tokens = count_message_tokens([msg], model)
            if running + msg_tokens > conv_budget:
                break
            trimmed_recent.insert(0, msg)
            running += msg_tokens
        return system_msgs + trimmed_recent

    # Fill remaining budget with older messages (most recent first)
    remaining_budget = conv_budget - recent_tokens
    kept_older = []
    for msg in reversed(older_msgs):
        msg_tokens = count_message_tokens([msg], model)
        if remaining_budget - msg_tokens < 0:
            break
        kept_older.insert(0, msg)
        remaining_budget -= msg_tokens

    return system_msgs + kept_older + recent_msgs
