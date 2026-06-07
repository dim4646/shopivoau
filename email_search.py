#!/usr/bin/env python3
"""
Email Q&A - Αναζήτηση στα emails με AI
Χρήση: python3 email_search.py
"""

import json
import urllib.request
import urllib.parse
import sys

# ── Config ──────────────────────────────────────────────────────────────────
SUPABASE_URL = "https://sbjvqzahmhsiotxhlrhr.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNianZxemFobWhzaW90eGhscmhyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA3NzQ3MzYsImV4cCI6MjA5NjM1MDczNn0.f_kODFZHpxxHHPqKW9w2YOVqz-RDspbo79B32fZCV3I"
GEMINI_KEY   = "YOUR_GEMINI_API_KEY"  # Βάλε εδώ το key σου
GEMINI_MODEL = "gemini-1.5-flash"
# ────────────────────────────────────────────────────────────────────────────


def search_emails(query, limit=15):
    """Αναζήτηση emails με full-text search."""
    words = query.strip().split()
    tsquery = " & ".join(words) if words else query

    sql = f"""
        SELECT date, from_email, from_name, subject,
               left(body_text, 800) as excerpt,
               ts_rank(
                 to_tsvector('english', coalesce(subject,'') || ' ' || coalesce(body_text,'')),
                 plainto_tsquery('english', {json.dumps(query)})
               ) as rank
        FROM emails
        WHERE to_tsvector('english', coalesce(subject,'') || ' ' || coalesce(body_text,''))
              @@ plainto_tsquery('english', {json.dumps(query)})
        ORDER BY rank DESC, date DESC
        LIMIT {limit}
    """

    encoded = urllib.parse.quote(sql)
    url = f"{SUPABASE_URL}/rest/v1/rpc/query"

    # Χρησιμοποιούμε το REST API με POST για SQL
    url = f"{SUPABASE_URL}/rest/v1/emails"

    # Απλή αναζήτηση βάσει subject με ilike για fallback
    params = urllib.parse.urlencode({
        "select": "date,from_email,from_name,subject,body_text",
        "order": "date.desc",
        "limit": str(limit)
    })

    req = urllib.request.Request(
        f"{url}?{params}",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        }
    )
    with urllib.request.urlopen(req) as resp:
        all_emails = json.loads(resp.read())

    # Τοπικό φιλτράρισμα με keywords
    keywords = [w.lower() for w in query.split() if len(w) > 2]
    scored = []
    for em in all_emails:
        text = (
            (em.get("subject") or "") + " " +
            (em.get("body_text") or "") + " " +
            (em.get("from_email") or "")
        ).lower()
        score = sum(text.count(kw) for kw in keywords)
        if score > 0:
            em["_score"] = score
            scored.append(em)

    scored.sort(key=lambda x: x["_score"], reverse=True)
    return scored[:limit]


def ask_gemini(question, emails):
    """Στείλε ερώτηση στο Gemini με context από emails."""

    context = ""
    for i, em in enumerate(emails, 1):
        date = (em.get("date") or "")[:10]
        sender = em.get("from_email") or ""
        subject = em.get("subject") or "(χωρίς θέμα)"
        body = (em.get("body_text") or "")[:600].strip()
        context += f"\n--- Email {i} ---\nΗμερομηνία: {date}\nΑποστολέας: {sender}\nΘέμα: {subject}\nΠεριεχόμενο: {body}\n"

    prompt = f"""Είσαι βοηθός που αναλύει emails σχετικά με μια υπόθεση WorkCover (εργατικό ατύχημα) στην Αυστραλία.

Τα παρακάτω emails είναι από την πραγματική αλληλογραφία:

{context}

ΕΡΩΤΗΣΗ: {question}

Απάντησε στα Ελληνικά. Βασίσου ΜΟΝΟ στα emails που σου δόθηκαν. Αναφέρε συγκεκριμένες ημερομηνίες και αποστολείς. Αν δεν βρίσκεις απάντηση στα emails, πες το ξεκάθαρα."""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}]
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            return result["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        return f"Σφάλμα Gemini API: {e.code}\n{error_body[:300]}"


def main():
    print("=" * 60)
    print("  Email Q&A — WorkCover / Supatech Αναζήτηση")
    print("  Πληκτρολόγησε 'exit' για έξοδο")
    print("=" * 60)

    while True:
        print()
        question = input("Ερώτηση: ").strip()

        if not question:
            continue
        if question.lower() in ("exit", "quit", "q"):
            print("Αντίο!")
            break

        print("\nΨάχνω στα emails...")
        emails = search_emails(question, limit=200)

        if not emails:
            print("Δεν βρέθηκαν σχετικά emails για αυτή την ερώτηση.")
            continue

        print(f"Βρέθηκαν {len(emails)} σχετικά emails. Ρωτώ το AI...")

        answer = ask_gemini(question, emails[:12])

        print("\n" + "─" * 60)
        print("ΑΠΑΝΤΗΣΗ:")
        print("─" * 60)
        print(answer)
        print("─" * 60)

        print(f"\n[Πηγές: {len(emails)} emails βρέθηκαν]")


if __name__ == "__main__":
    main()
