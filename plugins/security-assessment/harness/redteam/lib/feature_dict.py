"""feature_dict — curated fraud-detection feature dictionary.

Used by `02_schema_discovery.py` as the brute-force fallback when no OpenAPI
spec is available. Ten categories × ~20 features each, covering common
fraud-scoring feature surfaces.

This list is a starting point — projects extend via PRs. Category names are
stable; they flow through to prompt 02's output.
"""
from __future__ import annotations

FEATURE_CANDIDATES: dict[str, list[str]] = {
    "transaction": [
        "amount", "currency", "transaction_type", "mcc", "mcc_code",
        "transaction_id", "reference_number", "status", "auth_code",
        "installments", "processing_code", "purpose", "narration",
    ],
    "card_account": [
        "card_hash", "card_last4", "card_bin", "card_type", "card_brand",
        "card_country", "account_id", "account_type", "account_age_days",
        "card_present", "card_entry_mode", "emv_cvm", "tokenized",
    ],
    "merchant": [
        "merchant_id", "merchant_name", "merchant_country", "merchant_category",
        "merchant_mcc", "merchant_risk_tier", "acquirer_id", "terminal_id",
        "merchant_age_days", "merchant_chargeback_rate",
    ],
    "temporal": [
        "timestamp", "hour_of_day", "day_of_week", "is_weekend", "is_holiday",
        "time_since_last_tx", "tx_age_seconds", "local_time", "timezone_offset",
    ],
    "geolocation": [
        "country_code", "region", "city", "postal_code", "lat", "lon",
        "ip_country", "ip_asn", "ip_is_proxy", "ip_is_tor", "distance_from_home_km",
        "bin_country_match",
    ],
    "velocity_aggregates": [
        "velocity_1h", "velocity_24h", "velocity_7d", "velocity_30d",
        "count_1h", "count_24h", "sum_amount_1h", "sum_amount_24h",
        "distinct_merchants_24h", "distinct_countries_24h", "avg_amount_30d",
        "max_amount_30d", "last_24h", "last_1h",
    ],
    "device_digital": [
        "device_id", "device_fingerprint", "user_agent", "browser", "os",
        "device_risk_score", "screen_resolution", "timezone", "language",
        "is_new_device", "device_age_days",
    ],
    "risk_indicators": [
        "risk_score_provider_a", "risk_score_provider_b", "velocity_flag",
        "blacklist_flag", "watchlist_flag", "prior_chargebacks", "prior_disputes",
        "prior_fraud", "cvv_match", "avs_match", "avs_result",
    ],
    "client_routing": [
        "client_id", "tenant_id", "channel", "product_id", "campaign_id",
        "referrer", "origin_domain", "api_version", "partner_id",
    ],
    "authentication": [
        "auth_method", "3ds_version", "3ds_result", "otp_used", "biometric_used",
        "session_age_seconds", "login_count_24h", "mfa_enabled",
    ],
}


def all_features() -> list[str]:
    """Flat list of every feature across every category."""
    return [f for group in FEATURE_CANDIDATES.values() for f in group]


def category_for(feature: str) -> str | None:
    """Return the category a feature belongs to, or None if unknown."""
    for cat, feats in FEATURE_CANDIDATES.items():
        if feature in feats:
            return cat
    return None
