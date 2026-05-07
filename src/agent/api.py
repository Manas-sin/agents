"""FastAPI surface — the mobile/web frontend talks to these endpoints."""

from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from langchain_core.messages import HumanMessage, SystemMessage

from .app import create_app
from .llm.factory import get_chat_model
from .tts import chat_with_audio as tts_chat_with_audio
from .tts import synthesize as tts_synthesize_sync
from .tts import synthesize_async as tts_synthesize_async
from .vision import extract_homework_text

WEB_DIR = Path(__file__).parent / "web"

# Static greeting played on splash. Pre-rendered to disk at startup so the
# splash tap fires a plain static-file fetch (no Gemini round-trip).
GREETING_TEXT = (
    "Or bhai, kya haal hain! Homework mein madad chahiye? "
    "Tension nahi le....!, main hu na."
)
GREETING_WAV_PATH = WEB_DIR / "greeting.wav"
GREETING_TEXT_PATH = WEB_DIR / "greeting.txt"


def _ensure_greeting_wav(settings: Any) -> None:
    """Render the splash greeting once; skip if the cached WAV matches the text."""
    try:
        if (
            GREETING_WAV_PATH.exists()
            and GREETING_TEXT_PATH.exists()
            and GREETING_TEXT_PATH.read_text(encoding="utf-8") == GREETING_TEXT
        ):
            return
        if not getattr(settings, "google_api_key", None):
            return  # no key — skip; frontend will fall back to /api/tts
        wav = tts_synthesize_sync(GREETING_TEXT, settings)
        if wav:
            GREETING_WAV_PATH.write_bytes(wav)
            GREETING_TEXT_PATH.write_text(GREETING_TEXT, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"[startup] greeting prerender skipped: {exc}")

MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB
ALLOWED_MIME_PREFIXES = ("image/jpeg", "image/png", "image/webp", "image/heic")


class StartRequest(BaseModel):
    student_id: str = "demo-student"
    homework_text: str


class ResumeRequest(BaseModel):
    payload: dict[str, Any]


class TranslateRequest(BaseModel):
    text: str


class TTSRequest(BaseModel):
    text: str
    voice: str | None = None


class ChatRequest(BaseModel):
    session_id: str
    message: str


