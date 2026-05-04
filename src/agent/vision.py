"""Extract homework text from an image using Gemini's vision capabilities."""

import base64

from langchain_core.messages import HumanMessage, SystemMessage

from .config import Settings
from .llm.factory import get_chat_model

_VISION_INSTRUCTIONS = """\
You are looking at a photo of a student's homework. Extract every question
and instruction visible in the image, exactly as written. Preserve numbering.
Output ONLY the extracted homework text — no commentary, no explanations.
If the image has no readable homework, respond with the single word: NONE.
"""


def extract_homework_text(image_bytes: bytes, mime_type: str, settings: Settings) -> str:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    llm = get_chat_model("vision", settings)

    response = llm.invoke(
        [
            SystemMessage(content=_VISION_INSTRUCTIONS),
            HumanMessage(
                content=[
                    {"type": "text", "text": "Extract the homework from this image."},
                    {
                        "type": "image_url",
                        "image_url": f"data:{mime_type};base64,{encoded}",
                    },
                ]
            ),
        ]
    )
    text = response.content if isinstance(response.content, str) else str(response.content)
    text = text.strip()
    if text.upper() == "NONE":
        raise ValueError("No homework text could be extracted from the image.")
    return text
