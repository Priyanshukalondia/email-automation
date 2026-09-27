#!/usr/bin/env python3
"""Laptop brand outreach automation.

Design goals:
- Generate truthful, brand-specific outreach drafts from a CSV database.
- Never send by default.
- Require per-target approval in targets.csv before sending.
- Rate-limit SMTP sending and keep a durable sent ledger to prevent duplicates.
- Use only the Python standard library.

Usage:
    python outreach.py validate
    python outreach.py preview
    python outreach.py send --confirmed

SMTP credentials are read from environment variables; see .env.example.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import smtplib
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent
TARGETS_CSV = ROOT / "targets.csv"
CONFIG_JSON = ROOT / "config.json"
TEMPLATE_TXT = ROOT / "templates" / "email.txt"
SUBJECT_TXT = ROOT / "templates" / "subject.txt"
DRAFTS_DIR = ROOT / "drafts"
LOGS_DIR = ROOT / "logs"
SENT_LEDGER = LOGS_DIR / "sent.jsonl"
SEND_LOG = LOGS_DIR / "send.log"

EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.I)
YES_VALUES = {"yes", "y", "true", "1", "approved"}


@dataclass(frozen=True)
class Target:
    brand: str
    recipient_name: str
    recipient_email: str
    contact_type: str
    product_line: str
    appreciation: str
    india_context: str
    source_url: str
    source_checked: str
    approved: bool
    notes: str

    @property
    def key(self) -> str:
        raw = f"{self.brand.strip().lower()}|{self.recipient_email.strip().lower()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def die(message: str, code: int = 2) -> "NoReturn":
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        die(f"Missing required file: {path}")
    except json.JSONDecodeError as exc:
        die(f"Invalid JSON in {path}: {exc}")


def load_targets(path: Path = TARGETS_CSV) -> list[Target]:
    if not path.exists():
        die(f"Missing targets file: {path}")
    rows: list[Target] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {
            "brand", "recipient_name", "recipient_email", "contact_type",
            "product_line", "appreciation", "india_context", "source_url",
            "source_checked", "approved", "notes",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            die(f"targets.csv is missing columns: {', '.join(sorted(missing))}")
        for row in reader:
            email = (row.get("recipient_email") or "").strip()
            if not email:
                # Manual/non-email routes belong in manual_targets.csv.
                continue
            rows.append(Target(
                brand=(row.get("brand") or "").strip(),
                recipient_name=(row.get("recipient_name") or "").strip(),
                recipient_email=email,
                contact_type=(row.get("contact_type") or "").strip(),
                product_line=(row.get("product_line") or "").strip(),
                appreciation=(row.get("appreciation") or "").strip(),
                india_context=(row.get("india_context") or "").strip(),
                source_url=(row.get("source_url") or "").strip(),
                source_checked=(row.get("source_checked") or "").strip(),
                approved=(row.get("approved") or "").strip().lower() in YES_VALUES,
                notes=(row.get("notes") or "").strip(),
            ))
    return rows


def validate_profile(config: dict) -> list[str]:
    profile = config.get("profile", {})
    errors: list[str] = []
    required = ["full_name", "city_country", "student_or_role", "story", "use_case", "signature"]
    for key in required:
        value = str(profile.get(key, "")).strip()
        if not value or value.startswith("YOUR_") or "CHANGE_ME" in value:
            errors.append(f"config.json profile.{key} still needs your real information")
    return errors


def validate_targets(targets: Iterable[Target]) -> list[str]:
    errors: list[str] = []
    seen_emails: set[str] = set()
    seen_brands: set[str] = set()
    for t in targets:
        if not t.brand:
            errors.append("A target row has no brand")
        if not EMAIL_RE.match(t.recipient_email):
            errors.append(f"{t.brand}: invalid email address {t.recipient_email!r}")
        email_lower = t.recipient_email.lower()
        if email_lower in seen_emails:
            errors.append(f"Duplicate recipient email: {t.recipient_email}")
        seen_emails.add(email_lower)
        brand_lower = t.brand.lower()
        if brand_lower in seen_brands:
            # Multiple addresses for one brand can be intentional, but default dataset avoids it.
            errors.append(f"Duplicate brand row: {t.brand}. Keep one primary recipient per brand unless intentionally changed.")
        seen_brands.add(brand_lower)
        if not t.source_url.startswith("http"):
            errors.append(f"{t.brand}: missing official/public source URL")
        if len(t.appreciation) < 20:
            errors.append(f"{t.brand}: appreciation text is too thin for meaningful personalization")
    return errors


def load_template(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        die(f"Missing template file: {path}")


def render(template: str, target: Target, config: dict) -> str:
    profile = config.get("profile", {})
    ask = config.get("ask", {})
    values = {
        "brand": target.brand,
        "recipient_name": target.recipient_name or f"{target.brand} team",
        "recipient_email": target.recipient_email,
        "contact_type": target.contact_type,
        "product_line": target.product_line,
        "appreciation": target.appreciation,
        "india_context": target.india_context,
        "full_name": str(profile.get("full_name", "")).strip(),
        "city_country": str(profile.get("city_country", "")).strip(),
        "student_or_role": str(profile.get("student_or_role", "")).strip(),
        "story": str(profile.get("story", "")).strip(),
        "use_case": str(profile.get("use_case", "")).strip(),
        "portfolio_url": str(profile.get("portfolio_url", "")).strip(),
        "linkedin_url": str(profile.get("linkedin_url", "")).strip(),
        "signature": str(profile.get("signature", "")).strip(),
        "primary_request": str(ask.get("primary_request", "")).strip(),
        "fallback_request": str(ask.get("fallback_request", "")).strip(),
    }
    try:
        return template.format(**values)
    except KeyError as exc:
        die(f"Template uses an unknown placeholder: {exc}")


def safe_filename(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip())
    return text.strip("_") or "draft"


def make_html(body_text: str) -> str:
    paragraphs = []
    for block in body_text.split("\n\n"):
        block = block.strip()
        if block:
            paragraphs.append(f"<p>{html.escape(block).replace(chr(10), '<br>')}</p>")
    return "<html><body>" + "".join(paragraphs) + "</body></html>"


def sent_keys() -> set[str]:
    keys: set[str] = set()
    if not SENT_LEDGER.exists():
        return keys
    with SENT_LEDGER.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                if item.get("target_key"):
                    keys.add(str(item["target_key"]))
            except json.JSONDecodeError:
                # A damaged historical line should not block the whole workflow.
                continue
    return keys


def log_sent(target: Target, subject: str, message_id: str | None = None) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "target_key": target.key,
        "brand": target.brand,
        "recipient_email": target.recipient_email,
        "subject": subject,
        "message_id": message_id or "",
    }
    with SENT_LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    with SEND_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{entry['timestamp_utc']}\tSENT\t{target.brand}\t{target.recipient_email}\n")


def write_preview(target: Target, subject: str, body: str) -> Path:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    path = DRAFTS_DIR / f"{safe_filename(target.brand)}.txt"
    content = (
        f"TO: {target.recipient_email}\n"
        f"CONTACT TYPE: {target.contact_type}\n"
        f"SUBJECT: {subject}\n"
        f"SOURCE: {target.source_url}\n"
        f"SOURCE CHECKED: {target.source_checked}\n"
        f"APPROVED IN CSV: {'yes' if target.approved else 'no'}\n"
        f"\n{body.rstrip()}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def smtp_settings(config: dict) -> dict:
    mail_cfg = config.get("mail", {})
    host = os.getenv("SMTP_HOST", str(mail_cfg.get("smtp_host", "smtp.gmail.com")))
    port = int(os.getenv("SMTP_PORT", str(mail_cfg.get("smtp_port", 587))))
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    from_email = os.getenv("FROM_EMAIL", username).strip()
    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "from_email": from_email,
        "use_starttls": bool(mail_cfg.get("use_starttls", True)),
    }


def make_message(target: Target, subject: str, body: str, from_email: str, config: dict) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = from_email
    msg["To"] = target.recipient_email
    msg["Subject"] = subject
    reply_to = str(config.get("mail", {}).get("reply_to", "")).strip()
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    msg.add_alternative(make_html(body), subtype="html")
    return msg


def connect_smtp(settings: dict) -> smtplib.SMTP:
    if not settings["username"] or not settings["password"] or not settings["from_email"]:
        die(
            "SMTP credentials are missing. Set SMTP_USERNAME, SMTP_PASSWORD and optionally FROM_EMAIL. "
            "See .env.example."
        )
    client = smtplib.SMTP(settings["host"], settings["port"], timeout=30)
    client.ehlo()
    if settings["use_starttls"]:
        context = ssl.create_default_context()
        client.starttls(context=context)
        client.ehlo()
    client.login(settings["username"], settings["password"])
    return client


def validate_cmd(config: dict, targets: list[Target]) -> int:
    errors = validate_profile(config) + validate_targets(targets)
    print(f"Targets with direct email routes: {len(targets)}")
    print(f"Approved for sending: {sum(t.approved for t in targets)}")
    if errors:
        print("\nValidation issues:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("Validation passed.")
    return 0


def preview_cmd(config: dict, targets: list[Target]) -> int:
    profile_errors = validate_profile(config)
    if profile_errors:
        print("Profile must be completed before personalized previews are trustworthy:")
        for err in profile_errors:
            print(f"  - {err}")
        print("\nEdit config.json, then rerun preview.")
        return 1
    target_errors = validate_targets(targets)
    if target_errors:
        print("Target validation failed:")
        for err in target_errors:
            print(f"  - {err}")
        return 1

    subject_tpl = load_template(SUBJECT_TXT).strip()
    body_tpl = load_template(TEMPLATE_TXT)
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for t in targets:
        subject = render(subject_tpl, t, config).strip()
        body = render(body_tpl, t, config).strip() + "\n"
        path = write_preview(t, subject, body)
        print(f"Wrote {path.relative_to(ROOT)}")
        count += 1
    print(f"\nGenerated {count} drafts. Review them, then set approved=yes only for the rows you want sent.")
    return 0


def send_cmd(config: dict, targets: list[Target], confirmed: bool, limit_override: int | None) -> int:
    if not confirmed:
        die("Sending requires the explicit --confirmed flag. Run preview first and review the drafts.")

    errors = validate_profile(config) + validate_targets(targets)
    if errors:
        print("Cannot send until validation passes:")
        for err in errors:
            print(f"  - {err}")
        return 1

    approved = [t for t in targets if t.approved]
    already = sent_keys()
    pending = [t for t in approved if t.key not in already]

    send_cfg = config.get("sending", {})
    configured_limit = int(send_cfg.get("max_emails_per_run", 10))
    max_per_run = min(limit_override, configured_limit) if limit_override is not None else configured_limit
    max_per_run = max(1, max_per_run)
    delay_seconds = max(1, int(send_cfg.get("delay_seconds", 45)))

    if not approved:
        print("No targets are approved. Set approved=yes in targets.csv after reviewing previews.")
        return 0
    if not pending:
        print("Every approved target is already present in logs/sent.jsonl. Nothing to send.")
        return 0

    pending = pending[:max_per_run]
    settings = smtp_settings(config)
    subject_tpl = load_template(SUBJECT_TXT).strip()
    body_tpl = load_template(TEMPLATE_TXT)

    print(f"About to send {len(pending)} approved, previously-unsent email(s).")
    print(f"Rate limit: one message every {delay_seconds} seconds; max this run: {max_per_run}.")

    client = connect_smtp(settings)
    sent_count = 0
    try:
        for idx, t in enumerate(pending, start=1):
            subject = render(subject_tpl, t, config).strip()
            body = render(body_tpl, t, config).strip() + "\n"
            msg = make_message(t, subject, body, settings["from_email"], config)
            try:
                client.send_message(msg)
            except Exception as exc:
                LOGS_DIR.mkdir(parents=True, exist_ok=True)
                with SEND_LOG.open("a", encoding="utf-8") as f:
                    f.write(
                        f"{datetime.now(timezone.utc).isoformat()}\tERROR\t{t.brand}\t"
                        f"{t.recipient_email}\t{type(exc).__name__}: {exc}\n"
                    )
                print(f"FAILED {t.brand}: {exc}", file=sys.stderr)
                continue
            log_sent(t, subject, msg.get("Message-ID"))
            sent_count += 1
            print(f"SENT {idx}/{len(pending)}: {t.brand} -> {t.recipient_email}")
            if idx != len(pending):
                time.sleep(delay_seconds)
    finally:
        try:
            client.quit()
        except Exception:
            pass

    print(f"Finished. Successfully sent {sent_count} email(s).")
    return 0 if sent_count == len(pending) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Personalized laptop-brand outreach automation")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="validate your profile and target database")
    sub.add_parser("preview", help="generate local personalized drafts; sends nothing")
    send_p = sub.add_parser("send", help="send only rows marked approved=yes")
    send_p.add_argument("--confirmed", action="store_true", help="explicitly confirm that reviewed/approved rows may be sent")
    send_p.add_argument("--limit", type=int, default=None, help="optional lower per-run limit; cannot exceed config limit")
    args = parser.parse_args(argv)

    config = load_json(CONFIG_JSON)
    targets = load_targets()
    if args.command == "validate":
        return validate_cmd(config, targets)
    if args.command == "preview":
        return preview_cmd(config, targets)
    if args.command == "send":
        return send_cmd(config, targets, args.confirmed, args.limit)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
