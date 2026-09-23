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

# ReportLab imports for PDF Generation
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak
from reportlab.lib import colors

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
# CRASH-PROOF PDF TEXT SANITIZER
# -------------------------------------------------------------
def safe_pdf_text(raw_text: str) -> str:
    """Escapes raw XML/HTML characters (<, >, &) to prevent paraparser crashes."""
    if not raw_text:
        return ""
    escaped = html.escape(raw_text)
    escaped = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', escaped)
    escaped = re.sub(r'\*(.*?)\*', r'<i>\1</i>', escaped)
    escaped = escaped.replace("-&gt;", " &rarr; ")
    return escaped.encode("latin-1", "replace").decode("latin-1")

def build_pdf_story_for_qa(question: str, marks: int, answer_markdown: str, q_num: int = None):
    styles = getSampleStyleSheet()
    
    q_box = ParagraphStyle(
        f'QBox_{q_num}', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=colors.HexColor('#0d47a1'), spaceBefore=6, spaceAfter=6
    )
    h1_style = ParagraphStyle(
        f'H1_{q_num}', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9.5, leading=13, textColor=colors.HexColor('#1b5e20'), spaceBefore=7, spaceAfter=3
    )
    body_style = ParagraphStyle(
        f'Body_{q_num}', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, leading=12, textColor=colors.HexColor('#212121'), spaceAfter=3
    )
    bullet_style = ParagraphStyle(
        f'Bullet_{q_num}', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, leading=12, leftIndent=12, spaceAfter=2
    )

    story = []
    prefix = f"QUESTION #{q_num}" if q_num else "QUESTION"
    story.append(Paragraph(f"<b>{prefix} [{marks} Marks]:</b> {safe_pdf_text(question)}", q_box))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cccccc'), spaceBefore=2, spaceAfter=6))
    
    lines = answer_markdown.split("\n")
    in_mermaid = False
    
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
            
        if f"{TRIPLE_BACKTICKS}mermaid" in line:
            in_mermaid = True
            story.append(Paragraph("<b>[PROCESS FLOW / CONCEPTUAL DIAGRAM]</b>", h1_style))
            continue
        elif in_mermaid and TRIPLE_BACKTICKS in line:
            in_mermaid = False
            continue
        elif in_mermaid:
            clean_flow = line.replace("-->", " -> ").replace("[", "").replace("]", "").replace('"', '')
            story.append(Paragraph(f"&bull; {safe_pdf_text(clean_flow)}", bullet_style))
            continue
            
        if line.startswith("#"):
            clean_h = re.sub(r"^#+\s*", "", line)
            story.append(Paragraph(f"<b>{safe_pdf_text(clean_h)}</b>", h1_style))
        elif line.startswith("-") or line.startswith("*") or (len(line) > 2 and line[0].isdigit() and line[1] in [".", ")"]):
            clean_bullet = re.sub(r"^[-*]\s*", "", line)
            story.append(Paragraph(f"&bull; {safe_pdf_text(clean_bullet)}", bullet_style))
        else:
            story.append(Paragraph(safe_pdf_text(line), body_style))
            
    return story

