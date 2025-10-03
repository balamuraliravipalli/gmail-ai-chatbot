import os
import re
import base64
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from openai import OpenAI

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
CREDENTIALS_FILE = "client_secret.json"
TOKEN_FILE = "client_token.json"

def gmail_authenticate():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    service = build("gmail", "v1", credentials=creds)
    return service

emails_cache = []     # newest at index 0
last_email_index = None

def _safe_b64_decode(s):
    if not s:
        return ""
    if isinstance(s, str):
        s = s.encode('utf-8')
    s += b'=' * (-len(s) % 4)
    try:
        return base64.urlsafe_b64decode(s).decode('utf-8', errors='replace')
    except Exception:
        return ""

def _is_email_record(x):
    return isinstance(x, dict) and "from" in x and "subject" in x and "id" in x

def process_emails(service, refresh=False, only_unread=False, max_results=50):
    global emails_cache
    if emails_cache and not refresh and not only_unread and all(_is_email_record(x) for x in emails_cache):
        return emails_cache

    params = {"userId": "me", "maxResults": max_results}
    if only_unread:
        params["labelIds"] = ["UNREAD"]

    results = service.users().messages().list(**params).execute()
    messages = results.get("messages", []) or []

    emails = []
    for msg in messages:
        try:
            msg_data = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
            headers = msg_data.get("payload", {}).get("headers", [])
            subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "(No Subject)")
            sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "(Unknown)")
            snippet = msg_data.get("snippet", "")
            labels = msg_data.get("labelIds", [])
            emails.append({
                "id": msg["id"],
                "from": sender,
                "subject": subject,
                "snippet": snippet,
                "labels": labels
            })
        except Exception as e:
            print(f"[process_emails] warning: couldn't fetch msg {msg.get('id')}: {e}")

    emails_cache = emails
    return emails_cache

def search_emails(query):
    global emails_cache
    results = []
    q = (query or "").strip().lower()
    for email in emails_cache:
        if not _is_email_record(email):
            continue
        if q in email["from"].lower() or q in email["subject"].lower():
            results.append(email)
    if not results:
        return f"⚠️ No emails found matching '{query}'."
    reply = "📧 Search results:\n"
    for email in results[:5]:
        reply += f"\nID: {email['id']} | From {email['from']} | Subject: {email['subject']}"
    return reply

def search_emails_server(service, query, max_results=25):
    global emails_cache, last_email_index
    
    try:
        results = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_results
        ).execute()
        messages = results.get("messages", []) or []
        if not messages:
            return f"⚠️ No emails found matching '{query}'."

        emails_cache = []  # reset cache to only include search results
        reply = "📧 Search results:\n"
        for msg in messages[:5]:
            msg_data = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
            headers = msg_data.get("payload", {}).get("headers", [])
            subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "(No Subject)")
            sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "(Unknown)")

            # Add to cache
            emails_cache.append({
                "id": msg["id"],
                "from": sender,
                "subject": subject,
                "snippet": msg_data.get("snippet", ""),
                "labels": msg_data.get("labelIds", [])
            })

            reply += f"\nFrom {sender} | Subject: {subject}"

        # Auto-select first search result for summarization/navigation
        if emails_cache:
            last_email_index = 0

        return reply

    except Exception as e:
        return f"❌ Search failed: {e}"

def get_unread_emails():
    unread = [(i, email) for i, email in enumerate(emails_cache) if _is_email_record(email) and "UNREAD" in email.get("labels", [])]
    if not unread:
        return "✅ No unread emails."
    reply = "📬 Unread emails:\n"
    for idx, email in unread[:5]:
        reply += f"\nEmail #{idx}: From {email['from']} | Subject: {email['subject']}"
    return reply

def get_latest_email(service, refresh=False):
    global last_email_index
    process_emails(service, refresh=refresh, only_unread=False)
    if not emails_cache:
        last_email_index = None
        return "⚠️ No emails found."
    last_email_index = 0
    e = emails_cache[0]
    if not _is_email_record(e):
        # Fallback: fetch just the single latest message and format it
        lst = service.users().messages().list(userId="me", maxResults=1).execute()
        msgs = lst.get("messages", []) or []
        if not msgs:
            last_email_index = None
            return "⚠️ No emails found."
        msg_id = msgs[0]["id"]  # ✅ FIXED: index into list first
        msg_data = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
        headers = msg_data.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "(No Subject)")
        sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "(Unknown)")
        return f"Your latest email is from {sender} | Subject: {subject}"
    return f"Your latest email is from {e['from']} | Subject: {e['subject']}"

