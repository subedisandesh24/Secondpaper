import streamlit as st
import base64
import os
from groq import Groq
from PIL import Image
import io

# -------------------------------------------------------------
# PAGE CONFIGURATION
# -------------------------------------------------------------
st.set_page_config(
    page_title="Lok Sewa Agri Officer Coach",
    page_icon="🌾",
    layout="wide"
)

# -------------------------------------------------------------
# SYSTEM PROMPT FOR LOK SEWA AGRICULTURE COACH
# -------------------------------------------------------------
LOKSEWA_SYSTEM_PROMPT = """
You are an expert Nepal Lok Sewa Aayog answer-writing coach and strict evaluator for the Nepal Agricultural Service (Gazetted Third Class / रा.प. तृतीय श्रेणी - Agri Extension, Horticulture, Agronomy, Plant Protection, Soil Science).

Your task is to produce a high-scoring, examiner-friendly Lok Sewa examination answer following these strict rules:

1. CORE STRUCTURE (MANDATORY IN EVERY ANSWER):
   - [Question Heading & Marks Allotment]
   - 1. Introduction: 2-4 sentences defining concept, core issue, and direct relevance. No historical filler.
   - 2. Current Scenario / Ground Reality in Nepal: Latest credible facts, figures, statistics (from MoALD, NSO/CBS, Economic Survey, ADS 2015-2035, Periodic Plan).
   - 3. Policy, Legal & Constitutional Framework: Constitution of Nepal (Articles/Schedules), Sectoral Acts, Regulations, Policies, ADS, SDGs.
   - 4. Mandatory Process Diagram / Flowchart: Compulsory ASCII or text-based diagram illustrating the value chain, cycle, or institutional workflow.
   - 5. Main Analytical Body: POINT -> EXPLANATION -> PRACTICAL IMPLICATION / NEPAL CONTEXT.
   - 6. Key Challenges / Institutional Gaps: Categorized (Structural, Technical, Institutional, Governance, Input/Market).
   - 7. Way Forward / Practical Recommendations: Categorized across Federal, Provincial, and Local government levels where relevant.
   - 8. Mnemonic for Quick Recall: A clear mnemonic (using English or Nepali words) summarizing the core points for exam revision.
   - 9. Conclusion: Concise, forward-looking (Policy -> Implementation -> Outcome).

2. MARKS-BASED DEPTH CALIBRATION:
   - 5 Marks: Crisp, concise, ~1.5 pages equivalent, 6-8 core analytical points.
   - 10 Marks: Detailed, ~2.5 to 3 pages equivalent, 12-14 substantive points with deep policy & institutional linkages.
   - 15 Marks: Multi-dimensional, deep federalism lens, detailed institutional responsibility matrix.

3. TONE & PRESENTATION:
   - Examiner-friendly: Short paragraphs, clear bold headings, numbered bullets.
   - Think like a Government Officer (Administrative + Practical + Technical).
   - Never invent inaccurate article numbers or fictitious data; provide qualitative indicators if an exact figure is unverified.
"""

# -------------------------------------------------------------
# HELPER FUNCTIONS
# -------------------------------------------------------------
def get_groq_client(api_key: str):
    if not api_key:
        return None
    return Groq(api_key=api_key)

def get_active_groq_models(client):
    """Dynamically fetches active models from the user's Groq account."""
    try:
        models = client.models.list()
        return [m.id for m in models.data]
    except Exception:
        return []

def encode_image_to_base64(image: Image.Image) -> str:
    buffered = io.BytesIO()
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
    image.save(buffered, format="JPEG", quality=90)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def extract_questions_from_image(client, image: Image.Image, vision_model: str):
    """Uses Groq Vision Model to extract and separate questions from an image."""
    base64_image = encode_image_to_base64(image)
    
    extraction_prompt = """
    Analyze this exam paper image. Extract and transcribe EVERY SINGLE QUESTION clearly and accurately.
    Number each question clearly (e.g., Q1, Q2, Q3...).
    If marks are indicated on the paper (e.g., [5], [10], 5+5=10), mention the marks beside the question.
    
    Output format: Return ONLY the numbered list of all questions found on the paper. Do not add conversational intro or outro.
    """
    
    response = client.chat.completions.create(
        model=vision_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": extraction_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        temperature=0.1,
        max_tokens=2048,
    )
    return response.choices[0].message.content

