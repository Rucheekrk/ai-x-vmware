"""
PDF report generator — professional layout using ReportLab.
Each chart gets its own full-width section with proper breathing room.
"""

import os
import re
from datetime import datetime
from PIL import Image as PILImage

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Image, HRFlowable,
    PageBreak, KeepTogether, NextPageTemplate,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

# ── Page geometry ─────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = letter          # 8.5 × 11 in
L_MARGIN = 0.85 * inch
R_MARGIN = 0.85 * inch
T_MARGIN = 0.9  * inch
B_MARGIN = 0.85 * inch
CONTENT_W = PAGE_W - L_MARGIN - R_MARGIN   # ~6.8 in

# ── Colour palette ────────────────────────────────────────────────────────────
NAVY    = colors.HexColor("#0f2d55")
BLUE    = colors.HexColor("#1d4ed8")
LBLUE   = colors.HexColor("#dbeafe")
GRAY    = colors.HexColor("#6b7280")
DGRAY   = colors.HexColor("#374151")
LGRAY   = colors.HexColor("#e5e7eb")
XLIGHT  = colors.HexColor("#f9fafb")
WHITE   = colors.white
BLACK   = colors.HexColor("#111827")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")


# ── Paragraph styles ──────────────────────────────────────────────────────────
def _style(name, **kw) -> ParagraphStyle:
    return ParagraphStyle(name, **kw)

STYLES = {
    "cover_tag":  _style("ct",  fontName="Helvetica",      fontSize=10,  textColor=BLUE,  spaceBefore=0, spaceAfter=6,  alignment=TA_CENTER, leading=14),
    "cover_title":_style("cT",  fontName="Helvetica-Bold", fontSize=22,  textColor=NAVY,  spaceBefore=0, spaceAfter=8,  alignment=TA_CENTER, leading=28),
    "cover_date": _style("cD",  fontName="Helvetica",      fontSize=10,  textColor=GRAY,  spaceBefore=0, spaceAfter=0,  alignment=TA_CENTER, leading=14),
    "section_hd": _style("sH",  fontName="Helvetica-Bold", fontSize=13,  textColor=NAVY,  spaceBefore=0, spaceAfter=8,  alignment=TA_LEFT,   leading=18),
    "body":       _style("bdy", fontName="Helvetica",      fontSize=10,  textColor=DGRAY, spaceBefore=0, spaceAfter=0,  alignment=TA_JUSTIFY,leading=16),
    "caption":    _style("cap", fontName="Helvetica-Oblique", fontSize=9, textColor=GRAY,  spaceBefore=6, spaceAfter=0,  alignment=TA_CENTER, leading=13),
    "label":      _style("lbl", fontName="Helvetica-Bold", fontSize=9,   textColor=BLUE,  spaceBefore=0, spaceAfter=4,  alignment=TA_LEFT,   leading=12),
    "footer_txt": _style("ft",  fontName="Helvetica",      fontSize=8,   textColor=GRAY,  leading=10),
}


# ── Header / footer callbacks ─────────────────────────────────────────────────
def _draw_header_footer(canvas, doc):
    canvas.saveState()

    # Top rule
    canvas.setStrokeColor(NAVY)
    canvas.setLineWidth(2)
    canvas.line(L_MARGIN, PAGE_H - 0.55*inch, PAGE_W - R_MARGIN, PAGE_H - 0.55*inch)

    # Header text
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(NAVY)
    canvas.drawString(L_MARGIN, PAGE_H - 0.45*inch, "VMware Aria Operations")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRAY)
    canvas.drawRightString(PAGE_W - R_MARGIN, PAGE_H - 0.45*inch, doc.title)

    # Bottom rule
    canvas.setStrokeColor(LGRAY)
    canvas.setLineWidth(0.5)
    canvas.line(L_MARGIN, 0.6*inch, PAGE_W - R_MARGIN, 0.6*inch)

    # Footer text
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(L_MARGIN, 0.38*inch, f"Generated {datetime.now().strftime('%B %d, %Y')}")
    canvas.drawRightString(PAGE_W - R_MARGIN, 0.38*inch, f"Page {doc.page}")

    canvas.restoreState()


def _draw_cover(canvas, doc):
    """Cover page — no header rule, just a navy bar at top and footer."""
    canvas.saveState()

    # Full-width navy bar at top
    canvas.setFillColor(NAVY)
    canvas.rect(0, PAGE_H - 1.6*inch, PAGE_W, 1.6*inch, fill=1, stroke=0)

    # "VMware Aria Operations" in bar
    canvas.setFont("Helvetica", 11)
    canvas.setFillColor(colors.HexColor("#93c5fd"))
    canvas.drawCentredString(PAGE_W / 2, PAGE_H - 0.85*inch, "VMware Aria Operations")

    # Bottom rule + page number
    canvas.setStrokeColor(LGRAY)
    canvas.setLineWidth(0.5)
    canvas.line(L_MARGIN, 0.6*inch, PAGE_W - R_MARGIN, 0.6*inch)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRAY)
    canvas.drawCentredString(PAGE_W / 2, 0.38*inch, "Confidential — Internal Use Only")

    canvas.restoreState()


# ── Image helper — preserves aspect ratio ─────────────────────────────────────
def _sized_image(path: str, max_width: float, max_height: float) -> Image:
    """Return a ReportLab Image scaled to fit within max_width × max_height."""
    with PILImage.open(path) as im:
        w_px, h_px = im.size
    ratio = h_px / w_px
    width  = min(max_width, max_height / ratio)
    height = width * ratio
    if height > max_height:
        height = max_height
        width  = height / ratio
    return Image(path, width=width, height=height)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _versioned_path(output_dir: str, title: str) -> str:
    """
    Build a filename from the report title and auto-increment the version.
    e.g. 'VH-Flexpod Performance Report' → 'VH-Flexpod_Performance_Report_v1.pdf'
    If that file already exists, use v2, v3, etc.
    """
    # Convert title to a safe filename: keep letters, digits, hyphens; replace everything else with _
    safe = re.sub(r"[^\w\-]", "_", title)
    safe = re.sub(r"_+", "_", safe).strip("_")   # collapse multiple underscores

    version = 1
    while True:
        filename = f"{safe}_v{version}.pdf"
        path = os.path.join(output_dir, filename)
        if not os.path.exists(path):
            return path
        version += 1


