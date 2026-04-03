# EduBot+ — AI University Assistant

> Intelligent chatbot for university students powered by LangGraph agents, multi-LLM support, and a RAG knowledge base with Qdrant vector search.

---

## 📋 Project Status

> Last updated: March 2026 — tracked against the published paper (IC-ECBE 2026: *EduBot+: An NLP-Powered Chatbot for Multi-Domain Student Support*).

### Legend
| Badge | Meaning |
|---|---|
| ✅ Done | Fully implemented and working |

---

### 🤖 LLM & AI

| # | Feature | Status | Notes |
|---|---|---|---|
| 1 | Multi-LLM Provider Support (GPT-4, Gemini, Ollama, DeepSeek) | ✅ | OpenAI, Gemini, Ollama, DeepSeek fully wired with `auto` fallback chain. |
| 2 | Agent-based Architecture (LangGraph) | ✅ | `StateGraph` + tool nodes in `graph.py`. ReAct-style autonomous decision cycle with `MemorySaver` checkpointing. |
| 3 | Retrieval-Augmented Generation (RAG) | ✅ | `all-MiniLM-L6-v2` embeddings (384-dim) + Qdrant Cloud cosine similarity retrieval (top-k=5, threshold ≥ 0.20). |
| 4 | Semantic Similarity Search | ✅ | Qdrant Cloud vector DB. 800-char paragraph-aware chunks with 10% overlap. 6 tools: `search_university_info`, `search_academic_calendar`, `check_if_date_is_holiday`, `get_university_contact_info`, `search_educational_resources`, `search_all_domains`. |
| 5 | Domain-aware Query Routing | ✅ | Routes to Academic / Administrative / Educational via category-filtered vector search. Financial merged into Administrative domain. |
| 6 | Multi-hop Reasoning | ✅ | Parallel retrieval across domains with result aggregation. |

---

### 📄 Document Management

| # | Feature | Status | Notes |
|---|---|---|---|
| 7 | Faculty Document Upload | ✅ | PDF, DOCX, TXT upload via `POST /settings/upload` with category assignment. List, delete, and auto Qdrant vector sync. OCR fallback for scanned PDFs via Tesseract. |
| 8 | Document Processing → Vector Embeddings | ✅ | Upload → 800-char chunks (10% overlap) → embed with `all-MiniLM-L6-v2` → store in Qdrant Cloud. On delete: vectors auto-removed. |
| 9 | Automatic Document Indexing | ✅ | On upload: auto-indexed into Qdrant. On delete: vectors auto-removed. On startup: existing `data/` files seeded via `seed_existing_documents()` (skips already-indexed). |

---

### ⚙️ Backend

| # | Feature | Status | Notes |
|---|---|---|---|
| 10 | FastAPI Backend | ✅ | Async routers, middleware, CORS, dependency injection. Lifespan-managed startup (DB init + vector store seeding). |
| 11 | PostgreSQL Database | ✅ | PostgreSQL + asyncpg + SQLAlchemy 2 ORM (async). Connection pooling (pool_size=10, max_overflow=20). |
| 12 | Conversation History | ✅ | Messages saved to DB per chat (human + bot pairs). PostgreSQL-backed persistent conversation history with chat sidebar, rename, and archive. |

---

### 🔐 Authentication

| # | Feature | Status | Notes |
|---|---|---|---|
| 13 | OTP Authentication | ✅ | 6-digit email OTP via Gmail SMTP. 10-minute expiry, single-use, timing-safe comparison. Welcome email on registration. |
| 14 | JWT Token Security | ✅ | HS256 JWT via `python-jose`, 30-day configurable expiry. Password hashing: PBKDF2-HMAC-SHA256 (100k iterations). |
| 15 | Role-based Access Control | ✅ | `@pvpsiddhartha.ac.in` → admin (provider config, file management). `@pvpsit.ac.in` → student (chat, model config). Guest → public chat only. |

---

### 🖥️ Frontend

