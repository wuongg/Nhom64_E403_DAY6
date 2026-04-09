from __future__ import annotations

import inspect
import json
import re
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from functools import partial
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Iterable
from urllib.parse import parse_qs

import anyio
import httpx
from pydantic import BaseModel


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: Any = None, headers: dict[str, str] | None = None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.headers = headers or {}


class Depends:
    def __init__(self, dependency: Callable[..., Any]):
        self.dependency = dependency


class Response:
    def __init__(
        self,
        content: bytes | str | None = b"",
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        media_type: str = "text/plain; charset=utf-8",
    ):
        self.status_code = status_code
        self.headers = headers or {}
        self.media_type = media_type
        if content is None:
            self.body = b""
        elif isinstance(content, bytes):
            self.body = content
        else:
            self.body = content.encode("utf-8")

    async def __call__(self, scope: dict[str, Any], receive: Callable[[], Awaitable[dict[str, Any]]], send: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        headers = [(b"content-type", self.media_type.encode("utf-8"))]
        for key, value in self.headers.items():
            headers.append((key.lower().encode("utf-8"), str(value).encode("utf-8")))
        await send({"type": "http.response.start", "status": self.status_code, "headers": headers})
        await send({"type": "http.response.body", "body": self.body})


class JSONResponse(Response):
    def __init__(
        self,
        content: Any,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(
            content=json.dumps(to_jsonable(content), ensure_ascii=False, separators=(",", ":")),
            status_code=status_code,
            headers=headers,
            media_type="application/json; charset=utf-8",
        )


class Request:
    def __init__(self, app: "FastAPI", scope: dict[str, Any], receive: Callable[[], Awaitable[dict[str, Any]]]):
        self.app = app
        self.scope = scope
        self._receive = receive
        self._body_cache: bytes | None = None
        self.state = app.state
        self.path_params = scope.get("path_params", {})
        self.method = scope.get("method", "GET").upper()
        self.url = SimpleNamespace(path=scope.get("path", "/"), query=scope.get("query_string", b""))
        self.headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        query_string = scope.get("query_string", b"").decode("utf-8")
        self.query_params = {k: v[-1] for k, v in parse_qs(query_string, keep_blank_values=True).items()}

    async def body(self) -> bytes:
        if self._body_cache is not None:
            return self._body_cache

        chunks: list[bytes] = []
        while True:
            message = await self._receive()
            if message["type"] != "http.request":
                continue
            body = message.get("body", b"")
            if body:
                chunks.append(body)
            if not message.get("more_body", False):
                break
        self._body_cache = b"".join(chunks)
        return self._body_cache

    async def json(self) -> Any:
        raw = await self.body()
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))


class Route:
    def __init__(self, methods: set[str], path: str, handler: Callable[..., Any], name: str | None = None):
        self.methods = {method.upper() for method in methods}
        self.path = path
        self.handler = handler
        self.name = name or getattr(handler, "__name__", "route")
        self.regex, self.param_names = compile_path(path)


def compile_path(path: str) -> tuple[re.Pattern[str], list[str]]:
    param_names: list[str] = []

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        param_names.append(name)
        return f"(?P<{name}>[^/]+)"

    pattern = "^" + re.sub(r"{([^}]+)}", repl, path.rstrip("/")) + "/?$"
    return re.compile(pattern), param_names


def to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "isoformat") and callable(getattr(value, "isoformat")):
        try:
            return value.isoformat()
        except Exception:
            pass
    return value


