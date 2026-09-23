import streamlit as st
import streamlit.components.v1 as components
import base64
import os
import json
import re
import html
import time
from datetime import datetime
from groq import Groq
from PIL import Image
import io

# ReportLab imports for Clean PDF Generation
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak, Table, TableStyle
)
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Constant for triple backticks to avoid markdown copy truncation
TRIPLE_BACKTICKS = chr(96) * 3

# -------------------------------------------------------------
# PAGE CONFIGURATION
# -------------------------------------------------------------
st.set_page_config(
    page_title="Lok Sewa Agri Officer Coach",
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
# DYNAMIC UNICODE FONT LOADER & ARTIFACT CLEANER (NO '???')
# -------------------------------------------------------------
PDF_FONT = 'Helvetica'
PDF_FONT_BOLD = 'Helvetica-Bold'

def setup_pdf_font():
    """Tries to register a system TrueType font if available on the OS."""
    global PDF_FONT, PDF_FONT_BOLD
    system_font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf"
    ]
    for p in system_font_paths:
        if os.path.exists(p):
            try:
                pdfmetrics.registerFont(TTFont('AppUnicodeFont', p))
                PDF_FONT = 'AppUnicodeFont'
                PDF_FONT_BOLD = 'AppUnicodeFont'
                return
            except Exception:
                pass

setup_pdf_font()

def clean_pdf_text(raw_text: str) -> str:
    """
    Cleans Unicode punctuation, emojis, quotes, and symbols so they NEVER turn into '???'.
    """
    if not raw_text:
        return ""

    text = raw_text

    # 1. Map Unicode dashes to clean ASCII hyphens
    text = text.replace('—', ' - ').replace('–', ' - ').replace('―', ' - ')

    # 2. Map curly quotes to straight quotes
    text = text.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")

    # 3. Map arrows and math signs to clean text
    text = text.replace('→', ' -> ').replace('←', ' <- ').replace('↑', ' (up) ').replace('↓', ' (down) ')
    text = text.replace('≥', '>=').replace('≤', '<=').replace('≠', '!=').replace('≈', '~')

    # 4. Remove emojis that break Latin-1 fonts
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[📖🌾📌📝⭐🚀🔍📋📚🎉&bull;•]', '', text)

    # 5. Clean non-breaking spaces
    text = text.replace('\u00a0', ' ').replace('\u200b', '')

    # 6. Escape HTML characters for ReportLab paraparser
    escaped = html.escape(text)

    # 7. Convert markdown bold and italic tags
    escaped = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', escaped)
    escaped = re.sub(r'\*(.*?)\*', r'<i>\1</i>', escaped)
    escaped = escaped.replace("-&gt;", " &rarr; ")

    # 8. Encode safely without producing '?' artifacts
    if PDF_FONT == 'Helvetica':
        return escaped.encode('latin-1', 'ignore').decode('latin-1')
    return escaped

