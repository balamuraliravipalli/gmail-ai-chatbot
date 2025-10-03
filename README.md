# Gmail AI Chatbot

Streamlit app that connects to Gmail API and OpenAI to search, list unread, navigate, and summarize emails through chat commands.

## Features
- Latest/first email, next/previous navigation
- Search by sender or subject with Gmail server-side query
- Unread filter and mark-as-read
- AI summaries of the current email

## Setup
- Python 3.10+
- Create OAuth client_secret.json (Desktop) and place in project root
- Set OPENAI_API_KEY in environment
- pip install -r requirements.txt
- streamlit run app.py

## Security
- Do not commit client_secret.json or tokens
- Use .gitignore to exclude .env and token files

