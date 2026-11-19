"""Zero-install ASGI Gzip reverse proxy and bundled font-display rewriter for Streamlit."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import os
from urllib.parse import urlparse, urlunparse

import httpx
from starlette.applications import Starlette
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect
import uvicorn
import websockets
from websockets.exceptions import ConnectionClosed

UPSTREAM_URL = os.environ.get("UPSTREAM_URL", "http://127.0.0.1:8501").rstrip("/")
PROXY_HOST = os.environ.get("PROXY_HOST", "127.0.0.1")
PROXY_PORT = int(os.environ.get("PROXY_PORT", "8080"))

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
    "content-encoding",
}
_WS_SKIP_HEADERS = _HOP_BY_HOP | {
    "sec-websocket-key",
    "sec-websocket-version",
    "sec-websocket-extensions",
    "sec-websocket-protocol",
}


def _upstream_ws_url(base_http_url: str, path: str, query: str) -> str:
    """Convert an HTTP upstream URL into its matching ws:// or wss:// target URL."""
    parsed = urlparse(base_http_url)
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    base_path = parsed.path.rstrip("/")
    full_path = f"{base_path}{path}" if path.startswith("/") else f"{base_path}/{path}"
    return urlunparse((ws_scheme, parsed.netloc, full_path, "", query, ""))


def _rewrite_bundled_css(path: str, status_code: int, body: bytes) -> bytes:
    """Inject font-display:swap for Source variable fonts while leaving Material Symbols intact."""
    if status_code == 200 and path.startswith("/static/css/") and path.endswith(".css"):
        return body.replace(
            b"@font-face{font-family:Source ",
            b"@font-face{font-display:swap;font-family:Source ",
        )
    return body


def create_proxy_app(upstream_url: str = UPSTREAM_URL) -> Starlette:
    """Construct the Starlette Gzip reverse-proxy ASGI app targeting `upstream_url`."""
    clean_upstream = upstream_url.rstrip("/")

    @asynccontextmanager
    async def lifespan(app: Starlette):
        app.state.http_client = httpx.AsyncClient(
            base_url=clean_upstream,
            follow_redirects=False,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
        try:
            yield
        finally:
            await app.state.http_client.aclose()

    async def proxy_http(request: Request) -> Response:
        client: httpx.AsyncClient = request.app.state.http_client
        req_headers = [
            (k, v)
            for k, v in request.headers.raw
            if k.decode("latin-1").lower() not in _HOP_BY_HOP | {"accept-encoding"}
        ]
        target = request.url.path
        if request.url.query:
            target = f"{target}?{request.url.query}"

        req_body = await request.body()
        upstream_resp = await client.request(
            method=request.method,
            url=target,
            headers=req_headers,
            content=req_body,
        )

        body = _rewrite_bundled_css(request.url.path, upstream_resp.status_code, upstream_resp.content)
        resp = Response(content=body, status_code=upstream_resp.status_code)
        for name, value in upstream_resp.headers.multi_items():
            lower_name = name.lower()
            if lower_name in _HOP_BY_HOP:
                continue
            if lower_name == "cache-control" and request.url.path.startswith("/static/") and upstream_resp.status_code == 200:
                continue
            resp.headers.append(name, value)

        if upstream_resp.status_code == 200 and request.url.path.startswith("/static/"):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp

    async def proxy_ws(websocket: WebSocket) -> None:
        raw_subprotocols = websocket.headers.get("sec-websocket-protocol", "")
        subprotocols = [s.strip() for s in raw_subprotocols.split(",") if s.strip()]
        fwd_headers = {
            k: v
            for k, v in websocket.headers.items()
            if k.lower() not in _WS_SKIP_HEADERS
        }
        ws_url = _upstream_ws_url(clean_upstream, websocket.url.path, websocket.url.query)

        try:
            async with websockets.connect(
                ws_url,
                subprotocols=subprotocols or None,
                additional_headers=fwd_headers,
                max_size=None,
            ) as upstream_ws:
                await websocket.accept(subprotocol=upstream_ws.subprotocol)

                async def client_to_upstream() -> None:
                    while True:
                        msg = await websocket.receive()
                        if msg["type"] == "websocket.disconnect":
                            await upstream_ws.close()
                            return
                        if msg.get("text") is not None:
                            await upstream_ws.send(msg["text"])
                        elif msg.get("bytes") is not None:
                            await upstream_ws.send(msg["bytes"])

                async def upstream_to_client() -> None:
                    async for payload in upstream_ws:
                        if isinstance(payload, bytes):
                            await websocket.send_bytes(payload)
                        else:
                            await websocket.send_text(payload)

                tasks = [
                    asyncio.create_task(client_to_upstream()),
                    asyncio.create_task(upstream_to_client()),
                ]
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    exc = task.exception()
                    if exc is not None and not isinstance(exc, (WebSocketDisconnect, ConnectionClosed)):
                        raise exc
        except (WebSocketDisconnect, ConnectionClosed):
            return

    routes = [
        WebSocketRoute("/{path:path}", proxy_ws),
        Route(
            "/{path:path}",
            proxy_http,
            methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        ),
    ]
    app = Starlette(routes=routes, lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=6)
    return app


app = create_proxy_app()

if __name__ == "__main__":
    uvicorn.run(app, host=PROXY_HOST, port=PROXY_PORT, log_level="warning")
