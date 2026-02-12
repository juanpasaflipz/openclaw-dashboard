"""
Cost engine — centralized LLM token cost calculation.

All arithmetic uses Decimal to avoid float drift.
Pricing is loaded from DB with TTL-based in-memory caching.
Lookup uses longest-prefix matching to handle model version suffixes.
"""
import time
from decimal import Decimal, ROUND_HALF_UP
from datetime import date

from core.observability.constants import PRICING_CACHE_TTL

# Module-level cache (rebuilt on cold start in serverless)
_pricing_cache: dict[tuple[str, str], tuple[Decimal, Decimal]] = {}
_pricing_cache_ts: float = 0


_pricing_table_exists = None


def _load_pricing():
    """Load pricing from DB into module cache. Returns the cache dict."""
    global _pricing_cache, _pricing_cache_ts, _pricing_table_exists

    now = time.time()
    if _pricing_cache and (now - _pricing_cache_ts) < PRICING_CACHE_TTL:
        return _pricing_cache

    # Check if obs_llm_pricing table exists (cached after first check)
    if _pricing_table_exists is False:
        return _pricing_cache

    from models import db, ObsLlmPricing

    if _pricing_table_exists is None:
        try:
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            _pricing_table_exists = 'obs_llm_pricing' in inspector.get_table_names()
        except Exception:
            _pricing_table_exists = False
        if not _pricing_table_exists:
            return _pricing_cache

    try:
        today = date.today()
        rows = ObsLlmPricing.query.filter(
            ObsLlmPricing.effective_from <= today,
            db.or_(ObsLlmPricing.effective_to.is_(None), ObsLlmPricing.effective_to >= today),
        ).all()

        cache: dict[tuple[str, str], tuple[Decimal, Decimal]] = {}
        for r in rows:
            cache[(r.provider, r.model)] = (
                Decimal(str(r.input_cost_per_mtok)),
                Decimal(str(r.output_cost_per_mtok)),
            )

        _pricing_cache = cache
        _pricing_cache_ts = now
    except Exception:
        _pricing_table_exists = False

    return _pricing_cache


def invalidate_pricing_cache():
    """Force cache reload on next call. Useful after DB pricing updates."""
    global _pricing_cache, _pricing_cache_ts
    _pricing_cache = {}
    _pricing_cache_ts = 0


def calculate_cost(provider: str, model: str, tokens_in: int, tokens_out: int) -> Decimal:
    """
    Return estimated cost in USD as Decimal. Returns Decimal('0') if pricing not found.

    Lookup strategy:
    1. Exact match on (provider, model).
    2. Longest-prefix match: e.g. 'gpt-4o-mini-2024-07-18' matches 'gpt-4o-mini'.
    """
    pricing = _load_pricing()

    # 1. Exact match
    key = (provider, model)
    costs = pricing.get(key)

    # 2. Longest-prefix match (sorted by model name length descending)
    if costs is None and provider and model:
        best_match = None
        best_len = 0
        for (p, m), c in pricing.items():
            if p == provider and model.startswith(m) and len(m) > best_len:
                best_match = c
                best_len = len(m)
        costs = best_match

    if costs is None:
        return Decimal('0')

    input_cost_per_mtok, output_cost_per_mtok = costs
    tin = Decimal(str(tokens_in or 0))
    tout = Decimal(str(tokens_out or 0))

    cost = (tin * input_cost_per_mtok + tout * output_cost_per_mtok) / Decimal('1000000')
    return cost.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)


def calculate_cost_float(provider: str, model: str, tokens_in: int, tokens_out: int) -> float:
    """Convenience wrapper returning float. Use calculate_cost() for precision."""
    return float(calculate_cost(provider, model, tokens_in, tokens_out))