# -------------------------------------------------------------
# TWO-PASS NUMBERED CANVAS (PAGE X OF Y + CLEAN HEADER)
# -------------------------------------------------------------
class CleanNumberedCanvas(canvas.Canvas):
    """Prints running headers and page numbers on every page without '???'."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont(PDF_FONT_BOLD, 8)
        self.setFillColor(colors.HexColor('#1b5e20'))
        self.drawString(40, 810, "PUBLIC SERVICE COMMISSION (LOK SEWA AAYOG) - NEPAL")
        
        self.setFont(PDF_FONT, 8)
        self.setFillColor(colors.HexColor('#555555'))
        self.drawRightString(555, 810, "Nepal Agricultural Service | Gazetted 3rd Class")
        
        self.setStrokeColor(colors.HexColor('#1b5e20'))
        self.setLineWidth(1)
        self.line(40, 804, 555, 804)

        # Clean Footer
        self.setStrokeColor(colors.HexColor('#cbd5e1'))
        self.setLineWidth(0.5)
        self.line(40, 40, 555, 40)
        
        self.setFont(PDF_FONT, 7.5)
        self.setFillColor(colors.HexColor('#64748b'))
        self.drawString(40, 28, "Model Question Answers | Strict Exam Orientation")
        self.drawRightString(555, 28, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()

# -------------------------------------------------------------
# CLEAN QUESTION-ANSWER PDF BUILDER (NO INDEX / NO FLUFF)
# -------------------------------------------------------------
def build_pdf_story_for_qa(question: str, marks: int, answer_markdown: str, q_num: int = None):
    """Builds a styled, readable Q&A block without '???' artifacts."""
    styles = getSampleStyleSheet()
    content_width = 515

    q_badge_style = ParagraphStyle(
        f'QBadge_{q_num}', parent=styles['Normal'], fontName=PDF_FONT_BOLD, fontSize=8, leading=11, textColor=colors.HexColor('#0d47a1')
    )
    q_title_style = ParagraphStyle(
        f'QTitle_{q_num}', parent=styles['Normal'], fontName=PDF_FONT_BOLD, fontSize=10, leading=14, textColor=colors.HexColor('#0f172a')
    )
    h1_style = ParagraphStyle(
        f'H1_{q_num}', parent=styles['Normal'], fontName=PDF_FONT_BOLD, fontSize=9.5, leading=13, textColor=colors.HexColor('#1b5e20'), spaceBefore=8, spaceAfter=4
    )
    body_style = ParagraphStyle(
        f'Body_{q_num}', parent=styles['Normal'], fontName=PDF_FONT, fontSize=8.5, leading=12.5, textColor=colors.HexColor('#1f2937'), spaceAfter=3.5
    )
    bullet_style = ParagraphStyle(
        f'Bullet_{q_num}', parent=styles['Normal'], fontName=PDF_FONT, fontSize=8.5, leading=12.5, leftIndent=12, spaceAfter=2.5
    )
    story_text_style = ParagraphStyle(
        f'StoryTxt_{q_num}', parent=styles['Normal'], fontName=PDF_FONT, fontSize=8.5, leading=13, textColor=colors.HexColor('#78350f')
    )
    flow_step_style = ParagraphStyle(
        f'FlowTxt_{q_num}', parent=styles['Normal'], fontName=PDF_FONT, fontSize=8, leading=11.5, textColor=colors.HexColor('#14532d')
    )
    tbl_hdr_style = ParagraphStyle(
        f'TblHdr_{q_num}', parent=styles['Normal'], fontName=PDF_FONT_BOLD, fontSize=8, leading=10, textColor=colors.white, alignment=1
    )
    tbl_cell_style = ParagraphStyle(
        f'TblCell_{q_num}', parent=styles['Normal'], fontName=PDF_FONT, fontSize=8, leading=10.5, textColor=colors.HexColor('#1f2937')
    )

    story = []

    # 1. QUESTION BANNER CARD
    q_prefix = f"QUESTION #{q_num:02d}" if q_num else "QUESTION"
    card_data = [
        [Paragraph(f"<b>{q_prefix} &nbsp;|&nbsp; WEIGHTAGE: {marks} MARKS</b>", q_badge_style)],
        [Paragraph(clean_pdf_text(question), q_title_style)]
    ]
    q_card = Table(card_data, colWidths=[content_width])
    q_card.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0f6ff')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#bfdbfe')),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
        ('TOPPADDING', (0, 1), (-1, 1), 2),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(q_card)
    story.append(Spacer(1, 8))

    # Parse answer markdown lines
    lines = answer_markdown.split("\n")
    in_mermaid = False
    mermaid_lines = []
    in_table = False
    table_rows = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # Handle Mermaid diagram block
        if f"{TRIPLE_BACKTICKS}mermaid" in line:
            in_mermaid = True
            mermaid_lines = []
            continue
        elif in_mermaid and TRIPLE_BACKTICKS in line:
            in_mermaid = False
            flow_flowables = [
                Paragraph("<b>PROCESS FLOW & LOGICAL MECHANISM:</b>", ParagraphStyle('FTitle', fontName=PDF_FONT_BOLD, fontSize=8.5, textColor=colors.HexColor('#166534'), spaceAfter=4))
            ]
            step_idx = 1
            for m_line in mermaid_lines:
                clean_step = m_line.replace("-->", " -> ").replace("[", "").replace("]", "").replace('"', '').replace('<br/>', ' ').strip()
                if clean_step and not clean_step.lower().startswith(('graph', 'flowchart', 'subgraph', 'end')):
                    flow_flowables.append(Paragraph(f"<b>[Step {step_idx:02d}]</b> {clean_pdf_text(clean_step)}", flow_step_style))
                    flow_flowables.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;&darr;", ParagraphStyle('Arr', fontName=PDF_FONT_BOLD, fontSize=7.5, textColor=colors.HexColor('#16a34a'))))
                    step_idx += 1
            if len(flow_flowables) > 2:
                flow_flowables.pop()
                
            flow_card = Table([[flow_flowables]], colWidths=[content_width])
            flow_card.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0fdf4')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#bbf7d0')),
                ('PADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(Spacer(1, 4))
            story.append(flow_card)
            story.append(Spacer(1, 6))
            continue
        elif in_mermaid:
            mermaid_lines.append(line)
            continue

        # Handle Markdown Data Tables
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if not cells or all(c == "" or set(c) <= set("-:") for c in cells):
                continue
            table_rows.append(cells)
            in_table = True
            continue
        elif in_table:
            if table_rows:
                col_w = content_width / len(table_rows[0])
                t_data = []
                for r_idx, row in enumerate(table_rows):
                    p_row = []
                    for c_txt in row:
                        if r_idx == 0:
                            p_row.append(Paragraph(f"<b>{clean_pdf_text(c_txt)}</b>", tbl_hdr_style))
                        else:
                            p_row.append(Paragraph(clean_pdf_text(c_txt), tbl_cell_style))
                    t_data.append(p_row)
                    
                table_obj = Table(t_data, colWidths=[col_w] * len(table_rows[0]))
                table_obj.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1b5e20')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
                    ('PADDING', (0, 0), (-1, -1), 4.5),
                ]))
                story.append(table_obj)
                story.append(Spacer(1, 6))
            table_rows = []
            in_table = False

        # Handle English Memory Story Mnemonic (Warm Golden Box)
        if "memory story" in line.lower() or "mnemonic" in line.lower() or "rapid recall" in line.lower():
            story_box_data = [
                [Paragraph("<b>RAPID RECALL MEMORY STORY:</b>", ParagraphStyle('StryHdr', fontName=PDF_FONT_BOLD, fontSize=8.5, textColor=colors.HexColor('#92400e')))],
                [Paragraph(clean_pdf_text(line), story_text_style)]
            ]
            story_card = Table(story_box_data, colWidths=[content_width])
            story_card.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fffbeb')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#fde68a')),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ]))
            story.append(Spacer(1, 4))
            story.append(story_card)
            story.append(Spacer(1, 6))
            continue

        # Handle Headings
        if line.startswith("#"):
            clean_h = re.sub(r"^#+\s*", "", line)
            story.append(Paragraph(f"<b>{clean_pdf_text(clean_h).upper()}</b>", h1_style))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0'), spaceBefore=1, spaceAfter=4))
        # Handle Bullets
        elif line.startswith(("-", "*")) or (len(line) > 2 and line[0].isdigit() and line[1] in [".", ")"]):
            clean_bullet = re.sub(r"^[-*]\s*", "", line)
            clean_bullet = re.sub(r"^\d+[\.\)]\s*", "", clean_bullet)
            story.append(Paragraph(f"&bull;&nbsp;&nbsp;{clean_pdf_text(clean_bullet)}", bullet_style))
        else:
            story.append(Paragraph(clean_pdf_text(line), body_style))

    return story

def generate_single_pdf_bytes(question: str, marks: int, answer_markdown: str) -> bytes:
    """Generates a clean single Q&A PDF without '???' artifacts."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=48, bottomMargin=48)
    story = build_pdf_story_for_qa(question, marks, answer_markdown)
    doc.build(story, canvasmaker=CleanNumberedCanvas)
    return buffer.getvalue()

