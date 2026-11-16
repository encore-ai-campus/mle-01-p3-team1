"""Check Langfuse Cloud credentials and optionally send a synthetic smoke trace."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Langfuse connection; optionally send one safe test trace")
    parser.add_argument("--smoke", action="store_true", help="create a harmless synthetic trace")
    args = parser.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    from .langfuse_support import is_enabled
    if not is_enabled():
        print("Langfuse OFF. Set LANGFUSE_ENABLED=true (or LANGFUSE_TRACING_ENABLED=true) in .env")
        return 2
    if not os.getenv("LANGFUSE_PUBLIC_KEY") or not os.getenv("LANGFUSE_SECRET_KEY"):
        print("Missing Langfuse API keys. No connection attempt made.")
        return 2
    try:
        from langfuse import get_client
        client = get_client()
        ok = client.auth_check()
        print("Langfuse authentication:", "OK" if ok else "FAILED")
        if not ok:
            return 1
        if args.smoke:
            with client.start_as_current_observation(
                as_type="span", name="mle3-connection-smoke-test", input={"synthetic": True},
                metadata={"origin": "smoke_test"},
            ) as span:
                span.update(output={"status": "ok"})
            client.flush()
            print("Synthetic trace sent (no real question or dataset involved).")
        return 0
    except Exception as exc:
        print(f"Connection failed ({type(exc).__name__}); check network, base URL and SDK")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