def get_email_by_index(service, index):
    if not emails_cache:
        return "⚠️ No emails found."
    if index < 0 or index >= len(emails_cache):
        return f"⚠️ Invalid index. Choose 0-{len(emails_cache)-1}."
    e = emails_cache[index]
    if not _is_email_record(e):
        return "⚠️ Internal cache error. Try refreshing emails."
    return f"Email #{index}: From {e['from']} | Subject: {e['subject']}\nSnippet: {e.get('snippet','')}"

def get_next_email():
    global last_email_index
    if not emails_cache:
        return "⚠️ No emails found."
    if last_email_index is None:
        last_email_index = 0
    else:
        if last_email_index + 1 >= len(emails_cache):
            return "⚠️ You are already at the oldest email."
        last_email_index += 1
    e = emails_cache[last_email_index]
    if not _is_email_record(e):
        return "⚠️ Internal cache error. Try 'latest' to refresh."
    return f"Next email: From {e['from']} | Subject: {e['subject']}"

def get_previous_email():
    global last_email_index
    if not emails_cache:
        return "⚠️ No emails found."
    if last_email_index is None:
        last_email_index = 0
    else:
        if last_email_index - 1 < 0:
            return "⚠️ You are already at the newest email."
        last_email_index -= 1
    e = emails_cache[last_email_index]
    if not _is_email_record(e):
        return "⚠️ Internal cache error. Try 'latest' to refresh."
    return f"Previous email: From {e['from']} | Subject: {e['subject']}"

def get_email_body(service, index):
    if not emails_cache:
        return "(no emails)"
    if index < 0 or index >= len(emails_cache):
        return "(invalid index)"
    email_id = emails_cache[index]["id"]
    try:
        msg = service.users().messages().get(userId="me", id=email_id, format="full").execute()
        payload = msg.get("payload", {})
        parts = payload.get("parts") or []
        body_text = ""
        for part in parts:
            mime = part.get("mimeType", "")
            if mime == "text/plain":
                data = part.get("body", {}).get("data", "")
                body_text = _safe_b64_decode(data)
                if body_text:
                    break
            if part.get("parts"):
                for sub in part.get("parts"):
                    if sub.get("mimeType") == "text/plain":
                        data = sub.get("body", {}).get("data", "")
                        body_text = _safe_b64_decode(data)
                        if body_text:
                            break
        if not body_text and payload.get("mimeType") == "text/plain":
            data = payload.get("body", {}).get("data", "")
            body_text = _safe_b64_decode(data)
        if not body_text:
            body_text = msg.get("snippet", "")
        return body_text
    except Exception as e:
        return f"(error fetching body: {e})"

client = OpenAI()

def mark_email_as_read(service, index):
    global emails_cache, last_email_index
    if not emails_cache:
        return "⚠️ No emails found."
    if index is None or index < 0 or index >= len(emails_cache):
        return f"⚠️ Invalid email index. Choose 0-{len(emails_cache)-1}."
    message_id = emails_cache[index]["id"]
    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()
    except Exception as e:
        return f"❌ Failed to mark as read: {e}"
    removed = emails_cache.pop(index)
    if not emails_cache:
        last_email_index = None
    else:
        last_email_index = min(index, len(emails_cache) - 1)
    return f"✅ Marked as read: {removed['subject']}"

def ai_classify_email(user_message, service):
    msg = user_message.lower()
    if "latest" in msg or "last" in msg:
        return get_latest_email(service, refresh=True)
    if "next" in msg:
        return get_next_email()
    if "previous" in msg:
        return get_previous_email()
    if "mark read" in msg:
        if last_email_index is None:
            return "⚠️ No email selected to mark as read."
        return mark_email_as_read(service, last_email_index)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": user_message}],
        max_tokens=150
    )
    return response.choices[0].message.content  # ✅ FIXED