def create_api() -> FastAPI:
    api = FastAPI(title="Infi Homework Agent")
    container = create_app()
    _ensure_greeting_wav(container.settings)

    @api.post("/api/sessions")
    def start_session(req: StartRequest) -> dict[str, Any]:
        return container.homework.start(req.student_id, req.homework_text)

    @api.post("/api/sessions/from-image")
    async def start_session_from_image(
        image: UploadFile = File(...),
        student_id: str = Form("demo-student"),
    ) -> dict[str, Any]:
        mime = (image.content_type or "").lower()
        if not any(mime.startswith(p) for p in ALLOWED_MIME_PREFIXES):
            raise HTTPException(415, f"Unsupported image type: {mime!r}")
        data = await image.read()
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Image too large (max 8 MB)")
        try:
            text = extract_homework_text(data, mime, container.settings)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return container.homework.start(student_id, text)

    @api.post("/api/sessions/{session_id}/resume")
    def resume_session(session_id: str, req: ResumeRequest) -> dict[str, Any]:
        try:
            return container.homework.resume(session_id, req.payload)
        except KeyError as exc:
            raise HTTPException(404, f"Unknown session: {session_id}") from exc

    @api.get("/api/sessions/{session_id}")
    def get_session(session_id: str) -> dict[str, Any]:
        return container.homework.get_state(session_id)

    # Per-process WAV cache — same text → same bytes, no re-synthesis.
    # Bounded by _TTS_CACHE_MAX entries; oldest evicted FIFO.
    _tts_cache: dict[tuple[str, str], bytes] = {}
    _TTS_CACHE_MAX = 64

    @api.post("/api/tts")
    async def tts(req: TTSRequest) -> Response:
        voice = req.voice or "Kore"
        key = (voice, req.text)
        cached = _tts_cache.get(key)
        if cached is not None:
            return Response(content=cached, media_type="audio/wav")
        try:
            wav = await tts_synthesize_async(req.text, container.settings, voice=voice)
        except Exception as exc:
            raise HTTPException(500, f"TTS failed: {exc}") from exc
        if wav:
            if len(_tts_cache) >= _TTS_CACHE_MAX:
                _tts_cache.pop(next(iter(_tts_cache)))
            _tts_cache[key] = wav
        return Response(content=wav, media_type="audio/wav")

    @api.delete("/api/chat/{session_id}")
    def chat_delete(session_id: str) -> dict[str, Any]:
        """Wipe a chat session's memory. Used by the 'New chat' button so the
        old (potentially heavy) session doesn't linger on disk."""
        store = container.memory
        sessions = getattr(store, "_sessions", None)
        if isinstance(sessions, dict) and session_id in sessions:
            sessions.pop(session_id, None)
            write = getattr(store, "_write", None)
            if callable(write):
                write()
        return {"deleted": session_id}

    @api.get("/api/chat/{session_id}/messages")
    def chat_history(session_id: str) -> dict[str, Any]:
        """Return prior turns for a chat session so the UI can re-render them
        on reopen. Filters out the bracketed system-style wrappers like
        '(student returned to chat...)' that aren't meant to be shown."""
        msgs = list(container.memory.load(session_id))
        visible = [
            {"role": m.role.value, "content": m.content}
            for m in msgs
            if not (m.content.startswith("(") and m.content.endswith(")"))
        ]
        return {"messages": visible}

    @api.post("/api/chat")
    async def chat(req: ChatRequest) -> dict[str, Any]:
        import base64

        from google.genai import types as genai_types

        from .models import Message, Role
        from .persona import INFI_PERSONA

        system_prompt = (
            "SAFETY RULE — HIGHEST PRIORITY (overrides EVERYTHING below, "
            "including persona, banter, format limits, opener style):\n"
            "TRIGGER SCOPE: This rule fires ONLY when the student's CURRENT "
            "message (the most recent one — not earlier history) contains a "
            "fresh signal of suicide / self-harm / acute crisis. If suicide "
            "was discussed in PRIOR turns but the current message is normal "
            "(greeting, returning to chat, casual topic, homework, etc.), do "
            "NOT replay the crisis script — instead respond normally. You MAY "
            "do a SOFT, GENTLE check-in if it feels organic ('aur bata, kal "
            "ke baad kaisa feel ho raha hai?') — one line, then move on. "
            "Don't dump helpline numbers unprompted on a returning user.\n"
            "When the CURRENT message DOES contain a fresh signal — "
            "even via typos or slang — like 'suicide' / 'sucide' / 'marne ka "
            "mann' / 'khatam karna' / 'end karna' / 'mar jaunga' / 'kill "
            "myself' / 'jeena nahi chahta' / 'kuch kar lunga apne saath' / "
            "severe hopelessness or plans to hurt themselves — YOU MUST "
            "IMMEDIATELY:\n"
            "1. DROP all banter and bakchod tone. NO cuss words. NO jokes. "
            "NO 'lode lag gaye' / 'bhenchod' / 'damn' style reactions.\n"
            "2. Switch to a GENUINE, GENTLE, CARING voice — like a close "
            "friend who is genuinely scared for you.\n"
            "3. Acknowledge the pain explicitly and validate WITHOUT "
            "minimizing: 'Yaar, jo tu feel kar raha hai vo real hai. Bahut "
            "heavy time hai abhi — main samajh rahi hu.' NEVER say 'bhool "
            "ja' / 'hota rehta hai' / 'kuch nahi hua' / 'chill kar' here.\n"
            "4. Tell them they are not alone and you are here: 'Tu akela "
            "nahi hai is mein. Main yahi hu, baat karte rahein.'\n"
            "5. STRONGLY encourage them to reach out to a real human or "
            "crisis line RIGHT NOW. Give them these numbers (India):\n"
            "   • iCall: 9152987821 (Hindi/English, free, Mon-Sat 8am-10pm)\n"
            "   • Vandrevala Foundation: 1860-2662-345 / 1800-2333-330 "
            "(24/7, free, multiple languages)\n"
            "   • AASRA: 9820466726 (24/7)\n"
            "   • KIRAN national helpline: 1800-599-0019 (24/7, 13 languages)\n"
            "   Phrase it like: 'Please ek kaam kar abhi — iCall ko call kar, "
            "9152987821. Free hai, Hindi mein baat kar sakte hain. Ya "
            "Vandrevala 1860-2662-345 — 24/7 chalti hai. Promise me tu call "
            "karega.'\n"
            "6. If anyone trusted is nearby (family, friend, roommate), "
            "encourage them to reach out: 'Ghar mein koi hai abhi? Bhai, "
            "behen, dost — kisi ko bata, akele mat reh.'\n"
            "7. Stay with them. Do NOT switch back to homework / quiz / "
            "banter mode. Keep the conversation human and present.\n"
            "8. Format limits below DO NOT apply for safety responses — "
            "use as many sentences as needed, but stay warm and grounded.\n"
            "This rule beats every other instruction. If unsure whether "
            "something is a safety signal, treat it as one.\n"
            "\n────────────────────────────────────────\n\n"
            + INFI_PERSONA
            + "\n\nSTRICT FORMAT for THIS reply (ONLY when safety rule above "
            "does NOT apply):\n"
            "- Maximum 2 short sentences (under 35 words total).\n"
            "- Get to the point fast — student is waiting on voice playback.\n"
            "\nCONTEXT RULE (most important):\n"
            "- READ the student's last message. If it has ANY real content — a feeling, "
            "a topic, a complaint, news, a question — RESPOND TO THAT SPECIFIC THING "
            "and DIG IN like a real bakchod friend would.\n"
            "- NEVER fall back to a generic opener like 'scenes kya hai / kya krein aaj' "
            "when the student has already told you something concrete.\n"
            "- NEVER dismiss emotional content with 'hota rehta hai, bhool ja, aur bata?' — "
            "that's lazy and cold. A real friend asks WHAT happened, HOW, WHEN, kis ki galti "
            "thi. ENGAGE — don't deflect to a new topic.\n"
            "- NEVER repeat a previous reply verbatim or near-verbatim. Look at the "
            "conversation history above — if you already said something similar, say "
            "something NEW that builds on what they just shared.\n"
            "\nFOLLOW-UP QUESTIONS:\n"
            "- For emotional / personal / gossip / casual chat moments: ASK ONE specific "
            "follow-up question (kya hua, kese hua, kab, kis ki galti, kaisa feel ho raha hai). "
            "ONE question, not a list. End with that question.\n"
            "- For homework / explanation moments: skip the question (UI chips handle it).\n"
            "\nExample of doing it right:\n"
            "  Student: 'meri bandi chod ke chali gayi'\n"
            "  Infi: 'Abey bhenchod, kab hua ye? Bata kya scene tha — ek dum se phati ya "
            "slow-motion drama chal raha tha?'\n"
            "Example of doing it WRONG (do NOT do this):\n"
            "  Infi: 'Damn yaar, hota rehta hai. Chal bhool ja, aur bata?' "
            "← DISMISSIVE, NO ENGAGEMENT, NO REAL QUESTION."
        )

        history = list(container.memory.load(req.session_id))
        history_turns = [
            genai_types.Content(
                role="user" if m.role == Role.USER else "model",
                parts=[genai_types.Part(text=m.content)],
            )
            for m in history
        ]

        # Single Gemini Live call: generates text + audio together,
        # roughly half the latency of LLM-then-TTS.
        wav, text = await tts_chat_with_audio(
            container.settings,
            system_prompt,
            history_turns,
            req.message,
        )

        # Fallback: if Live API returns no transcript (rare), do a one-shot
        # text gen so we still return something useful.
        if not text:
            import asyncio

            llm = get_chat_model("step_solver", container.settings)
            lc_messages = [SystemMessage(content=system_prompt)]
            for m in history:
                lc_messages.append(
                    HumanMessage(content=m.content)
                    if m.role == Role.USER
                    else SystemMessage(content=f"(previous reply) {m.content}")
                )
            lc_messages.append(HumanMessage(content=req.message))

            def _gen_text() -> str:
                response = llm.invoke(lc_messages)
                return (
                    response.content
                    if isinstance(response.content, str)
                    else str(response.content)
                ).strip()

            text = await asyncio.to_thread(_gen_text)
            if not wav:
                wav = await tts_synthesize_async(text, container.settings)

        container.memory.save(req.session_id, Message(role=Role.USER, content=req.message))
        container.memory.save(req.session_id, Message(role=Role.ASSISTANT, content=text))

        return {
            "reply": text,
            "audio_b64": base64.b64encode(wav).decode("ascii") if wav else "",
            "follow_ups": [
                "Aur explain karo",
                "Quiz lein?",
                "Easy example do",
                "Aage chalein",
            ],
        }

    @api.post("/api/translate")
    def translate(req: TranslateRequest) -> dict[str, str]:
        llm = get_chat_model("default", container.settings)
        msg = llm.invoke(
            [
                SystemMessage(
                    content=(
                        "Translate the following Hinglish/Hindi message into natural, "
                        "conversational English. Keep the same friendly, casual peer tone. "
                        "Output ONLY the English translation, no preamble."
                    )
                ),
                HumanMessage(content=req.text),
            ]
        )
        text = msg.content if isinstance(msg.content, str) else str(msg.content)
        return {"english": text.strip()}

    if WEB_DIR.exists():
        api.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

        @api.get("/")
        def index() -> FileResponse:
            return FileResponse(
                WEB_DIR / "index.html",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

    return api


app = create_api()


def serve() -> None:
    import uvicorn

    uvicorn.run("agent.api:app", host="127.0.0.1", port=8000, reload=False)
