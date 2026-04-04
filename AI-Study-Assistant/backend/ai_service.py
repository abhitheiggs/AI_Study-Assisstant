#improved

import json
import os
from typing import Any, Dict, List, Optional

from ai_utils import generate_flashcards as heuristic_flashcards
from ai_utils import generate_quiz as heuristic_quiz
from ai_utils import summarize_text as heuristic_summary


class AIServiceError(Exception):
    pass


def _extract_json(text: str) -> Optional[str]:
    """
    Extract the first JSON array/object found in a string.
    This makes the system tolerant to extra prose around JSON.
    """
    if not text:
        return None
    s = text.strip()
    first_arr = s.find("[")
    first_obj = s.find("{")
    starts = [i for i in (first_arr, first_obj) if i != -1]
    if not starts:
        return None
    start = min(starts)
    
    # Determine end by matching closing bracket type.
    if s[start] == "[":
        end = s.rfind("]")
    else:
        end = s.rfind("}")
    if end == -1 or end <= start:
        return None
    return s[start : end + 1]


def _safe_json_loads(text: str) -> Any:
    candidate = _extract_json(text) or text
    return json.loads(candidate)


def _has_gemini() -> bool:
    """
    Checks if the Gemini API key is configured.
    """
    return bool(os.environ.get("GEMINI_API_KEY"))


def _get_gemini_client():
    """
    Uses the modern `google-genai` client.
    """
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise AIServiceError("GEMINI_API_KEY is not set.")
    return genai.Client(api_key=api_key)


def _gemini_generate(prompt: str, system: Optional[str] = None) -> str:
    """
    Standard text generation call using Gemini 2.5 Flash.
    """
    client = _get_gemini_client()
    model = "gemini-2.5-flash"
    full = prompt if not system else f"{system}\n\n{prompt}"
    resp = client.models.generate_content(model=model, contents=full)
    return (getattr(resp, "text", None) or "").strip()


def generate_summary(text: str) -> str:
    """
    LLM-first summary. Falls back to local heuristic summary if API isn't configured.
    """
    text = (text or "").strip()
    if not text:
        return ""

    system = (
        "You are a helpful study assistant. Summarize the user's notes for exam revision. "
        "Be concise, factual, and well-structured."
    )
    user_prompt = (
    "You are an expert academic assistant. Analyze the following study material and generate a COMPLETE, structured, and exam-focused summary.\n\n"

    "INSTRUCTIONS:\n"
    "1. Cover ALL topics and subtopics. Do not skip anything important.\n"
    "2. Keep explanations simple, clear, and easy to revise.\n"
    "3. Focus on high-yield, exam-relevant content.\n\n"

    "OUTPUT FORMAT:\n\n"

    "1. TOPIC-WISE SUMMARY:\n"
    "- Break content into topics/subtopics\n"
    "- For each topic:\n"
    "  • Short explanation\n"
    "  • Key concepts\n\n"

    "2. IMPORTANT BULLET POINTS:\n"
    "- Provide 10–20 crisp, high-yield bullet points\n"
    "- Include formulas, facts, and important ideas\n\n"

    "3. KEY TERMS:\n"
    "- List important terms with 1-line definitions\n\n"

    "4. QUICK REVISION:\n"
    "- Provide a very short last-day revision summary (5–7 bullets)\n\n"

    "5. PRACTICE QUESTIONS:\n"
    "- 5 MCQs (with answers)\n"
    "- 3 Short answer questions\n"
    "- 2 Long answer questions\n\n"

    "Ensure the output is structured, clean, and easy to study.\n\n"

    f"STUDY MATERIAL:\n{text}"
    )
    

    # try:
    #     if _has_gemini():
    #         return _gemini_generate(user_prompt, system=system)
    #     return heuristic_summary(text)
    # except Exception:
    #     return heuristic_summary(text)

    try:
        if _has_gemini():
            return _gemini_generate(user_prompt, system=system)
        return ("Ai not working!")
    except Exception:
        return ("Ai not working!")