| # | Feature | Status | Notes |
|---|---|---|---|
| 16 | Next.js Responsive Web Interface | ✅ | Next.js 15, CSS Modules, React 18. |
| 17 | Chat Interface | ✅ | Markdown rendering (`react-markdown`), chat history sidebar, rename/delete chats, welcome screen with example questions, guest mode. |
| 18 | Settings Page | ✅ | Tabbed UI — "AI Model" (provider/model/API key config with test-connection) and "Upload Documents" (drag-and-drop `.txt` with category assignment). API keys stored in browser `localStorage` only. |

---

### 🌐 Data & Automation

| # | Feature | Status | Notes |
|---|---|---|---|
| 19 | Web Scraper — Official College Website | ✅ | Scrapes PVP Siddhartha website pages (configurable URL list), extracts content, chunks and indexes into Qdrant knowledge base. Admin UI with scrape history and status tracking. |

---

### 📊 Overall Progress

| Category | ✅ Done |
|---|---|
| LLM & AI | 6 / 6 |
| Document Management | 3 / 3 |
| Backend | 3 / 3 |
| Authentication | 3 / 3 |
| Frontend | 3 / 3 |
| Data & Automation | 1 / 1 |
| **Total** | **19 / 19** |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL
- Qdrant Cloud account (or self-hosted Qdrant)
- Ollama *(optional — for local AI)*

### 1 — Clone & install

```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### 2 — Configure environment

Create `backend/.env`:

```env
# Database (PostgreSQL)
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/edubot
DATABASE_URL_SYNC=postgresql://user:pass@localhost:5432/edubot

# JWT
JWT_SECRET_KEY=change-me-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRY=30

# CORS
CORS_ORIGINS=http://localhost:3000

# Qdrant Vector Database
QDRANT_URL=https://your-cluster.cloud.qdrant.io:6333
QDRANT_API_KEY=your-qdrant-api-key

# Email (Gmail SMTP for OTP)
EMAIL_ADDRESS=your-email@gmail.com
EMAIL_PASSWORD=your-app-password

# Optional: University-level API keys (auto provider fallback)
# OPENAI_API_KEY=sk-...
# GOOGLE_API_KEY=AI...
# DEEPSEEK_API_KEY=sk-...

DEBUG=True
```

### 3 — Run

```bash
# Terminal 1 — Backend
cd backend
python -m uvicorn app.main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm run dev
```

- App: http://localhost:3000
- API docs: http://localhost:8000/docs

---

## 🤖 AI Providers

Configure your provider in **Settings → AI Model** after logging in:

| Provider | Requires | Models |
|---|---|---|
| Ollama | Ollama running locally | Any pulled model (e.g. `llama3.1:8b`) |
| OpenAI | API key | `gpt-4o-mini` |
| Google Gemini | API key | `gemini-2.5-flash`, `gemini-flash-latest` |
| DeepSeek | API key | `deepseek-chat`, `deepseek-reasoner` (R1) |
| Auto | — | Cascading fallback: OpenAI → Gemini → DeepSeek → Ollama |

> API keys entered in the settings page are stored **only in your browser's localStorage** — they are never saved to the server.

---

## 📡 API Reference

### Authentication

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/auth/register` | — | Direct registration (returns JWT) |
| `POST` | `/api/auth/login` | — | Login with email/password (returns JWT) |
| `POST` | `/api/auth/send-otp` | — | Send OTP email for verification |
| `POST` | `/api/auth/verify-otp` | — | Verify OTP and complete registration |
| `GET` | `/api/auth/me` | Bearer | Get current user info |

