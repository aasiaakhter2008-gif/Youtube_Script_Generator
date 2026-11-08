from io import BytesIO

from app.schemas.export import ExportFormat
from app.schemas.script import Storyboard, WrittenScript


def script_to_text(script: WrittenScript) -> str:
    parts: list[str] = []
    for section in script.sections:
        parts.append(f"[{section.section_type.upper()}] {section.title}")
        parts.append(section.content)
        for cue in section.b_roll_cues:
            parts.append(f"[B-roll: {cue}]")
        for cue in section.on_screen_text:
            parts.append(f"[On-screen text: {cue}]")
        parts.append("")
    return "\n".join(parts)


def _to_markdown(script: WrittenScript) -> str:
    lines: list[str] = ["# YouTube Script", ""]
    for section in script.sections:
        lines.append(f"## {section.title} ({section.section_type})")
        lines.append("")
        lines.append(section.content)
        lines.append("")
        for cue in section.b_roll_cues:
            lines.append(f"- **B-roll:** {cue}")
        for cue in section.on_screen_text:
            lines.append(f"- **On-screen text:** {cue}")
        lines.append("")
    return "\n".join(lines)


def _to_docx(script: WrittenScript, topic: str) -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading(f"{topic} - YouTube Script", level=1)
    for section in script.sections:
        doc.add_heading(section.title, level=2)
        doc.add_paragraph(section.content)
        for cue in section.b_roll_cues:
            doc.add_paragraph(f"[B-roll: {cue}]")
        for cue in section.on_screen_text:
            doc.add_paragraph(f"[On-screen text: {cue}]")
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _to_pdf(script: WrittenScript, topic: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [Paragraph(f"<b>{topic} - YouTube Script</b>", styles["Title"])]
    for section in script.sections:
        story.append(Paragraph(f"{section.title}", styles["Heading2"]))
        story.append(Paragraph(section.content, styles["Normal"]))
        for cue in section.b_roll_cues:
            story.append(Paragraph(f"[B-roll: {cue}]", styles["Normal"]))
        for cue in section.on_screen_text:
            story.append(Paragraph(f"[On-screen text: {cue}]", styles["Normal"]))
        story.append(Spacer(1, 6))
    doc.build(story)
    return buffer.getvalue()


def export_script(
    script: WrittenScript,
    fmt: ExportFormat,
    *,
    topic: str = "YouTube Script",
) -> tuple[bytes, str]:
    """Export a written script to txt / md / docx / pdf. Returns (file_bytes, media_type)."""
    if fmt == ExportFormat.TXT:
        return script_to_text(script).encode("utf-8"), "text/plain; charset=utf-8"
    if fmt == ExportFormat.MD:
        return _to_markdown(script).encode("utf-8"), "text/markdown; charset=utf-8"
    if fmt == ExportFormat.DOCX:
        return _to_docx(script, topic), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if fmt == ExportFormat.PDF:
        return _to_pdf(script, topic), "application/pdf"
    raise ValueError(f"Unsupported export format: {fmt}")


def storyboard_to_csv(storyboard: Storyboard) -> str:
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["section_type", "shot_type", "visual_description", "b_roll_keywords", "on_screen_text", "estimated_duration_seconds"])
    for shot in storyboard.shots:
        writer.writerow(
            [
                shot.section_type,
                shot.shot_type,
                shot.visual_description,
                "; ".join(shot.b_roll_keywords),
                shot.on_screen_text,
                shot.estimated_duration_seconds,
            ]
        )
    return buffer.getvalue()


def storyboard_to_pdf(storyboard: Storyboard, topic: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [Paragraph(f"<b>{topic} - Storyboard</b>", styles["Title"])]
    for shot in storyboard.shots:
        story.append(Paragraph(f"{shot.section_type} - {shot.shot_type}", styles["Heading2"]))
        story.append(Paragraph(shot.visual_description, styles["Normal"]))
        for keyword in shot.b_roll_keywords:
            story.append(Paragraph(f"B-roll keyword: {keyword}", styles["Normal"]))
        if shot.on_screen_text:
            story.append(Paragraph(f"On-screen text: {shot.on_screen_text}", styles["Normal"]))
        story.append(Spacer(1, 6))
    doc.build(story)
    return buffer.getvalue()


def export_storyboard(storyboard: Storyboard, fmt: str, *, topic: str = "YouTube Script") -> tuple[bytes, str]:
    """Export a storyboard to csv or pdf. Returns (file_bytes, media_type)."""
    if fmt == "csv":
        return storyboard_to_csv(storyboard).encode("utf-8"), "text/csv; charset=utf-8"
    if fmt == "pdf":
        return storyboard_to_pdf(storyboard, topic), "application/pdf"
    raise ValueError(f"Unsupported storyboard export format: {fmt}")
