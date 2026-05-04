from collections.abc import Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from ..models import Message, Role


def to_langchain(messages: Sequence[Message]) -> list[BaseMessage]:
    mapping = {
        Role.USER: HumanMessage,
        Role.ASSISTANT: AIMessage,
        Role.SYSTEM: SystemMessage,
    }
    return [mapping[m.role](content=m.content) for m in messages]


def from_langchain(message: BaseMessage) -> Message:
    role = {
        "human": Role.USER,
        "ai": Role.ASSISTANT,
        "system": Role.SYSTEM,
    }.get(message.type, Role.ASSISTANT)
    text = message.content if isinstance(message.content, str) else str(message.content)
    return Message(role=role, content=text)
