from typing import Optional
from ai_service import chat_answer

def answer_question(question: str, note_text: str) -> str:
    """
    Passes the full document text directly to Gemini.
    Gemini has a massive context window, so we don't need vector search.
    """
    # chat_answer expects a list of strings, so we wrap the text in a list
    return chat_answer(question=question, context_chunks=[note_text])