"""
PDF Security Incident Report generator.
Produces a professional, branded PDF using ReportLab Platypus.

Layout:
  - Dark HOF Capital / LockDown header banner
  - Incident overview table
  - Suspect profile + CCTV image
  - VLM analysis section (Nemotron)
  - Full written report (Claude)
  - Recommended actions
  - Confidential footer
"""
from __future__ import annotations

import io
import logging
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ReportLab helpers
# ---------------------------------------------------------------------------

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor, white, black, Color
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, Image as RLImage, KeepTogether,
    )
    from reportlab.platypus.flowables import HRFlowable
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# Brand colours (matches dashboard)
HOF_DARK   = HexColor("#0f172a") if REPORTLAB_AVAILABLE else None
HOF_NAVY   = HexColor("#1e293b") if REPORTLAB_AVAILABLE else None
HOF_RED    = HexColor("#ef4444") if REPORTLAB_AVAILABLE else None
HOF_ORANGE = HexColor("#f97316") if REPORTLAB_AVAILABLE else None
HOF_AMBER  = HexColor("#f59e0b") if REPORTLAB_AVAILABLE else None
HOF_SLATE  = HexColor("#475569") if REPORTLAB_AVAILABLE else None
HOF_LIGHT  = HexColor("#f1f5f9") if REPORTLAB_AVAILABLE else None
HOF_TEXT   = HexColor("#1e293b") if REPORTLAB_AVAILABLE else None


def _extract_gif_frame(gif_path: Path) -> Optional[bytes]:
    """Extract the middle frame of the GIF recording as JPEG bytes."""
    try:
        from PIL import Image
        img = Image.open(gif_path)
        frames = []
        try:
            while True:
                frames.append(img.copy().convert("RGB"))
                img.seek(img.tell() + 1)
        except EOFError:
            pass
        if not frames:
            return None
        mid = frames[len(frames) // 2]
        # Scale up slightly so it looks better in the PDF
        w, h = mid.size
        if w < 400:
            scale = 400 / w
            mid = mid.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        mid.save(buf, format="JPEG", quality=88)
        return buf.getvalue()
    except Exception as e:
        logger.warning("Could not extract GIF frame: %s", e)
        return None


def _build_styles():
    base = getSampleStyleSheet()
    styles = {}

    styles["title_brand"] = ParagraphStyle(
        "title_brand",
        fontName="Helvetica-Bold",
        fontSize=26,
        textColor=HOF_RED,
        spaceAfter=0,
        leading=30,
        letterSpacing=6,
    )
    styles["title_sub"] = ParagraphStyle(
        "title_sub",
        fontName="Helvetica",
        fontSize=10,
        textColor=HexColor("#94a3b8"),
        spaceAfter=0,
        leading=14,
        letterSpacing=2,
    )
    styles["company"] = ParagraphStyle(
        "company",
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=white,
        spaceAfter=0,
        leading=14,
        alignment=TA_RIGHT,
    )
    styles["company_sub"] = ParagraphStyle(
        "company_sub",
        fontName="Helvetica",
        fontSize=9,
        textColor=HexColor("#94a3b8"),
        spaceAfter=0,
        leading=12,
        alignment=TA_RIGHT,
    )
    styles["ref_label"] = ParagraphStyle(
        "ref_label",
        fontName="Helvetica-Bold",
        fontSize=8,
        textColor=HOF_SLATE,
        spaceAfter=2,
        leading=10,
        letterSpacing=1,
    )
    styles["ref_value"] = ParagraphStyle(
        "ref_value",
        fontName="Helvetica",
        fontSize=9,
        textColor=HOF_TEXT,
        spaceAfter=0,
        leading=12,
    )
    styles["section_head"] = ParagraphStyle(
        "section_head",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=white,
        spaceAfter=0,
        leading=12,
        letterSpacing=2,
    )
    styles["field_label"] = ParagraphStyle(
        "field_label",
        fontName="Helvetica-Bold",
        fontSize=8,
        textColor=HOF_SLATE,
        spaceAfter=1,
        leading=10,
    )
    styles["field_value"] = ParagraphStyle(
        "field_value",
        fontName="Helvetica",
        fontSize=9,
        textColor=HOF_TEXT,
        spaceAfter=0,
        leading=13,
    )
    styles["body"] = ParagraphStyle(
        "body",
        fontName="Helvetica",
        fontSize=9.5,
        textColor=HOF_TEXT,
        spaceAfter=6,
        leading=15,
        firstLineIndent=0,
    )
    styles["body_bold"] = ParagraphStyle(
        "body_bold",
        parent=styles["body"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=HOF_TEXT,
        spaceAfter=4,
        spaceBefore=10,
    )
    styles["threat_high"] = ParagraphStyle(
        "threat_high",
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=HOF_RED,
        spaceAfter=0,
        leading=14,
    )
    styles["caption"] = ParagraphStyle(
        "caption",
        fontName="Helvetica",
        fontSize=7.5,
        textColor=HOF_SLATE,
        alignment=TA_CENTER,
        spaceAfter=0,
        leading=10,
    )
    styles["footer"] = ParagraphStyle(
        "footer",
        fontName="Helvetica",
        fontSize=7.5,
        textColor=HOF_SLATE,
        alignment=TA_CENTER,
        leading=11,
    )
    styles["confidential"] = ParagraphStyle(
        "confidential",
        fontName="Helvetica-Bold",
        fontSize=7.5,
        textColor=HOF_RED,
        alignment=TA_CENTER,
        letterSpacing=1,
        leading=11,
    )
    return styles


def _hr(color=None, thickness=0.5):
    return HRFlowable(
        width="100%",
        thickness=thickness,
        color=color or HOF_NAVY,
        spaceAfter=6,
        spaceBefore=6,
    )


def _section_banner(text: str, styles: dict):
    """Dark banner row with white text — used as section headers."""
    cell = Paragraph(text, styles["section_head"])
    tbl = Table([[cell]], colWidths=["100%"])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HOF_DARK),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
    ]))
    return tbl


