class ProviderAuthError(RuntimeError):
    """Raised when a broker/market-data provider rejects authentication, or
    reports that a requested feature isn't available on the current
    plan/account (e.g. a 401/403, or an explicit "not entitled" response).

    This is not a transient connectivity blip - retrying every few seconds
    will never succeed until a human fixes the credentials or upgrades the
    plan. RecoveryService backs off much longer for this class of error
    than for an ordinary dropped connection, and callers that have a
    static fallback (e.g. AlpacaMarketData.get_active_symbols) should use
    it instead of raising.
    """
