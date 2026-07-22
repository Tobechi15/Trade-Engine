from __future__ import annotations

from typing import Any


def ok(data: Any = None) -> dict:
    return {"success": True, "data": data if data is not None else {}}


def err(code: str, message: str) -> dict:
    return {"success": False, "error": {"code": code, "message": message}}
