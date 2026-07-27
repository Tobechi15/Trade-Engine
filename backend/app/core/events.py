from enum import StrEnum


class EventType(StrEnum):
    # Market events
    NEW_CANDLE = "NEW_CANDLE"
    NEW_QUOTE = "NEW_QUOTE"
    VOLUME_UPDATE = "VOLUME_UPDATE"
    MARKET_STATUS = "MARKET_STATUS"
    MARKET_OPEN = "MARKET_OPEN"
    MARKET_CLOSE = "MARKET_CLOSE"
    OPENING_RANGE_READY = "OPENING_RANGE_READY"
    ORB_CUTOFF = "ORB_CUTOFF"
    CLOSING_BIAS_START = "CLOSING_BIAS_START"

    # Strategy events
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    SIGNAL_REJECTED = "SIGNAL_REJECTED"
    TRADE_ENTERED = "TRADE_ENTERED"
    TRADE_EXITED = "TRADE_EXITED"

    # Risk events
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    DAILY_LOSS_HIT = "DAILY_LOSS_HIT"
    MAX_EXPOSURE_HIT = "MAX_EXPOSURE_HIT"
    MARGIN_WARNING = "MARGIN_WARNING"
    TRADING_DISABLED = "TRADING_DISABLED"

    # Order events
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_PARTIALLY_FILLED = "ORDER_PARTIALLY_FILLED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_REJECTED = "ORDER_REJECTED"

    # Position events
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_UPDATED = "POSITION_UPDATED"
    POSITION_CLOSED = "POSITION_CLOSED"

    # Recovery events
    RECOVERY_STARTED = "RECOVERY_STARTED"
    RECOVERY_COMPLETED = "RECOVERY_COMPLETED"
    RECOVERY_FAILED = "RECOVERY_FAILED"
    BROKER_RECONNECTED = "BROKER_RECONNECTED"
    MARKET_DATA_RECONNECTED = "MARKET_DATA_RECONNECTED"
    STATE_RESTORED = "STATE_RESTORED"

    # System events
    ENGINE_STARTED = "ENGINE_STARTED"
    ENGINE_STOPPED = "ENGINE_STOPPED"
    ENGINE_PAUSED = "ENGINE_PAUSED"
    ENGINE_RESUMED = "ENGINE_RESUMED"

    # Notification events
    INFO_NOTIFICATION = "INFO_NOTIFICATION"
    WARNING_NOTIFICATION = "WARNING_NOTIFICATION"
    ERROR_NOTIFICATION = "ERROR_NOTIFICATION"
    CRITICAL_NOTIFICATION = "CRITICAL_NOTIFICATION"


# Only these event types are persisted (per EVENT_BUS.md). Everything else is
# transient / in-memory only.
PERSISTED_EVENT_TYPES: frozenset[EventType] = frozenset(
    {
        EventType.SIGNAL_GENERATED,
        EventType.SIGNAL_REJECTED,
        EventType.TRADE_ENTERED,
        EventType.TRADE_EXITED,
        EventType.ORDER_FILLED,
        EventType.RISK_REJECTED,
        EventType.DAILY_LOSS_HIT,
        EventType.RECOVERY_FAILED,
    }
)

# WebSocket channels exposed to the dashboard (ENGINE_API.md).
WEBSOCKET_CHANNELS: frozenset[str] = frozenset(
    {
        "engine",
        "scanner",
        "orders",
        "positions",
        "portfolio",
        "strategies",
        "analytics",
        "logs",
        "notifications",
        "recovery",
    }
)

# Maps each event type to the dashboard WebSocket channel(s) it should be
# rebroadcast on.
EVENT_TO_CHANNELS: dict[EventType, tuple[str, ...]] = {
    EventType.NEW_CANDLE: ("scanner",),
    EventType.NEW_QUOTE: ("scanner",),
    EventType.VOLUME_UPDATE: ("scanner",),
    EventType.MARKET_STATUS: ("engine",),
    EventType.MARKET_OPEN: ("engine", "strategies"),
    EventType.MARKET_CLOSE: ("engine", "strategies"),
    EventType.OPENING_RANGE_READY: ("strategies", "scanner"),
    EventType.ORB_CUTOFF: ("strategies",),
    EventType.CLOSING_BIAS_START: ("strategies",),
    EventType.SIGNAL_GENERATED: ("strategies", "scanner", "logs"),
    EventType.SIGNAL_REJECTED: ("strategies", "logs"),
    EventType.TRADE_ENTERED: ("portfolio", "analytics"),
    EventType.TRADE_EXITED: ("portfolio", "analytics", "logs"),
    EventType.RISK_APPROVED: ("orders",),
    EventType.RISK_REJECTED: ("logs", "notifications"),
    EventType.DAILY_LOSS_HIT: ("strategies", "notifications"),
    EventType.MAX_EXPOSURE_HIT: ("strategies",),
    EventType.MARGIN_WARNING: ("notifications",),
    EventType.TRADING_DISABLED: ("engine", "notifications"),
    EventType.ORDER_SUBMITTED: ("orders",),
    EventType.ORDER_FILLED: ("orders", "positions"),
    EventType.ORDER_PARTIALLY_FILLED: ("orders",),
    EventType.ORDER_CANCELLED: ("orders",),
    EventType.ORDER_REJECTED: ("orders", "logs"),
    EventType.POSITION_OPENED: ("positions", "portfolio"),
    EventType.POSITION_UPDATED: ("positions", "portfolio"),
    EventType.POSITION_CLOSED: ("positions", "portfolio", "analytics"),
    EventType.RECOVERY_STARTED: ("recovery", "notifications"),
    EventType.RECOVERY_COMPLETED: ("recovery", "notifications"),
    EventType.RECOVERY_FAILED: ("recovery", "notifications"),
    EventType.BROKER_RECONNECTED: ("recovery", "notifications"),
    EventType.MARKET_DATA_RECONNECTED: ("recovery", "notifications"),
    EventType.STATE_RESTORED: ("recovery",),
    EventType.ENGINE_STARTED: ("engine",),
    EventType.ENGINE_STOPPED: ("engine",),
    EventType.ENGINE_PAUSED: ("engine",),
    EventType.ENGINE_RESUMED: ("engine",),
    EventType.INFO_NOTIFICATION: ("notifications",),
    EventType.WARNING_NOTIFICATION: ("notifications",),
    EventType.ERROR_NOTIFICATION: ("notifications",),
    EventType.CRITICAL_NOTIFICATION: ("notifications",),
}
