import streamlit as st
import streamlit.components.v1 as components
import base64
import os
import re
import html
import time
import urllib.request
import urllib.parse
from datetime import datetime
from groq import Groq
from PIL import Image
import io

# ReportLab imports for Clean PDF Generation
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak, Table, TableStyle, Image as RLImage
)
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

TRIPLE_BACKTICKS = chr(96) * 3

# -------------------------------------------------------------
# PAGE CONFIGURATION & IN-MEMORY (AUTO-ERASE) STATE
# -------------------------------------------------------------
st.set_page_config(
    page_title="Lok Sewa Agri Officer Dynamic Coach",
    page_icon="🌾",
    layout="wide"
)

# Pure in-memory session: Automatically wiped clean when the browser window closes
if "saved_notes" not in st.session_state:
    st.session_state["saved_notes"] = []

# -------------------------------------------------------------
# DYNAMIC UNICODE FONT LOADER & ARTIFACT CLEANER
# -------------------------------------------------------------
PDF_FONT = 'Helvetica'
PDF_FONT_BOLD = 'Helvetica-Bold'

def setup_pdf_font():
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
    """Cleans Unicode characters to avoid '???' artifacts in ReportLab."""
    if not raw_text:
        return ""
    text = raw_text
    text = text.replace('—', ' - ').replace('–', ' - ').replace('―', ' - ')
    text = text.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
    text = text.replace('→', ' -> ').replace('←', ' <- ').replace('↑', ' (up) ').replace('↓', ' (down) ')
    text = text.replace('≥', '>=').replace('≤', '<=').replace('≠', '!=').replace('≈', '~')
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[📖🌾📌📝⭐🚀🔍📋📚🎉&bull;•🔄🌳🎯💡🔬🧪🖼️]', '', text)
    text = text.replace('\u00a0', ' ').replace('\u200b', '')

    escaped = html.escape(text)
    escaped = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', escaped)
    escaped = re.sub(r'\*(.*?)\*', r'<i>\1</i>', escaped)
    escaped = escaped.replace("-&gt;", " &rarr; ")

    if PDF_FONT == 'Helvetica':
        return escaped.encode('latin-1', 'ignore').decode('latin-1')
    return escaped

# -------------------------------------------------------------
# TWO-PASS NUMBERED CANVAS (PAGE X OF Y)
# -------------------------------------------------------------
class CleanNumberedCanvas(canvas.Canvas):
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
        self.drawRightString(555, 810, "Nepal Agricultural Service | Gazetted 3rd Class (Officer Level)")
        
        self.setStrokeColor(colors.HexColor('#1b5e20'))
        self.setLineWidth(1)
        self.line(40, 804, 555, 804)

        self.setStrokeColor(colors.HexColor('#cbd5e1'))
        self.setLineWidth(0.5)
        self.line(40, 40, 555, 40)
        
        self.setFont(PDF_FONT, 7.5)
        self.setFillColor(colors.HexColor('#64748b'))
        self.drawString(40, 28, "Dynamic Subject-Tailored Model Answers & Flowchart Revision Notes")
        self.drawRightString(555, 28, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()

# -------------------------------------------------------------
# MERMAID CODE SANITIZER (PREVENTS PARSER CRASHES)
# -------------------------------------------------------------
def sanitize_mermaid_code(code: str) -> str:
    """Sanitizes syntax to guarantee error-free rendering in Mermaid.js & ReportLab."""
    clean = code.strip()
    clean = re.sub(r'^(graph|flowchart)\s+(TD|TB|LR)', r'flowchart \2', clean, flags=re.IGNORECASE)
    clean = clean.replace('&nbsp;', ' ').replace('&bull;', '').replace('•', '-')
    clean = re.sub(r'&(?!amp;|lt;|gt;)', 'and', clean)
    clean = clean.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')
    return clean

# -------------------------------------------------------------
# NATIVE IMAGE FETCH HELPER
# -------------------------------------------------------------
def fetch_mermaid_png_bytes(mermaid_code: str):
    """Fetches high-res PNG image bytes for diagram saving and PDF embedding."""
    try:
        clean_code = sanitize_mermaid_code(mermaid_code)
        encoded = base64.b64encode(clean_code.encode("utf-8")).decode("ascii")
        url = f"https://mermaid.ink/img/{encoded}?bgColor=FFFFFF"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=4.5) as resp:
            if resp.status == 200:
                return resp.read()
    except Exception:
        pass
    return None

