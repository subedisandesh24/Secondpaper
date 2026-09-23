import streamlit as st
import streamlit.components.v1 as components
import base64
import os
import json
import re
from datetime import datetime
from groq import Groq
from PIL import Image
import io

# ReportLab imports for PDF Generation
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib import colors

# -------------------------------------------------------------
# PAGE CONFIGURATION
# -------------------------------------------------------------
st.set_page_config(
    page_title="Lok Sewa Agri Officer (Gazetted 3rd Class) Coach",
    page_icon="🌾",
    layout="wide"
)

SAVED_NOTES_FILE = "saved_loksewa_notes.json"

def load_saved_notes():
    if os.path.exists(SAVED_NOTES_FILE):
        try:
            with open(SAVED_NOTES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_notes_to_disk(notes):
    with open(SAVED_NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)

if "saved_notes" not in st.session_state:
    st.session_state["saved_notes"] = load_saved_notes()

# -------------------------------------------------------------
# PDF GENERATION ENGINE
# -------------------------------------------------------------
def sanitize_for_pdf(text: str) -> str:
    """Safely encodes characters so standard PDF fonts never raise Unicode errors."""
    return text.encode("latin-1", "replace").decode("latin-1")

def generate_pdf_bytes(question: str, marks: int, answer_markdown: str) -> bytes:
    """Creates an A4 PDF formatted for Lok Sewa examinations."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=36,
        bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    
    header_style = ParagraphStyle(
        'Header',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=colors.HexColor('#1b5e20'),
        alignment=1
    )
    sub_header = ParagraphStyle(
        'SubHeader',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#555555'),
        alignment=1
    )
    q_box = ParagraphStyle(
        'QBox',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor('#0d47a1'),
        spaceBefore=4,
        spaceAfter=6
    )
    h1_style = ParagraphStyle(
        'H1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor('#1b5e20'),
        spaceBefore=7,
        spaceAfter=3
    )
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#212121'),
        spaceAfter=3
    )
    bullet_style = ParagraphStyle(
        'Bullet',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        leftIndent=12,
        spaceAfter=2
    )

    story = []
    
    # Official Header
    story.append(Paragraph("PUBLIC SERVICE COMMISSION (LOK SEWA AAYOG) - NEPAL", header_style))
    story.append(Paragraph("Nepal Agricultural Service | Gazetted Third Class (Technical Officer / कृषि अधिकृत)", sub_header))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1b5e20'), spaceBefore=4, spaceAfter=8))
    
    # Question Metadata
    clean_q = sanitize_for_pdf(question)
    story.append(Paragraph(f"<b>QUESTION [{marks} Marks]:</b> {clean_q}", q_box))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cccccc'), spaceBefore=2, spaceAfter=6))
    
    # Parse Markdown lines into structured PDF elements
    lines = answer_markdown.split("\n")
    in_mermaid = False
    
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
            
        if "```mermaid" in line:
            in_mermaid = True
            story.append(Paragraph("<b>[PROCESS FLOW / CONCEPTUAL DIAGRAM]</b>", h1_style))
            continue
        elif in_mermaid and "```" in line:
            in_mermaid = False
            continue
        elif in_mermaid:
            clean_flow = line.replace("-->", " -> ").replace("[", "").replace("]", "")
            story.append(Paragraph(f"&bull; {sanitize_for_pdf(clean_flow)}", bullet_style))
            continue
            
        # Headings
        if line.startswith("#"):
            clean_h = re.sub(r"^#+\s*", "", line)
            story.append(Paragraph(f"<b>{sanitize_for_pdf(clean_h)}</b>", h1_style))
        # Bullet points
        elif line.startswith("-") or line.startswith("*") or (len(line) > 2 and line[0].isdigit() and line[1] in [".", ")"]):
            clean_bullet = re.sub(r"^[-*]\s*", "", line)
            clean_bullet = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", clean_bullet)
            story.append(Paragraph(f"&bull; {sanitize_for_pdf(clean_bullet)}", bullet_style))
        else:
            clean_body = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", line)
            story.append(Paragraph(sanitize_for_pdf(clean_body), body_style))
            
    doc.build(story)
    return buffer.getvalue()

# -------------------------------------------------------------
# LOK SEWA HIGH-SCORING SYSTEM PROMPT
# -------------------------------------------------------------
LOKSEWA_SYSTEM_PROMPT = """
You are an elite Nepal Lok Sewa Aayog evaluator and answer-writing mentor for the Nepal Agricultural Service (Gazetted Third Class / रा.प. तृतीय श्रेणी - Agri Extension, Horticulture, Agronomy, Plant Protection, Soil Science).

Your mission is to produce high-scoring, concise, examiner-friendly answers tailored for the 3-hour written exam.
Do NOT write endless superficial bullet points. In a real exam, candidates have only ~13-14 minutes per 10-mark question. Provide FEWER, PUNCHY, HIGH-IMPACT, EASY-TO-REMEMBER points.

MANDATORY AUTHENTIC DATA BASELINE TO USE:
1. Economic Survey 2080/81: Agriculture contributes 24.09% to national GDP; AGDP annual growth rate is ~3.05%.
2. National Sample Census of Agriculture 2078 (NSO):
   - 4.13 million farm holdings (62% of households depend on agriculture).
   - Total agricultural land: 2.218 million hectares.
   - Average holding size: 0.55 ha (heavily fragmented, ~2.8 parcels/holding).
   - Only 54.5% of agricultural land has access to irrigation, and barely 1/3rd has year-round irrigation.
3. 16th Periodic Plan (2081/82 - 2085/86): Priority on structural transformation, production clusters, commercial value chains, and import substitution.
4. ADS (2015-2035): 4 Core Pillars (Governance, Productivity, Commercialization, Competitiveness).
5. Legal Foundations: Constitution of Nepal (Art. 36: Right to Food & Food Sovereignty; Art. 51(h): Agriculture Policies; Schedules 5, 6, 7, 8, 9 for jurisdiction).

STRICT ANSWER ARCHITECTURE:
1. **Concise Introduction (2-3 sentences):** Direct definition, scope, and strategic importance.
2. **Current Scenario & Data Snapshot:** Exactly 3-4 bullet points citing verified data (Economic Survey 2080/81, Census 2078, 16th Plan).
3. **Mermaid Flowchart (MANDATORY):**
   Output a valid, clean Mermaid code block:
   ```mermaid
   graph TD
   A[Input / Source] --> B[Processing / Action]
   B --> C[Outcome / Market]
