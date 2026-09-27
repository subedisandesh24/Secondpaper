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

# Constant for triple backticks to avoid markdown parsing collisions
TRIPLE_BACKTICKS = chr(96) * 3

# -------------------------------------------------------------
# PAGE CONFIGURATION
# -------------------------------------------------------------
st.set_page_config(
    page_title="Lok Sewa Agri Officer Master Coach",
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
# DYNAMIC UNICODE FONT LOADER & ARTIFACT CLEANER
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
    """Cleans Unicode punctuation, emojis, and symbols so they never turn into '???'."""
    if not raw_text:
        return ""
    text = raw_text
    text = text.replace('—', ' - ').replace('–', ' - ').replace('―', ' - ')
    text = text.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
    text = text.replace('→', ' -> ').replace('←', ' <- ').replace('↑', ' (up) ').replace('↓', ' (down) ')
    text = text.replace('≥', '>=').replace('≤', '<=').replace('≠', '!=').replace('≈', '~')
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[📖🌾📌📝⭐🚀🔍📋📚🎉&bull;•🔄🌳]', '', text)
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
        self.drawString(40, 28, "MoALD / Economic Survey / NARC Baseline Verified Answers")
        self.drawRightString(555, 28, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()

# -------------------------------------------------------------
# PDF BUILDER SUPPORTING BOTH LINEAR & CYCLIC/BRANCHING FLOWS
# -------------------------------------------------------------
def build_pdf_story_for_qa(question: str, marks: int, answer_markdown: str, q_num: int = None):
    styles = getSampleStyleSheet()
    content_width = 515

    q_badge_style = ParagraphStyle(
        f'QBadge_{q_num}', parent=styles['Normal'], fontName=PDF_FONT_BOLD, fontSize=8, leading=11, textColor=colors.HexColor('#0d47a1')
    )
    q_title_style = ParagraphStyle(
        f'QTitle_{q_num}', parent=styles['Normal'], fontName=PDF_FONT_BOLD, fontSize=9.5, leading=13.5, textColor=colors.HexColor('#0f172a')
    )
    h1_style = ParagraphStyle(
        f'H1_{q_num}', parent=styles['Normal'], fontName=PDF_FONT_BOLD, fontSize=9, leading=12.5, textColor=colors.HexColor('#1b5e20'), spaceBefore=7, spaceAfter=3
    )
    body_style = ParagraphStyle(
        f'Body_{q_num}', parent=styles['Normal'], fontName=PDF_FONT, fontSize=8.2, leading=12, textColor=colors.HexColor('#1f2937'), spaceAfter=3
    )
    bullet_style = ParagraphStyle(
        f'Bullet_{q_num}', parent=styles['Normal'], fontName=PDF_FONT, fontSize=8.2, leading=12, leftIndent=12, spaceAfter=2.5
    )
    story_text_style = ParagraphStyle(
        f'StoryTxt_{q_num}', parent=styles['Normal'], fontName=PDF_FONT, fontSize=8.2, leading=12.5, textColor=colors.HexColor('#78350f')
    )
    diag_row_style = ParagraphStyle(
        f'DiagRow_{q_num}', parent=styles['Normal'], fontName=PDF_FONT, fontSize=7.8, leading=11, textColor=colors.HexColor('#14532d')
    )
    tbl_hdr_style = ParagraphStyle(
        f'TblHdr_{q_num}', parent=styles['Normal'], fontName=PDF_FONT_BOLD, fontSize=7.8, leading=10, textColor=colors.white, alignment=1
    )
    tbl_cell_style = ParagraphStyle(
        f'TblCell_{q_num}', parent=styles['Normal'], fontName=PDF_FONT, fontSize=7.8, leading=10, textColor=colors.HexColor('#1f2937')
    )

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
        ('TOPPADDING', (0, 0), (-1, 0), 5),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
        ('TOPPADDING', (0, 1), (-1, 1), 2),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
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
            
            # Detect model architecture: Cyclic, Hierarchical/Branching, or Linear
            mermaid_raw_str = " ".join(mermaid_lines).lower()
            is_cyclic = any(kw in mermaid_raw_str for kw in ["cycle", "feedback", "recycle", "loop", "re-circulate"])
            diag_label = "CYCLIC / CLOSED-LOOP MECHANISM" if is_cyclic else "SYSTEM PROCESS FLOW & ARCHITECTURE"

            diag_elements = [
                Paragraph(f"<b>DIAGRAMMATIC MODEL: {diag_label}</b>", ParagraphStyle('DTitle', fontName=PDF_FONT_BOLD, fontSize=8.5, textColor=colors.HexColor('#166534'), spaceAfter=4))
            ]
            
            flow_connections = []
            for m_line in mermaid_lines:
                clean_l = m_line.replace("[", "").replace("]", "").replace('"', '').replace('<br/>', ' ').strip()
                if not clean_l or clean_l.lower().startswith(('graph', 'flowchart', 'subgraph', 'end', '%%')):
                    continue
                if "-->" in clean_l or "---" in clean_l or "-.->" in clean_l:
                    parts = re.split(r'--+>|-+\.->|---+', clean_l)
                    if len(parts) >= 2:
                        src = parts[0].strip()
                        dest = parts[1].strip()
                        flow_connections.append(f"&bull; <b>{src}</b> &rarr; {dest}")
                else:
                    flow_connections.append(f"&bull; {clean_l}")

            for conn in flow_connections[:10]:
                diag_elements.append(Paragraph(clean_pdf_text(conn), diag_row_style))

            diag_card = Table([[diag_elements]], colWidths=[content_width])
            diag_card.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0fdf4')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#bbf7d0')),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(Spacer(1, 3))
            story.append(diag_card)
            story.append(Spacer(1, 5))
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
                story.append(Spacer(1, 5))
            table_rows = []
            in_table = False

        if "memory story" in line.lower() or "mnemonic" in line.lower() or "rapid recall" in line.lower():
            story_box_data = [
                [Paragraph("<b>RAPID RECALL MEMORY STORY:</b>", ParagraphStyle('StryHdr', fontName=PDF_FONT_BOLD, fontSize=8.2, textColor=colors.HexColor('#92400e')))],
                [Paragraph(clean_pdf_text(line), story_text_style)]
            ]
            story_card = Table(story_box_data, colWidths=[content_width])
            story_card.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fffbeb')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#fde68a')),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(Spacer(1, 3))
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

