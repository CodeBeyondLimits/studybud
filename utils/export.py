from typing import Dict


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
