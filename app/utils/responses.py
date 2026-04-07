from typing import Any


def ok(data: Any = None) -> dict[str, Any]:
    return {"success": True, "data": data}


def err(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details
    return {"success": False, "error": body}
