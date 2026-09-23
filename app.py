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

# Constant for triple backticks to avoid markdown copy truncation
TRIPLE_BACKTICKS = chr(96) * 3

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
    
    # Header
    story.append(Paragraph("PUBLIC SERVICE COMMISSION (LOK SEWA AAYOG) - NEPAL", header_style))
    story.append(Paragraph("Nepal Agricultural Service | Gazetted Third Class (Technical Officer / कृषि अधिकृत)", sub_header))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1b5e20'), spaceBefore=4, spaceAfter=8))
    
    # Question
    clean_q = sanitize_for_pdf(question)
    story.append(Paragraph(f"<b>QUESTION [{marks} Marks]:</b> {clean_q}", q_box))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cccccc'), spaceBefore=2, spaceAfter=6))
    
    lines = answer_markdown.split("\n")
    in_mermaid = False
    
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
            
        if f"{TRIPLE_BACKTICKS}mermaid" in line:
            in_mermaid = True
            story.append(Paragraph("<b>[DIAGRAM / GRAPHICAL VISUALIZATION]</b>", h1_style))
            continue
        elif in_mermaid and TRIPLE_BACKTICKS in line:
            in_mermaid = False
            continue
        elif in_mermaid:
            clean_flow = line.replace("-->", " -> ").replace("[", "").replace("]", "")
            story.append(Paragraph(f"&bull; {sanitize_for_pdf(clean_flow)}", bullet_style))
            continue
            
        if line.startswith("#"):
            clean_h = re.sub(r"^#+\s*", "", line)
            story.append(Paragraph(f"<b>{sanitize_for_pdf(clean_h)}</b>", h1_style))
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
# LOK SEWA UPDATED SYSTEM PROMPT (2080/2081 REVISED FRAMEWORKS)
# -------------------------------------------------------------
LOKSEWA_SYSTEM_PROMPT = (
    "You are an elite Nepal Lok Sewa Aayog evaluator and answer-writing mentor for the Nepal Agricultural Service "
    "(Gazetted Third Class / रा.प. तृतीय श्रेणी - Agri Extension, Horticulture, Agronomy, Plant Protection, Soil Science).\n\n"
    "Your mission is to produce high-scoring, concise, examiner-friendly answers tailored for the 3-hour written exam.\n"
    "Provide FEWER, PUNCHY, HIGH-IMPACT, EASY-TO-REMEMBER points suitable for a 13-14 minute writing window.\n\n"
    "MANDATORY UPDATED LEGISLATION & POLICY BASELINE (2080/2081/2082):\n"
    "- National Agriculture Policy, 2081 (राष्ट्रिय कृषि नीति, २०८१): Federalized alignment (Schedules 5-9), commercial ecosystem, climate resilience, and import substitution.\n"
    "- Agriculture Investment Decade 2081-2091 (कृषिमा लगानी दशक, २०८१-२०९१): Public-Private-Cooperative partnership model.\n"
    "- Food Hygiene and Quality Act, 2081 (खाद्य स्वच्छता तथा गुणस्तर ऐन, २०८१): Farm-to-fork quality, SPS compliance, and traceability.\n"
    "- Pesticides Management Act, 2076 & Pesticide Management Regulation, 2081 (विषादी व्यवस्थापन नियमावली, २०८१).\n"
    "- Plant Protection Regulation (First Amendment), 2080.\n"
    "- 16th Periodic Plan (2081/82-2085/86): Production corridors and structural economic transformation.\n"
    "- Constitution of Nepal: Art. 36 (Food Sovereignty), Art. 51(h) (Policies on Agriculture/Land).\n"
    "- ADS (2015-2035) 4 Pillars: Governance, Productivity, Commercialization, Competitiveness.\n\n"
    "AUTHENTIC STATISTICAL DATA:\n"
    "- Economic Survey 2080/81: Agriculture contributes 24.09% to GDP; sector growth rate is 3.05%.\n"
    "- Agri Census 2078 (NSO): 4.13 million holdings; 2.218 million ha cultivated land; 0.55 ha average parcel; 54.5% holdings irrigated (~33% year-round).\n\n"
    "MANDATORY GRAPH OR FLOWCHART INSTRUCTION:\n"
    "In every answer, include AT LEAST ONE graphical visualization using valid Mermaid syntax enclosed in " + TRIPLE_BACKTICKS + "mermaid ... " + TRIPLE_BACKTICKS + ".\n"
    "Depending on the question type, choose either:\n"
    "1. A Data Graph / Chart (e.g. `xychart-beta` bar/line chart or `pie` chart for statistics, land use, or budgets).\n"
    "2. A Process Flowchart (e.g. `graph TD` or `flowchart LR` for value chains, certification, or institutional linkages).\n\n"
    "STRICT ANSWER ARCHITECTURE:\n"
    "1. Concise Introduction (2-3 sentences)\n"
    "2. Current Scenario & Verified Data Snapshot (3-4 bullet points)\n"
    "3. Mandatory Mermaid Diagram / Graph (Flowchart, Bar Chart, or Pie Chart)\n"
    "4. Policy & Constitutional Linkage (National Agri Policy 2081, 16th Plan, Investment Decade 2081-2091, Food Hygiene Act 2081)\n"
    "5. Main Analytical Core (5-7 punchy points: Bold Heading -> Cause/Effect -> Practical Implication)\n"
    "6. Key Operational Challenges (4-5 categorized points)\n"
    "7. Actionable Way Forward (Federal, Provincial, Local roles)\n"
    "8. Mnemonic for Quick Recall (English or Nepali acronym)\n"
    "9. Strategic Conclusion"
)

