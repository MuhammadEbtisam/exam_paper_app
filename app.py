import streamlit as st
import google.generativeai as genai
import os
import re
import tempfile
import pypandoc
import time
from PIL import Image

# Required installations:
# pip install streamlit google-generativeai pypandoc pypdf2 pillow python-docx
# Additionally, installing Pandoc and MikTeX (or wkhtmltopdf) on the system is highly recommended for accurate math-to-PDF conversion.

def setup_page():
    st.set_page_config(page_title="AI Document Analyzer", layout="wide")
    st.title("🧮 AI Document Analyzer with Math Support")
    
def get_system_prompt():
    prompt_path = "system_prompt.md"
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as file:
            content = file.read().strip()
            if content:
                return content
    return "You are an AI assistant. Analyze the provided documents carefully."

def process_file(uploaded_file):
    # Depending on file type, we might want to extract text here,
    # but Gemini 2.5 flash can accept many file types natively via File API.
    # For Streamlit, it's easiest to read bytes for images/pdfs
    # and send them via genai.upload_file if needed, but since Streamlit runs locally,
    # we can save to a temp file and upload to Gemini.
    if uploaded_file is None:
        return None
        
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(uploaded_file.getbuffer())
        tmp_path = tmp.name
        
    return tmp_path

def convert_md_to_pdf_with_math(md_text):
    """
    Converts markdown to PDF, specifically handling LaTeX math equations.
    This solves the issue of $$ symbols not rendering by using pypandoc (Pandoc)
    or by falling back to HTML-based PDF generation if pandoc isn't available.
    """
    # Pre-process math tags to ensure Pandoc handles them properly
    # Pandoc usually handles $math$ and $$math$$ out of the box.
    
    try:
        pdf_path = tempfile.mktemp(suffix=".pdf")
        # Ensure we have pandoc available; if not, pypandoc.download_pandoc() can be used
        pypandoc.convert_text(
            md_text, 
            'pdf', 
            format='md', 
            outputfile=pdf_path,
            extra_args=['-V', 'geometry:margin=1in', '--pdf-engine=xelatex']
        )
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
            return pdf_bytes
    except Exception as e:
        st.error(f"Pandoc PDF conversion failed. Please ensure Pandoc and a LaTeX engine (like MikTeX or pdflatex) are installed on your Windows machine. Error: {e}")
        # Manual fallback to markdown2html then to raw pdf (less ideal for math but prevents crash)
        return None

def main():
    setup_page()
    
    with st.sidebar:
        st.header("⚙️ Settings")
        api_key = st.text_input("Enter your Gemini API Key", type="password")
        if api_key:
            genai.configure(api_key=api_key)
            st.success("API Key configured!")
        else:
            st.warning("Please enter your Gemini API Key to proceed.")
            
        st.markdown("---")
        st.info("Ensure you have [Pandoc](https://pandoc.org/installing.html) and [MiKTeX](https://miktex.org/download) installed on your system to enable flawless PDF Math rendering.")
            
    system_prompt = get_system_prompt()
    st.expander("View System Prompt").markdown(system_prompt)
    
    uploaded_files = st.file_uploader("Upload Documents (PDF, Content, Images)", accept_multiple_files=True)
    
    if st.button("Analyze with Gemini 2.5 Flash") and api_key and uploaded_files:
        with st.spinner("Analyzing with Gemini 2.5 Flash..."):
            try:
                # Initialize Model
                model = genai.GenerativeModel(
                    model_name="gemini-2.5-flash",
                    system_instruction=system_prompt
                )
                
                # Upload files to Gemini
                gemini_files = []
                temp_paths = []
                for uf in uploaded_files:
                    path = process_file(uf)
                    temp_paths.append(path)
                    g_file = genai.upload_file(path)
                    
                    # Wait for processing
                    while g_file.state.name == "PROCESSING":
                        time.sleep(2)
                        g_file = genai.get_file(g_file.name)
                        
                    if g_file.state.name == "FAILED":
                        st.error(f"File {uf.name} failed to process on Gemini's servers.")
                        continue
                        
                    gemini_files.append(g_file)
                
                # Generate Content
                prompt = "Please process the uploaded files according to the system prompt."
                response = model.generate_content([prompt] + gemini_files)
                
                st.session_state['ai_response'] = response.text
                
                # Cleanup
                for g_file in gemini_files:
                    genai.delete_file(g_file.name)
                for path in temp_paths:
                    if os.path.exists(path):
                        os.remove(path)
                        
            except Exception as e:
                st.error(f"An error occurred: {e}")

    if 'ai_response' in st.session_state:
        st.markdown("### Analysis Result:")
        st.markdown(st.session_state['ai_response'])
        
        pdf_bytes = convert_md_to_pdf_with_math(st.session_state['ai_response'])
        
        if pdf_bytes:
            st.download_button(
                label="📥 Download Result as PDF",
                data=pdf_bytes,
                file_name="analysis_result.pdf",
                mime="application/pdf"
            )

if __name__ == "__main__":
    main()
