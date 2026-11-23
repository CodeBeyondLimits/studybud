# STUDYBUD

STUDYBUD turns notes and PDF documents into concise revision packs with summaries, quizzes, and key terms.

## Local setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Copy `.env.example` to `.env` if using the environment-variable fallback, or create `.streamlit/secrets.toml`:

```toml
GEMINI_API_KEY = "PASTE_YOUR_NEW_GEMINI_API_KEY_HERE"
```

Run locally:

```powershell
streamlit run app.py
```

The application uses one centrally configured key; users never enter an API key.

## Streamlit Community Cloud

1. Push this project to GitHub without `.streamlit/secrets.toml` or `.env`.
2. Deploy the repository in Streamlit Community Cloud.
3. Open **App Settings → Secrets**.
4. Add:

```toml
GEMINI_API_KEY = "your-new-key"
```

Then reboot the app.

## Security

- Never commit a real API key.
- Treat any previously exposed key as compromised and rotate it.
- `.streamlit/secrets.toml` and `.env` are excluded by `.gitignore`.
- Gemini requests and keys remain on the server side.
