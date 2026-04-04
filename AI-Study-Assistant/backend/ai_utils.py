import json
import os
import re
from functools import lru_cache
from typing import Dict, List

from PyPDF2 import PdfReader


def extract_text_from_pdf(pdf_path: str) -> str:
    try:
        reader = PdfReader(pdf_path)
    except Exception:
        return ""
    parts: List[str] = []
    for page in reader.pages:
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        parts.append(txt)
    return "\n".join(parts).strip()


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sentences(text: str) -> List[str]:
    """
    Beginner-friendly sentence splitter (no heavy NLP deps).
    """
    text = normalize_text(text)
    if not text:
        return []
    # Split on . ? ! followed by space/newline.
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) >= 20]
    return sentences


@lru_cache(maxsize=1)
def _get_summarizer():
    """
    Lazy-load the HF pipeline once. This keeps app startup fast.
    """
    from transformers import pipeline

    model_name = os.environ.get("SUMMARIZER_MODEL", "sshleifer/distilbart-cnn-12-6")
    return pipeline("summarization", model=model_name)


def summarize_text(text: str, max_chars: int = 12000) -> str:
    """
    Summarize with HF transformers. If model download fails (offline),
    fall back to a simple extractive summary so the app still runs.
    """
    text = normalize_text(text)
    if not text:
        return ""

    # Transformers models have input limits; keep it simple.
    text = text[:max_chars]

    try:
        summarizer = _get_summarizer()
        out = summarizer(text, max_length=180, min_length=60, do_sample=False)
        return (out[0].get("summary_text") or "").strip()
    except Exception:
        # Fallback: first ~6 sentences.
        sents = split_sentences(text)
        return " ".join(sents[:6]).strip()


def _pick_keyword(sentence: str) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z\-]{3,}", sentence)
    if not words:
        return ""
    stop = {
        "this",
        "that",
        "with",
        "from",
        "into",
        "than",
        "then",
        "when",
        "where",
        "which",
        "their",
        "there",
        "these",
        "those",
        "because",
        "while",
        "about",
        "between",
        "through",
        "using",
        "used",
        "also",
        "such",
        "have",
        "has",
        "been",
        "were",
        "will",
        "would",
        "could",
        "should",
        "into",
        "over",
        "under",
        "most",
        "some",
        "many",
        "more",
        "less",
    }
    candidates = [w for w in words if w.lower() not in stop]
    if not candidates:
        candidates = words
    # Prefer longer words (often more “key-term”-like).
    return sorted(candidates, key=lambda w: (-len(w), w.lower()))[0]


def generate_flashcards(text: str, limit: int = 10) -> List[Dict[str, str]]:
    """
    Anki-style "Basic" flashcards (Front / Back).

    Heuristic approach:
    - Pick informative sentences
    - Choose a keyword
    - Front: cloze-style sentence with blank
    - Back: keyword (answer)
    """
    sentences = split_sentences(text)
    cards: List[Dict[str, str]] = []

    for s in sentences:
        if len(cards) >= limit:
            break
        kw = _pick_keyword(s)
        if not kw:
            continue
        front = re.sub(rf"\b{re.escape(kw)}\b", "_____", s, flags=re.IGNORECASE)
        if front == s:
            continue
        cards.append({"front": front.strip(), "back": kw.strip()})

    return cards


def generate_quiz(text: str, limit: int = 5) -> List[Dict]:
    """
    Generate very simple MCQs (college-minor-project level):
    - For each question, hide a keyword in a sentence
    - Build options from other keywords as distractors
    """
    sentences = split_sentences(text)
    keywords: List[str] = []
    for s in sentences[:50]:
        kw = _pick_keyword(s)
        if kw and kw.lower() not in {k.lower() for k in keywords}:
            keywords.append(kw)

    quiz: List[Dict] = []
    used = set()

    for s in sentences:
        if len(quiz) >= limit:
            break
        ans = _pick_keyword(s)
        if not ans or ans.lower() in used:
            continue
        used.add(ans.lower())

        q = re.sub(rf"\b{re.escape(ans)}\b", "_____", s, flags=re.IGNORECASE).strip()
        if q == s:
            continue

        distractors = [k for k in keywords if k.lower() != ans.lower()]
        distractors = distractors[:3]
        options = distractors + [ans]
        # Keep deterministic order: place correct at end.
        correct_index = len(options) - 1
        quiz.append(
            {
                "question": q,
                "options": options,
                "correct_index": correct_index,
            }
        )

    return quiz


def options_to_json(options: List[str]) -> str:
    return json.dumps(options, ensure_ascii=False)


def options_from_json(options_json: str) -> List[str]:
    return json.loads(options_json)