# -------------------------------------------------------------
# MERMAID RENDERING HELPER (SUPPORTS GRAPHS & FLOWCHARTS)
# -------------------------------------------------------------
def render_loksewa_content(content_text: str):
    mermaid_pattern = rf"({TRIPLE_BACKTICKS}mermaid[\s\S]*?{TRIPLE_BACKTICKS})"
    parts = re.split(mermaid_pattern, content_text)
    for part in parts:
        if part.startswith(f"{TRIPLE_BACKTICKS}mermaid"):
            mermaid_code = part.replace(f"{TRIPLE_BACKTICKS}mermaid", "").replace(TRIPLE_BACKTICKS, "").strip()
            html_code = f"""
            <div class="mermaid" style="display: flex; justify-content: center; background-color: #f8f9fa; padding: 15px; border-radius: 8px; border: 1px solid #e0e0e0;">
                {mermaid_code}
            </div>
            <script type="module">
                import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
                mermaid.initialize({{ startOnLoad: true, theme: 'default', securityLevel: 'loose' }});
            </script>
            """
            components.html(html_code, height=300, scrolling=True)
        else:
            if part.strip():
                st.markdown(part)

# -------------------------------------------------------------
# GROQ API HELPERS
# -------------------------------------------------------------
def get_groq_client(api_key: str):
    if not api_key:
        return None
    return Groq(api_key=api_key)

def auto_detect_models(client):
    try:
        active_ids = [m.id for m in client.models.list().data]
        vision_model = "qwen/qwen3.8-27b" if "qwen/qwen3.8-27b" in active_ids else "qwen/qwen3.6-27b"
        text_model = "llama-3.3-70b-versatile" if "llama-3.3-70b-versatile" in active_ids else "llama-3.1-70b-versatile"
        return vision_model, text_model
    except Exception:
        return "qwen/qwen3.8-27b", "llama-3.3-70b-versatile"

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

def generate_loksewa_answer(client, question_text: str, marks: int, text_model: str):
    user_prompt = f"""
    Write a high-scoring Lok Sewa examination answer for:
    
    QUESTION: {question_text}
    MARKS ALLOTTED: {marks} Marks
    
    Adhere strictly to the required answer format:
    1. Concise Introduction (2-3 sentences)
    2. Current Scenario & Official Data Snapshot (Economic Survey 2080/81 & Census 2078)
    3. Mermaid Diagram or Data Graph (Use ```mermaid ... ``` - either xychart bar/line chart or process flowchart)
    4. Policy & Constitutional Linkage (Include National Agriculture Policy 2081, Investment Decade 2081-2091, Food Hygiene & Quality Act 2081, 16th Plan)
    5. Main Analytical Core (5-7 punchy points: Bold Heading -> Cause/Effect -> Practical Implication)
    6. Key Challenges (4-5 points)
    7. Way Forward (Federal, Provincial, Local roles)
    8. Mnemonic for Quick Recall
    9. Strategic Conclusion
    """
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

# -------------------------------------------------------------
# SIDEBAR
# -------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Lok Sewa Setup")
    groq_api_key = st.text_input(
        "Groq API Key", 
        type="password", 
        value=os.getenv("GROQ_API_KEY", ""),
        help="Free API Key from console.groq.com"
    )
    st.markdown("---")
    st.markdown("### 📜 2080/81 Legal & Policy Updates")
    st.caption(
        "• **राष्ट्रिय कृषि नीति, २०८१**\n"
        "• **कृषिमा लगानी दशक (२०८१-२०९१)**\n"
        "• **खाद्य स्वच्छता तथा गुणस्तर ऐन, २०८१**\n"
        "• **विषादी व्यवस्थापन नियमावली, २०८१**\n"
        "• **१६औँ आवधिक योजना (२०८१/८२-२०८५/८६)**\n"
        "• **Economic Survey 2080/81** (AGDP: 24.09%)"
    )
    st.markdown("---")
    saved_count = len(st.session_state["saved_notes"])
    st.markdown(f"### 📚 Saved Notes: **{saved_count}**")