def generate_bulk_pdf_bytes(qa_list: list, title: str = "") -> bytes:
    """
    Generates a bulk PDF containing strictly Question and Answers only.
    No index, no table of contents, no filler pages.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=48, bottomMargin=48)
    story = []

    # Pure Question-Answer sequence separated by clean page breaks
    for idx, item in enumerate(qa_list):
        q_story = build_pdf_story_for_qa(
            item["question"],
            item.get("marks", 10),
            item["answer"],
            q_num=idx + 1
        )
        story.extend(q_story)
        if idx < len(qa_list) - 1:
            story.append(Spacer(1, 15))
            story.append(PageBreak())  # Next question starts on a fresh page

    doc.build(story, canvasmaker=CleanNumberedCanvas)
    return buffer.getvalue()

# -------------------------------------------------------------
# LOK SEWA SYSTEM PROMPT (POST-2024 REVISED DATA & DIRECTIVES)
# -------------------------------------------------------------
LOKSEWA_SYSTEM_PROMPT = (
    "You are an elite Nepal Lok Sewa Aayog evaluator and answer-writing mentor for the Nepal Agricultural Service "
    "(Gazetted Third Class / रा.प. तृतीय श्रेणी - Agri Extension, Horticulture, Agronomy, Plant Protection, Soil Science).\n\n"
    "Your mission is to produce high-scoring, concise, examiner-friendly answers tailored for the 3-hour written exam.\n"
    "Provide FEWER, PUNCHY, HIGH-IMPACT, EASY-TO-REMEMBER points suitable for a 13-14 minute writing window.\n\n"
    "MANDATORY POST-2024 / 2081/2082 VERIFIED OFFICIAL STATISTICAL & INSTITUTIONAL BASELINE:\n"
    "1. Macroeconomic Accounts (Post-2024 MoF & NSO Surveys):\n"
    "   * Agriculture, Forestry & Fisheries share in GDP: 25.16% (Primary sector: ~25.2%, Industry: 12.83%, Services: 62.01%).\n"
    "   * Economic Growth Rate (GDP Growth): 4.61%.\n"
    "   * National GDP Size: NPR 61.07 Kharba (Rs. 6.107 Trillion).\n"
    "   * Per Capita GNI: USD 1,517.\n"
    "   * Cereal Production: National paddy harvest stands at 5.75 - 5.95 Million MT (average productivity ~4.14-4.19 MT/ha); Maize ~3.15M MT; Wheat ~2.18M MT.\n"
    "2. PQPMC Banned Pesticides Gazette Update (December 2024 Notification):\n"
    "   * Exactly 27 active ingredients are now banned in Nepal (December 2024 gazette added Paraquat, Chlorpyrifos, and Phorate).\n"
    "   * Pesticide import volume: ~1,664 MT active ingredients.\n"
    "3. SQCC & Seed Sector Updates:\n"
    "   * Over 700+ notified crop varieties; Seed Replacement Rate (SRR: Paddy ~24%, Wheat ~22%, Maize ~20% against 25-33% national seed vision target).\n"
    "4. Post-2024 Legislative & Policy Enactments:\n"
    "   * National Agriculture Policy, 2081 (2024 AD) - Federalized execution, contract farming, climate resilience.\n"
    "   * Agriculture Investment Decade, 2081-2091 (2024-2034 AD) - Public-Private-Cooperative financing.\n"
    "   * Food Hygiene and Quality Act, 2081 (2024 AD) - Farm-to-fork standards, SPS compliance, traceability.\n"
    "   * Pesticides Management Regulation, 2081 (2024 AD) - Framed under Pesticides Management Act 2076.\n"
    "   * Plant Protection Regulation (First Amendment), 2080 (2024 AD).\n"
    "   * 16th Periodic Plan (2081/82-2085/86) - Production corridors and structural agro-transformation.\n\n"
    "DYNAMIC TECHNICAL DATA CITATION:\n"
    "- NEVER blindly copy-paste the same general GDP data onto technical agronomy, pathology, soil, or horticulture questions.\n"
    "- Provide genuine, domain-specific technical metrics (e.g., Economic Threshold Levels, spore germination temperatures, chilling hours, TSS/Brix, soil pH/SOM ranges, benefit-cost ratios, Seed Certification standards) citing NARC, DoA (Krishi Diary), PQPMC, SQCC, or PMAMP.\n\n"
    "CRITICAL MERMAID INSTRUCTIONS (DETAILED, COMPLETE & BEAUTIFULLY STRUCTURED):\n"
    "1. Do NOT limit flowcharts to 4 simple steps. Build a detailed, comprehensive, multi-stage model (5 to 8+ interconnected steps, branches, or feedback loops) that truly explains the technical mechanism.\n"
    "2. ALWAYS use Top-Down orientation: `graph TD`.\n"
    "3. Keep text inside boxes concise (3-5 words) using `<br/>` for line breaks.\n"
    "4. Always wrap node labels in double quotes, e.g., A[\"Stage 1: Awareness<br/>(Mass Media Reach)\"] --> B[\"Stage 2: Interest<br/>(Demonstration Visits)\"].\n"
    "5. NEVER print meta-text comments like '(Only 4 steps)'.\n\n"
    "STORY-BASED MNEMONIC REQUIREMENT (ENGLISH STORY ONLY):\n"
    "- DO NOT generate dry letter acronyms.\n"
    "- Provide a memorable 1-2 sentence narrative micro-story strictly in ENGLISH connecting all core analytical points in chronological order.\n"
    "- Format Example:\n"
    "  * 📖 **Memory Story (Rapid Recall Narrative):** 'Farmer **Hari** first tested his **Soil & Certified Seed** (Inputs), adopted **AKC Extension Advice** (Technical Knowledge), stored his harvest in a **Cold Chain Hub** (Post-Harvest Infrastructure), and secured a direct contract via the **Cooperatives Value Chain** (Market Linkage) to achieve **Double Net Profit** (Economic Outcome).'\n\n"
    "STRICT ANSWER ARCHITECTURE:\n"
    "1. Concise Introduction (2-3 sentences: concept, scope, importance)\n"
    "2. Current Scenario & Topic-Specific Data Snapshot (Cite post-2024 NARC/DoA/PQPMC/SQCC/PMAMP publications/data)\n"
    "3. Mandatory Mermaid Diagram / Process Model (Detailed Top-Down `graph TD` showing the full mechanism)\n"
    "4. Policy, Legal & Institutional Linkage (National Agri Policy 2081, 16th Plan, Food Hygiene Act 2081, PMAMP, SQCC/PQPMC Acts)\n"
    "5. Main Analytical Core (5-7 punchy points: Bold Heading -> Cause/Effect -> Practical Implication)\n"
    "6. Key Operational Challenges (4-5 points)\n"
    "7. Actionable Way Forward (Federal, Provincial, Local roles & Project Linkages)\n"
    "8. Story-Based Mnemonic for Rapid Recall (English narrative micro-story)\n"
    "9. Strategic Conclusion"
)

# -------------------------------------------------------------
# RESPONSIVE TOP-DOWN MERMAID RENDERING ENGINE
# -------------------------------------------------------------
def render_loksewa_content(content_text: str):
    """Renders markdown text with an auto-fitting, responsive vertical Mermaid diagram."""
    mermaid_pattern = rf"({TRIPLE_BACKTICKS}mermaid[\s\S]*?{TRIPLE_BACKTICKS})"
    parts = re.split(mermaid_pattern, content_text)
    
    for part in parts:
        if part.startswith(f"{TRIPLE_BACKTICKS}mermaid"):
            mermaid_code = part.replace(f"{TRIPLE_BACKTICKS}mermaid", "").replace(TRIPLE_BACKTICKS, "").strip()
            mermaid_code = re.sub(r'\b(graph|flowchart)\s+LR\b', r'\1 TD', mermaid_code, flags=re.IGNORECASE)
            
            line_count = len(mermaid_code.strip().split('\n'))
            dyn_height = min(950, max(320, line_count * 45 + 100))
            
            html_code = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{
                        margin: 0;
                        padding: 8px;
                        background: transparent;
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                    }}
                    .mermaid-wrapper {{
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        background-color: #f8fafc;
                        border: 1px solid #cbd5e1;
                        border-radius: 8px;
                        padding: 16px;
                        box-sizing: border-box;
                        width: 100%;
                        max-width: 680px;
                    }}
                    .mermaid {{
                        width: 100%;
                        display: flex;
                        justify-content: center;
                    }}
                    .mermaid svg {{
                        max-width: 100% !important;
                        height: auto !important;
                    }}
                </style>
            </head>
            <body>
                <div class="mermaid-wrapper">
                    <pre class="mermaid">
{mermaid_code}
                    </pre>
                </div>
                <script type="module">
                    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
                    mermaid.initialize({{
                        startOnLoad: true,
                        theme: 'neutral',
                        securityLevel: 'loose',
                        themeVariables: {{
                            fontSize: '12px',
                            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
                        }},
                        flowchart: {{
                            useMaxWidth: false,
                            htmlLabels: true,
                            curve: 'basis'
                        }}
                    }});
                </script>
            </body>
            </html>
            """
            components.html(html_code, height=dyn_height, scrolling=True)
        else:
            if part.strip():
                st.markdown(part)

