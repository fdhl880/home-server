"""
Pyrofuel v3 Atomic Execution Engine & Real-Time Microstructure Routing Package.
"""
from exec.avellaneda_router import AvellanedaStoikovRouter
from exec.engine import AtomicExecutionEngineV3, generate_client_order_id
from exec.event_bus import (
    CLOSED_CANDLE_BOUNDARY_SCAN,
    CRITICAL_POSITION_INTERRUPT,
    MICROSTRUCTURE_SNIPER_TRIGGER,
    BusEvent,
    EventPriority,
    PriorityEventBus,
)
from exec.native_pricematch import (
    NativePriceMatchRouter,
    build_fallback_gtx_params,
    build_native_pricematch_params,
)
from exec.thesis_monitor import IntrabarThesisMonitor
from exec.userstream import UserDataStreamManager

__all__ = [
    "AtomicExecutionEngineV3",
    "AvellanedaStoikovRouter",
    "BusEvent",
    "CLOSED_CANDLE_BOUNDARY_SCAN",
    "CRITICAL_POSITION_INTERRUPT",
    "EventPriority",
    "IntrabarThesisMonitor",
    "MICROSTRUCTURE_SNIPER_TRIGGER",
    "NativePriceMatchRouter",
    "PriorityEventBus",
    "UserDataStreamManager",
    "build_fallback_gtx_params",
    "build_native_pricematch_params",
    "generate_client_order_id",
]