def generate_single_pdf_bytes(question: str, marks: int, answer_markdown: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    header_style = ParagraphStyle('Header', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=12, leading=15, textColor=colors.HexColor('#1b5e20'), alignment=1)
    sub_header = ParagraphStyle('SubHeader', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=11, textColor=colors.HexColor('#555555'), alignment=1)

    story = [
        Paragraph("PUBLIC SERVICE COMMISSION (LOK SEWA AAYOG) - NEPAL", header_style),
        Paragraph("Nepal Agricultural Service | Gazetted Third Class (Technical Officer / कृषि अधिकृत)", sub_header),
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1b5e20'), spaceBefore=4, spaceAfter=8)
    ]
    story.extend(build_pdf_story_for_qa(question, marks, answer_markdown))
    doc.build(story)
    return buffer.getvalue()

def generate_bulk_pdf_bytes(qa_list: list, title: str = "EXAMINATION MODEL ANSWERS") -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    header_style = ParagraphStyle('HeaderBulk', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=13, leading=16, textColor=colors.HexColor('#1b5e20'), alignment=1)
    sub_header = ParagraphStyle('SubHeaderBulk', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, leading=11, textColor=colors.HexColor('#555555'), alignment=1)

    story = [
        Paragraph("PUBLIC SERVICE COMMISSION (LOK SEWA AAYOG) - NEPAL", header_style),
        Paragraph(f"Nepal Agricultural Service | {title}", sub_header),
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1b5e20'), spaceBefore=4, spaceAfter=10)
    ]
    
    for idx, item in enumerate(qa_list):
        q_story = build_pdf_story_for_qa(item["question"], item.get("marks", 10), item["answer"], q_num=idx + 1)
        story.extend(q_story)
        if idx < len(qa_list) - 1:
            story.append(Spacer(1, 15))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e0e0e0'), spaceBefore=10, spaceAfter=15))
            story.append(PageBreak())
            
    doc.build(story)
    return buffer.getvalue()

# -------------------------------------------------------------
# LOK SEWA SYSTEM PROMPT (STORY-BASED MNEMONIC + STRICT MERMAID)
# -------------------------------------------------------------
LOKSEWA_SYSTEM_PROMPT = (
    "You are an elite Nepal Lok Sewa Aayog evaluator and answer-writing mentor for the Nepal Agricultural Service "
    "(Gazetted Third Class / रा.प. तृतीय श्रेणी - Agri Extension, Horticulture, Agronomy, Plant Protection, Soil Science).\n\n"
    "Your mission is to produce high-scoring, concise, examiner-friendly answers tailored for the 3-hour written exam.\n"
    "Provide FEWER, PUNCHY, HIGH-IMPACT, EASY-TO-REMEMBER points suitable for a 13-14 minute writing window.\n\n"
    "MANDATORY OFFICIAL VERIFIED STATISTICAL BASELINE:\n"
    "- Economic Survey & National Statistics Office (NSO) Latest Official Data:\n"
    "  * Agriculture sector contribution to GDP: 25.16% (Industry: 12.83%, Services: 62.01%)\n"
    "  * National Economic Growth Rate (GDP Growth): 4.61%\n"
    "  * National GDP Size: NPR 6.107 Trillion (रु. ६१ खर्ब ७ अर्ब)\n"
    "  * Per Capita GNI: USD 1,517\n"
    "- National Sample Census of Agriculture 2078 (NSO):\n"
    "  * 4.13 million farm holdings (62% of households depend on agriculture)\n"
    "  * Total agricultural land: 2.218 million hectares\n"
    "  * Average holding size: 0.55 ha (heavily fragmented, ~2.8 parcels/holding)\n"
    "  * 54.5% holdings irrigated, but only ~33% have year-round irrigation\n\n"
    "MANDATORY LEGISLATIVE & POLICY ANCHORS (2081/2082):\n"
    "- National Agriculture Policy, 2081 (राष्ट्रिय कृषि नीति, २०८१): Federalized alignment (Schedules 5-9), commercial ecosystem, climate resilience.\n"
    "- Agriculture Investment Decade 2081-2091 (कृषिमा लगानी दशक, २०८१-२०९१): Public-Private-Cooperative partnership.\n"
    "- Food Hygiene and Quality Act, 2081 (खाद्य स्वच्छता तथा गुणस्तर ऐन, २०८१): Farm-to-fork quality, SPS compliance, traceability.\n"
    "- Pesticides Management Act, 2076 & Pesticide Management Regulation, 2081.\n"
    "- Plant Protection Regulation (First Amendment), 2080.\n"
    "- 16th Periodic Plan (2081/82-2085/86): Production corridors and structural economic transformation.\n"
    "- Constitution of Nepal: Art. 36 (Food Sovereignty), Art. 51(h) (Policies on Agriculture/Land).\n"
    "- ADS (2015-2035) 4 Pillars: Governance, Productivity, Commercialization, Competitiveness.\n\n"
    "CRITICAL MERMAID SYNTAX RULES:\n"
    "1. Always wrap node text in double quotes to prevent syntax crashes: e.g., A[\"Farmer (Small)\"] --> B[\"Storage / Processing\"].\n"
    "2. Never use unquoted parentheses `()`, slashes `/`, or ampersands `&` inside `[...]`.\n"
    "3. Keep flowcharts clean, logical, and compact.\n\n"
    "STORY-BASED MNEMONIC REQUIREMENT (कथा स्मरण सूत्र):\n"
    "- DO NOT generate dry acronyms.\n"
    "- Create a vivid, memorable 1-2 sentence micro-story (in Nepali or English) connecting all the core analytical points in chronological order.\n"
    "- Example format:\n"
    "  * 📖 **कथा स्मरण सूत्र (Memory Story):** 'किसान **राम**ले स्वस्थ **माटो र बीउ** (Inputs) छानी, **AKC को प्राविधिक सल्लाह** (Extension) लिएर **शीतभण्डार** (Storage) पुर्याई **बजार मूल्य शृङ्खला** (Value Chain) जोडेपछि **आम्दानी दोब्बर** (Outcome) बनाए।'\n\n"
    "STRICT ANSWER ARCHITECTURE:\n"
    "1. Concise Introduction (2-3 sentences: concept, scope, importance)\n"
    "2. Current Scenario & Verified Data Snapshot (cite 25.16% Agri GDP share, 4.61% GDP growth, Census 2078)\n"
    "3. Mandatory Mermaid Diagram / Graph (wrapped cleanly with quoted node names)\n"
    "4. Policy & Constitutional Linkage (National Agri Policy 2081, Investment Decade 2081-2091, Food Hygiene Act 2081, 16th Plan)\n"
    "5. Main Analytical Core (5-7 punchy points: Bold Heading -> Cause/Effect -> Practical Implication)\n"
    "6. Key Operational Challenges (4-5 points)\n"
    "7. Actionable Way Forward (Federal, Provincial, Local roles)\n"
    "8. Story-Based Mnemonic for Rapid Recall (कथा स्मरण सूत्र - vivid 1-2 sentence real-world story)\n"
    "9. Strategic Conclusion"
)

# -------------------------------------------------------------
# ENHANCED RESPONSIVE MERMAID RENDERING HELPER
# -------------------------------------------------------------
def render_loksewa_content(content_text: str):
    """Renders markdown text with an auto-scaling Mermaid SVG container."""
    mermaid_pattern = rf"({TRIPLE_BACKTICKS}mermaid[\s\S]*?{TRIPLE_BACKTICKS})"
    parts = re.split(mermaid_pattern, content_text)
    
    for part in parts:
        if part.startswith(f"{TRIPLE_BACKTICKS}mermaid"):
            mermaid_code = part.replace(f"{TRIPLE_BACKTICKS}mermaid", "").replace(TRIPLE_BACKTICKS, "").strip()
            
            # Auto-calculate height based on diagram lines
            line_count = len(mermaid_code.strip().split('\n'))
            dyn_height = min(650, max(280, line_count * 45 + 90))
            
            html_code = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{
                        margin: 0;
                        padding: 10px;
                        background: transparent;
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                    }}
                    .mermaid-wrapper {{
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        background-color: #f8fafc;
                        border: 1px solid #e2e8f0;
                        border-radius: 8px;
                        padding: 16px;
                        overflow-x: auto;
                    }}
                    .mermaid {{
                        margin: 0;
                        background: transparent;
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
# SILENT AUTO-DISCOVERY OF MODELS (NO SIDEBAR CLUTTER)
# -------------------------------------------------------------
def get_groq_client(api_key: str):
    if not api_key:
        return None
    return Groq(api_key=api_key)

def auto_select_models_silently(client):
    """Silently determines the best active models without showing any sidebar UI clutter."""
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
    1. Concise Introduction (2-3 sentences)
    2. Current Scenario & Official Data Snapshot (Use Verified Data: Agriculture GDP share 25.16%, GDP Growth 4.61%, Census 2078)
    3. Mermaid Diagram or Data Graph (Use ```mermaid ... ``` - ensure node labels are double-quoted)
    4. Policy & Constitutional Linkage (National Agri Policy 2081, Investment Decade 2081-2091, Food Hygiene Act 2081, 16th Plan)
    5. Main Analytical Core (5-7 punchy points: Bold Heading -> Cause/Effect -> Practical Implication)
    6. Key Challenges (4-5 points)
    7. Way Forward (Federal, Provincial, Local roles)
    8. Story-Based Mnemonic for Rapid Recall (कथा स्मरण सूत्र - vivid 1-2 sentence real-world story connecting core points)
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
st.caption("Official Data: 25.16% AGDP Share | Story Mnemonics | Responsive Mermaid Flowcharts")

if not groq_api_key:
    st.warning("👈 Please enter your Groq API Key in the left sidebar to start.")
    st.stop()

# Initialize client and silently detect models
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
        
        # Option A: Single Watch & Save
        if mode == "Option A: Watch & Answer Single Question":
            col_q, col_m = st.columns([3, 1])
            with col_q:
                selected_q = st.selectbox("Choose question:", question_list)
            with col_m:
                q_marks = st.selectbox("Marks:", [5, 10, 15], index=1, key="tab1_single_marks")
                
            if st.button("🚀 Generate Answer for Selected Question", type="primary"):
                with st.spinner("Preparing answer with story mnemonic and responsive Mermaid diagram..."):
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

        # Option B: Bulk Process
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
                    bulk_pdf_bytes = generate_bulk_pdf_bytes(bulk_data, title="COMPLETE EXAM PAPER MODEL ANSWERS")
                    st.download_button(
                        label=f"📥 Download ALL {len(bulk_data)} Answers as Single PDF",
                        data=bulk_pdf_bytes,
                        file_name=f"complete_exam_set_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
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
        placeholder="e.g., Explain the role of the Agriculture Investment Decade (2081-2091) and National Agriculture Policy, 2081 in enhancing commercial agriculture in Nepal. [10 marks]",
        height=100
    )
    col1, col2 = st.columns([1, 3])
    with col1:
        s_marks = st.selectbox("Marks Weightage:", [5, 10, 15], index=1, key="tab2_marks")
        
    if st.button("🚀 Generate Answer", type="primary", key="btn_single"):
        if not single_q.strip():
            st.warning("Please type a question.")
        else:
            with st.spinner("Preparing answer with story mnemonic and diagrams..."):
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
            all_bank_pdf = generate_bulk_pdf_bytes(notes, title="MY COMPLETE REVISION BANK NOTES")
            st.download_button(
                label=f"📥 Download Entire Revision Bank ({len(notes)} Questions) as Single PDF",
                data=all_bank_pdf,
                file_name=f"complete_revision_bank_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
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