# -------------------------------------------------------------
# SILENT AUTO-DISCOVERY OF MODELS
# -------------------------------------------------------------
def get_groq_client(api_key: str):
    if not api_key:
        return None
    return Groq(api_key=api_key)

def auto_select_models_silently(client):
    try:
        models = client.models.list()
        all_ids = [m.id for m in models.data]
        
        text_priority = [
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "llama-3.1-8b-instant"
        ]
        text_model = "llama-3.1-8b-instant"
        for tp in text_priority:
            if tp in all_ids:
                text_model = tp
                break
                
        vision_model = "qwen/qwen3.8-27b"
        for m in all_ids:
            if "qwen" in m.lower() or "vision" in m.lower():
                vision_model = m
                break
                
        return vision_model, text_model
    except Exception:
        return "qwen/qwen3.8-27b", "llama-3.1-8b-instant"

def preprocess_and_encode_image(image: Image.Image) -> str:
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
    max_dim = 1200
    if max(image.size) > max_dim:
        image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=85)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def extract_questions_from_image(client, image: Image.Image, vision_model: str):
    base64_image = preprocess_and_encode_image(image)
    extraction_prompt = (
        "Examine this exam paper image. Extract and transcribe ALL individual questions concisely.\n"
        "Number each question clearly (e.g. Q1, Q2, Q3...). Include marks if shown (e.g. [5], [10]).\n"
        "Output ONLY the cleanly numbered list of questions."
    )
    response = client.chat.completions.create(
        model=vision_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": extraction_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                    }
                ]
            }
        ],
        temperature=0.1,
        max_tokens=700,
    )
    return response.choices[0].message.content