def generate_flashcards(text: str, limit: int = 12) -> List[Dict[str, str]]:
    """
    Returns Anki-like Q/A pairs: [{question, answer}, ...]
    LLM-first with fallback.
    """
    text = (text or "").strip()
    if not text:
        return []

    prompt = f"""
Create {limit} high-quality study flashcards for active recall from the notes.
Rules:
- Each card MUST be concept-based.
- Question should be short and clear.
- Answer should be short (1-2 sentences or a definition).
- Avoid duplicates.

Return ONLY valid JSON (no markdown), exactly as:
[
  {{"question":"...","answer":"..."}},
  ...
]

NOTES:
{text}
""".strip()

    try:
        if _has_gemini():
            raw = _gemini_generate(prompt, system="You generate clean JSON for flashcards.")
            data = _safe_json_loads(raw)
            cards: List[Dict[str, str]] = []
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    q = (item.get("question") or "").strip()
                    a = (item.get("answer") or "").strip()
                    if q and a:
                        cards.append({"question": q, "answer": a})
            return cards[:limit]
        else:
            raise AIServiceError("API not configured.")
    except Exception:
        # Fallback to heuristic cloze cards, converted to Q/A
        fallback = heuristic_flashcards(text, limit=min(limit, 10))
        return [{"question": c.get("front", ""), "answer": c.get("back", "")} for c in fallback if c.get("front") and c.get("back")]


def generate_quiz(text: str, limit: int = 6) -> List[Dict[str, Any]]:
    """
    Returns MCQs with explanation:
    [
      {"question": "...", "options": ["A","B","C","D"], "answer": "B", "explanation": "..."}
    ]
    LLM-first with fallback.
    """
    text = (text or "").strip()
    if not text:
        return []

    prompt = f"""
Create {limit} multiple-choice questions (MCQs) from the notes.
Rules:
- Each question must have exactly 4 options.
- Exactly 1 correct answer.
- Include a short explanation (1-2 sentences) why it's correct.
- Keep options plausible.

Return ONLY valid JSON (no markdown), exactly as:
[
  {{"question":"...","options":["A","B","C","D"],"answer":"<one of the options exactly>","explanation":"..."}},
  ...
]

NOTES:
{text}
""".strip()

    try:
        if _has_gemini():
            raw = _gemini_generate(prompt, system="You generate clean JSON for quizzes.")
            data = _safe_json_loads(raw)
            out: List[Dict[str, Any]] = []
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    q = (item.get("question") or "").strip()
                    options = item.get("options") or []
                    ans = (item.get("answer") or "").strip()
                    exp = (item.get("explanation") or "").strip()
                    
                    if not q or not isinstance(options, list) or len(options) != 4:
                        continue
                    
                    options = [str(o).strip() for o in options]
                    if any(not o for o in options):
                        continue
                    
                    # Ensure uniqueness to avoid confusing MCQs
                    if len({o.lower() for o in options}) != 4:
                        continue
                    if ans not in options:
                        continue
                    if not exp:
                        exp = "Correct based on the notes."
                    
                    out.append({
                        "question": q,
                        "options": options,
                        "answer": ans,
                        "explanation": exp,
                    })
            return out[:limit]
        else:
            raise AIServiceError("API not configured.")
    except Exception:
        # Fallback: heuristic quiz, add best-effort answer/explanation
        fb = heuristic_quiz(text, limit=min(limit, 5))
        out: List[Dict[str, Any]] = []
        for it in fb:
            options = it.get("options") or []
            ci = int(it.get("correct_index") or 0)
            ans = options[ci] if options and 0 <= ci < len(options) else (options[0] if options else "")
            out.append({
                "question": it.get("question", ""),
                "options": options,
                "answer": ans,
                "explanation": "Derived from the notes (fallback mode).",
            })
        return out


def chat_answer(question: str, context_chunks: List[str]) -> str:
    """
    Answer a question using retrieved context chunks.
    """
    q = (question or "").strip()
    if not q:
        return ""
    
    context = "\n\n---\n\n".join([c.strip() for c in context_chunks if c and c.strip()][:8])
    
    try:
        system = (
            "You are a helpful study assistant. Use ONLY the provided context to answer. "
            "If the answer is not in the context, say you don't have enough information."
        )
        user_prompt = f"CONTEXT:\n{context}\n\nQUESTION:\n{q}\n\nAnswer clearly in 3-6 sentences."

        if _has_gemini():
            return _gemini_generate(user_prompt, system=system)
            
        return "AI provider is not configured. Set GEMINI_API_KEY and try again."
    except Exception:
        return "I couldn't reach the AI service right now. Please try again."