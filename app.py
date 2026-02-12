import os
import streamlit as st
from dotenv import load_dotenv
from google import genai
from pdf2image import convert_from_path
import pytesseract
import pdfplumber
import mysql.connector
from mysql.connector import Error

# Load environment variables
load_dotenv()

# Configure Google Gemini AI
# Replace with your actual API key
client = genai.Client(api_key="AIzaSyACvEenYfOmQGULQhlkNLh4e4iNO1hSHd8")

# Function to extract text from PDF
def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        # Try direct text extraction
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text

        if text.strip():
            return text.strip()
    except Exception as e:
        print(f"Direct text extraction failed: {e}")

    # Fallback to OCR for image-based PDFs
    print("Falling back to OCR for image-based PDF.")
    try:
        images = convert_from_path(pdf_path)
        for image in images:
            page_text = pytesseract.image_to_string(image)
            text += page_text + "\n"
    except Exception as e:
        print(f"OCR failed: {e}")

    return text.strip()

# Function to connect to the database
def connect_to_database():
    try:
        connection = mysql.connector.connect(
            host="localhost",  # Replace with your MySQL host
            user="root",       # Replace with your MySQL username
            password="admin123",  # Replace with your MySQL password
            database="resume_analyzer"  # Replace with your database name
        )
        if connection.is_connected():
            print("Connected to MySQL database")
            return connection
    except Error as e:
        print(f"Error while connecting to MySQL: {e}")
        return None