# -------------------------------------------------------------
# PDF BUILDER 1: FULL MODEL ANSWER
# -------------------------------------------------------------
def build_pdf_story_for_qa(question: str, marks: int, answer_markdown: str, q_num: int = None):
    styles = getSampleStyleSheet()
    content_width = 515

    q_badge_style = ParagraphStyle(f'QB_{q_num}', parent=styles['Normal'], fontName=PDF_FONT_BOLD, fontSize=8, leading=11, textColor=colors.HexColor('#0d47a1'))
    q_title_style = ParagraphStyle(f'QT_{q_num}', parent=styles['Normal'], fontName=PDF_FONT_BOLD, fontSize=9.5, leading=13.5, textColor=colors.HexColor('#0f172a'))
    h1_style = ParagraphStyle(f'H1_{q_num}', parent=styles['Normal'], fontName=PDF_FONT_BOLD, fontSize=9, leading=12.5, textColor=colors.HexColor('#1b5e20'), spaceBefore=7, spaceAfter=3)
    body_style = ParagraphStyle(f'B_{q_num}', parent=styles['Normal'], fontName=PDF_FONT, fontSize=8.2, leading=12, textColor=colors.HexColor('#1f2937'), spaceAfter=3)
    bullet_style = ParagraphStyle(f'BL_{q_num}', parent=styles['Normal'], fontName=PDF_FONT, fontSize=8.2, leading=12, leftIndent=12, spaceAfter=2.5)
    story_text_style = ParagraphStyle(f'ST_{q_num}', parent=styles['Normal'], fontName=PDF_FONT, fontSize=8.2, leading=12.5, textColor=colors.HexColor('#78350f'))
    diag_row_style = ParagraphStyle(f'DR_{q_num}', parent=styles['Normal'], fontName=PDF_FONT, fontSize=7.8, leading=11, textColor=colors.HexColor('#14532d'))
    tbl_hdr_style = ParagraphStyle(f'TH_{q_num}', parent=styles['Normal'], fontName=PDF_FONT_BOLD, fontSize=7.8, leading=10, textColor=colors.white, alignment=1)
    tbl_cell_style = ParagraphStyle(f'TC_{q_num}', parent=styles['Normal'], fontName=PDF_FONT, fontSize=7.8, leading=10, textColor=colors.HexColor('#1f2937'))

    story = []
    q_prefix = f"QUESTION #{q_num:02d}" if q_num else "QUESTION"
    card_data = [
        [Paragraph(f"<b>{q_prefix} &nbsp;|&nbsp; WEIGHTAGE: {marks} MARKS</b>", q_badge_style)],
        [Paragraph(clean_pdf_text(question), q_title_style)]
    ]
    q_card = Table(card_data, colWidths=[content_width])
    q_card.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0f6ff')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#bfdbfe')),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(q_card)
    story.append(Spacer(1, 6))

    lines = answer_markdown.split("\n")
    in_mermaid = False
    mermaid_lines = []
    in_table = False
    table_rows = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        if f"{TRIPLE_BACKTICKS}mermaid" in line:
            in_mermaid = True
            mermaid_lines = []
            continue
        elif in_mermaid and TRIPLE_BACKTICKS in line:
            in_mermaid = False
            mermaid_code = sanitize_mermaid_code("\n".join(mermaid_lines))
            is_conclusion_flow = "flowchart lr" in mermaid_code.lower() or "graph lr" in mermaid_code.lower() or len(mermaid_lines) <= 6
            diag_label = "CONCLUSION TARGET MICRO-FLOWCHART" if is_conclusion_flow else "TECHNICAL PROCESS / MECHANISM MODEL"
            
            png_bytes = fetch_mermaid_png_bytes(mermaid_code)
            if png_bytes:
                try:
                    img_stream = io.BytesIO(png_bytes)
                    pil_img = Image.open(img_stream)
                    w, h = pil_img.size
                    display_w = min(content_width, 450)
                    display_h = (h / w) * display_w
                    if display_h > 270:
                        display_h = 270
                        display_w = (w / h) * display_h
                    img_stream.seek(0)
                    story.append(Paragraph(f"<b>{diag_label}:</b>", ParagraphStyle('DT', fontName=PDF_FONT_BOLD, fontSize=8, textColor=colors.HexColor('#166534'), spaceAfter=4)))
                    story.append(RLImage(img_stream, width=display_w, height=display_h))
                    story.append(Spacer(1, 6))
                    continue
                except Exception:
                    pass

            diag_elements = [Paragraph(f"<b>{diag_label}:</b>", ParagraphStyle('DTF', fontName=PDF_FONT_BOLD, fontSize=8, textColor=colors.HexColor('#166534'), spaceAfter=3))]
            for m_line in mermaid_lines:
                clean_l = m_line.replace("[", "").replace("]", "").replace('"', '').replace('<br/>', ' - ').strip()
                if clean_l and not clean_l.lower().startswith(('graph', 'flowchart', 'subgraph', 'end', '%%')):
                    diag_elements.append(Paragraph(f"&bull;&nbsp;{clean_pdf_text(clean_l)}", diag_row_style))
            
            flow_card = Table([[diag_elements]], colWidths=[content_width])
            flow_card.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0fdf4')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#bbf7d0')),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(flow_card)
            story.append(Spacer(1, 6))
            continue
        elif in_mermaid:
            mermaid_lines.append(line)
            continue

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
                    ('PADDING', (0, 0), (-1, -1), 3.5),
                ]))
                story.append(table_obj)
                story.append(Spacer(1, 4))
            table_rows = []
            in_table = False

        if "memory story" in line.lower() or "mnemonic" in line.lower():
            story_card = Table([[Paragraph(clean_pdf_text(line), story_text_style)]], colWidths=[content_width])
            story_card.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fffbeb')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#fde68a')),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(story_card)
            story.append(Spacer(1, 5))
            continue

        if line.startswith("#"):
            clean_h = re.sub(r"^#+\s*", "", line)
            story.append(Paragraph(f"<b>{clean_pdf_text(clean_h).upper()}</b>", h1_style))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0'), spaceBefore=1, spaceAfter=3))
        elif line.startswith(("-", "*")) or (len(line) > 2 and line[0].isdigit() and line[1] in [".", ")"]):
            clean_bullet = re.sub(r"^[-*]\s*", "", line)
            clean_bullet = re.sub(r"^\d+[\.\)]\s*", "", clean_bullet)
            story.append(Paragraph(f"&bull;&nbsp;&nbsp;{clean_pdf_text(clean_bullet)}", bullet_style))
        else:
            story.append(Paragraph(clean_pdf_text(line), body_style))

    return story

