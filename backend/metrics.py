import time
from prometheus_client import Counter, Histogram
from starlette.types import ASGIApp, Receive, Scope, Send

REQUESTS=Counter(
    "http_requests_total","HTTP requests",["method","route","status"]
)
LATENCY=Histogram(
    "http_request_duration_seconds","Request latency",["method","route"]
)

class MetricsMiddleware:
    def __init__(self,app:ASGIApp):
        self.app=app

    async def __call__(self,scope:Scope,receive:Receive,send:Send):
        if scope["type"]!="http" or scope["path"].endswith("/metrics"):
            await self.app(scope, receive, send)
            return

        status={"code": 500}
        start=time.perf_counter()

        async def send_wrapper(message):
            if message["type"]=="http.response.start":
                status["code"]=message["status"]
            await send(message)

        try:
            await self.app(scope,receive,send_wrapper)
        finally:
            route=scope.get("route")
            path=route.path if route else "unmatched"
            REQUESTS.labels(scope["method"],path,str(status["code"])).inc()
            LATENCY.labels(scope["method"],path).observe(time.perf_counter()-start)