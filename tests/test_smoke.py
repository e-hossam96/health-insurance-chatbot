from backend.app import app
from chatbot_ai import *


def test_backend_app_imports() -> None:
    assert app.title == "Health Insurance Chatbot"


def test_chatbot_ai_imports() -> None:
    import chatbot_ai

    assert hasattr(chatbot_ai, "__name__")
