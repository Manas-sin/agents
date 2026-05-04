from collections.abc import Sequence

from agent.chat_service import ChatService
from agent.interfaces import LLM
from agent.memory.in_memory import InMemoryStore
from agent.models import Message, Role


class FakeLLM(LLM):
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.last_input: list[Message] = []

    def invoke(self, messages: Sequence[Message]) -> Message:
        self.last_input = list(messages)
        return Message(role=Role.ASSISTANT, content=self.reply)


def test_chat_saves_user_and_reply():
    llm = FakeLLM(reply="hi there")
    memory = InMemoryStore()
    service = ChatService(llm=llm, memory=memory)

    reply = service.chat(session_id="s1", user_input="hello")

    assert reply.content == "hi there"
    stored = list(memory.load("s1"))
    assert [m.role for m in stored] == [Role.USER, Role.ASSISTANT]
    assert stored[0].content == "hello"
    assert llm.last_input[-1].content == "hello"
