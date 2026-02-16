# PY314 bootstrap — must run before third-party async libs
from src.runtime.asyncio_runtime import ensure_event_loop  # noqa: F401