def generate_pdf_report(
    alert: dict,
    nemotron: dict,
    report_text: str,
    data_dir: Path,
) -> bytes:
    """
    Build and return the PDF as bytes.
    alert        – the security alert dict
    nemotron     – result from analyze_frame_with_nemotron()
    report_text  – full written report from write_report_with_claude()
    data_dir     – backend data directory (to locate the GIF recording)
    """
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab is not installed. Run: pip install reportlab")

    styles = _build_styles()

    # --- page dimensions ---
    PAGE_W, PAGE_H = A4
    MARGIN = 1.8 * cm
    CONTENT_W = PAGE_W - 2 * MARGIN

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title="HOF Capital Security Incident Report",
        author="LockDown Security System",
    )

    story = []

    # ===================================================================
    # HEADER BANNER – dark band with LOCKDOWN + company name
    # ===================================================================
    brand_left = Table(
        [[Paragraph("🔒 LOCKDOWN", styles["title_brand"])],
         [Paragraph("SECURITY INCIDENT REPORT", styles["title_sub"])]],
        colWidths=[CONTENT_W * 0.42],
    )
    brand_left.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))

    brand_right = Table(
        [[Paragraph("HOF CAPITAL MANAGEMENT", styles["company"])],
         [Paragraph("Confidential — Internal Use Only", styles["company_sub"])]],
        colWidths=[CONTENT_W * 0.58],
    )
    brand_right.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))

    header_row = Table(
        [[brand_left, brand_right]],
        colWidths=[CONTENT_W * 0.42, CONTENT_W * 0.58],
    )
    header_row.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), HOF_DARK),
        ("TOPPADDING",    (0, 0), (-1, -1), 16),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(header_row)
    story.append(Spacer(1, 0.3 * cm))

    # ===================================================================
    # REFERENCE / META ROW
    # ===================================================================
    ts_raw = alert.get("timestamp", "")
    try:
        dt = datetime.strptime(ts_raw, "%Y-%m-%dT%H:%M:%S")
        date_str = dt.strftime("%A, %d %B %Y")
        time_str = dt.strftime("%H:%M:%S")
        ref_date = dt.strftime("%Y%m%d")
    except Exception:
        date_str = ts_raw
        time_str = ""
        ref_date = "XXXXXX"

    short_id = alert.get("alert_id", "")[:8].upper()
    ref_number = f"HOF-SEC-{ref_date}-{short_id}"
    alert_type_display = alert.get("alert_type", "zone_presence").replace("_", " ").title()

    meta_data = [
        ["REPORT REFERENCE", ref_number, "DATE ISSUED", date_str],
        ["CLASSIFICATION", "RESTRICTED — INTERNAL USE ONLY", "ALERT TYPE", alert_type_display],
    ]
    meta_table = Table(
        [[Paragraph(label, styles["ref_label"]),
          Paragraph(value, styles["ref_value"])]
         for row in meta_data for label, value in [(row[0], row[1]), (row[2], row[3])]],
        colWidths=[CONTENT_W * 0.22, CONTENT_W * 0.28, CONTENT_W * 0.22, CONTENT_W * 0.28],
        rowHeights=None,
    )
    # Re-build as a 2×4 table properly
    meta_rows = []
    for row in meta_data:
        meta_rows.append([
            Paragraph(row[0], styles["ref_label"]),
            Paragraph(row[1], styles["ref_value"]),
            Paragraph(row[2], styles["ref_label"]),
            Paragraph(row[3], styles["ref_value"]),
        ])
    meta_table = Table(
        meta_rows,
        colWidths=[CONTENT_W * 0.22, CONTENT_W * 0.28, CONTENT_W * 0.22, CONTENT_W * 0.28],
    )
    meta_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), HOF_LIGHT),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.3, HexColor("#cbd5e1")),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.4 * cm))

    # ===================================================================
    # INCIDENT OVERVIEW
    # ===================================================================
    story.append(_section_banner("INCIDENT OVERVIEW", styles))
    story.append(Spacer(1, 0.2 * cm))

    zone = alert.get("zone_name", "Analyst Zone")
    feed_num = alert.get("feed_id", 0) + 1
    location_full = f"1/2 Bond Street, HOF Capital Building, 2nd Floor, {zone}"

    overview_rows = [
        ("Date", date_str),
        ("Time", time_str),
        ("Location", location_full),
        ("Camera Feed", f"Camera Feed {feed_num}"),
        ("Detection Method", "Automated Restricted Zone Presence Detection"),
        ("Alert Status", "OPEN — Requires Immediate Review"),
    ]
    ov_table = Table(
        [[Paragraph(k, styles["field_label"]), Paragraph(v, styles["field_value"])]
         for k, v in overview_rows],
        colWidths=[CONTENT_W * 0.25, CONTENT_W * 0.75],
    )
    ov_table.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [HexColor("#f8fafc"), white]),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, HexColor("#e2e8f0")),
        ("VALIGN",    (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(ov_table)
    story.append(Spacer(1, 0.4 * cm))

    # ===================================================================
    # SUSPECT PROFILE + CCTV IMAGE
    # ===================================================================
    story.append(_section_banner("SUSPECT PROFILE", styles))
    story.append(Spacer(1, 0.2 * cm))

    person_name = alert.get("person_name", "Unknown")
    subject_label = (
        person_name if person_name.lower() != "unknown"
        else "Unknown — No match in HOF Capital face database"
    )
    subject_status = (
        "Registered (see above)" if person_name.lower() != "unknown"
        else "UNAUTHORIZED — Unregistered person"
    )

    suspect_rows = [
        ("Identified Name", subject_label),
        ("Access Status", "UNAUTHORIZED"),
        ("Registration", subject_status),
        ("Detected Zone", zone),
    ]
    sus_table = Table(
        [[Paragraph(k, styles["field_label"]), Paragraph(v, styles["field_value"])]
         for k, v in suspect_rows],
        colWidths=[CONTENT_W * 0.25, CONTENT_W * 0.75],
    )
    sus_table.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [HexColor("#f8fafc"), white]),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, HexColor("#e2e8f0")),
        ("VALIGN",    (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(sus_table)
    story.append(Spacer(1, 0.3 * cm))

    # CCTV image
    alert_id = alert.get("alert_id", "")
    gif_path = data_dir / "recordings" / f"{alert_id}.gif"
    frame_bytes = _extract_gif_frame(gif_path) if gif_path.exists() else None

    if frame_bytes:
        try:
            img_buf = io.BytesIO(frame_bytes)
            from PIL import Image as PILImage
            pil = PILImage.open(img_buf)
            iw, ih = pil.size
            max_img_w = CONTENT_W * 0.65
            scale = min(max_img_w / iw, (8 * cm) / ih, 1.0)
            disp_w = iw * scale
            disp_h = ih * scale
            img_buf.seek(0)
            rl_img = RLImage(img_buf, width=disp_w, height=disp_h)

            img_caption = Paragraph(
                f"FIGURE 1 — CCTV INCIDENT FOOTAGE  |  Camera Feed {feed_num}  |  {zone}  |  {ts_raw}",
                styles["caption"],
            )

            img_table = Table(
                [[rl_img], [Spacer(1, 0.1 * cm)], [img_caption]],
                colWidths=[CONTENT_W],
            )
            img_table.setStyle(TableStyle([
                ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
                ("BACKGROUND",    (0, 0), (0, 0), HOF_DARK),
                ("TOPPADDING",    (0, 0), (0, 0), 8),
                ("BOTTOMPADDING", (0, 0), (0, 0), 8),
                ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ]))
            story.append(img_table)
        except Exception as e:
            logger.warning("Could not embed image in PDF: %s", e)
            story.append(Paragraph(
                "[CCTV image unavailable — view recording via the dashboard]",
                styles["caption"],
            ))
    else:
        story.append(Paragraph(
            "[No CCTV recording available for this incident]",
            styles["caption"],
        ))

    story.append(Spacer(1, 0.4 * cm))

    # ===================================================================
    # VLM ANALYSIS
    # ===================================================================
    story.append(_section_banner(
        "VLM ANALYSIS — NVIDIA NEMOTRON NANO 12B VL v2", styles
    ))
    story.append(Spacer(1, 0.2 * cm))

    tl = nemotron.get("threat_level", "HIGH")
    tl_color = HOF_RED if tl == "HIGH" else HOF_AMBER if tl == "MEDIUM" else HexColor("#22c55e")
    tl_style = ParagraphStyle(
        "tl_inline",
        parent=styles["field_value"],
        fontName="Helvetica-Bold",
        textColor=tl_color,
    )

    if nemotron.get("available"):
        vlm_rows = [
            ("Human Confirmed",    str(nemotron.get("human_confirmed", True))),
            ("Physical Description", nemotron.get("physical_description", "N/A")),
            ("Observed Behavior",  nemotron.get("behavior", "N/A")),
            ("Security Observations", nemotron.get("observations", "N/A")),
            ("Analysis Confidence", nemotron.get("confidence", "N/A")),
        ]
        vlm_table = Table(
            [[Paragraph(k, styles["field_label"]), Paragraph(v, styles["field_value"])]
             for k, v in vlm_rows]
            + [[Paragraph("Threat Level", styles["field_label"]),
                Paragraph(tl, tl_style)]],
            colWidths=[CONTENT_W * 0.28, CONTENT_W * 0.72],
        )
    else:
        vlm_table = Table(
            [[Paragraph("Status", styles["field_label"]),
              Paragraph(nemotron.get("physical_description", "VLM analysis unavailable."),
                        styles["field_value"])]],
            colWidths=[CONTENT_W * 0.28, CONTENT_W * 0.72],
        )

    vlm_table.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [HexColor("#f8fafc"), white]),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, HexColor("#e2e8f0")),
        ("VALIGN",    (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(vlm_table)
    story.append(Spacer(1, 0.4 * cm))

    # ===================================================================
    # FORMAL WRITTEN REPORT (Claude)
    # ===================================================================
    story.append(_section_banner("FORMAL SECURITY INCIDENT REPORT", styles))
    story.append(Spacer(1, 0.25 * cm))

    # Split on section headings (ALL CAPS lines)
    for line in report_text.splitlines():
        stripped = line.strip()
        if not stripped:
            story.append(Spacer(1, 0.15 * cm))
            continue
        # Detect section headings: all uppercase, no trailing period
        if stripped.isupper() and len(stripped) > 3 and not stripped.endswith("."):
            story.append(Paragraph(stripped, styles["body_bold"]))
        else:
            story.append(Paragraph(stripped, styles["body"]))

    story.append(Spacer(1, 0.5 * cm))

    # ===================================================================
    # FOOTER
    # ===================================================================
    story.append(_hr(HOF_NAVY, 1))
    story.append(Spacer(1, 0.1 * cm))

    now_str = datetime.now().strftime("%d %B %Y at %H:%M:%S")
    story.append(Paragraph("CONFIDENTIAL — INTERNAL USE ONLY", styles["confidential"]))
    story.append(Spacer(1, 0.1 * cm))
    story.append(Paragraph(
        f"Generated by LockDown Security System  |  HOF Capital Management  |  {now_str}",
        styles["footer"],
    ))
    story.append(Paragraph(
        f"Incident ID: {alert.get('alert_id', 'N/A')}",
        styles["footer"],
    ))
    story.append(Spacer(1, 0.1 * cm))
    story.append(Paragraph(
        "This report is confidential and intended solely for authorised HOF Capital personnel. "
        "Unauthorised disclosure, copying, or distribution is strictly prohibited. "
        "© 2026 HOF Capital Management. All rights reserved.",
        styles["footer"],
    ))

    doc.build(story)
    return buf.getvalue()
