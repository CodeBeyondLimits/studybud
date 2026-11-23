from io import BytesIO
from xml.sax.saxutils import escape
from typing import Dict

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def build_revision_markdown(source_name: str, pack: Dict) -> str:
    lines = [
        "# STUDYBUD Revision Pack",
        "",
        f"Source: {source_name}",
        "",
        "## Quick Summary",
        "",
    ]
    lines.extend(f"- {point}" for point in pack["summary"])

    lines.extend(["", "## Practice Quiz", ""])
    for index, question in enumerate(pack["quiz"], start=1):
        lines.append(f"### {index}. {question['question']}")
        lines.extend(f"- {option}" for option in question["options"])
        lines.append(f"- **Correct answer:** {question['correct_answer']}")
        lines.append(f"- **Explanation:** {question['explanation']}")
        lines.append("")

    lines.extend(["## Key Terms", ""])
    for term in pack["key_terms"]:
        lines.append(f"### {term['term']}")
        lines.append(f"**Meaning:** {term['meaning']}")
        lines.append("")
        lines.append(term["explanation"])
        lines.append("")

    return "\n".join(lines)


def build_revision_text(source_name: str, pack: Dict) -> str:
    lines = [
        "STUDYBUD REVISION PACK",
        f"Source: {source_name}",
        "",
        "QUICK SUMMARY",
    ]
    lines.extend(f"- {point}" for point in pack["summary"])
    lines.extend(["", "PRACTICE QUIZ"])

    for index, question in enumerate(pack["quiz"], start=1):
        lines.append(f"{index}. {question['question']}")
        lines.extend(
            f"   {option_letter}. {option}"
            for option_letter, option in zip("ABCD", question["options"])
        )
        lines.append(f"   Correct answer: {question['correct_answer']}")
        lines.append(f"   Explanation: {question['explanation']}")
        lines.append("")

    lines.append("KEY TERMS")
    for term in pack["key_terms"]:
        lines.extend(
            [
                f"{term['term']}: {term['meaning']}",
                term["explanation"],
                "",
            ]
        )
    return "\n".join(lines)


def build_revision_pdf(source_name: str, pack: Dict) -> bytes:
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    story = [
        Paragraph("STUDYBUD Revision Pack", styles["Title"]),
        Paragraph(f"Source: {escape(source_name)}", styles["Normal"]),
        Spacer(1, 0.2 * inch),
        Paragraph("Quick Summary", styles["Heading2"]),
    ]
    story.extend(
        Paragraph(f"- {escape(point)}", styles["BodyText"])
        for point in pack["summary"]
    )
    story.extend([Spacer(1, 0.15 * inch), Paragraph("Practice Quiz", styles["Heading2"])])

    for index, question in enumerate(pack["quiz"], start=1):
        story.append(
            Paragraph(
                f"<b>{index}. {escape(question['question'])}</b>",
                styles["BodyText"],
            )
        )
        story.extend(
            Paragraph(f"- {escape(option)}", styles["BodyText"])
            for option in question["options"]
        )
        story.append(
            Paragraph(
                f"<b>Correct answer:</b> {escape(question['correct_answer'])}",
                styles["BodyText"],
            )
        )
        story.append(
            Paragraph(
                f"<b>Explanation:</b> {escape(question['explanation'])}",
                styles["BodyText"],
            )
        )
        story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("Key Terms", styles["Heading2"]))
    for term in pack["key_terms"]:
        story.append(
            Paragraph(
                f"<b>{escape(term['term'])}:</b> {escape(term['meaning'])}",
                styles["BodyText"],
            )
        )
        story.append(Paragraph(escape(term["explanation"]), styles["BodyText"]))
        story.append(Spacer(1, 0.1 * inch))

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title="STUDYBUD Revision Pack",
    )
    document.build(story)
    return buffer.getvalue()