def generate_single_pdf_bytes(question: str, marks: int, answer_markdown: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=48, bottomMargin=48)
    story = build_pdf_story_for_qa(question, marks, answer_markdown)
    doc.build(story, canvasmaker=CleanNumberedCanvas)
    return buffer.getvalue()

def generate_bulk_pdf_bytes(qa_list: list) -> bytes:
    """Generates bulk PDF containing strictly Question and Answers only."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=48, bottomMargin=48)
    story = []

    for idx, item in enumerate(qa_list):
        q_story = build_pdf_story_for_qa(
            item["question"],
            item.get("marks", 10),
            item["answer"],
            q_num=idx + 1
        )
        story.extend(q_story)
        if idx < len(qa_list) - 1:
            story.append(Spacer(1, 12))
            story.append(PageBreak())

    doc.build(story, canvasmaker=CleanNumberedCanvas)
    return buffer.getvalue()

# -------------------------------------------------------------
# LOK SEWA SYSTEM PROMPT - RIGOROUS NEPAL GOVT OFFICIAL BASELINE
# -------------------------------------------------------------
LOKSEWA_SYSTEM_PROMPT = (
    "You are an elite Nepal Lok Sewa Aayog Senior Examiner and Answer-Writing Mentor for the Nepal Agricultural Service "
    "(Gazetted 3rd Class / रा.प. तृतीय श्रेणी: Agri Extension, Horticulture, Agronomy, Plant Protection, Soil Science).\n\n"
    "CRITICAL MANDATE: Provide FEWER, PUNCHY, HIGH-IMPACT, ACCURATE points tailored to an intense 13-14 minute writing timeframe.\n\n"
    "VERIFIED GOVERNMENT OF NEPAL OFFICIAL DATA BASELINE (Economic Survey 2080/81 & 2081/82, MoALD Statistical Report, PQPMC, SQCC, 16th Plan):\n"
    "1. Macroeconomic Accounts (Ministry of Finance - MoF & National Statistics Office - NSO):\n"
    "   * Agriculture, Forestry & Fisheries share in GDP: 24.1% - 25.16% at current prices.\n"
    "   * Agriculture sector real growth rate: 3.05% - 3.28% (Constant prices).\n"
    "   * National GDP Size: Rs. 57.05 Kharba (FY 2080/81 revised) / Rs. 61.07 - 61.7 Kharba (FY 2081/82).\n"
    "   * Per Capita Gross National Income (GNI): USD 1,456 (2080/81) to USD 1,517 (2081/82).\n"
    "   * National Employment in Agriculture: ~62.4% (Population Census 2021) / 66.7% (National Agriculture Census 2021/22).\n"
    "2. MoALD / Krishi Diary Production & Yield Statistics:\n"
    "   * Paddy (Rice): National harvest achieved a historic record of 5.724 Million MT (57.24 Lakh MT in FY 2080/81) across 1.438 Million ha; Average productivity 3.98 - 4.14 MT/ha (Koshi Province highest at 4.43 MT/ha; Madhesh at ~3.49-3.86 MT/ha).\n"
    "   * Maize: ~3.15 Million MT (Yield ~3.21 MT/ha across ~980,000 ha).\n"
    "   * Wheat: ~2.18 Million MT (Yield ~3.04 MT/ha across ~716,000 ha).\n"
    "   * Total Cereal Output: ~11.2 - 11.5 Million MT.\n"
    "   * Subsidized Chemical Fertilizer: ~4.25 Lakh MT distributed annually via KSCL & STC.\n"
    "3. PQPMC (Plant Quarantine & Pesticide Management Centre) Official Gazette Records:\n"
    "   * Exactly 27 active pesticide ingredients are currently BANNED in Nepal.\n"
    "   * December 2024 Gazette Notification added: Paraquat dichloride, Chlorpyrifos, and Phorate to the banned list.\n"
    "   * Average pesticide consumption: ~396 gm active ingredient (a.i.)/ha nationally, but exceeds 1.5 - 2.5 kg a.i./ha in commercial vegetable belts (Kavre, Dhading, Chitwan).\n"
    "4. SQCC (Seed Quality Control Centre) & Seed Milestones:\n"
    "   * 700+ registered/notified crop varieties.\n"
    "   * Seed Replacement Rate (SRR): Paddy ~24.5%, Wheat ~22.8%, Maize ~20.2% (Target: 25-33% under National Seed Vision).\n"
    "5. Recent Legislative & Policy Frameworks:\n"
    "   * 16th Periodic Plan (आर्थिक वर्ष २०८१/८२ - २०८५/८६): Theme 'Good Governance, Social Justice and Prosperity'; emphasizes agricultural commercialization corridors, land consolidation (चक्लाबन्दी), and climate-smart value chains.\n"
    "   * Agriculture Investment Decade (कृषि लगानी दशक: २०८१-२०९१ / 2024-2034 AD).\n"
    "   * Food Hygiene and Quality Act, 2081 (खाद्य स्वच्छता तथा गुणस्तर ऐन, २०८१) replacing Food Act 2023.\n"
    "   * Pesticides Management Regulation, 2081 (जीवनाशक विषादी व्यवस्थापन नियमावली, २०८१) under Pesticides Management Act 2076.\n"
    "   * National Agriculture Policy, 2081 (revised federalized execution).\n\n"
    "TECHNICAL SPECIFICITY DIRECTIVE:\n"
    "- NEVER copy-paste generic GDP figures for pure technical agronomy, entomology, plant pathology, or soil science questions.\n"
    "- For technical topics, cite genuine metrics: Economic Threshold Levels (ETL), degree days, chilling hours, TSS/Brix, seed certification tolerances, soil pH/SOM critical limits from NARC, DoA, or PQPMC.\n\n"
    "MERMAID DIAGRAM INSTRUCTIONS - LINEAR, CYCLIC, BRANCHING & SWIMLANES:\n"
    "1. DO NOT RESTRICT TO LINEAR FLOWS. Choose the diagram structure that truly represents the subject matter:\n"
    "   * CYCLIC / CLOSED-LOOP: Use for nutrient cycles (N, P, K), disease/pest life cycles, IPM biological feedback loops, seed multiplication cycles (Breeder->Foundation->Certified->Improved), extension-farmer feedback cycles. Example syntax: A --> B --> C --> D -->|Recycle / Feedback| A.\n"
    "   * BRANCHING / DECISION TREE: Use for IPM spray decisions, diagnostic keys, classification of horticultural crops, federal-provincial-local mandate distribution.\n"
    "   * SWIMLANES / SUBGRAPHS: Group institutional roles: `subgraph NARC ... end`, `subgraph DoA/AKC ... end`, `subgraph Local Government ... end`.\n"
    "   * LINEAR: For sequential processing steps, export quarantine protocols, cold chain transport.\n"
    "2. Orientation: Use `graph TD` for top-down or `graph LR` where wide layout makes sense.\n"
    "3. Keep node text concise (3-5 words) using `<br/>` for line breaks. Wrap ALL node texts in double quotes: A[\"Soil Sampling<br/>(Grid Method)\"].\n\n"
    "STORY-BASED RAPID RECALL MNEMONIC (ENGLISH STORY ONLY):\n"
    "- Provide a memorable 1-2 sentence narrative micro-story strictly in ENGLISH connecting all core analytical points in logical order.\n"
    "- Example: 'Farmer **Hari** first tested his **Soil & Certified Seed** (Inputs), adopted **AKC Extension Advice** (Technical Knowledge), stored his harvest in a **Cold Chain Hub** (Post-Harvest Infrastructure), and secured a direct contract via the **Cooperatives Value Chain** (Market Linkage) to achieve **Double Net Profit** (Economic Outcome).'\n\n"
    "STANDARD ANSWER ARCHITECTURE:\n"
    "1. Concise Introduction (2-3 sentences)\n"
    "2. Current Scenario & Domain-Specific Data Snapshot (Cite MoALD, NARC, PQPMC, SQCC, or Economic Survey)\n"
    "3. Conceptual Diagram (Mermaid code block: Linear, Cyclic, Branching, or Swimlane)\n"
    "4. Policy, Legal & Institutional Linkages (Cite 16th Plan, Food Hygiene Act 2081, Pesticides Reg 2081, etc.)\n"
    "5. Main Analytical Core (5-7 punchy points: Bold Heading -> Cause/Effect -> Practical Implication)\n"
    "6. Key Operational Challenges (4-5 bullet points)\n"
    "7. Actionable Way Forward (Three-tier federal distribution: Federal, Provincial, Local)\n"
    "8. Story-Based Mnemonic for Rapid Recall (English micro-story)\n"
    "9. Strategic Conclusion"
)

# -------------------------------------------------------------
# RESPONSIVE MERMAID RENDERER WITH 1-CLICK PNG/SVG EXPORT
# -------------------------------------------------------------
def render_loksewa_content(content_text: str):
    """Renders markdown text and embeds an interactive Mermaid diagram with PNG/SVG image download tools."""
    mermaid_pattern = rf"({TRIPLE_BACKTICKS}mermaid[\s\S]*?{TRIPLE_BACKTICKS})"
    parts = re.split(mermaid_pattern, content_text)
    
    for idx, part in enumerate(parts):
        if part.startswith(f"{TRIPLE_BACKTICKS}mermaid"):
            mermaid_code = part.replace(f"{TRIPLE_BACKTICKS}mermaid", "").replace(TRIPLE_BACKTICKS, "").strip()
            line_count = len(mermaid_code.strip().split('\n'))
            dyn_height = min(1100, max(360, line_count * 45 + 130))
            container_id = f"mermaid_box_{idx}_{int(time.time()*1000)%10000}"
            
            html_code = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{
                        margin: 0;
                        padding: 6px;
                        background: transparent;
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    }}
                    .outer-container {{
                        background: #ffffff;
                        border: 1px solid #cbd5e1;
                        border-radius: 10px;
                        padding: 14px;
                        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
                        max-width: 850px;
                        margin: 0 auto;
                    }}
                    .toolbar {{
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-bottom: 12px;
                        padding-bottom: 8px;
                        border-bottom: 1px solid #f1f5f9;
                    }}
                    .title-tag {{
                        font-size: 12px;
                        font-weight: 700;
                        color: #166534;
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                    }}
                    .btn-group {{
                        display: flex;
                        gap: 8px;
                    }}
                    .action-btn {{
                        background: #f0fdf4;
                        color: #15803d;
                        border: 1px solid #bbf7d0;
                        padding: 4px 10px;
                        border-radius: 6px;
                        font-size: 11.5px;
                        font-weight: 600;
                        cursor: pointer;
                        display: inline-flex;
                        align-items: center;
                        gap: 4px;
                        transition: all 0.2s ease;
                    }}
                    .action-btn:hover {{
                        background: #dcfce7;
                        border-color: #86efac;
                    }}
                    .diagram-viewport {{
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        background: #f8fafc;
                        border-radius: 8px;
                        padding: 16px;
                        overflow-x: auto;
                    }}
                    .mermaid svg {{
                        max-width: 100% !important;
                        height: auto !important;
                    }}
                </style>
            </head>
            <body>
                <div class="outer-container" id="{container_id}">
                    <div class="toolbar">
                        <span class="title-tag">🌾 Diagrammatic Architecture (Cyclic / Branching / Flow)</span>
                        <div class="btn-group">
                            <button class="action-btn" onclick="saveAsImage('png')">📸 Save as PNG</button>
                            <button class="action-btn" onclick="saveAsImage('svg')">💾 Save as SVG</button>
                        </div>
                    </div>
                    <div class="diagram-viewport">
                        <pre class="mermaid">
{mermaid_code}
                        </pre>
                    </div>
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

                <script>
                    function saveAsImage(format) {{
                        const container = document.getElementById('{container_id}');
                        const svgEl = container.querySelector('.mermaid svg');
                        if (!svgEl) return;
                        
                        const svgData = new XMLSerializer().serializeToString(svgEl);
                        
                        if (format === 'svg') {{
                            const blob = new Blob([svgData], {{type: 'image/svg+xml;charset=utf-8'}});
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = 'loksewa_model_diagram.svg';
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                            URL.revokeObjectURL(url);
                        }} else {{
                            const canvas = document.createElement('canvas');
                            const bbox = svgEl.getBoundingClientRect();
                            const scale = 2;
                            canvas.width = Math.max(bbox.width, 600) * scale;
                            canvas.height = Math.max(bbox.height, 350) * scale;
                            const ctx = canvas.getContext('2d');
                            
                            const img = new Image();
                            const blob = new Blob([svgData], {{type: 'image/svg+xml;charset=utf-8'}});
                            const url = URL.createObjectURL(blob);
                            
                            img.onload = function() {{
                                ctx.fillStyle = '#ffffff';
                                ctx.fillRect(0, 0, canvas.width, canvas.height);
                                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                                URL.revokeObjectURL(url);
                                
                                const pngUrl = canvas.toDataURL('image/png');
                                const a = document.createElement('a');
                                a.href = pngUrl;
                                a.download = 'loksewa_model_diagram.png';
                                document.body.appendChild(a);
                                a.click();
                                document.body.removeChild(a);
                            }};
                            img.src = url;
                        }}
                    }}
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
    Produce an elite, high-scoring Nepal Lok Sewa examination model answer for:
    
    QUESTION: {question_text}
    MARKS ALLOTTED: {marks} Marks
    
    Comply strictly with the verified Government of Nepal baseline and format:
    1. Concise Introduction (2-3 sentences: context, operational scope, importance)
    2. Current Scenario & Sectoral Data Snapshot:
       - Economic Survey 2080/81 & 2081/82: AGDP share (24.1% - 25.16%), Ag growth (3.05%-3.28%), GDP (Rs. 57.05 - 61.07 Kharba), GNI per capita (USD 1,456 - 1,517), Ag labor (62.4%-66.7%).
       - MoALD: Historic paddy output (5.724M MT; yield 3.98-4.14 MT/ha), Maize (3.15M MT), Wheat (2.18M MT), fertilizer distribution (~4.25 Lakh MT).
       - PQPMC Banned Pesticides: Exactly 27 banned (including Dec 2024 additions: Paraquat dichloride, Chlorpyrifos, Phorate); national average ~396 gm a.i./ha vs commercial pockets (1.5-2.5 kg/ha).
       - SQCC: 700+ varieties, SRR (Paddy 24.5%, Wheat 22.8%, Maize 20.2%).
       - If question is technical agronomy/protection/soil/horticulture, provide exact technical thresholds (ETLs, temperature/moisture requirements, critical soil nutrient levels).
    3. Mermaid Diagram (NOT limited to linear graphs):
       - If cyclic/closed-loop (nutrient cycles, pathogen cycle, seed multiplication, feedback loops), use cyclic syntax: A --> B --> C -->|Recycle/Feedback| A.
       - If decision hierarchy/classification, use branching trees or subgraphs.
       - Wrap labels in double quotes. Do NOT output meta comments like '(only 4 steps)'.
    4. Policy, Legal & Institutional Linkage (Explicitly cite 16th Periodic Plan 2081/82-2085/86, Food Hygiene and Quality Act 2081, Agriculture Investment Decade 2081-2091, Pesticide Regulation 2081, or National Agriculture Policy 2081).
    5. Main Analytical Core (5-7 punchy points: Bold Heading -> Cause/Effect -> Practical Implication)
    6. Key Operational Challenges (4-5 points)
    7. Actionable Way Forward (Federal, Provincial, and Local Government mandates)
    8. Story-Based Mnemonic for Rapid Recall (1-2 sentence real-world narrative micro-story in ENGLISH connecting analytical points)
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
# SIDEBAR
# -------------------------------------------------------------
groq_api_key = os.getenv("GROQ_API_KEY", "")
if not groq_api_key and "GROQ_API_KEY" in st.secrets:
    groq_api_key = st.secrets["GROQ_API_KEY"]

if not groq_api_key:
    groq_api_key = st.sidebar.text_input("Enter Groq API Key", type="password", help="Get free key from console.groq.com")

saved_count = len(st.session_state["saved_notes"])
st.sidebar.markdown(f"### 📚 Saved Notes: **{saved_count}**")
st.sidebar.markdown("---")
st.sidebar.info(
    "**Govt of Nepal Verified Publications:**\n"
    "- MoF Economic Survey 2080/81 & 2081/82\n"
    "- MoALD Krishi Diary & Stat Report\n"
    "- PQPMC 27 Banned Pesticides (Dec 2024)\n"
    "- 16th Periodic Plan (2081/82-2085/86)\n"
    "- Food Hygiene & Quality Act 2081"
)

# -------------------------------------------------------------
# MAIN APP BODY
# -------------------------------------------------------------
st.title("🌾 Lok Sewa Agri Officer Master Coach")
st.caption("Official Publications Baseline | Multi-Type Diagrams (Cyclic/Branching/Linear) | 1-Click Diagram Export | Collective PDF Engine")

if not groq_api_key:
    st.warning("👈 Please enter your Groq API Key in the left sidebar to start.")
    st.stop()

client = get_groq_client(groq_api_key)
vision_model, text_model = auto_select_models_silently(client)

tab1, tab2, tab3 = st.tabs([
    "📸 Photo Upload & Batch Answering", 
    "✍️ Single Question Direct Input", 
    f"📚 Revision Bank & Bulk PDF Export ({len(st.session_state['saved_notes'])})"
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
            st.image(image, caption="Uploaded Question Paper", use_container_width=True)
            
        with col_act:
            if st.button("🔍 Extract Questions from Photo", type="primary", use_container_width=True):
                with st.spinner("Extracting questions via Vision AI..."):
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
        
        mode = st.radio(
            "Select Processing Mode:",
            ["Option A: Answer Questions Individually", "Option B: Answer ALL Questions & Download Collective PDF"],
            horizontal=True
        )
        
        if mode == "Option A: Answer Questions Individually":
            col_q, col_m = st.columns([3, 1])
            with col_q:
                selected_q = st.selectbox("Choose Question:", question_list)
            with col_m:
                q_marks = st.selectbox("Marks:", [5, 10, 15], index=1, key="tab1_single_marks")
                
            if st.button("🚀 Generate Answer for Selected Question", type="primary"):
                with st.spinner("Preparing answer with official data, cyclic/branching diagrams, and memory stories..."):
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
                    if st.button("⭐ Save to Revision Bank", key="save_tab1", use_container_width=True):
                        new_item = {
                            "question": st.session_state["current_q"],
                            "marks": st.session_state.get("current_marks", 10),
                            "answer": st.session_state["current_ans"],
                            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                        }
                        st.session_state["saved_notes"].append(new_item)
                        save_notes_to_disk(st.session_state["saved_notes"])
                        st.toast("✅ Saved in order to Revision Bank!", icon="📚")
                with col_pdf:
                    pdf_data = generate_single_pdf_bytes(
                        st.session_state["current_q"],
                        st.session_state.get("current_marks", 10),
                        st.session_state["current_ans"]
                    )
                    st.download_button(
                        label="📥 Download Answer PDF",
                        data=pdf_data,
                        file_name=f"loksewa_answer_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                
                render_loksewa_content(st.session_state["current_ans"])

        else:
            bulk_marks = st.selectbox("Assign Default Marks per Question:", [5, 10, 15], index=1, key="tab1_bulk_marks")
            
            if st.button("🚀 Answer ALL Questions in Photo & Prepare Collective PDF", type="primary"):
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
                status_text.success("🎉 All questions generated successfully!")

            if "bulk_results" in st.session_state and st.session_state["bulk_results"]:
                bulk_data = st.session_state["bulk_results"]
                st.markdown("---")
                
                col_b1, col_b2 = st.columns([1, 1])
                with col_b1:
                    bulk_pdf_bytes = generate_bulk_pdf_bytes(bulk_data)
                    st.download_button(
                        label=f"📥 Download ALL {len(bulk_data)} Answers as Collective PDF",
                        data=bulk_pdf_bytes,
                        file_name=f"collective_exam_answers_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )
                with col_b2:
                    if st.button("⭐ Save ALL to Revision Bank", use_container_width=True):
                        for b_item in bulk_data:
                            st.session_state["saved_notes"].append(b_item)
                        save_notes_to_disk(st.session_state["saved_notes"])
                        st.toast(f"✅ Saved all {len(bulk_data)} answers to Revision Bank!", icon="📚")
                
                st.markdown("### 📋 View Answers Individually:")
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
        placeholder="e.g., Explain the seed multiplication and certification system in Nepal. Analyze the role of SQCC, and illustrate the cycle from Breeder Seed to Certified Seed under federal governance. [10 marks]",
        height=100
    )
    col1, col2 = st.columns([1, 3])
    with col1:
        s_marks = st.selectbox("Marks Weightage:", [5, 10, 15], index=1, key="tab2_marks")
        
    if st.button("🚀 Generate Answer", type="primary", key="btn_single"):
        if not single_q.strip():
            st.warning("Please type a question.")
        else:
            with st.spinner("Preparing answer with official data, cyclic/branching diagrams, and memory stories..."):
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
            if st.button("⭐ Save to Revision Bank", key="save_tab2", use_container_width=True):
                new_item = {
                    "question": st.session_state["single_q"],
                    "marks": st.session_state.get("single_marks", 10),
                    "answer": st.session_state["single_ans"],
                    "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                st.session_state["saved_notes"].append(new_item)
                save_notes_to_disk(st.session_state["saved_notes"])
                st.toast("✅ Saved in order to Revision Bank!", icon="📚")
        with col_pdf:
            pdf_data = generate_single_pdf_bytes(
                st.session_state["single_q"],
                st.session_state.get("single_marks", 10),
                st.session_state["single_ans"]
            )
            st.download_button(
                label="📥 Download Answer PDF",
                data=pdf_data,
                file_name=f"loksewa_answer_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
                
        render_loksewa_content(st.session_state["single_ans"])

# =============================================================
# TAB 3: REVISION BANK & COLLECTIVE BULK PDF DOWNLOAD
# =============================================================
with tab3:
    st.subheader(f"📚 Serial Revision Bank ({len(st.session_state['saved_notes'])} Notes)")
    notes = st.session_state["saved_notes"]
    
    if not notes:
        st.info("No answers saved yet. Click '⭐ Save to Revision Bank' on any question to collect answers here.")
    else:
        col_r1, col_r2 = st.columns([2, 1])
        with col_r1:
            all_bank_pdf = generate_bulk_pdf_bytes(notes)
            st.download_button(
                label=f"📥 Download Entire Revision Bank ({len(notes)} Questions) as Single Collective PDF",
                data=all_bank_pdf,
                file_name=f"collective_revision_notes_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
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
