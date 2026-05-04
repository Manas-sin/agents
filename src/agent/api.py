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
from .tts import synthesize_async as tts_synthesize_async
from .vision import extract_homework_text

WEB_DIR = Path(__file__).parent / "web"

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

    @api.post("/api/tts")
    async def tts(req: TTSRequest) -> Response:
        try:
            wav = await tts_synthesize_async(
                req.text,
                container.settings,
                voice=req.voice or "Charon",
            )
        except Exception as exc:
            raise HTTPException(500, f"TTS failed: {exc}") from exc
        return Response(content=wav, media_type="audio/wav")

    @api.post("/api/chat")
    async def chat(req: ChatRequest) -> dict[str, Any]:
        import asyncio
        import base64

        from .models import Message, Role
        from .persona import INFI_PERSONA

        history = list(container.memory.load(req.session_id))
        lc_messages = [
            SystemMessage(content=INFI_PERSONA),
            SystemMessage(
                content=(
                    "STRICT FORMAT for THIS reply:\n"
                    "- Maximum 1 short sentence (under 20 words).\n"
                    "- Do NOT ask any question at the end. The UI shows action buttons for that.\n"
                    "- Get to the point fast — student is waiting on voice playback."
                )
            ),
        ]
        for m in history:
            lc_messages.append(
                HumanMessage(content=m.content)
                if m.role == Role.USER
                else SystemMessage(content=f"(previous reply) {m.content}")
            )
        lc_messages.append(HumanMessage(content=req.message))

        # Generate text reply (fast Gemini Flash Lite) and TTS in parallel
        # once text is ready.
        llm = get_chat_model("step_solver", container.settings)

        def _gen_text() -> str:
            response = llm.invoke(lc_messages)
            return (
                response.content if isinstance(response.content, str) else str(response.content)
            ).strip()

        text = await asyncio.to_thread(_gen_text)
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