# -------------------------------------------------------------
# MAIN APP BODY
# -------------------------------------------------------------
st.title("🌾 Lok Sewa Agri Officer Answer Coach")
st.caption("Updated with 2081 Policies | Data Charts & Flowcharts | PDF Export")

if not groq_api_key:
    st.warning("👈 Please enter your Groq API Key in the left sidebar to start.")
    st.stop()

client = get_groq_client(groq_api_key)
vision_model, text_model = auto_detect_models(client)

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
        st.subheader("📋 Select Question to Answer")
        question_list = st.session_state.get("parsed_questions", [])
        
        col_q, col_m = st.columns([3, 1])
        with col_q:
            selected_q = st.selectbox("Choose question:", question_list)
        with col_m:
            q_marks = st.selectbox("Marks:", [5, 10, 15], index=1, key="tab1_marks")
            
        if st.button("🚀 Generate High-Scoring Answer", type="primary"):
            with st.spinner("Preparing answer with 2081 policies and Mermaid visualization..."):
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
                if st.button("⭐ Save to Notes", key="save_tab1", use_container_width=True):
                    new_item = {
                        "question": st.session_state["current_q"],
                        "marks": st.session_state.get("current_marks", 10),
                        "answer": st.session_state["current_ans"],
                        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
                    st.session_state["saved_notes"].insert(0, new_item)
                    save_notes_to_disk(st.session_state["saved_notes"])
                    st.toast("✅ Saved to Revision Bank!", icon="📚")
            with col_pdf:
                pdf_data = generate_pdf_bytes(
                    st.session_state["current_q"],
                    st.session_state.get("current_marks", 10),
                    st.session_state["current_ans"]
                )
                st.download_button(
                    label="📥 Download PDF",
                    data=pdf_data,
                    file_name=f"loksewa_answer_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            
            render_loksewa_content(st.session_state["current_ans"])

# =============================================================
# TAB 2: MANUAL SINGLE QUESTION INPUT
# =============================================================
with tab2:
    st.subheader("Type or Paste Question")
    single_q = st.text_area(
        "Question:", 
        placeholder="e.g., Explain the significance of the National Agriculture Policy, 2081 and Agriculture Investment Decade (2081-2091) in transforming commercial agriculture in Nepal. [10 marks]",
        height=100
    )
    col1, col2 = st.columns([1, 3])
    with col1:
        s_marks = st.selectbox("Marks Weightage:", [5, 10, 15], index=1, key="tab2_marks")
        
    if st.button("🚀 Generate Answer", type="primary", key="btn_single"):
        if not single_q.strip():
            st.warning("Please type a question.")
        else:
            with st.spinner("Preparing answer with latest 2081 acts and charts..."):
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
            if st.button("⭐ Save to Notes", key="save_tab2", use_container_width=True):
                new_item = {
                    "question": st.session_state["single_q"],
                    "marks": st.session_state.get("single_marks", 10),
                    "answer": st.session_state["single_ans"],
                    "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                st.session_state["saved_notes"].insert(0, new_item)
                save_notes_to_disk(st.session_state["saved_notes"])
                st.toast("✅ Saved to Revision Bank!", icon="📚")
        with col_pdf:
            pdf_data = generate_pdf_bytes(
                st.session_state["single_q"],
                st.session_state.get("single_marks", 10),
                st.session_state["single_ans"]
            )
            st.download_button(
                label="📥 Download PDF",
                data=pdf_data,
                file_name=f"loksewa_answer_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
                
        render_loksewa_content(st.session_state["single_ans"])

# =============================================================
# TAB 3: REVISION BANK (SAVED FOR LATER)
# =============================================================
with tab3:
    st.subheader("📚 My Revision Bank (Saved Lok Sewa Answers)")
    notes = st.session_state["saved_notes"]
    
    if not notes:
        st.info("No answers saved yet. Click '⭐ Save to Notes' on any generated answer to keep it here.")
    else:
        for idx, item in enumerate(notes):
            with st.expander(f"📌 {item['question']} (Saved: {item.get('saved_at', 'Recently')})"):
                col_exp_pdf, col_exp_del = st.columns([1, 1])
                with col_exp_pdf:
                    pdf_saved = generate_pdf_bytes(item["question"], item.get("marks", 10), item["answer"])
                    st.download_button(
                        label=f"📥 Download PDF #{idx+1}",
                        data=pdf_saved,
                        file_name=f"saved_note_{idx+1}.pdf",
                        mime="application/pdf",
                        key=f"pdf_saved_{idx}"
                    )
                with col_exp_del:
                    if st.button(f"🗑️ Delete Note #{idx+1}", key=f"del_{idx}"):
                        notes.pop(idx)
                        save_notes_to_disk(notes)
                        st.rerun()
                        
                render_loksewa_content(item["answer"])
