"""
adapters — Thin wrappers around external service APIs.

Each adapter exposes action-oriented functions that accept plain data
(user_id + dict) and return (result_dict, error_string | None).
Adapters never mutate domain models directly.
"""
