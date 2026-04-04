# EduBot+ (PVPSIT Assistant)

EduBot+ is a production-style university assistant built with FastAPI, Next.js, LangGraph, and Qdrant RAG.
It now includes:

- Multi-provider LLM orchestration (OpenAI, Gemini, DeepSeek, Ollama)
- Backend-grounded responses only
- Feedback lifecycle with reasons + workflow stages
- Golden example curation from feedback
- Sentiment analysis + topic recommendation layer
- Dataset-driven training metrics for viva/demo

## Features

### Core Chat
- Domain-aware retrieval across Academic, Administrative, Educational data
- Multi-hop retrieval for multi-domain questions
- Tool-routed reasoning with strict backend grounding
- Streaming chat responses
- Chat history, rename, archive

### AI Provider Fallback
- Primary provider with automatic fallback chain
- Quota/rate-limit recovery to available providers
- Tool-support aware fallback selection

### Feedback Workflow
- User feedback capture (positive/negative) with reason catalog
- Workflow statuses: `pending -> triaged -> in_review -> actioned -> resolved`
- Optional dismiss path at each stage
- Admin feedback dashboard with status transitions
- Golden response creation from feedback

### ML Enhancements
- Sentiment classifier (Logistic Regression + TF-IDF)
- Optional HuggingFace/BERT sentiment pipeline fallback
- Topic recommendation (TF-IDF + cosine similarity)
- Runtime metrics endpoint for dataset size and accuracy

---

## Tech Stack

### Backend
- Python 3.11+
- FastAPI
- SQLAlchemy (async) + asyncpg
- LangChain + LangGraph
- Qdrant + FastEmbed
- scikit-learn

### Frontend
- Next.js 15
- React + TypeScript
- CSS Modules

---

## Project Structure

```text
Edubot/
  backend/
    app/
      auth.py
      config.py
      graph.py
      learning_intelligence.py
      llm_provider.py
      main.py
      query_router.py
      routers/
        auth_router.py
        chat_router.py
        feedback_router.py
        integrations_router.py
        settings_router.py
      db/
        database.py
        models.py
      tools.py
      vector_store.py
    data/
      Academic/
      Administrative/
      Educational/
      ml/
        sentiment_dataset.csv
        topic_catalog.csv
        DATASET_SOURCES.txt
    requirements.txt
  frontend/
    app/
    lib/
    package.json
  README.md
```

---

## Download / Clone

```bash
git clone <your-repository-url>.git
cd Edubot
```

If repository already exists locally, pull latest changes:

```bash
git pull
```

---

## Prerequisites

- Python 3.11 or later
- Node.js 18 or later
- PostgreSQL database
- Qdrant (cloud or local)
- (Optional) Ollama for local LLM fallback

---

## Backend Setup

### 1) Create virtual environment

```bash
cd backend
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Configure environment

Create `backend/.env` using `backend/.env.example` and set:

- `DATABASE_URL`
- `DATABASE_URL_SYNC`
- `JWT_SECRET_KEY`
- `QDRANT_URL`
- `QDRANT_API_KEY`
- provider keys/models (`OPENAI_*`, `GOOGLE_*`, `OLLAMA_*`, etc.)

Important defaults used in this project:

- `AI_PROVIDER=auto`
- `ADMIN_OVERRIDE_USERNAMES=azeez`
- `USE_BERT_SENTIMENT=false`

### 4) Run backend

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend API:
- http://127.0.0.1:8000
- Swagger docs: http://127.0.0.1:8000/docs

---

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend app:
- http://localhost:3000

If needed, set API URL:

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api
```

---

## Admin Access (Azeez)

This project now supports username-based admin override.

- Config: `ADMIN_OVERRIDE_USERNAMES=azeez`
- Startup bootstrap ensures matching users are admin and have:
  - `feedback.manage`
  - `integration.manage`

Additionally, Azeez has been updated in DB in this environment.

---

## Feedback Reasons and Workflow

### Reason catalog
- Positive:
  - Accurate answer
  - Clear explanation
  - Helpful step-by-step guidance
  - Good recommendation
  - Fast response

- Negative:
  - Incorrect information
  - Answer too generic
  - Missing important details
  - Not grounded in backend data
  - Hard to understand
  - Irrelevant recommendation

### Workflow stages
- `pending`
- `triaged`
- `in_review`
- `actioned`
- `resolved`
- `dismissed`

### Workflow transitions
- `pending -> triaged|dismissed`
- `triaged -> in_review|dismissed`
- `in_review -> actioned|dismissed`
- `actioned -> resolved|in_review`
- `resolved -> resolved`
- `dismissed -> dismissed`

### Relevant APIs
- `GET /api/feedback/taxonomy`
- `POST /api/feedback/`
- `GET /api/feedback/stats`
- `PATCH /api/feedback/{feedback_id}/status`
- `POST /api/feedback/{feedback_id}/golden-example`

---

## Sentiment + Recommendation Datasets

Dataset files used by the app:

- `backend/data/ml/sentiment_dataset.csv`
- `backend/data/ml/topic_catalog.csv`

The service supports both:
- `text,label`
- `textID,text,sentiment,...`

and handles common encodings (`utf-8`, `utf-8-sig`, `cp1252`, `latin-1`).

### Public dataset download links

1. TweetEval Sentiment
- https://huggingface.co/datasets/tweet_eval
- Keep mapped file at: `backend/data/ml/sentiment_dataset.csv`

2. GoEmotions
- https://huggingface.co/datasets/google-research-datasets/go_emotions
- Map to positive/negative/neutral and keep at: `backend/data/ml/sentiment_dataset.csv`

3. Topic source reference
- https://en.wikipedia.org/wiki/List_of_computer_science_topics
- Curate syllabus topics into: `backend/data/ml/topic_catalog.csv`

---

## ML Runtime APIs

- `GET /api/chat/ml/metrics`
  - Returns accuracy, train/test split counts, class distribution

- `GET /api/chat/ml/dataset-sources`
  - Returns dataset links + expected file target paths

---

## Common Troubleshooting

### Backend exits on startup
- Check `.env` values are valid
- Ensure database is reachable
- Ensure Qdrant URL/API key is valid
- Run:
  ```bash
  python -c "from app.main import app; print('backend-import-ok')"
  ```

### No response in chat
- Check provider quota and fallback models
- Ensure Ollama is running if used as fallback
- Verify model supports tool calling

### Feedback actions blocked
- Confirm user has admin or required permissions
- For Azeez, ensure username/email prefix is `azeez` and app restarted

---

## Run Checklist

1. `pip install -r backend/requirements.txt`
2. Configure `backend/.env`
3. Start backend on `:8000`
4. `npm install` then `npm run dev` in frontend
5. Login and verify:
   - Chat works
   - Feedback reason submission works
   - Admin feedback workflow transitions work
   - `/api/chat/ml/metrics` returns model metrics

---

## License

Use according to your organization/academic policy.
