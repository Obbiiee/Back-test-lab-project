"""Explicit opt-in server runner; Windows Psycopg needs a selector event loop."""
import asyncio
import os
import uvicorn
from .app import from_environment


def main():
    trusted_proxies = os.environ.get("BTL_TRUSTED_PROXY_IPS", "")
    if "*" in trusted_proxies:
        raise ValueError("Explicit trusted proxy addresses required")
    config = uvicorn.Config(from_environment(), host=os.environ.get("BTL_BIND_HOST", "127.0.0.1"),
        port=int(os.environ.get("BTL_BIND_PORT", "8001")),
        ssl_certfile=os.environ.get("BTL_TLS_CERT"), ssl_keyfile=os.environ.get("BTL_TLS_KEY"),
        proxy_headers=bool(trusted_proxies), forwarded_allow_ips=trusted_proxies)
    loop_factory = asyncio.SelectorEventLoop if os.name == "nt" else asyncio.new_event_loop
    asyncio.run(uvicorn.Server(config).serve(), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
