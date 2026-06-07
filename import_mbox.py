#!/usr/bin/env python3
"""
mbox → Supabase importer
Χρήση: python import_mbox.py /path/to/your/file.mbox
"""

import mailbox
import sys
import json
import email.utils
from datetime import datetime, timezone
from email.header import decode_header
import urllib.request
import urllib.parse

# ── Supabase config ─────────────────────────────────────────────────────────
SUPABASE_URL = "https://sbjvqzahmhsiotxhlrhr.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNianZxemFobWhzaW90eGhscmhyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA3NzQ3MzYsImV4cCI6MjA5NjM1MDczNn0.f_kODFZHpxxHHPqKW9w2YOVqz-RDspbo79B32fZCV3I"
BATCH_SIZE = 50
# ────────────────────────────────────────────────────────────────────────────


def decode_str(value):
    if not value:
        return ""
    parts = decode_header(value)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result).strip()


def parse_addresses(header_value):
    if not header_value:
        return []
    addrs = []
    for name, addr in email.utils.getaddresses([header_value]):
        if addr:
            addrs.append(addr.lower())
    return addrs


def parse_date(date_str):
    if not date_str:
        return None
    try:
        t = email.utils.parsedate_to_datetime(date_str)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.isoformat()
    except Exception:
        return None


def get_body(msg):
    text, html = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                decoded = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if ct == "text/plain" and not text:
                text = decoded
            elif ct == "text/html" and not html:
                html = decoded
    else:
        charset = msg.get_content_charset() or "utf-8"
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                decoded = payload.decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    html = decoded
                else:
                    text = decoded
        except Exception:
            pass
    return text[:50000], html[:50000]  # trim very large bodies


def parse_message(msg):
    body_text, body_html = get_body(msg)
    labels_raw = msg.get("X-Gmail-Labels", "")
    labels = [l.strip() for l in labels_raw.split(",") if l.strip()] if labels_raw else []

    return {
        "message_id": msg.get("Message-ID", "").strip() or None,
        "date": parse_date(msg.get("Date")),
        "from_email": parse_addresses(msg.get("From"))[0] if parse_addresses(msg.get("From")) else None,
        "from_name": decode_str(msg.get("From")).split("<")[0].strip().strip('"') or None,
        "to_emails": parse_addresses(msg.get("To")),
        "cc_emails": parse_addresses(msg.get("Cc")),
        "subject": decode_str(msg.get("Subject")) or None,
        "body_text": body_text or None,
        "body_html": body_html or None,
        "thread_id": msg.get("X-GM-THRID", "").strip() or None,
        "labels": labels,
    }


def insert_batch(batch):
    url = f"{SUPABASE_URL}/rest/v1/emails"
    data = json.dumps(batch).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Prefer": "resolution=ignore-duplicates,return=minimal",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        print(f"  ✗ HTTP {e.code}: {e.read().decode()[:200]}")
        return e.code


def main():
    if len(sys.argv) < 2:
        print("Χρήση: python import_mbox.py /path/to/file.mbox")
        sys.exit(1)

    mbox_path = sys.argv[1]
    print(f"Ανάγνωση: {mbox_path}")

    mbox = mailbox.mbox(mbox_path)
    total = 0
    inserted = 0
    batch = []

    for msg in mbox:
        total += 1
        try:
            record = parse_message(msg)
            batch.append(record)
        except Exception as e:
            print(f"  ✗ Σφάλμα ανάγνωσης μηνύματος #{total}: {e}")
            continue

        if len(batch) >= BATCH_SIZE:
            status = insert_batch(batch)
            inserted += len(batch)
            print(f"  ✓ {inserted}/{total} emails ({status})")
            batch = []

    if batch:
        status = insert_batch(batch)
        inserted += len(batch)
        print(f"  ✓ {inserted}/{total} emails ({status})")

    print(f"\nΟλοκληρώθηκε! {inserted} emails εισήχθησαν στη Supabase.")


if __name__ == "__main__":
    main()
