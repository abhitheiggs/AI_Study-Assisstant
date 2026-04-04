# AI-Based Intelligent Study Assistant

AI-Based Intelligent Study Assistant for **Automated Notes, Flashcards and Quiz Generation**.

## Features

- User authentication (register/login/logout) using Flask sessions
- Upload **PDF** or **TXT**
- Extract text from PDF
- Generate:
  - Summary (HuggingFace `transformers` summarization pipeline)
  - Flashcards (simple Q&A / cloze questions)
  - Quiz (simple MCQ)
- SQLite database (local, in `database/`)

## Project structure

```
AI-Study-Assistant/
├── frontend/              # reference (optional)
├── backend/               # Flask backend
├── database/              # SQLite DB will be created here
├── static/                # CSS/JS
└── templates/             # HTML pages
```

## How to run (Windows)

### 1) Create a virtual environment

Open PowerShell:

```bash
cd "d:\ai modle\AI-Study-Assistant\backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2) Install dependencies

```bash
```

> Note: `torch` and `transformers` are large. First run may take time because the summarization model downloads automatically.

### 3) Start the server

```bash
python app.py
```

Open:
- `http://127.0.0.1:5000/register`
- `http://127.0.0.1:5000/login`
- `http://127.0.0.1:5000/dashboard`

## Usage

1. Register and login
2. Upload a `.pdf` or `.txt`
3. On the dashboard, click:
   - **Generate / Refresh** under Summary
   - **Generate / Refresh** under Flashcards
   - **Generate / Refresh** under Quiz

## Notes (beginner-friendly)

- The database file is created automatically at `AI-Study-Assistant/database/study_assistant.db`
- If the HuggingFace model can’t download (no internet), the app still works using a simple fallback summary.