# -------------------------------------------------------------
# PDF BUILDER 2: DIAGRAMS-ONLY VISUAL REVISION BOOKLET
# -------------------------------------------------------------
def generate_diagrams_only_pdf_bytes(qa_list: list) -> bytes:
    """Builds a PDF booklet containing ONLY questions, technical diagrams, and micro-flowcharts."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=48, bottomMargin=48)
    styles = getSampleStyleSheet()
    content_width = 515
    story = []

    title_style = ParagraphStyle('DTitle', fontName=PDF_FONT_BOLD, fontSize=13.5, leading=17, textColor=colors.HexColor('#1b5e20'), alignment=1)
    sub_style = ParagraphStyle('DSub', fontName=PDF_FONT, fontSize=8.5, leading=12, textColor=colors.HexColor('#475569'), alignment=1)
    story.append(Paragraph("<b>LOK SEWA AGRI OFFICER - TECHNICAL DIAGRAM CHEAT SHEET</b>", title_style))
    story.append(Paragraph("Context-Specific Process Models & Target-Linked Conclusion Micro-Flows", sub_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#1b5e20'), spaceBefore=2, spaceAfter=12))

    for idx, item in enumerate(qa_list):
        q_text = item.get("question", "")
        ans_text = item.get("answer", "")
        
        q_banner = Table([
            [Paragraph(f"<b>QUESTION #{idx+1:02d}:</b> {clean_pdf_text(q_text)}", ParagraphStyle('QBH', fontName=PDF_FONT_BOLD, fontSize=9, leading=12.5, textColor=colors.HexColor('#0f172a')))]
        ], colWidths=[content_width])
        q_banner.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f1f5f9')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(q_banner)
        story.append(Spacer(1, 8))

        mermaid_blocks = re.findall(rf"{TRIPLE_BACKTICKS}mermaid\s*([\s\S]*?){TRIPLE_BACKTICKS}", ans_text)
        
        if not mermaid_blocks:
            story.append(Paragraph("<i>No visual diagram was attached for this item.</i>", ParagraphStyle('ND', fontName=PDF_FONT, fontSize=8, textColor=colors.gray)))
            story.append(Spacer(1, 10))
        else:
            for d_idx, raw_code in enumerate(mermaid_blocks):
                m_code = sanitize_mermaid_code(raw_code)
                is_conclusion = "flowchart lr" in m_code.lower() or "graph lr" in m_code.lower() or len(m_code.strip().split('\n')) <= 6
                label = "🎯 Conclusion Micro-Flowchart (Quick Recall)" if is_conclusion else f"🌾 Diagram {d_idx+1}: Topic Process Architecture"
                
                story.append(Paragraph(f"<b>{label}</b>", ParagraphStyle('DH', fontName=PDF_FONT_BOLD, fontSize=8.5, textColor=colors.HexColor('#166534'), spaceAfter=4)))
                
                png_bytes = fetch_mermaid_png_bytes(m_code)
                if png_bytes:
                    try:
                        img_stream = io.BytesIO(png_bytes)
                        pil_img = Image.open(img_stream)
                        w, h = pil_img.size
                        display_w = min(content_width, 440)
                        display_h = (h / w) * display_w
                        if display_h > 260:
                            display_h = 260
                            display_w = (w / h) * display_h
                        img_stream.seek(0)
                        story.append(RLImage(img_stream, width=display_w, height=display_h))
                        story.append(Spacer(1, 8))
                        continue
                    except Exception:
                        pass

                steps_data = []
                for line in m_code.strip().split('\n'):
                    clean_l = line.replace("[", "").replace("]", "").replace('"', '').replace('<br/>', ' - ').strip()
                    if clean_l and not clean_l.lower().startswith(('graph', 'flowchart', 'subgraph', 'end')):
                        steps_data.append(Paragraph(f"&bull;&nbsp;{clean_pdf_text(clean_l)}", ParagraphStyle('FST', fontName=PDF_FONT, fontSize=8, leading=11)))
                
                if steps_data:
                    card = Table([[steps_data]], colWidths=[content_width])
                    card.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
                        ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#cbd5e1')),
                        ('PADDING', (0, 0), (-1, -1), 6),
                    ]))
                    story.append(card)
                    story.append(Spacer(1, 8))

        if idx < len(qa_list) - 1:
            story.append(Spacer(1, 10))
            story.append(PageBreak())

    doc.build(story, canvasmaker=CleanNumberedCanvas)
    return buffer.getvalue()

def generate_single_pdf_bytes(question: str, marks: int, answer_markdown: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=48, bottomMargin=48)
    story = build_pdf_story_for_qa(question, marks, answer_markdown)
    doc.build(story, canvasmaker=CleanNumberedCanvas)
    return buffer.getvalue()

def generate_bulk_pdf_bytes(qa_list: list) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=48, bottomMargin=48)
    story = []
    for idx, item in enumerate(qa_list):
        q_story = build_pdf_story_for_qa(item["question"], item.get("marks", 10), item["answer"], q_num=idx + 1)
        story.extend(q_story)
        if idx < len(qa_list) - 1:
            story.append(Spacer(1, 12))
            story.append(PageBreak())
    doc.build(story, canvasmaker=CleanNumberedCanvas)
    return buffer.getvalue()

# -------------------------------------------------------------
# ZERO-PREMADE-DATA LOK SEWA SYSTEM PROMPT
# -------------------------------------------------------------
LOKSEWA_SYSTEM_PROMPT = (
    "You are an elite, highly rigorous Nepal Public Service Commission (Lok Sewa Aayog) Senior Evaluator for the "
    "Nepal Agricultural Service (Gazetted Third Class / रा.प. तृतीय श्रेणी: Agronomy, Horticulture, Plant Protection, "
    "Soil Science, Agri Extension, and Agricultural Economics).\n\n"
    "STRICT DIRECTIVE: ZERO PRE-MADE DATA & ZERO COOKIE-CUTTER TEMPLATES:\n"
    "1. Under NO circumstances should you repeat a fixed table of macroeconomic or generic indicators (like GDP, national grain totals, or pesticide counts) unless the question explicitly asks for them.\n"
    "2. Every answer must be built from the ground up, tailored 100% to the question's specific discipline, command terms (e.g., Explain, Critically Evaluate, Differentiate, Describe, Formulate), and marks weightage.\n"
    "3. All empirical figures, technical dosages, economic thresholds (ETL), incubation periods, CCE values, chemical active ingredients, NARC varietal names, or legal Acts cited MUST be directly relevant to that specific subject matter.\n\n"
    "DYNAMIC SUBJECT-MATTER RULES:\n"
    "- If Plant Pathology / Entomology: Focus strictly on etiology, taxonomy, symptoms, infection/life cycle, ETLs, and precise cultural, biological, and chemical IPM dosages (e.g., ml/L, g/L, or kg/ha). Diagram must be an Infection Cycle or IPM Decision Tree.\n"
    "- If Agronomy / Seed Science: Focus on agro-ecology, certified seed classes, varietal release mechanisms (SQCC), land preparation, sowing geometry, nutrient splitting, and Seed Replacement Rate (SRR). Diagram must be a Cultivation SOP or Seed Multiplication Loop.\n"
    "- If Soil Science: Focus on soil chemical/physical properties, acidity correction dynamics, CCE calculation, nutrient interactions, Soil Health Card diagnostics, and fertilizer efficiency. Diagram must be a Nutrient Transformation or Liming Cycle.\n"
    "- If Horticulture / Post-Harvest: Focus on rootstocks, canopy architecture, chilling requirements, maturity indices, sorting, cold-chain preservation, and shelf-life extension. Diagram must be a Value Addition or Post-Harvest Handling Process.\n"
    "- If Agricultural Extension & Policy: Focus on constitutional allocations (Schedules 5 to 9), institutional interfaces (Federal DoA, Provincial AKC, Local 753 units), technology adoption models, and federal coordination. Diagram must be an Institutional Service Delivery Architecture.\n\n"
    "MERMAID SYNTAX RULES (GUARANTEED ERROR-FREE):\n"
    "- Always start the process diagram with `flowchart TD`.\n"
    "- Use standard rectangular nodes: A[\"Stage Title<br/>- Technical detail 1<br/>- Technical detail 2\"].\n"
    "- Do NOT use round brackets (), HTML tags like <b>, bullets like •, or raw ampersands & inside node text. Use 'and'.\n"
    "- The diagram must clearly portray the core technical mechanism of the question.\n\n"
    "STRICTLY CONTEXTUAL CONCLUSION:\n"
    "- Frame a contextual strategic vision directly answering the question's core problem.\n"
    "- Propose an actionable, field-level solution viable under Nepal's federal reality.\n"
    "- Conclude by linking directly to the specific official target governing that topic (e.g., 16th Plan target, ADS 2015-2035 target, National Seed Vision target, Food Hygiene Act 2081, or SDG-2).\n"
    "- Finish with an EXACTLY 3-to-4 node horizontal flowchart (`flowchart LR`) showing: `[Strategic Concept] --> [Field Action] --> [Target Realized]`.\n\n"
    "TIME & MARKS CALIBRATION:\n"
    "- 5 Marks: ~180-250 words, concise, focused, 1 short diagram.\n"
    "- 10 Marks: ~450-650 words, comprehensive, technical core, main diagram + conclusion micro-flowchart.\n"
    "- 15 Marks: ~750-950 words, in-depth analytical evaluation, multi-tier operational details."
)

# -------------------------------------------------------------
# RESPONSIVE CONTENT RENDERER WITH FAILSAFE JS ENGINE
# -------------------------------------------------------------
def render_loksewa_content(content_text: str):
    mermaid_pattern = rf"({TRIPLE_BACKTICKS}mermaid[\s\S]*?{TRIPLE_BACKTICKS})"
    parts = re.split(mermaid_pattern, content_text)
    
    diagram_count = 0
    for part in parts:
        if part.startswith(f"{TRIPLE_BACKTICKS}mermaid"):
            diagram_count += 1
            raw_code = part.replace(f"{TRIPLE_BACKTICKS}mermaid", "").replace(TRIPLE_BACKTICKS, "").strip()
            mermaid_code = sanitize_mermaid_code(raw_code)
            line_count = len(mermaid_code.strip().split('\n'))
            dyn_height = min(720, max(260, line_count * 42 + 110))
            container_id = f"mermaid_box_{diagram_count}_{int(time.time()*100)%10000}"
            
            is_micro = "flowchart lr" in mermaid_code.lower() or "graph lr" in mermaid_code.lower() or line_count <= 6
            card_title = "🎯 Conclusion Micro-Flowchart (Quick Exam Recall)" if is_micro else "🌾 Question-Specific Technical Process Architecture"
            
            html_code = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{
                        margin: 0; padding: 4px; background: transparent;
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    }}
                    .outer-container {{
                        background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
                        border: 1px solid #cbd5e1; border-radius: 10px;
                        padding: 14px; box-shadow: 0 3px 6px rgba(0,0,0,0.04); max-width: 820px; margin: 0 auto;
                    }}
                    .toolbar {{
                        display: flex; justify-content: space-between; align-items: center;
                        margin-bottom: 10px; padding-bottom: 6px; border-bottom: 1px solid #e2e8f0;
                    }}
                    .title-tag {{ font-size: 12px; font-weight: 700; color: #166534; text-transform: uppercase; }}
                    .action-btn {{
                        background: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0;
                        padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 600; cursor: pointer;
                    }}
                    .action-btn:hover {{ background: #dcfce7; }}
                    .diagram-viewport {{
                        display: flex; justify-content: center; align-items: center;
                        background: #ffffff; border: 1px dashed #cbd5e1; border-radius: 8px; padding: 14px; overflow-x: auto;
                    }}
                    .mermaid svg {{ max-width: 100% !important; height: auto !important; }}
                    .error-fallback {{ color: #b91c1c; font-size: 12px; font-family: monospace; white-space: pre-wrap; }}
                </style>
            </head>
            <body>
                <div class="outer-container" id="{container_id}">
                    <div class="toolbar">
                        <span class="title-tag">{card_title}</span>
                        <button class="action-btn" onclick="openDiagramWindow()">🔍 Open in New Tab</button>
                    </div>
                    <div class="diagram-viewport">
                        <pre class="mermaid" id="diag_{container_id}">
{mermaid_code}
                        </pre>
                    </div>
                </div>

                <script type="module">
                    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
                    mermaid.initialize({{
                        startOnLoad: false,
                        theme: 'neutral',
                        securityLevel: 'loose',
                        themeVariables: {{
                            fontSize: '12px',
                            fontFamily: '-apple-system, sans-serif',
                            primaryColor: '#e0f2fe',
                            primaryBorderColor: '#0284c7',
                            lineColor: '#16a34a'
                        }},
                        flowchart: {{ useMaxWidth: false, htmlLabels: true, curve: 'basis' }}
                    }});
                    try {{
                        await mermaid.run();
                    }} catch (e) {{
                        const el = document.getElementById('diag_{container_id}');
                        if (el) {{
                            el.innerHTML = '<div class="error-fallback"><b>[Flowchart Process Flow]:</b><br/>' + el.innerText.replace(/-->/g, ' ➔ ').replace(/flowchart (TD|LR)/g, '') + '</div>';
                        }}
                    }}
                </script>

                <script>
                    function openDiagramWindow() {{
                        const svgEl = document.querySelector('#{container_id} .mermaid svg');
                        if (!svgEl) return;
                        const svgData = new XMLSerializer().serializeToString(svgEl);
                        const canvas = document.createElement('canvas');
                        const bbox = svgEl.getBoundingClientRect();
                        canvas.width = Math.max(bbox.width, 600) * 2;
                        canvas.height = Math.max(bbox.height, 320) * 2;
                        const ctx = canvas.getContext('2d');
                        const img = new Image();
                        const svgBlob = new Blob([svgData], {{type: 'image/svg+xml;charset=utf-8'}});
                        const url = URL.createObjectURL(svgBlob);
                        img.onload = function() {{
                            ctx.fillStyle = '#ffffff';
                            ctx.fillRect(0, 0, canvas.width, canvas.height);
                            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                            URL.revokeObjectURL(url);
                            const w = window.open("");
                            w.document.write('<title>Technical Diagram</title><body style="margin:0;display:flex;justify-content:center;background:#f8fafc;"><img src="' + canvas.toDataURL() + '" style="max-width:100%;height:auto;margin:20px;box-shadow:0 4px 12px rgba(0,0,0,0.09);border-radius:8px;"/></body>');
                        }};
                        img.src = url;
                    }}
                </script>
            </body>
            </html>
            """
            components.html(html_code, height=dyn_height, scrolling=True)
            
            # Native Streamlit Image Download
            col_save1, col_save2 = st.columns([1, 3])
            with col_save1:
                png_bytes = fetch_mermaid_png_bytes(mermaid_code)
                if png_bytes:
                    st.download_button(
                        label=f"📸 Save Diagram #{diagram_count} as PNG",
                        data=png_bytes,
                        file_name=f"technical_diagram_{diagram_count}_{int(time.time())}.png",
                        mime="image/png",
                        key=f"native_png_{diagram_count}_{int(time.time()*1000)%10000}"
                    )
                else:
                    st.download_button(
                        label=f"💾 Save Diagram #{diagram_count} (.mmd)",
                        data=mermaid_code,
                        file_name=f"technical_diagram_{diagram_count}.mmd",
                        mime="text/plain",
                        key=f"native_mmd_{diagram_count}_{int(time.time()*1000)%10000}"
                    )
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
        text_priority = ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "llama-3.1-8b-instant"]
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
    extraction_prompt = "Examine this exam paper image. Extract and transcribe ALL individual questions concisely with marks. Output ONLY the cleanly numbered list of questions."
    response = client.chat.completions.create(
        model=vision_model,
        messages=[{"role": "user", "content": [{"type": "text", "text": extraction_prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}],
        temperature=0.1,
        max_tokens=700,
    )
    return response.choices[0].message.content

def generate_loksewa_answer(client, question_text: str, marks: int, text_model: str, retries: int = 2):
    user_prompt = f"""
    Write a high-scoring Nepal Lok Sewa examination model answer for:
    
    QUESTION: {question_text}
    MARKS ALLOTTED: {marks} Marks
    
    DYNAMIC INSTRUCTIONS (ZERO PRE-MADE FILLER DATA):
    1. Tailor the entire answer architecture, headings, and technical depth strictly to this specific question.
    2. Data Snapshot: Do NOT include generic national GDP or general cereal lists unless the question asks for it. Provide ONLY 3 to 4 technical parameters, chemical dosages, threshold metrics, or specific empirical data directly relevant to this exact subject.
    3. Authentic Legal & Institutional Context: Cite the exact parent Acts, Regulations, and public agencies (e.g., MoALD, NARC, DoA, PQPMC, SQCC, DFTQC, Local Governments) governing this topic.
    4. Technical Diagram: Design an authentic process model, life cycle, decision key, or institutional flow strictly matching this topic. Start with `flowchart TD`, use rectangular nodes: A["Stage Title<br/>- Detail 1<br/>- Detail 2"], and do NOT use unescaped brackets or symbols.
    5. Main Analytical Core: Provide sharp, officer-grade technical points with headings, cause-and-effect explanations, and field-level applications in Nepal.
    6. Operational Challenges & Actionable Way Forward: Specific to this topic's reality under Nepal's federal structure.
    7. Rapid Recall Mnemonic: A 1-2 sentence real-world narrative micro-story in English connecting the analytical core.
    8. Strategic Conclusion:
       - Contextual Strategy addressing the question directly.
       - Practical field solution viable in Nepal.
       - Explicit linkage to the official target governing this topic (16th Plan, ADS, Seed Vision, Food Hygiene Act 2081, or SDG-2).
       - End with an EXACTLY 3-4 node horizontal flowchart (`flowchart LR`): `[Topic Strategy] --> [Actionable Solution] --> [Policy Target Attained]`.
    """
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model=text_model,
                messages=[{"role": "system", "content": LOKSEWA_SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
                temperature=0.25,
                max_tokens=3200,
            )
            return response.choices[0].message.content
        except Exception as e:
            if "429" in str(e) and attempt < retries:
                time.sleep(5)
                continue
            raise e

# -------------------------------------------------------------
# SIDEBAR
# -------------------------------------------------------------
groq_api_key = os.getenv("GROQ_API_KEY", "")
if not groq_api_key and "GROQ_API_KEY" in st.secrets:
    groq_api_key = st.secrets["GROQ_API_KEY"]

if not groq_api_key:
    groq_api_key = st.sidebar.text_input("Enter Groq API Key", type="password", help="Get free key from console.groq.com")

saved_count = len(st.session_state["saved_notes"])
st.sidebar.markdown(f"### 📚 Active Session Bank: **{saved_count}** Notes")
st.sidebar.caption("🔒 Session-Only Memory: Data automatically erases when you close this browser tab.")
st.sidebar.markdown("---")
st.sidebar.info(
    "**Dynamic Evaluation Engine:**\n"
    "• Zero Hardcoded / Pre-made Filler Data\n"
    "• Discipline-Specific Technical Models\n"
    "• Syntax-Safe Mermaid Flowcharts\n"
    "• Question-Linked Policy Targets\n"
    "• Diagrams-Only Visual Revision PDF"
)

# -------------------------------------------------------------
# MAIN APP BODY
# -------------------------------------------------------------
st.title("🌾 Lok Sewa Agri Officer Dynamic Coach")
st.caption("Zero-Template Adaptive Engine | Topic-Specific Technical Diagrams | Direct Policy Linkages | Diagrams-Only PDF Booklet")

if not groq_api_key:
    st.warning("👈 Please enter your Groq API Key in the left sidebar to start.")
    st.stop()

client = get_groq_client(groq_api_key)
vision_model, text_model = auto_select_models_silently(client)

tab1, tab2, tab3 = st.tabs([
    "📸 Photo Upload & Batch Answering", 
    "✍️ Single Question Direct Input", 
    f"📚 Revision Bank & Visual PDF ({len(st.session_state['saved_notes'])})"
])

# =============================================================
# TAB 1: PHOTO UPLOAD & BATCH PROCESSING
# =============================================================
with tab1:
    st.subheader("Upload Exam Paper Snapshot")
    uploaded_file = st.file_uploader("Upload Question Paper Snapshot (JPG, PNG)...", type=["jpg", "jpeg", "png"])
    
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
                        st.success(f"✅ Extracted {len(st.session_state['parsed_questions'])} questions!")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

    if "extracted_questions_raw" in st.session_state:
        st.markdown("---")
        question_list = st.session_state.get("parsed_questions", [])
        mode = st.radio("Select Processing Mode:", ["Option A: Answer Single Question", "Option B: Answer ALL Questions & Generate Visual Booklet"], horizontal=True)
        
        if mode == "Option A: Answer Single Question":
            col_q, col_m = st.columns([3, 1])
            with col_q:
                selected_q = st.selectbox("Choose Question:", question_list)
            with col_m:
                q_marks = st.selectbox("Marks:", [5, 10, 15], index=1, key="tab1_single_marks")
                
            if st.button("🚀 Generate Dynamic Answer", type="primary"):
                with st.spinner("Evaluating question domain and generating custom answer..."):
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
                    if st.button("⭐ Save to Active Session", key="save_tab1", use_container_width=True):
                        st.session_state["saved_notes"].append({
                            "question": st.session_state["current_q"],
                            "marks": st.session_state.get("current_marks", 10),
                            "answer": st.session_state["current_ans"],
                            "saved_at": datetime.now().strftime("%H:%M")
                        })
                        st.toast("✅ Added to active session! (Erases upon closing tab)", icon="📚")
                with col_pdf:
                    pdf_data = generate_single_pdf_bytes(st.session_state["current_q"], st.session_state.get("current_marks", 10), st.session_state["current_ans"])
                    st.download_button(label="📥 Full Answer PDF", data=pdf_data, file_name=f"loksewa_answer_{datetime.now().strftime('%H%M%S')}.pdf", mime="application/pdf", use_container_width=True)
                
                render_loksewa_content(st.session_state["current_ans"])

        else:
            bulk_marks = st.selectbox("Assign Default Marks per Question:", [5, 10, 15], index=1, key="tab1_bulk_marks")
            if st.button("🚀 Answer ALL Questions in Photo", type="primary"):
                all_results = []
                prog_bar = st.progress(0)
                status_text = st.empty()
                total_count = len(question_list)
                
                for idx, q_text in enumerate(question_list):
                    status_text.write(f"✍️ **Drafting Question {idx+1}/{total_count}:** {q_text}")
                    try:
                        ans_text = generate_loksewa_answer(client, q_text, bulk_marks, text_model)
                        all_results.append({"question": q_text, "marks": bulk_marks, "answer": ans_text, "saved_at": datetime.now().strftime("%H:%M")})
                    except Exception as e:
                        all_results.append({"question": q_text, "marks": bulk_marks, "answer": f"Error: {str(e)}", "saved_at": datetime.now().strftime("%H:%M")})
                    prog_bar.progress((idx + 1) / total_count)
                    if idx < total_count - 1:
                        time.sleep(2)
                        
                st.session_state["bulk_results"] = all_results
                status_text.success("🎉 All questions generated successfully!")

            if "bulk_results" in st.session_state and st.session_state["bulk_results"]:
                bulk_data = st.session_state["bulk_results"]
                st.markdown("---")
                
                col_b1, col_b2, col_b3 = st.columns([1, 1, 1])
                with col_b1:
                    bulk_pdf_bytes = generate_bulk_pdf_bytes(bulk_data)
                    st.download_button(label=f"📥 Download Full Q&A PDF ({len(bulk_data)})", data=bulk_pdf_bytes, file_name="all_model_answers.pdf", mime="application/pdf", use_container_width=True)
                with col_b2:
                    diag_only_pdf = generate_diagrams_only_pdf_bytes(bulk_data)
                    st.download_button(label=f"🖼️ Download DIAGRAMS-ONLY PDF ({len(bulk_data)})", data=diag_only_pdf, file_name="technical_diagrams_only.pdf", mime="application/pdf", type="primary", use_container_width=True)
                with col_b3:
                    if st.button("⭐ Save ALL to Active Session", use_container_width=True):
                        for b_item in bulk_data:
                            st.session_state["saved_notes"].append(b_item)
                        st.toast(f"✅ Added {len(bulk_data)} items to active session!", icon="📚")
                
                st.markdown("### 📋 View Generated Answers:")
                for b_idx, b_item in enumerate(bulk_data):
                    with st.expander(f"Question #{b_idx+1}: {b_item['question']}"):
                        render_loksewa_content(b_item["answer"])

# =============================================================
# TAB 2: MANUAL SINGLE QUESTION INPUT
# =============================================================
with tab2:
    st.subheader("Type or Paste Exam Question")
    single_q = st.text_area(
        "Question:", 
        placeholder="e.g., Explain the role of Soil Health Cards in correcting soil acidity and nutrient imbalance in Nepal. Suggest field solutions and link them to national targets. [10 marks]",
        height=100
    )
    col1, col2 = st.columns([1, 3])
    with col1:
        s_marks = st.selectbox("Marks Weightage:", [5, 10, 15], index=1, key="tab2_marks")
        
    if st.button("🚀 Generate Dynamic Answer", type="primary", key="btn_single"):
        if not single_q.strip():
            st.warning("Please enter a question.")
        else:
            with st.spinner("Analyzing question domain and crafting custom model answer..."):
                try:
                    ans = generate_loksewa_answer(client, single_q, s_marks, text_model)
                    st.session_state["single_ans"] = ans
                    st.session_state["single_q"] = single_q
                    st.session_state["single_marks"] = s_marks
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    if "single_ans" in st.session_state:
        st.markdown("---")
        col_t, col_save, col_pdf1, col_pdf2 = st.columns([2, 1, 1, 1])
        with col_t:
            st.subheader("📝 Model Answer")
        with col_save:
            if st.button("⭐ Save to Active Session", key="save_tab2", use_container_width=True):
                st.session_state["saved_notes"].append({
                    "question": st.session_state["single_q"],
                    "marks": st.session_state.get("single_marks", 10),
                    "answer": st.session_state["single_ans"],
                    "saved_at": datetime.now().strftime("%H:%M")
                })
                st.toast("✅ Added to session! (Erases upon closing tab)", icon="📚")
        with col_pdf1:
            pdf_data = generate_single_pdf_bytes(st.session_state["single_q"], st.session_state.get("single_marks", 10), st.session_state["single_ans"])
            st.download_button(label="📥 Full Answer PDF", data=pdf_data, file_name="loksewa_model_answer.pdf", mime="application/pdf", use_container_width=True)
        with col_pdf2:
            single_diag_pdf = generate_diagrams_only_pdf_bytes([{"question": st.session_state["single_q"], "answer": st.session_state["single_ans"]}])
            st.download_button(label="🖼️ Diagrams-Only PDF", data=single_diag_pdf, file_name="technical_diagram_cheat_sheet.pdf", mime="application/pdf", type="primary", use_container_width=True)
                
        render_loksewa_content(st.session_state["single_ans"])

# =============================================================
# TAB 3: REVISION BANK & VISUAL DIAGRAMS-ONLY PDF EXPORT
# =============================================================
with tab3:
    st.subheader(f"📚 Active Session Revision Bank ({len(st.session_state['saved_notes'])} Notes)")
    st.caption("🔒 All notes in this bank are kept strictly in RAM and will **automatically erase** as soon as you close or reload this window.")
    notes = st.session_state["saved_notes"]
    
    if not notes:
        st.info("No answers in current session. Generate and click '⭐ Save to Active Session' to collect items here.")
    else:
        col_r1, col_r2, col_r3 = st.columns([1, 1, 1])
        with col_r1:
            all_bank_pdf = generate_bulk_pdf_bytes(notes)
            st.download_button(
                label=f"📥 Download Full Notes PDF ({len(notes)} Q&A)",
                data=all_bank_pdf,
                file_name="complete_session_notes.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        with col_r2:
            all_diags_pdf = generate_diagrams_only_pdf_bytes(notes)
            st.download_button(
                label=f"🖼️ Download DIAGRAMS-ONLY PDF ({len(notes)} Q&A)",
                data=all_diags_pdf,
                file_name="technical_diagrams_revision_booklet.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )
        with col_r3:
            if st.button("🗑️ Erase Active Session Now", use_container_width=True):
                st.session_state["saved_notes"] = []
                st.rerun()

        st.markdown("---")
        
        for idx, item in enumerate(notes):
            serial_no = idx + 1
            with st.expander(f"📌 #{serial_no}. {item['question']} (Added: {item.get('saved_at', 'N/A')})"):
                col_exp_pdf, col_exp_del = st.columns([1, 1])
                with col_exp_pdf:
                    pdf_saved = generate_single_pdf_bytes(item["question"], item.get("marks", 10), item["answer"])
                    st.download_button(
                        label=f"📥 Download Full PDF #{serial_no}",
                        data=pdf_saved,
                        file_name=f"note_{serial_no}.pdf",
                        mime="application/pdf",
                        key=f"pdf_saved_{idx}"
                    )
                with col_exp_del:
                    if st.button(f"🗑️ Remove #{serial_no}", key=f"del_{idx}"):
                        notes.pop(idx)
                        st.rerun()
                        
                render_loksewa_content(item["answer"])
