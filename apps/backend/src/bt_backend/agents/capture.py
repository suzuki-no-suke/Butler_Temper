"""SDK が実際に送受信した HTTP の中身を記録する httpx クライアント。"""

import json
from datetime import UTC, datetime
from typing import Any

import httpx2

# 記録してよいヘッダー（API キーを含むヘッダーは記録しない）
_SAFE_HEADERS = {
    "content-type",
    "anthropic-version",
    "anthropic-beta",
    "request-id",
    "x-request-id",
}


def _body(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return raw.decode("utf-8", errors="replace")


def _headers(headers: httpx2.Headers) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() in _SAFE_HEADERS}


def capturing_client(
    timeout: float = 600.0, transport: httpx2.BaseTransport | None = None
) -> tuple[httpx2.Client, list[dict[str, Any]]]:
    exchanges: list[dict[str, Any]] = []

    def on_request(request: httpx2.Request) -> None:
        exchanges.append(
            {
                "sent_at": datetime.now(UTC).isoformat(),
                "method": request.method,
                # クエリに API キーが入る API があるため、クエリは記録しない
                "url": str(request.url.copy_with(query=None)),
                "request_headers": _headers(request.headers),
                "request": _body(request.content),
            }
        )

    def on_response(response: httpx2.Response) -> None:
        response.read()
        exchanges[-1].update(
            {
                "received_at": datetime.now(UTC).isoformat(),
                "status": response.status_code,
                "response_headers": _headers(response.headers),
                "response": _body(response.content),
            }
        )

    client = httpx2.Client(
        timeout=timeout,
        transport=transport,
        event_hooks={"request": [on_request], "response": [on_response]},
    )
    return client, exchanges
