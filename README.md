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

The app defaults to the stable `gemini-3.8-flash` model and falls back to
`gemini-3.6-flash` after temporary primary-model service failures. Override the
models with `GEMINI_MODEL` and `GEMINI_FALLBACK_MODEL`; set the latter to an
empty value to disable fallback. The app checks configured models against the
models available to the configured API key before generation.
See Google's [Gemini models documentation](https://ai.google.dev/gemini-api/docs/models)
for current model status and capabilities.

Run locally:

```powershell
streamlit run app.py
```

The application uses one centrally configured key; users never enter an API key.
Generated revision packs can be downloaded as Markdown, plain text, or PDF.

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
