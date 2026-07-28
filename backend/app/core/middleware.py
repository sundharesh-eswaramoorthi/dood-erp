import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Surfaces the Idempotency-Key to handlers and stamps a request id.

    Actual dedup is enforced in the service layer against the durable
    `idempotency_key` table (Redis is only a fast pre-check). This middleware
    just makes the key conveniently available and echoes a correlation id.
    """

    async def dispatch(self, request: Request, call_next):
        request.state.idempotency_key = request.headers.get("Idempotency-Key")
        request.state.request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response
