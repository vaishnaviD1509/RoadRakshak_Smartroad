"""PDF generation for Road Rakshak, using ReportLab.

Two reports:
  - build_complaint_pdf(complaint)   -> a single complaint's record, for the
    citizen who filed it (receipt / proof of report, with its full status
    history).
  - build_summary_pdf(stats, ...)    -> an admin-facing summary report over
    a date range, built from the same aggregate numbers as the analytics
    dashboard (Stage 9), so the PDF and the on-screen charts never disagree.

Both return raw PDF bytes via io.BytesIO, so callers can stream them
straight out with Flask's send_file without touching disk.
"""

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                 TableStyle)

DARK_GREEN = colors.HexColor("#1b4332")
MID_GREEN = colors.HexColor("#2d6a4f")
LIGHT_GREY = colors.HexColor("#f1f3f1")


def _styles():
    sheet = getSampleStyleSheet()
    sheet.add(ParagraphStyle(
        name="RRTitle", parent=sheet["Title"], textColor=DARK_GREEN, fontSize=18,
    ))
    sheet.add(ParagraphStyle(
        name="RRHeading", parent=sheet["Heading2"], textColor=DARK_GREEN, spaceBefore=12,
    ))
    sheet.add(ParagraphStyle(
        name="RRBody", parent=sheet["BodyText"], textColor=colors.HexColor("#222222"),
    ))
    sheet.add(ParagraphStyle(
        name="RRFootnote", parent=sheet["BodyText"], fontSize=8, textColor=colors.grey,
    ))
    return sheet


def _header_table(rows):
    table = Table(rows, colWidths=[4.5 * cm, 11 * cm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), DARK_GREEN),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e3e6e3")),
    ]))
    return table


def build_complaint_pdf(complaint) -> io.BytesIO:
    """A single complaint's full record: details, AI classification,
    and its complete status history - a citizen's proof-of-report PDF."""
    styles = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
    )

    elements = [
        Paragraph("Road Rakshak", styles["RRTitle"]),
        Paragraph("Complaint report", styles["RRHeading"]),
        Spacer(1, 6),
    ]

    elements.append(_header_table([
        ["Complaint ID", complaint.complaint_id],
        ["Damage category", complaint.damage_category],
        ["Status", complaint.status],
        ["Location", complaint.location_name or "Not specified"],
        ["Reported on", complaint.created_at.strftime("%d %b %Y, %I:%M %p")],
        ["Last updated", complaint.updated_at.strftime("%d %b %Y, %I:%M %p")],
        ["Assigned team", complaint.assigned_team or "Not yet assigned"],
    ]))
    elements.append(Spacer(1, 14))

    elements.append(Paragraph("Description", styles["RRHeading"]))
    elements.append(Paragraph(complaint.description or "No description provided.", styles["RRBody"]))
    elements.append(Spacer(1, 10))

    if complaint.ai_prediction:
        label = "AI classification" if not complaint.ai_admin_reviewed else "Classification (reviewed by admin)"
        confidence_text = (
            f"{complaint.ai_prediction} ({complaint.ai_confidence:.0%} confidence)"
            if complaint.ai_confidence is not None
            else complaint.ai_prediction
        )
        elements.append(Paragraph(label, styles["RRHeading"]))
        elements.append(Paragraph(confidence_text, styles["RRBody"]))
        elements.append(Spacer(1, 10))

    elements.append(Paragraph("Status history", styles["RRHeading"]))
    if complaint.updates:
        history_rows = [["Date", "Status", "Remarks"]]
        for update in complaint.updates:
            history_rows.append([
                update.created_at.strftime("%d %b %Y"),
                update.new_status,
                update.remarks or "-",
            ])
        history_table = Table(history_rows, colWidths=[3 * cm, 4 * cm, 8.5 * cm])
        history_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), DARK_GREEN),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e3e6e3")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(history_table)
    else:
        elements.append(Paragraph("No status changes recorded yet.", styles["RRBody"]))

    elements.append(Spacer(1, 20))
    elements.append(Paragraph(
        f"Generated by Road Rakshak on {datetime.utcnow().strftime('%d %b %Y, %I:%M %p')} UTC. "
        "This document reflects the complaint's status at the time of generation.",
        styles["RRFootnote"],
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def build_summary_pdf(stats: dict, date_from=None, date_to=None, category_filter: str = "") -> io.BytesIO:
    """An admin-facing summary report built from the same aggregate stats
    as the Stage 9 analytics dashboard (by_category, by_status,
    resolved_vs_unresolved, total)."""
    styles = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
    )

    elements = [
        Paragraph("Road Rakshak", styles["RRTitle"]),
        Paragraph("Complaint summary report", styles["RRHeading"]),
        Spacer(1, 6),
    ]

    range_text = "All time"
    if date_from or date_to:
        start = date_from.strftime("%d %b %Y") if date_from else "the beginning"
        end = date_to.strftime("%d %b %Y") if date_to else "today"
        range_text = f"{start} to {end}"

    elements.append(_header_table([
        ["Date range", range_text],
        ["Category filter", category_filter or "All categories"],
        ["Total complaints", str(stats["total"])],
        ["Resolved", str(stats["resolved_vs_unresolved"]["resolved"])],
        ["Unresolved", str(stats["resolved_vs_unresolved"]["unresolved"])],
    ]))
    elements.append(Spacer(1, 14))

    elements.append(Paragraph("Complaints by damage category", styles["RRHeading"]))
    category_rows = [["Category", "Count"]] + [
        [label, str(value)] for label, value in zip(stats["by_category"]["labels"], stats["by_category"]["values"])
    ]
    elements.append(_stat_table(category_rows))
    elements.append(Spacer(1, 14))

    elements.append(Paragraph("Complaints by status", styles["RRHeading"]))
    status_rows = [["Status", "Count"]] + [
        [label, str(value)] for label, value in zip(stats["by_status"]["labels"], stats["by_status"]["values"])
    ]
    elements.append(_stat_table(status_rows))

    elements.append(Spacer(1, 20))
    elements.append(Paragraph(
        f"Generated by Road Rakshak on {datetime.utcnow().strftime('%d %b %Y, %I:%M %p')} UTC.",
        styles["RRFootnote"],
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def _stat_table(rows):
    if len(rows) == 1:
        rows.append(["No data", "-"])
    table = Table(rows, colWidths=[9 * cm, 4 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), MID_GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e3e6e3")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table