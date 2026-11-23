"""Concise prompt construction for revision-pack generation."""


def build_revision_prompt(source_text: str) -> str:
    return (
        "Create exam-focused study material from the source text below. "
        "Use simple language, rely only on the source, and keep explanations brief. "
        "Return 5 or 6 summary points, exactly 5 multiple-choice questions with "
        "4 unique options and one correct answer plus explanation each, and exactly "
        "3 key terms with a simple meaning and brief explanation.\n\n"
        f"SOURCE TEXT:\n{source_text}"
    )