### Chat

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/chat/message` | — | Send message (public/guest) |
| `POST` | `/api/chat/prompt_public` | — | Alias for `/message` |
| `GET` | `/api/chat/` | Bearer | List all chats (excludes archived) |
| `POST` | `/api/chat/prompt` | Bearer | Send message (persisted to DB) |
| `POST` | `/api/chat/prompt/stream` | Bearer | Streaming response via SSE |
| `GET` | `/api/chat/messages/{chat_id}` | Bearer | Get chat message history |
| `PUT` | `/api/chat/rename/{chat_id}` | Bearer | Rename a chat |
| `DELETE` | `/api/chat/archive/{chat_id}` | Bearer | Soft-archive a chat |

### Settings & Knowledge Base

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/settings/provider/defaults` | — | Check which providers have server-side API keys |
| `POST` | `/api/settings/test-connection` | Bearer | Test provider API key / Ollama connectivity |
| `GET` | `/api/settings/provider` | Bearer | Get current AI provider config |
| `PUT` | `/api/settings/provider` | Admin | Update AI provider |
| `GET` | `/api/settings/` | Bearer | Get app settings |
| `PUT` | `/api/settings/` | Bearer | Update app settings |
| `POST` | `/api/settings/upload` | Bearer† | Upload `.txt` file to knowledge base |
| `GET` | `/api/settings/files` | Bearer | List all KB files by category |
| `DELETE` | `/api/settings/files/{cat}/{name}` | Bearer† | Delete a KB file |

### System

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/` | — | Root info |
| `GET` | `/health` | — | Health check |

> †Not allowed for `@pvpsit.ac.in` (student) users.

Full interactive docs at **http://localhost:8000/docs** (Swagger) and **http://localhost:8000/redoc** (ReDoc).

---

## 🗂️ Project Structure

```
Project/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + lifespan (DB init, vector seeding)
│   │   ├── config.py            # Env config (DB, JWT, Qdrant, AI providers)
│   │   ├── auth.py              # JWT + password hashing + auth dependencies
│   │   ├── llm_provider.py      # Multi-provider LLM abstraction + auto fallback
│   │   ├── graph.py             # LangGraph agent workflow (StateGraph + tools)
│   │   ├── vector_store.py      # Qdrant integration (embed, index, search, delete)
│   │   ├── tools.py             # 6 RAG retrieval tools for the agent
│   │   ├── schemas.py           # Pydantic v2 request/response models
│   │   ├── email_service.py     # OTP + welcome email via Gmail SMTP
│   │   ├── db/
│   │   │   ├── database.py      # Async SQLAlchemy engine + session factory
│   │   │   └── models.py        # ORM models (User, Chat, Message, Setting)
│   │   └── routers/
│   │       ├── auth_router.py   # Registration, login, OTP, user info
│   │       ├── chat_router.py   # Messaging, streaming, chat CRUD
│   │       └── settings_router.py # Provider config, file upload/list/delete
│   ├── data/
│   │   ├── Academic/            # Academic calendar, holidays
│   │   ├── Administrative/      # University info, fee structure
│   │   └── Educational/         # Course materials (SQL)
│   └── requirements.txt
│
└── frontend/
    ├── app/
    │   ├── layout.tsx           # Root layout with AuthProvider
    │   ├── page.tsx             # Redirects to /chat
    │   ├── login/page.tsx       # Login form
    │   ├── register/page.tsx    # Registration + OTP verification
    │   ├── chat/page.tsx        # Chat interface (markdown, history, guest mode)
    │   ├── settings/
    │   │   ├── page.tsx         # Tabbed settings (AI Model + Upload)
    │   │   └── components/
    │   │       ├── ModelSection.tsx    # Provider/model/API key config
    │   │       └── UploadSection.tsx   # Drag-and-drop file upload
    │   └── components/
    │       └── CustomSelect.tsx # Reusable select dropdown
    ├── lib/
    │   ├── api.ts               # API client (auth + API key injection)
    │   ├── auth-context.tsx     # Auth state context + localStorage persistence
    │   └── types.ts             # TypeScript interfaces
    └── package.json
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, TypeScript, React 18, CSS Modules |
| Backend | FastAPI 0.115, Python 3.11+, SQLAlchemy 2 (async), asyncpg |
| Agent | LangChain 0.3, LangGraph 0.6, LangChain-OpenAI / Gemini / Ollama |
| Database | PostgreSQL (asyncpg, connection pooling) |
| Vector DB | Qdrant Cloud (`all-MiniLM-L6-v2`, 384-dim, cosine similarity) |
| Auth | JWT (`python-jose`, HS256), PBKDF2-HMAC-SHA256, OTP via Gmail SMTP |
| AI Providers | OpenAI, Google Gemini, Ollama, DeepSeek (with auto fallback) |

---

## 📄 License

MIT
