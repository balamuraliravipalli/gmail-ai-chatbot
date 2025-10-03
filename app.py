import re
import streamlit as st
from gmail_bot import (
    gmail_authenticate,
    get_latest_email,
    get_next_email,
    get_previous_email,
    mark_email_as_read,
    get_email_by_index,
    get_email_body,
    search_emails,            
    get_unread_emails,        
    emails_cache,
    process_emails,           
    search_emails_server
)
from openai import OpenAI

st.set_page_config(page_title="📧 Email Chatbot", layout="centered")
st.title("📧 Email Chatbot")

if "gmail_service" not in st.session_state:
    st.session_state.gmail_service = gmail_authenticate()

if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_email_index" not in st.session_state:
    st.session_state.last_email_index = None

client = OpenAI()

def chat_with_bot(user_msg):
    gmail_service = st.session_state.gmail_service
    msg_lower = user_msg.lower().strip()

    # Latest / last email
    if "latest" in msg_lower or "last" in msg_lower:
        reply = get_latest_email(gmail_service, refresh=True)
        if emails_cache:
            st.session_state.last_email_index = 0
        return reply

    # First email (oldest)
    elif "first" in msg_lower:
        process_emails(gmail_service, refresh=True)
        if not emails_cache:
            return "⚠️ No emails found."
        st.session_state.last_email_index = len(emails_cache) - 1
        email = emails_cache[st.session_state.last_email_index]
        return f"First email: From {email.get('from','(Unknown)')} | Subject: {email.get('subject','(No Subject)')}"

    # Search emails
    elif msg_lower.startswith("search") or msg_lower.startswith("find"):
        parts = user_msg.split(" ", 1)
        if len(parts) < 2 or not parts[1].strip():
            return "⚠️ Please provide a search term, e.g., 'search LinkedIn'."
        query_text = parts[1].strip().strip('"').strip("'")
        q = f"subject:{query_text} OR from:{query_text}"
        search_reply = search_emails_server(gmail_service, q)
        if emails_cache:
            st.session_state.last_email_index = 0
        return search_reply

    # Unread emails
    elif msg_lower == "unread" or " unread" in msg_lower:
        process_emails(gmail_service, refresh=True)
        return get_unread_emails()

    # Next email
    elif "next" in msg_lower:
        if st.session_state.last_email_index is None:
            return "⚠️ No email selected. Try 'latest email' first."
        if st.session_state.last_email_index + 1 >= len(emails_cache):
            return "⚠️ You are already at the oldest email."
        st.session_state.last_email_index += 1
        email = emails_cache[st.session_state.last_email_index]
        return f"Next email: From {email.get('from','(Unknown)')} | Subject: {email.get('subject','(No Subject)')}"

    # Previous email
    elif "previous" in msg_lower:
        if st.session_state.last_email_index is None:
            return "⚠️ No email selected. Try 'latest email' first."
        if st.session_state.last_email_index - 1 < 0:
            return "⚠️ You are already at the newest email."
        st.session_state.last_email_index -= 1
        email = emails_cache[st.session_state.last_email_index]
        return f"Previous email: From {email.get('from','(Unknown)')} | Subject: {email.get('subject','(No Subject)')}"

    # Summarize - handle "summary to latest" or "summarize latest"
    elif "summar" in msg_lower:
        # If they say "latest" in the same message, load latest first
        if "latest" in msg_lower or "last" in msg_lower:
            get_latest_email(gmail_service, refresh=True)
            if emails_cache:
                st.session_state.last_email_index = 0
        
        if st.session_state.last_email_index is None:
            return "⚠️ No email selected. Try 'latest email' first."
        
        body = get_email_body(gmail_service, st.session_state.last_email_index)
        if not body.strip():
            return "⚠️ Email has no readable body to summarize."
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": f"Summarize this email:\n\n{body}"}],
            max_tokens=150,
        )
        return response.choices[0].message.content  # ✅ FIXED

    # Mark as read
    elif "mark" in msg_lower and "read" in msg_lower:
        if st.session_state.last_email_index is None:
            return "⚠️ No email selected to mark as read."
        return mark_email_as_read(gmail_service, st.session_state.last_email_index)

    # Email by index
    elif match := re.search(r"email (\-?\d+)", msg_lower):
        index = int(match.group(1))
        st.session_state.last_email_index = index
        return get_email_by_index(gmail_service, index)

    # Default: AI chat
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=st.session_state.messages + [{"role": "user", "content": user_msg}],
        max_tokens=150,
    )
    return response.choices[0].message.content  # ✅ FIXED

user_input = st.chat_input("Type a message...")
if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    bot_reply = chat_with_bot(user_input)
    st.session_state.messages.append({"role": "assistant", "content": bot_reply})

for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.chat_message("user").write(msg["content"])
    else:
        st.chat_message("assistant").write(msg["content"])
