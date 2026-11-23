import os
from typing import Optional

import streamlit as st
from dotenv import load_dotenv

from utils.export import build_revision_markdown
from utils.gemini import GeminiConfigurationError, GeminiServiceError, generate_revision_pack
from utils.pdf_processor import PDFExtractionError, extract_pdf_text


st.set_page_config(
    page_title="STUDYBUD",
    page_icon="SB",
    layout="wide",
    initial_sidebar_state="collapsed",
)

load_dotenv()


def load_css() -> None:
    css_path = os.path.join(os.path.dirname(__file__), "assets", "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as css_file:
            st.markdown(f"<style>{css_file.read()}</style>", unsafe_allow_html=True)


load_css()


@st.cache_resource(show_spinner=False)
def get_api_key() -> str:
    try:
        secret_key = st.secrets["GEMINI_API_KEY"].strip()
    except Exception:
        secret_key = ""
    if secret_key and "PASTE" not in secret_key.upper():
        return secret_key
    environment_key = os.getenv("GEMINI_API_KEY", "").strip()
    return "" if "PASTE" in environment_key.upper() else environment_key


def reset_generation() -> None:
    st.session_state.pop("revision_pack", None)
    st.session_state.pop("source_name", None)
    st.session_state.pop("submitted_quiz", None)
    st.session_state.pop("quiz_answers", None)


def copy_summary(text: str) -> None:
    st.code(text, language=None)
    st.caption("Select the summary above to copy it.")


def quiz_section(pack: dict) -> None:
    st.markdown('<div class="section-heading"><p>Practice</p><h2>Practice quiz</h2></div>', unsafe_allow_html=True)

    questions = pack["quiz"]
    if "quiz_answers" not in st.session_state:
        st.session_state.quiz_answers = {}

    with st.form("revision_quiz"):
        for index, question in enumerate(questions, start=1):
            st.markdown(f"**{index}. {question['question']}**")
            choices = question["options"]
            st.session_state.quiz_answers[index - 1] = st.radio(
                f"Choose an answer for question {index}",
                choices,
                index=None,
                label_visibility="collapsed",
                key=f"quiz_choice_{index}",
            )
            st.markdown("")

        submitted = st.form_submit_button("Submit quiz", use_container_width=True)

    if submitted:
        unanswered = [q for q in range(len(questions)) if st.session_state.quiz_answers.get(q) is None]
        if unanswered:
            st.warning("Answer all five questions before submitting.")
            st.session_state.submitted_quiz = False
            return

        score = 0
        for index, question in enumerate(questions):
            if st.session_state.quiz_answers[index] == question["correct_answer"]:
                score += 1
        st.session_state.submitted_quiz = True
        st.session_state.quiz_score = score

    if st.session_state.get("submitted_quiz"):
        score = st.session_state.quiz_score
        st.success(f"You scored {score} out of {len(questions)}.")
        for index, question in enumerate(questions):
            selected = st.session_state.quiz_answers[index]
            is_correct = selected == question["correct_answer"]
            st.markdown(
                f"{'Correct' if is_correct else 'Review'} — **{index + 1}. {question['question']}**"
            )
            st.caption(
                f"Correct answer: {question['correct_answer']}  \n"
                f"Explanation: {question['explanation']}"
            )

        if st.button("Retake quiz", use_container_width=True):
            st.session_state.submitted_quiz = False
            st.session_state.quiz_answers = {}
            for index in range(1, len(questions) + 1):
                st.session_state.pop(f"quiz_choice_{index}", None)
            st.rerun()


def main() -> None:
    st.markdown(
        '<header class="topbar"><div class="brand"><span class="brand-mark">S</span>'
        '<div><strong>STUDYBUD</strong><small>Less reading. Smarter revising.</small></div></div></header>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<section class="hero"><p class="eyebrow">AI STUDY ASSISTANT</p>'
        '<h1>Turn notes into a<br><em>clearer way to revise.</em></h1>'
        '<p class="intro">Paste a chapter or upload a PDF. STUDYBUD creates a concise summary, '
        'a focused quiz, and the terms worth remembering.</p></section>',
        unsafe_allow_html=True,
    )

    api_key = get_api_key()
    if not api_key:
        st.warning(
            "Gemini is not configured. Add GEMINI_API_KEY to Streamlit Secrets or "
            "set it in your local environment."
        )

    tab_notes, tab_pdf = st.tabs(["Paste notes", "Upload PDF"])
    pasted_text: Optional[str] = None
    source_name = "Pasted notes"

    with tab_notes:
        pasted_text = st.text_area(
            "Notes",
            height=280,
            placeholder="Paste your notes or textbook chapter here...",
            label_visibility="collapsed",
        )

    with tab_pdf:
        uploaded_pdf = st.file_uploader("Choose a PDF", type=["pdf"])
        if uploaded_pdf is not None:
            try:
                extracted_text, document_info = extract_pdf_text(uploaded_pdf)
                pasted_text = extracted_text
                source_name = uploaded_pdf.name
                col1, col2, col3 = st.columns(3)
                col1.metric("Document", uploaded_pdf.name)
                col2.metric("Pages", document_info["pages"])
                col3.metric("Characters", f"{document_info['characters']:,}")
            except PDFExtractionError as exc:
                st.error(str(exc))

    generate_disabled = not api_key
    if st.button("Generate my revision pack", type="primary", use_container_width=True, disabled=generate_disabled):
        if not pasted_text or not pasted_text.strip():
            st.error("Please paste notes or upload a PDF containing readable text.")
        else:
            with st.spinner("Building your revision pack..."):
                try:
                    pack = generate_revision_pack(pasted_text, api_key)
                except GeminiConfigurationError as exc:
                    st.error(str(exc))
                except GeminiServiceError as exc:
                    st.error(str(exc))
                else:
                    st.session_state.revision_pack = pack
                    st.session_state.source_name = source_name
                    st.session_state.submitted_quiz = False
                    st.session_state.quiz_answers = {}
                    st.rerun()

    pack = st.session_state.get("revision_pack")
    if pack:
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

        st.markdown('<div class="section-heading"><p>Quick study</p><h2>Quick summary</h2></div>', unsafe_allow_html=True)
        summary_text = "\n".join(f"- {point}" for point in pack["summary"])
        st.markdown('<div class="summary-card">', unsafe_allow_html=True)
        for point in pack["summary"]:
            st.markdown(f"<p><span class='bullet'></span>{point}</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        copy_col, download_col = st.columns(2)
        with copy_col:
            if st.button("Copy summary", use_container_width=True):
                copy_summary(summary_text)
        with download_col:
            markdown = build_revision_markdown(
                st.session_state.get("source_name", "Revision pack"),
                pack,
            )
            st.download_button(
                "Download revision pack",
                data=markdown,
                file_name="studybud_revision_pack.md",
                mime="text/markdown",
                use_container_width=True,
            )

        quiz_section(pack)

        st.markdown('<div class="section-heading"><p>Remember</p><h2>Key terms</h2></div>', unsafe_allow_html=True)
        for term in pack["key_terms"]:
            st.markdown(
                f'<article class="term-card"><h3>{term["term"]}</h3>'
                f'<p class="meaning">{term["meaning"]}</p>'
                f'<p>{term["explanation"]}</p></article>',
                unsafe_allow_html=True,
            )

        if st.button("Generate another revision pack", use_container_width=True):
            reset_generation()
            st.rerun()


if __name__ == "__main__":
    main()