# Function to store analysis results in the database
def store_analysis_in_db(candidate_name, email, skills, education, ats_score, feedback, job_description):
    connection = connect_to_database()
    if connection:
        try:
            cursor = connection.cursor()
            # Updated query to insert data into the database
            query = """
                INSERT INTO analysis_results 
                (candidate_name, email, skills, education, ats_score, feedback, job_description)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            values = (candidate_name, email, skills, education, ats_score, feedback, job_description)
            cursor.execute(query, values)
            connection.commit()
            print("Analysis results stored in the database successfully.")
        except Error as e:
            print(f"Error while storing data: {e}")
        finally:
            cursor.close()
            connection.close()

# Function to get response from Gemini AI
def analyze_resume(resume_text, job_description=None):
    if not resume_text:
        return {"error": "Resume text is required for analysis."}
    
    # Updated base_prompt with strict format instructions
    base_prompt = f"""
    **You MUST follow this format:**
    Name: [Candidate's Full Name]
    Email: [Candidate's Email Address]
    Skill: [Comma-separated technical skills]
    Education: [Degree, Institution]
    ATS Score: [0-100]
    Feedback: [50-word concise feedback] [strengths and weaknesses]

    **Resume Content:**
    {resume_text}

    **Job Description:**
    {job_description if job_description else "N/A"}
    """

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=base_prompt
    )

    # Extract structured data from the response
    analysis = response.text.strip()
    print("AI Response:", analysis)  # Debugging: Print the AI response

    # Split the response into lines
    lines = analysis.split("\n")

    # Initialize all fields with default values
    analysis_data = {
        "candidate_name": "Not found",
        "email": "Not found",
        "skills": "Not found",
        "education": "Not found",
        "ats_score": 0,
        "feedback": "Not found"
    }

    # Parse dynamically for fields (order doesn't matter)
    for line in lines:
        line = line.strip()
        if "Name:" in line:
            analysis_data["candidate_name"] = line.split(":")[1].strip()
        elif "Email:" in line:
            analysis_data["email"] = line.split(":")[1].strip()
        elif "Skill:" in line:
            analysis_data["skills"] = line.split(":")[1].strip()
        elif "Education:" in line:
            analysis_data["education"] = line.split(":")[1].strip()
        elif "ATS Score:" in line:
            try:
                analysis_data["ats_score"] = int(line.split(":")[1].strip().replace('%', ''))
            except (IndexError, ValueError):
                pass
        elif "Feedback:" in line:
            analysis_data["feedback"] = line.split(":")[1].strip()

    # Validate critical fields
    if analysis_data["candidate_name"] == "Not found":
        return {"error": "AI response missing candidate name"}
    if analysis_data["ats_score"] == 0:
        return {"error": "Invalid ATS score in AI response"}

    return analysis_data  # Guaranteed to have all keys

# Function to fetch data from the database
def fetch_data_from_db():
    connection = connect_to_database()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            query = "SELECT * FROM analysis_results"
            cursor.execute(query)
            results = cursor.fetchall()
            return results
        except Error as e:
            print(f"Error while fetching data: {e}")
            return []
        finally:
            cursor.close()
            connection.close()

# Streamlit app

st.set_page_config(page_title="Resume Analyzer", layout="wide")
# Title
st.title("AI Driven Resume Analyzer")
st.write("Analyze your resume and match it with job descriptions using Google Gemini AI.")

# Tabs for navigation
tab1, tab2 = st.tabs(["Resume Analysis", "Dashboard & Analytics"])

# Tab 1: Resume Analysis
with tab1:
    col1, col2, col3 = st.columns(3)  # Added col3 for parsed resume text

    with col1:
        uploaded_file = st.file_uploader("Upload your resume (PDF)", type=["pdf"])
    with col2:
        job_description = st.text_area("Enter Job Description:", placeholder="Paste the job description here...")
    with col3:
        st.subheader("Parsed Resume Text")  # Header for parsed resume text
        if uploaded_file:
            # Save uploaded file locally for processing
            with open("uploaded_resume.pdf", "wb") as f:
                f.write(uploaded_file.getbuffer())
            # Extract text from PDF
            resume_text = extract_text_from_pdf("uploaded_resume.pdf")
            if resume_text:
                st.text_area("Resume Content", resume_text, height=300)  # Display parsed resume text
            else:
                st.warning("Could not extract text from the uploaded PDF.")

    if uploaded_file is not None:
        st.success("Resume uploaded successfully!")
    else:
        st.warning("Please upload a resume in PDF format.")

    st.markdown("<div style= 'padding-top: 10px;'></div>", unsafe_allow_html=True)
    if uploaded_file:
        if st.button("Analyze Resume"):
            with st.spinner("Analyzing resume..."):
                try:
                    # Call the analyze_resume function
                    analysis = analyze_resume(resume_text, job_description)
                    
                    # Check for error key in the analysis result
                    if "error" in analysis:
                        st.error(f"Analysis Error: {analysis['error']}")
                    else:
                        st.success("Analysis complete!")
                        
                        # Display the parsed analysis results
                        st.write(f"**Name:** {analysis['candidate_name']}")
                        st.write(f"**Email:** {analysis['email']}")
                        st.write(f"**Skills:** {analysis['skills']}")
                        st.write(f"**Education:** {analysis['education']}")
                        st.write(f"**ATS Score:** {analysis['ats_score']}")
                        st.write(f"**Feedback:** {analysis['feedback']}")
                        
                        # Store the analysis results in the database
                        store_analysis_in_db(
                            candidate_name=analysis['candidate_name'],
                            email=analysis['email'],
                            skills=analysis['skills'],
                            education=analysis['education'],
                            ats_score=analysis['ats_score'],
                            feedback=analysis['feedback'],
                            job_description=job_description
                        )
                        
                except Exception as e:
                    # Handle any unexpected errors
                    st.error(f"Critical Error: {str(e)}")

# Tab 2: Dashboard & Analytics
with tab2:
    st.header("Dashboard & Analytics")
    st.write("Visualize the performance and insights from the analyzed resumes.")

    # Fetch data from the database
    data = fetch_data_from_db()

    if data:
        # Display data as a table
        st.subheader("Analysis Results Table")
        st.dataframe(data)

        # Bar chart for skill frequency
        st.subheader("Skill Frequency Chart")
        skill_counts = {}
        for row in data:
            for skill in row["skills"].split(","):
                skill = skill.strip()
                skill_counts[skill] = skill_counts.get(skill, 0) + 1
        st.bar_chart(skill_counts)

        # Line chart for ATS scores
        st.subheader("ATS Score Trends")
        ats_scores = [row["ats_score"] for row in data]
        candidates = [row["candidate_name"] for row in data]
        st.line_chart(data={"Candidates": candidates, "ATS Scores": ats_scores})

        # Summary statistics
        st.subheader("Summary Statistics")
        st.write(f"Average ATS Score: {sum(ats_scores) / len(ats_scores):.2f}")
        st.write(f"Highest ATS Score: {max(ats_scores)}")
        st.write(f"Lowest ATS Score: {min(ats_scores)}")
    else:
        st.warning("No data available in the database.")

# Footer
st.markdown("---")
st.markdown("""<p style= 'text-align: center;' >Powered by <b>Streamlit</b> and <b>Google Gemini AI</b> | Developed by <a href="https://www.linkedin.com/in/bharath-kumar-127b502a2/"  target="_blank" style='text-decoration: none; color: #FFFFFF'><b>Bharath Kumar</b></a></p>""", unsafe_allow_html=True)

if __name__ == "__main__":
    connection = connect_to_database()
    if connection:
        print("Database connection successful!")
        connection.close()
