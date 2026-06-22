#!/usr/bin/env python3
"""Send a plain-text email via SMTP (stdlib only). Used by VPS auto-import notifications."""

from __future__ import annotations

import argparse
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _split_recipients(value: str) -> list[str]:
    return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]


def _smtp_password() -> str:
    pass_file = os.environ.get("NOTIFY_SMTP_PASS_FILE", "").strip()
    if pass_file:
        return Path(pass_file).read_text(encoding="utf-8").strip()
    return os.environ.get("NOTIFY_SMTP_PASS", "").strip()


def send_email(
    *,
    to_addrs: Iterable[str],
    subject: str,
    body: str,
    from_addr: str | None = None,
    smtp_host: str | None = None,
    smtp_port: int | None = None,
    smtp_user: str | None = None,
    smtp_password: str | None = None,
    starttls: bool | None = None,
) -> None:
    host = (smtp_host or os.environ.get("NOTIFY_SMTP_HOST", "")).strip()
    if not host:
        raise ValueError("NOTIFY_SMTP_HOST is not set")

    port = smtp_port
    if port is None:
        port = int(os.environ.get("NOTIFY_SMTP_PORT", "587"))

    user = (smtp_user or os.environ.get("NOTIFY_SMTP_USER", "")).strip()
    password = smtp_password if smtp_password is not None else _smtp_password()
    # Port 465 is implicit TLS (SMTPS); never plain SMTP + STARTTLS on that port.
    use_ssl = port == 465 or _env_bool("NOTIFY_SMTP_SSL", False)
    use_starttls = False if use_ssl else (starttls if starttls is not None else _env_bool("NOTIFY_SMTP_STARTTLS", True))
    debug = _env_bool("NOTIFY_SMTP_DEBUG", False)

    sender = (from_addr or os.environ.get("NOTIFY_EMAIL_FROM", "")).strip()
    if not sender:
        sender = user or "noreply@bowlyzer.online"

    recipients = list(to_addrs)
    if not recipients:
        raise ValueError("no recipients")
    if user and not password:
        raise ValueError("NOTIFY_SMTP_PASS or NOTIFY_SMTP_PASS_FILE is empty")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)

    context = ssl.create_default_context()
    if debug:
        print(
            f"send_notify_email: host={host} port={port} ssl={use_ssl} starttls={use_starttls}",
            file=sys.stderr,
        )

    if use_ssl:
        smtp: smtplib.SMTP | smtplib.SMTP_SSL = smtplib.SMTP_SSL(host, port, timeout=30, context=context)
    else:
        smtp = smtplib.SMTP(host, port, timeout=30)

    with smtp:
        if debug:
            smtp.set_debuglevel(1)
        smtp.ehlo()
        if use_starttls:
            smtp.starttls(context=context)
            smtp.ehlo()
        if user:
            smtp.login(user, password)
        smtp.send_message(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--to", required=True, help="Comma-separated recipient(s)")
    parser.add_argument("--subject", required=True)
    body_group = parser.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--body")
    body_group.add_argument("--body-file", type=Path)
    parser.add_argument("--from-addr", default="")
    args = parser.parse_args()

    if args.body_file is not None:
        body = args.body_file.read_text(encoding="utf-8")
    else:
        body = args.body

    try:
        send_email(
            to_addrs=_split_recipients(args.to),
            subject=args.subject,
            body=body,
            from_addr=args.from_addr or None,
        )
    except Exception as exc:  # noqa: BLE001 — CLI reports failure to caller
        print(f"send_notify_email: {exc}", file=sys.stderr)
        port = int(os.environ.get("NOTIFY_SMTP_PORT", "587"))
        if port == 465 and "unexpectedly closed" in str(exc).lower():
            print(
                "send_notify_email: hint: port 465 needs SMTP_SSL (update send_notify_email.py); "
                "set NOTIFY_SMTP_STARTTLS=0",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