class APIRouter:
    def __init__(self, prefix: str = ""):
        self.prefix = prefix.rstrip("/")
        self.routes: list[Route] = []

    def add_api_route(self, path: str, endpoint: Callable[..., Any], methods: Iterable[str], name: str | None = None, **_: Any) -> Callable[..., Any]:
        full_path = self._join(path)
        self.routes.append(Route(set(methods), full_path, endpoint, name=name))
        return endpoint

    def get(self, path: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return partial(self.add_api_route, path, methods=["GET"], **kwargs)

    def post(self, path: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return partial(self.add_api_route, path, methods=["POST"], **kwargs)

    def _join(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        if not self.prefix:
            return path
        return self.prefix + path


class CORSMiddleware:
    def __init__(
        self,
        app: Any,
        allow_origins: list[str] | tuple[str, ...] | None = None,
        allow_methods: list[str] | tuple[str, ...] | None = None,
        allow_headers: list[str] | tuple[str, ...] | None = None,
        allow_credentials: bool = False,
    ):
        self.app = app
        self.allow_origins = list(allow_origins or [])
        self.allow_methods = [method.upper() for method in (allow_methods or ["*"])]
        self.allow_headers = [header.lower() for header in (allow_headers or ["*"])]
        self.allow_credentials = allow_credentials


class FastAPI:
    def __init__(self, *, lifespan: Callable[["FastAPI"], Any] | None = None, title: str | None = None, version: str | None = None, **_: Any):
        self.title = title or "FastAPI"
        self.version = version or "0.1.0"
        self.state = SimpleNamespace()
        self.routes: list[Route] = []
        self._lifespan_factory = lifespan
        self._lifespan_cm = None
        self._started = False
        self._cors: dict[str, Any] | None = None

    def add_middleware(self, middleware_class: type[Any], **options: Any) -> None:
        if middleware_class is not CORSMiddleware:
            raise RuntimeError("This lightweight app only supports CORSMiddleware")
        self._cors = options

    def include_router(self, router: APIRouter, **_: Any) -> None:
        self.routes.extend(router.routes)

    def add_api_route(self, path: str, endpoint: Callable[..., Any], methods: Iterable[str], name: str | None = None, **kwargs: Any) -> Callable[..., Any]:
        route = Route(set(methods), path, endpoint, name=name)
        self.routes.append(route)
        return endpoint

    def get(self, path: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return partial(self.add_api_route, path, methods=["GET"], **kwargs)

    def post(self, path: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return partial(self.add_api_route, path, methods=["POST"], **kwargs)

    async def startup(self) -> None:
        if self._started:
            return
        if self._lifespan_factory is not None:
            self._lifespan_cm = self._lifespan_factory(self)
            await self._lifespan_cm.__aenter__()
        self._started = True

    async def shutdown(self) -> None:
        if not self._started:
            return
        if self._lifespan_cm is not None:
            await self._lifespan_cm.__aexit__(None, None, None)
            self._lifespan_cm = None
        self._started = False

    async def __call__(self, scope: dict[str, Any], receive: Callable[[], Awaitable[dict[str, Any]]], send: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        scope_type = scope.get("type")
        if scope_type == "lifespan":
            await self._handle_lifespan(receive, send)
            return
        if scope_type != "http":
            raise RuntimeError(f"Unsupported ASGI scope type: {scope_type}")
        if not self._started:
            await self.startup()

        request = Request(self, scope, receive)
        response = await self._dispatch(request)
        response = self._apply_cors(request, response)
        await response(scope, receive, send)

    async def _handle_lifespan(self, receive: Callable[[], Awaitable[dict[str, Any]]], send: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    await self.startup()
                    await send({"type": "lifespan.startup.complete"})
                except Exception as exc:
                    await send({"type": "lifespan.startup.failed", "message": str(exc)})
            elif message["type"] == "lifespan.shutdown":
                try:
                    await self.shutdown()
                    await send({"type": "lifespan.shutdown.complete"})
                except Exception as exc:
                    await send({"type": "lifespan.shutdown.failed", "message": str(exc)})
                return

    async def _dispatch(self, request: Request) -> Response:
        method = request.method.upper()
        path = request.scope.get("path", "/")
        for route in self.routes:
            if method not in route.methods:
                continue
            match = route.regex.match(path.rstrip("/") or "/")
            if not match:
                continue
            request.scope["path_params"] = match.groupdict()
            request.path_params = match.groupdict()
            try:
                result = await maybe_await(call_handler(route.handler, request, request.path_params))
                return self._coerce_response(result)
            except HTTPException as exc:
                payload = {"detail": exc.detail}
                return JSONResponse(payload, status_code=exc.status_code, headers=exc.headers)
            except Exception as exc:
                return JSONResponse({"detail": str(exc)}, status_code=500)

        if method == "OPTIONS":
            return Response(content=b"", status_code=204, media_type="text/plain; charset=utf-8")
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    def _coerce_response(self, result: Any) -> Response:
        if isinstance(result, Response):
            return result
        if isinstance(result, BaseModel):
            return JSONResponse(result)
        if result is None:
            return Response(content=b"", status_code=204)
        return JSONResponse(result)

    def _apply_cors(self, request: Request, response: Response) -> Response:
        if not self._cors:
            return response

        origins = self._cors.get("allow_origins") or []
        origin = request.headers.get("origin")
        allow_origin = None
        if "*" in origins:
            allow_origin = "*"
        elif origin and origin in origins:
            allow_origin = origin
        elif origins:
            allow_origin = origins[0]

        headers = dict(response.headers)
        if allow_origin:
            headers["access-control-allow-origin"] = allow_origin
            headers.setdefault("vary", "Origin")
        headers.setdefault("access-control-allow-credentials", "true" if self._cors.get("allow_credentials") else "false")
        allow_methods = self._cors.get("allow_methods") or ["*"]
        headers.setdefault("access-control-allow-methods", ", ".join(allow_methods))
        allow_headers = self._cors.get("allow_headers") or ["*"]
        headers.setdefault("access-control-allow-headers", ", ".join(allow_headers))
        response.headers = headers
        return response


async def maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def call_handler(handler: Callable[..., Any], request: Request, path_params: dict[str, str]) -> Any:
    signature = inspect.signature(handler)
    kwargs: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if name == "request":
            kwargs[name] = request
        elif name in path_params:
            kwargs[name] = path_params[name]
        elif name == "app":
            kwargs[name] = request.app
        elif parameter.default is not inspect._empty:
            continue
    return handler(**kwargs)


class TestClient:
    def __init__(self, app: FastAPI, base_url: str = "http://testserver"):
        self.app = app
        self.base_url = base_url
        self._entered = False

    def __enter__(self) -> "TestClient":
        anyio.run(self.app.startup)
        self._entered = True
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        anyio.run(self.app.shutdown)
        self._entered = False

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async def _request() -> httpx.Response:
            if not self._entered and not self.app._started:
                await self.app.startup()
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url=self.base_url) as client:
                return await client.request(method, url, **kwargs)

        return anyio.run(_request)

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def options(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("OPTIONS", url, **kwargs)