def generate_loksewa_answer(client, question_text: str, marks: int, text_model: str):
    """Generates a high-scoring Lok Sewa formatted answer."""
    user_prompt = f"""
    Please write an examination answer for the following Lok Sewa Aayog (Nepal Agricultural Service) question:
    
    QUESTION: {question_text}
    MARKS ALLOTTED: {marks} Marks
    
    Strictly adhere to the required answer format:
    1. Introduction
    2. Current Scenario / Ground Reality in Nepal
    3. Policy, Legal & Constitutional Framework
    4. Text-based Flowchart / Diagram (MANDATORY)
    5. Main Analytical Body (Point -> Explanation -> Implication)
    6. Key Challenges / Institutional Gaps
    7. Way Forward / Practical Measures (Federal, Provincial, Local)
    8. Mnemonic for Quick Recall (English / Nepali words)
    9. Conclusion
    """
    
    response = client.chat.completions.create(
        model=text_model,
        messages=[
            {"role": "system", "content": LOKSEWA_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3,
        max_tokens=4096,
    )
    return response.choices[0].message.content

# -------------------------------------------------------------
# SIDEBAR CONFIGURATION
# -------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Groq AI Settings")
    groq_api_key = st.text_input(
        "Enter Groq API Key", 
        type="password", 
        value=os.getenv("GROQ_API_KEY", ""),
        help="Get your key from https://console.groq.com/keys"
    )
    
    # Official replacement vision models on Groq
    default_vision_models = [
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "qwen/qwen3.6-27b"
    ]
    
    # Text reasoning models
    default_text_models = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant"
    ]
    
    st.markdown("---")
    st.subheader("Model Selection")
    
    # Vision model selection with custom fallback
    vision_model = st.selectbox(
        "Vision Model (for Photo OCR)",
        options=default_vision_models,
        index=0,
        help="Llama 4 Scout is Groq's official replacement for Llama 3.2 Vision."
    )
    
    text_model = st.selectbox(
        "Reasoning / Writing Model",
        options=default_text_models,
        index=0
    )
    
    st.markdown("---")
    st.info("💡 **Model Update:** `llama-3.2-11b-vision-preview` was deprecated by Groq. Upgraded to `meta-llama/llama-4-scout-17b-16e-instruct`.")

# -------------------------------------------------------------
# MAIN APP BODY
# -------------------------------------------------------------
st.title("🌾 Lok Sewa Aayog Agriculture Answer Generator")
st.caption("Nepal Agricultural Service | Gazetted Third Class (Technical Officer / कृषि अधिकृत)")

if not groq_api_key:
    st.warning("⚠️ Please provide your Groq API Key in the left sidebar to proceed.")
    st.stop()

client = get_groq_client(groq_api_key)

tab1, tab2 = st.tabs(["📸 Question Paper Photo Upload (Up to 12 Questions)", "✍️ Single Question Manual Input"])

# =============================================================
# TAB 1: PHOTO UPLOAD WITH UP TO 12 QUESTIONS
# =============================================================
with tab1:
    st.subheader("Upload Exam Paper Snapshot")
    st.write("Upload an image containing up to 12 questions. The AI will extract all questions, and you can generate answers individually or in bulk.")
    
    uploaded_file = st.file_uploader("Choose question paper image...", type=["jpg", "jpeg", "png"])
    
    if uploaded_file is not None:
        col_img, col_act = st.columns([1, 1])
        image = Image.open(uploaded_file)
        
        with col_img:
            st.image(image, caption="Uploaded Question Paper", use_container_width=True)
            
        with col_act:
            if st.button("🔍 Extract All Questions from Image", type="primary", use_container_width=True):
                with st.spinner(f"Analyzing image using {vision_model}..."):
                    try:
                        extracted_text = extract_questions_from_image(client, image, vision_model)
                        st.session_state["extracted_questions_raw"] = extracted_text
                        
                        # Parse lines into list
                        lines = [q.strip() for q in extracted_text.split("\n") if q.strip() and (q[0].isdigit() or q.upper().startswith("Q"))]
                        st.session_state["parsed_questions"] = lines if lines else [extracted_text]
                        st.success("✅ Questions extracted successfully!")
                    except Exception as e:
                        st.error(f"Error during extraction: {str(e)}")

    if "extracted_questions_raw" in st.session_state:
        st.markdown("---")
        st.subheader("📋 Extracted Questions")
        st.text_area("Extracted List (You can edit or add missing numbers if needed):", 
                     value=st.session_state["extracted_questions_raw"], 
                     height=200, 
                     key="editable_questions")
        
        question_list = st.session_state.get("parsed_questions", [])
        
        mode = st.radio("Choose answering mode:", ["Answer a Specific Question", "Answer ALL Questions Sequentially"], horizontal=True)
        
        if mode == "Answer a Specific Question":
            selected_q = st.selectbox("Select the question to answer:", question_list)
            q_marks = st.selectbox("Select Marks for this question:", [5, 10, 15], index=1)
            
            if st.button("🚀 Generate Lok Sewa Answer", type="primary"):
                with st.spinner("Drafting high-scoring answer with data, diagrams, and mnemonics..."):
                    try:
                        ans = generate_loksewa_answer(client, selected_q, q_marks, text_model)
                        st.markdown("---")
                        st.markdown(ans)
                        st.download_button("📥 Download Answer as Markdown", data=ans, file_name="loksewa_answer.md", mime="text/markdown")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
                        
        else: # Answer all questions
            bulk_marks = st.selectbox("Assign default marks for each question:", [5, 10, 15], index=1)
            if st.button("🚀 Generate Answers for ALL Extracted Questions", type="primary"):
                all_answers = []
                progress_bar = st.progress(0)
                total_q = len(question_list)
                
                for idx, q_item in enumerate(question_list):
                    st.write(f"✍️ **Generating answer for {idx+1}/{total_q}:** {q_item}")
                    try:
                        ans = generate_loksewa_answer(client, q_item, bulk_marks, text_model)
                        all_answers.append(f"# {q_item}\n\n{ans}\n\n---\n")
                    except Exception as e:
                        all_answers.append(f"# {q_item}\n\nFailed to generate: {str(e)}\n\n---\n")
                    progress_bar.progress((idx + 1) / total_q)
                
                final_combined = "\n\n".join(all_answers)
                st.success("✅ All answers generated!")
                st.markdown(final_combined)
                st.download_button("📥 Download Complete Answer Set", data=final_combined, file_name="all_loksewa_answers.md", mime="text/markdown")

# =============================================================
# TAB 2: MANUAL SINGLE QUESTION INPUT
# =============================================================
with tab2:
    st.subheader("Type or Paste Question")
    single_question = st.text_area("Enter question here (English or Nepali):", 
                                  placeholder="e.g., Explain the importance and seed certification procedures of major cereal crops in Nepal. [10 marks]",
                                  height=120)
    
    col1, col2 = st.columns([1, 2])
    with col1:
        marks = st.selectbox("Marks Weightage:", [5, 10, 15], index=1, key="single_marks")
        
    if st.button("🚀 Generate Answer", type="primary", key="btn_single"):
        if not single_question.strip():
            st.warning("Please enter a question first.")
        else:
            with st.spinner("Formulating structured Lok Sewa answer..."):
                try:
                    answer = generate_loksewa_answer(client, single_question, marks, text_model)
                    st.markdown("---")
                    st.markdown(answer)
                    st.download_button("📥 Download Answer as Markdown", data=answer, file_name="single_loksewa_answer.md", mime="text/markdown")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
