"""Server-side TTS via Gemini Live API + native audio model.

Uses the same `gemini-2.5-flash-native-audio-latest` model the infi-companion-voice
reference does — much more natural intonation than the bolt-on TTS preview model.

This is a one-shot text → audio call (not full bidirectional WebRTC).
"""

import io
import struct
from functools import lru_cache

from google import genai
from google.genai import types

from .config import Settings

_LIVE_MODEL = "models/gemini-2.5-flash-native-audio-latest"
_FAST_TTS_MODEL = "gemini-2.5-flash-preview-tts"  # generates ~4x real-time
_DEFAULT_VOICE = "Kore"  # firm, grounded female — calm bestie vibe
_PCM_RATE = 24000

# Style prefix tells preview-tts to code-switch correctly between Hindi and
# English: Hindi words ("bhasad", "yaar") in Hindi pronunciation, English words
# ("scenes", "chill", "exam") in normal English pronunciation. Without this the
# model either reads everything letter-by-letter or applies one accent globally.
_HINGLISH_STYLE = (
    "Read the following as a young Indian speaker speaking natural casual "
    "Hinglish — code-switch fluidly: pronounce Hindi/Romanized-Hindi words "
    "(bhasad, yaar, bhai, kya, scene-kya-hai's 'kya hai') the way a native "
    "Hindi speaker would, AND pronounce English words (scenes, chill, exam, "
    "homework, quiz) with their normal English pronunciation — NOT spelled "
    "out letter-by-letter, NOT with an exaggerated accent. Smooth, "
    "conversational, like a friend on a call: "
)
_PCM_CHANNELS = 1
_PCM_SAMPLE_WIDTH = 2


@lru_cache(maxsize=1)
def _client_for(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def synthesize(text: str, settings: Settings, voice: str = _DEFAULT_VOICE) -> bytes:
    """Fast TTS via the preview-tts model. Generates ~4x faster than realtime —
    much better latency than the Live API's real-time-speed model."""
    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY not set — cannot synthesize speech.")

    client = _client_for(settings.google_api_key)
    response = client.models.generate_content(
        model=_FAST_TTS_MODEL,
        contents=_HINGLISH_STYLE + text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        ),
    )
    try:
        pcm = response.candidates[0].content.parts[0].inline_data.data
    except (AttributeError, IndexError, TypeError):
        pcm = None
    if not pcm:
        return b""  # caller can decide what to do — typically just no audio
    return _pcm_to_wav(pcm)


async def synthesize_async(text: str, settings: Settings, voice: str = _DEFAULT_VOICE) -> bytes:
    """Async wrapper around synthesize for the FastAPI endpoint."""
    import asyncio
    return await asyncio.to_thread(synthesize, text, settings, voice)


async def chat_with_audio(
    settings: Settings,
    system_prompt: str,
    history_turns: list,
    user_message: str,
    voice: str = _DEFAULT_VOICE,
) -> tuple[bytes, str]:
    """One Live API call → (WAV bytes, transcript text). Half the latency of doing
    text-LLM + TTS as two separate hops."""
    turns = list(history_turns) + [
        types.Content(role="user", parts=[types.Part(text=user_message)])
    ]
    pcm, transcript = await _live_call(settings, voice, system_prompt, turns)
    wav = _pcm_to_wav(pcm) if pcm else b""
    return wav, transcript


async def _live_call(
    settings: Settings,
    voice: str,
    system_prompt: str,
    turns: list,
) -> tuple[bytes, str]:
    """Internal: one Live API roundtrip → (raw_pcm_bytes, output_transcript)."""
    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY not set — cannot synthesize speech.")
    client = _client_for(settings.google_api_key)

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        ),
        thinking_config=types.ThinkingConfig(thinking_budget=512),
        system_instruction=types.Content(parts=[types.Part(text=system_prompt)]),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )

    audio_chunks: list[bytes] = []
    text_chunks: list[str] = []
    async with client.aio.live.connect(model=_LIVE_MODEL, config=config) as session:
        await session.send_client_content(turns=turns, turn_complete=True)
        async for response in session.receive():
            if getattr(response, "data", None):
                audio_chunks.append(response.data)
            sc = getattr(response, "server_content", None)
            if sc:
                ot = getattr(sc, "output_transcription", None)
                if ot and getattr(ot, "text", None):
                    text_chunks.append(ot.text)
                if getattr(sc, "turn_complete", False):
                    break

    return b"".join(audio_chunks), "".join(text_chunks).strip()


def _pcm_to_wav(pcm: bytes) -> bytes:
    """Wrap raw PCM 24kHz mono int16 into a minimal WAV container."""
    out = io.BytesIO()
    n_samples = len(pcm) // _PCM_SAMPLE_WIDTH
    byte_rate = _PCM_RATE * _PCM_CHANNELS * _PCM_SAMPLE_WIDTH
    block_align = _PCM_CHANNELS * _PCM_SAMPLE_WIDTH

    out.write(b"RIFF")
    out.write(struct.pack("<I", 36 + n_samples * _PCM_SAMPLE_WIDTH))
    out.write(b"WAVE")

    out.write(b"fmt ")
    out.write(struct.pack("<I", 16))
    out.write(struct.pack("<H", 1))
    out.write(struct.pack("<H", _PCM_CHANNELS))
    out.write(struct.pack("<I", _PCM_RATE))
    out.write(struct.pack("<I", byte_rate))
    out.write(struct.pack("<H", block_align))
    out.write(struct.pack("<H", _PCM_SAMPLE_WIDTH * 8))

    out.write(b"data")
    out.write(struct.pack("<I", n_samples * _PCM_SAMPLE_WIDTH))
    out.write(pcm)
    return out.getvalue()
