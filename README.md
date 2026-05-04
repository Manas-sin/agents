# Infi — Homework Agent

A Hinglish-speaking homework buddy built with **LangGraph + Gemini**. Walks K-12 students through their homework one step at a time, with a Samay-Raina-flavoured peer-mentor persona, voice replies, and three input modes: free chat, typed worksheet, or photo of a problem.

## Stack

- **Python 3.13** · `uv` for env + deps
- **LangGraph 1.x** — stateful homework workflow with checkpointed interrupts
- **LangChain 1.x** — LLM abstraction (Gemini / OpenAI / Anthropic / fake)
- **Gemini Flash Lite** — text reasoning + vision (photo-to-homework)
- **Gemini TTS** (`gemini-2.5-flash-preview-tts`) — voice replies
- **FastAPI + uvicorn** — backend
- **Vanilla HTML / CSS / JS** — frontend (no build step)
- **Honcho** — optional cross-session memory

## Quick start

```bash
# 1. Install deps
uv sync

# 2. Configure
cp .env.example .env
# Edit .env and set GOOGLE_API_KEY=AIza...

# 3. Run
uv run agent-serve
# Open http://127.0.0.1:8000
```

## Modes

| Mode | What it does |
|---|---|
| **💬 Chat** | Free-form Hinglish conversation. Bot replies in 1-2 lines + voice + quick-reply chips. |
| **📝 Worksheet** | Paste a multi-question worksheet → Gemini classifies subject + class → breaks into Socratic steps → walks the student through each step with hints. |
| **📸 Photo** | Snap or upload a photo → Gemini vision extracts the homework text → same worksheet flow. |

## Structure

```
src/agent/
├── models.py         # Pydantic entities (Message, Step, etc.)
├── state.py          # LangGraph HomeworkState TypedDict
├── interfaces.py     # Abstract LLM + MemoryStore
├── persona.py        # Infi's Hinglish voice (Samay-style)
├── done_detection.py # Pure function: continue / ask_done / offer_help
├── nodes.py          # Graph nodes (classify, breakdown, solve_step, ...)
├── graph.py          # LangGraph builder
├── homework_service.py
├── chat_service.py
├── api.py            # FastAPI surface
├── app.py            # DI / composition root
├── cli.py            # Local CLI
├── tts.py            # Server-side Gemini TTS
├── vision.py         # Photo → homework text extractor
├── llm/              # Provider implementations + factory
├── memory/           # InMemory + Honcho stores
└── web/              # Frontend (index.html, styles.css, app.js)
```

## Configuration (`.env`)

```bash
LLM_PROVIDER=gemini              # anthropic | openai | gemini | fake
LLM_MODEL=gemini-2.5-flash-lite
GOOGLE_API_KEY=...
# Optional:
HONCHO_API_KEY=...               # for cross-session memory
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/sessions` | Start a worksheet session from text |
| POST | `/api/sessions/from-image` | Start from an uploaded photo |
| POST | `/api/sessions/{id}/resume` | Resume after a `Command(resume=...)` interrupt |
| POST | `/api/chat` | Free chat turn — returns text + audio + follow-up chips |
| POST | `/api/tts` | Standalone text → WAV |
| POST | `/api/translate` | Hinglish → English |

## Tests

```bash
uv run pytest -q
```

## Status

Functionally complete. Voice latency lands at 6-12s warm — bottlenecked by Gemini TTS. To go sub-3s, swap TTS to OpenAI `tts-1` or stream audio.
