"""Public command-line entrypoint for Cliffy.

Argument parsing is deliberately dependency-free and does not import the
interactive runtime until a command actually starts it.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Sequence

__version__ = "0.1.0"
_PROVIDERS = ("groq", "openai", "anthropic", "gemini", "custom", "apinex")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cliffy", description="AI-assisted interactive shell")
    p.add_argument("--version", action="version", version=f"cliffy {__version__}")
    p.add_argument("--check-api", action="store_true", help="check configured provider connectivity")
    p.add_argument("--no-ai", action="store_true", help="disable AI requests for this session")
    p.add_argument("--no-startup-check", action="store_true", help="skip startup connectivity check")
    p.add_argument("--provider", choices=_PROVIDERS, default=None, help="provider (also configurable by environment)")
    p.add_argument("--model", default=None, help="model identifier")
    p.add_argument("--base-url", default=None, help="provider API base URL")
    p.add_argument("--timeout", default=None, help="request timeout in seconds (must be positive)")
    return p


def run_runtime() -> int:
    from ai_shell_integration import main as runtime_main
    return runtime_main() or 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.timeout is not None:
        try:
            if not 0 < float(args.timeout) <= 300:
                raise ValueError
        except ValueError:
            parser().error("--timeout must be a positive number of seconds (maximum 300)")
    if args.no_ai:
        os.environ["CLIFFY_NO_AI"] = "1"
    if args.no_startup_check:
        os.environ["CLIFFY_SKIP_STARTUP_CHECK"] = "1"
    mappings = (("provider", "CLIFFY_PROVIDER"), ("model", "CLIFFY_MODEL"), ("base_url", "CLIFFY_BASE_URL"), ("timeout", "CLIFFY_TIMEOUT"))
    for attr, key in mappings:
        value = getattr(args, attr)
        if value is not None:
            os.environ[key] = str(value)
    if args.check_api:
        if args.no_ai or os.environ.get("CLIFFY_NO_AI", "").strip().lower() in {"1", "true", "yes", "on"}:
            print("API check unavailable: AI is disabled.", file=sys.stderr)
            return 1
        try:
            from ai_shell_integration import test_api_connection
            return 0 if test_api_connection() else 1
        except Exception:
            print("API check failed; review provider configuration and connectivity.", file=sys.stderr)
            return 1
    return run_runtime() or 0


if __name__ == "__main__":
    raise SystemExit(main())