def generate_loksewa_answer(client, question_text: str, marks: int, text_model: str, retries: int = 2):
    user_prompt = f"""
    Write a high-scoring Lok Sewa examination answer for:
    
    QUESTION: {question_text}
    MARKS ALLOTTED: {marks} Marks
    
    Adhere strictly to the required answer format:
    1. Concise Introduction (2-3 sentences: concept, scope, importance)
    2. Current Scenario & Topic-Specific Data Snapshot:
       - Use latest post-2024 official data (Economic Survey: AGDP 25.16%, GDP Growth 4.61%, Paddy 5.75-5.95M MT; PQPMC updated 27 banned pesticides; SQCC 700+ varieties; SRR 24% rice / 22% wheat).
       - Provide technical thresholds, ratios, and metrics directly relevant to this question's domain from NARC, DoA (Krishi Diary), PQPMC, SQCC, or PMAMP.
    3. Mermaid Diagram: MANDATORY Top-Down `graph TD`. Make it a detailed, comprehensive, multi-stage model (5 to 8+ steps) that fully captures the technical mechanism. Wrap all node labels in double quotes. Do NOT add meta comments like '(only 4 steps)'.
    4. Policy, Legal & Institutional Linkage (Explicitly cite National Agriculture Policy 2081, 16th Periodic Plan, Food Hygiene Act 2081, Agriculture Investment Decade 2081-2091, Pesticide Regulation 2081, or relevant sectoral acts)
    5. Main Analytical Core (5-7 punchy points: Bold Heading -> Cause/Effect -> Practical Implication)
    6. Key Operational Challenges (4-5 points)
    7. Actionable Way Forward (Federal, Provincial, Local roles & Project linkages)
    8. Story-Based Mnemonic for Rapid Recall (MANDATORY in English: 1-2 sentence real-world narrative micro-story connecting all core analytical points)
    9. Strategic Conclusion
    """
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model=text_model,
                messages=[
                    {"role": "system", "content": LOKSEWA_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=3200,
            )
            return response.choices[0].message.content
        except Exception as e:
            if "429" in str(e) and attempt < retries:
                time.sleep(5)
                continue
            raise e

# -------------------------------------------------------------
# CLEAN SIDEBAR
# -------------------------------------------------------------
groq_api_key = os.getenv("GROQ_API_KEY", "")
if not groq_api_key and "GROQ_API_KEY" in st.secrets:
    groq_api_key = st.secrets["GROQ_API_KEY"]

if not groq_api_key:
    groq_api_key = st.sidebar.text_input("Enter Groq API Key", type="password", help="Get free key from console.groq.com")

saved_count = len(st.session_state["saved_notes"])
st.sidebar.markdown(f"### 📚 Saved Notes: **{saved_count}**")

# -------------------------------------------------------------
# MAIN APP BODY
# -------------------------------------------------------------
st.title("🌾 Lok Sewa Agri Officer Answer Coach")
st.caption("Post-2024 Verified Data Baseline | Clean Q&A PDF Engine (No Artifacts) | English Story Mnemonics")

if not groq_api_key:
    st.warning("👈 Please enter your Groq API Key in the left sidebar to start.")
    st.stop()

client = get_groq_client(groq_api_key)
vision_model, text_model = auto_select_models_silently(client)

tab1, tab2, tab3 = st.tabs([
    "📸 Photo Upload (Up to 12 Questions)", 
    "✍️ Single Question Direct Input", 
    f"📚 Revision Bank ({len(st.session_state['saved_notes'])})"
])

# =============================================================
# TAB 1: PHOTO UPLOAD
# =============================================================
with tab1:
    st.subheader("Upload Exam Paper Snapshot")
    uploaded_file = st.file_uploader("Upload Question Paper (JPG, PNG)...", type=["jpg", "jpeg", "png"])
    
    if uploaded_file is not None:
        col_img, col_act = st.columns([1, 1])
        image = Image.open(uploaded_file)
        
        with col_img:
            st.image(image, caption="Uploaded Paper", use_container_width=True)
            
        with col_act:
            if st.button("🔍 Extract Questions from Photo", type="primary", use_container_width=True):
                with st.spinner("Extracting questions cleanly..."):
                    try:
                        extracted_text = extract_questions_from_image(client, image, vision_model)
                        st.session_state["extracted_questions_raw"] = extracted_text
                        lines = [q.strip() for q in extracted_text.split("\n") if q.strip() and (q[0].isdigit() or q.upper().startswith("Q"))]
                        st.session_state["parsed_questions"] = lines if lines else [extracted_text]
                        st.success("✅ Questions extracted!")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

    if "extracted_questions_raw" in st.session_state:
        st.markdown("---")
        question_list = st.session_state.get("parsed_questions", [])
        
        mode = st.radio(
            "Select Answering Mode:",
            ["Option A: Watch & Answer Single Question", "Option B: Answer & Download ALL Questions at Once"],
            horizontal=True
        )
        
        if mode == "Option A: Watch & Answer Single Question":
            col_q, col_m = st.columns([3, 1])
            with col_q:
                selected_q = st.selectbox("Choose question:", question_list)
            with col_m:
                q_marks = st.selectbox("Marks:", [5, 10, 15], index=1, key="tab1_single_marks")
                
            if st.button("🚀 Generate Answer for Selected Question", type="primary"):
                with st.spinner("Preparing answer with post-2024 citations, detailed diagram, and story mnemonic..."):
                    try:
                        ans = generate_loksewa_answer(client, selected_q, q_marks, text_model)
                        st.session_state["current_ans"] = ans
                        st.session_state["current_q"] = selected_q
                        st.session_state["current_marks"] = q_marks
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

            if "current_ans" in st.session_state:
                st.markdown("---")
                col_t, col_save, col_pdf = st.columns([3, 1, 1])
                with col_t:
                    st.subheader("📝 Model Answer")
                with col_save:
                    if st.button("⭐ Save to Notes (Serial)", key="save_tab1", use_container_width=True):
                        new_item = {
                            "question": st.session_state["current_q"],
                            "marks": st.session_state.get("current_marks", 10),
                            "answer": st.session_state["current_ans"],
                            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                        }
                        st.session_state["saved_notes"].append(new_item)
                        save_notes_to_disk(st.session_state["saved_notes"])
                        st.toast("✅ Saved in serial order to Revision Bank!", icon="📚")
                with col_pdf:
                    pdf_data = generate_single_pdf_bytes(
                        st.session_state["current_q"],
                        st.session_state.get("current_marks", 10),
                        st.session_state["current_ans"]
                    )
                    st.download_button(
                        label="📥 Download This Answer (PDF)",
                        data=pdf_data,
                        file_name=f"loksewa_answer_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                
                render_loksewa_content(st.session_state["current_ans"])

        else:
            bulk_marks = st.selectbox("Assign Default Marks per Question:", [5, 10, 15], index=1, key="tab1_bulk_marks")
            
            if st.button("🚀 Generate Answers for ALL Questions at Once", type="primary"):
                all_results = []
                prog_bar = st.progress(0)
                status_text = st.empty()
                total_count = len(question_list)
                
                for idx, q_text in enumerate(question_list):
                    status_text.write(f"✍️ **Drafting Question {idx+1}/{total_count}:** {q_text}")
                    try:
                        ans_text = generate_loksewa_answer(client, q_text, bulk_marks, text_model)
                        all_results.append({
                            "question": q_text,
                            "marks": bulk_marks,
                            "answer": ans_text,
                            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                        })
                    except Exception as e:
                        all_results.append({
                            "question": q_text,
                            "marks": bulk_marks,
                            "answer": f"Generation failed: {str(e)}",
                            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                        })
                    
                    prog_bar.progress((idx + 1) / total_count)
                    if idx < total_count - 1:
                        time.sleep(2)
                        
                st.session_state["bulk_results"] = all_results
                status_text.success("🎉 All questions answered successfully!")

            if "bulk_results" in st.session_state and st.session_state["bulk_results"]:
                bulk_data = st.session_state["bulk_results"]
                st.markdown("---")
                
                col_b1, col_b2 = st.columns([1, 1])
                with col_b1:
                    # Clean PDF with pure Questions and Answers only (no index page)
                    bulk_pdf_bytes = generate_bulk_pdf_bytes(bulk_data)
                    st.download_button(
                        label=f"📥 Download ALL {len(bulk_data)} Q&A as Single PDF",
                        data=bulk_pdf_bytes,
                        file_name=f"all_exam_answers_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )
                with col_b2:
                    if st.button("⭐ Save ALL to Revision Bank (Serial)", use_container_width=True):
                        for b_item in bulk_data:
                            st.session_state["saved_notes"].append(b_item)
                        save_notes_to_disk(st.session_state["saved_notes"])
                        st.toast(f"✅ Saved all {len(bulk_data)} questions in serial order!", icon="📚")
                
                st.markdown("### 📋 View Answers Individually:")
                for b_idx, b_item in enumerate(bulk_data):
                    with st.expander(f"Question #{b_idx+1}: {b_item['question']}"):
                        render_loksewa_content(b_item["answer"])

# =============================================================
# TAB 2: MANUAL SINGLE QUESTION INPUT
# =============================================================
with tab2:
    st.subheader("Type or Paste Question")
    single_q = st.text_area(
        "Question:", 
        placeholder="e.g., Explain the recent updates in pesticide regulations in Nepal including the PQPMC banned list, and analyze alternative pest management options under IPM. [10 marks]",
        height=100
    )
    col1, col2 = st.columns([1, 3])
    with col1:
        s_marks = st.selectbox("Marks Weightage:", [5, 10, 15], index=1, key="tab2_marks")
        
    if st.button("🚀 Generate Answer", type="primary", key="btn_single"):
        if not single_q.strip():
            st.warning("Please type a question.")
        else:
            with st.spinner("Preparing answer with post-2024 verified publications, detailed diagram, and story mnemonic..."):
                try:
                    ans = generate_loksewa_answer(client, single_q, s_marks, text_model)
                    st.session_state["single_ans"] = ans
                    st.session_state["single_q"] = single_q
                    st.session_state["single_marks"] = s_marks
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    if "single_ans" in st.session_state:
        st.markdown("---")
        col_t, col_save, col_pdf = st.columns([3, 1, 1])
        with col_t:
            st.subheader("📝 Model Answer")
        with col_save:
            if st.button("⭐ Save to Notes (Serial)", key="save_tab2", use_container_width=True):
                new_item = {
                    "question": st.session_state["single_q"],
                    "marks": st.session_state.get("single_marks", 10),
                    "answer": st.session_state["single_ans"],
                    "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                st.session_state["saved_notes"].append(new_item)
                save_notes_to_disk(st.session_state["saved_notes"])
                st.toast("✅ Saved in serial order to Revision Bank!", icon="📚")
        with col_pdf:
            pdf_data = generate_single_pdf_bytes(
                st.session_state["single_q"],
                st.session_state.get("single_marks", 10),
                st.session_state["single_ans"]
            )
            st.download_button(
                label="📥 Download This Answer (PDF)",
                data=pdf_data,
                file_name=f"loksewa_answer_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
                
        render_loksewa_content(st.session_state["single_ans"])

# =============================================================
# TAB 3: REVISION BANK (SERIAL ORDER: 1ST SAVED = #1)
# =============================================================
with tab3:
    st.subheader(f"📚 Serial Revision Bank ({len(st.session_state['saved_notes'])} Notes)")
    notes = st.session_state["saved_notes"]
    
    if not notes:
        st.info("No answers saved yet. Click '⭐ Save to Notes' on any question to store it here serially.")
    else:
        col_r1, col_r2 = st.columns([2, 1])
        with col_r1:
            # Clean Revision Bank PDF with Questions and Answers only (no index)
            all_bank_pdf = generate_bulk_pdf_bytes(notes)
            st.download_button(
                label=f"📥 Download Entire Revision Bank ({len(notes)} Questions) as Single PDF",
                data=all_bank_pdf,
                file_name=f"my_revision_notes_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )
        with col_r2:
            if st.button("🗑️ Clear Entire Revision Bank", use_container_width=True):
                st.session_state["saved_notes"] = []
                save_notes_to_disk([])
                st.rerun()

        st.markdown("---")
        
        for idx, item in enumerate(notes):
            serial_no = idx + 1
            with st.expander(f"📌 #{serial_no}. {item['question']} (Saved: {item.get('saved_at', 'N/A')})"):
                col_exp_pdf, col_exp_del = st.columns([1, 1])
                with col_exp_pdf:
                    pdf_saved = generate_single_pdf_bytes(item["question"], item.get("marks", 10), item["answer"])
                    st.download_button(
                        label=f"📥 Download PDF for #{serial_no}",
                        data=pdf_saved,
                        file_name=f"note_serial_{serial_no}.pdf",
                        mime="application/pdf",
                        key=f"pdf_saved_{idx}"
                    )
                with col_exp_del:
                    if st.button(f"🗑️ Delete Note #{serial_no}", key=f"del_{idx}"):
                        notes.pop(idx)
                        save_notes_to_disk(notes)
                        st.rerun()
                        
                render_loksewa_content(item["answer"])
