from uuid import uuid4

from dotenv import load_dotenv

from .app import create_app


def run() -> None:
    load_dotenv()
    app = create_app()
    session_id = str(uuid4())

    print(f"Agent ready (session={session_id[:8]}). Type 'exit' to quit.")
    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break

        reply = app.chat.chat(session_id, user_input)
        print(f"bot> {reply.content}")


if __name__ == "__main__":
    run()