# ── Public API ─────────────────────────────────────────────────────────────────
def generate_pdf(
    chart_paths: list[str],
    chart_specs: list[dict],
    summary: str,
    report_title: str = "Infrastructure Performance Report",
) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = _versioned_path(OUTPUT_DIR, report_title)

    # ── Document with two page templates ──────────────────────────────────────
    doc = BaseDocTemplate(
        out_path,
        pagesize=letter,
        leftMargin=L_MARGIN,
        rightMargin=R_MARGIN,
        topMargin=T_MARGIN,
        bottomMargin=B_MARGIN,
        title=report_title,
    )

    cover_frame = Frame(
        L_MARGIN, B_MARGIN,
        CONTENT_W, PAGE_H - B_MARGIN - 1.8*inch,   # leave room for navy bar
        id="cover_frame", showBoundary=0,
    )
    body_frame = Frame(
        L_MARGIN, B_MARGIN,
        CONTENT_W, PAGE_H - T_MARGIN - B_MARGIN,
        id="body_frame", showBoundary=0,
    )

    doc.addPageTemplates([
        PageTemplate(id="Cover", frames=[cover_frame], onPage=_draw_cover),
        PageTemplate(id="Body",  frames=[body_frame],  onPage=_draw_header_footer),
    ])

    story = []

    # ── COVER PAGE ────────────────────────────────────────────────────────────
    # Build a meaningful description from chart specs
    metrics_mentioned = []
    for s in chart_specs:
        metrics_mentioned.extend(s.get("columns", []))
    metrics_str = ", ".join(dict.fromkeys(metrics_mentioned))  # deduplicated
    entities_str = ", ".join(
        dict.fromkeys(e for s in chart_specs for e in (s.get("entities") or ["VH-Flexpod"]))
    )
    chart_word = "chart" if len(chart_paths) == 1 else "charts"
    cover_description = (
        f"This report presents {len(chart_paths)} {chart_word} covering "
        f"{metrics_str} for {entities_str}, "
        f"generated from live VMware Aria Operations data on "
        f"{datetime.now().strftime('%B %d, %Y')}."
    )

    # Vertically centre cover content.
    # Place the title block at ~38% from the top of the page (just above visual
    # centre), leaving more breathing room below than above the navy bar.
    # Fixed spacer avoids under/over-shooting when the title wraps to 2 lines.
    centre_spacer = 2.0 * inch

    story.append(NextPageTemplate("Cover"))
    story += [
        Spacer(1, centre_spacer),
        Paragraph(report_title, STYLES["cover_title"]),
        Spacer(1, 0.15 * inch),
        HRFlowable(width="60%", thickness=1.5, color=BLUE, hAlign="CENTER", spaceAfter=16),
        Paragraph(datetime.now().strftime("%B %d, %Y"), STYLES["cover_date"]),
        Spacer(1, 0.25 * inch),
        Paragraph(cover_description, STYLES["body"]),
        PageBreak(),
    ]

    # ── EXECUTIVE SUMMARY PAGE ────────────────────────────────────────────────
    story.append(NextPageTemplate("Body"))
    story += [
        Paragraph("Executive Summary", STYLES["section_hd"]),
        HRFlowable(width="100%", thickness=0.75, color=NAVY, spaceAfter=14),
        Paragraph(summary, STYLES["body"]),
        Spacer(1, 0.2 * inch),
    ]

    # Chart index — no forced PageBreak, ReportLab flows naturally into chart pages
    if chart_specs:
        story.append(Paragraph("Charts in this report:", STYLES["label"]))
        for i, spec in enumerate(chart_specs, 1):
            story.append(
                Paragraph(f"&nbsp;&nbsp;{i}.&nbsp; {spec['title']}", STYLES["body"])
            )
        story.append(Spacer(1, 0.3 * inch))

    # ── ONE CHART PER PAGE ────────────────────────────────────────────────────
    # Title block height ~0.55in, caption ~0.25in, rule+padding ~0.3in
    TITLE_BLOCK = 0.55 * inch
    CAPTION_H   = 0.25 * inch
    RULE_PAD    = 0.3  * inch
    chart_max_w = CONTENT_W
    chart_max_h = PAGE_H - T_MARGIN - B_MARGIN - TITLE_BLOCK - CAPTION_H - RULE_PAD

    for i, (path, spec) in enumerate(zip(chart_paths, chart_specs), 1):
        if not os.path.exists(path):
            continue

        section = []
        section.append(Paragraph(f"Chart {i}  —  {spec['title']}", STYLES["section_hd"]))
        section.append(HRFlowable(width="100%", thickness=0.75, color=NAVY, spaceAfter=12))

        img = _sized_image(path, chart_max_w, chart_max_h)
        section.append(img)
        section.append(
            Paragraph(
                f"{spec['chart_type'].title()} chart  ·  "
                f"Metrics: {', '.join(spec['columns'])}  ·  "
                f"Entities: {', '.join(spec['entities']) if spec.get('entities') else 'VH-Flexpod'}",
                STYLES["caption"],
            )
        )

        story.append(KeepTogether(section))
        story.append(Spacer(1, 0.2 * inch))

    doc.build(story)
    return out_path
