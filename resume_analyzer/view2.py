import json
import uuid

import io
import requests
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from ccp.settings import DB
from main_app.views import verify_token
import jwt
from ccp.settings import SECRET_KEY
import re

# Add these imports for PDF text extraction
import fitz  # PyMuPDF
import pytesseract
from PIL import Image

# Configure pytesseract path if needed (for Windows)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def extract_text_from_pdf_url(pdf_url):
    """Extract text from a PDF URL using PyMuPDF and OCR if needed"""
    try:
        # Download the PDF from the URL
        response = requests.get(pdf_url)
        if response.status_code != 200:
            return "Failed to download PDF"
        
        pdf_content = response.content
        return extract_text_from_pdf_bytes(pdf_content)
    except Exception as e:
        return f"Error extracting text: {str(e)}"

def extract_text_from_pdf_bytes(pdf_bytes):
    """Extract text from PDF bytes using PyMuPDF and OCR if needed"""
    text = ""
    
    # Open the PDF from bytes
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            
            # First try to extract text directly (for searchable PDFs)
            page_text = page.get_text()
            
            # If no text is found or very little text, use OCR
            if not page_text.strip() or len(page_text.strip()) < 100:
                # Render page to an image at higher resolution for better OCR
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                
                # Use OCR to extract text from the image
                page_text = pytesseract.image_to_string(img)
            
            text += page_text + "\n\n"
    
    return text

@csrf_exempt
def public_resume_score(request):
    """Public resume score checker - no login required"""
    return render(request, 'src/html/resume_score.html')


@csrf_exempt
def analyze_resume_direct(request):
    """Handle resume analysis based on S3 URL"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)
    
    try:
        # Get data from request
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            email = data.get('email')
            resume_url = data.get('resume_url')
            resume_filename = data.get('resume_filename')
        else:
            # For backward compatibility
            email = request.POST.get('email')
            resume_url = request.POST.get('resume_url')
            resume_filename = request.POST.get('resume_filename')
        
        if not email or not resume_url:
            return JsonResponse({'status': 'error', 'message': 'Email and resume URL are required'}, status=400)
        
        # Validate email format
        if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
            return JsonResponse({'status': 'error', 'message': 'Invalid email format'}, status=400)
        
        # Extract text from the resume PDF
        extracted_text = extract_text_from_pdf_url(resume_url)
        
        # Generate a unique ID for this analysis
        temp_id = str(uuid.uuid4())
        
        # Use Google Generative AI for analysis
        from main_app.utils import get_resume_report_text_prompts, generate_and_get_resume_report
        
        # Generate the prompt for AI
        input_prompt = get_resume_report_text_prompts(extracted_text)
        
        # Get AI-generated report
        ai_report = generate_and_get_resume_report(input_prompt)
        
        # No need to remove markdown formatting here, we'll convert it to HTML when displaying
        
        # Extract score (assuming AI outputs a score somewhere in the text)
        score_match = re.search(r'(\d{1,3})%', ai_report)
        score = int(score_match.group(1)) if score_match else 65
        
        # Extract key findings and improvement areas
        findings = []
        improvements = []
        
        # Simple parsing logic - can be improved
        sections = ai_report.split('\n\n')
        for section in sections:
            if 'strength' in section.lower() or 'positive' in section.lower():
                points = [p.strip() for p in section.split('\n') if p.strip() and not p.strip().endswith(':')]
                findings.extend(points[:3])  # Take up to 3 points
            elif 'improve' in section.lower() or 'weakness' in section.lower():
                points = [p.strip() for p in section.split('\n') if p.strip() and not p.strip().endswith(':')]
                improvements.extend(points[:3])  # Take up to 3 points
        
        # Clean markdown from findings and improvements for list display
        # We'll convert ** to <strong> and * to <em> for HTML display
        findings = [re.sub(r'\*\*(.*?)\*\*', r'\1', f) for f in findings]
        findings = [re.sub(r'\*([^\*]+)\*', r'\1', f) for f in findings]
        
        improvements = [re.sub(r'\*\*(.*?)\*\*', r'\1', i) for i in improvements]
        improvements = [re.sub(r'\*([^\*]+)\*', r'\1', i) for i in improvements]
        
        # Ensure we have some findings and improvements
        if not findings:
            findings = ['Your resume includes relevant technical skills', 
                       'Education section is well-formatted', 
                       'Work experience is clearly presented']
        
        if not improvements:
            improvements = ['Add more quantifiable achievements',
                           'Include more keywords relevant to your target role',
                           'Improve formatting consistency']
        
        # Create analysis object
        analysis = {
            'score': score,
            'key_findings': findings[:3],  # Limit to 3 findings
            'improvement_areas': improvements[:3],  # Limit to 3 improvements
            'full_report': ai_report  # Store the cleaned AI response
        }
        
        # Store the analysis with the email for later retrieval
        DB.temp_resume_analysis.insert_one({
            'id': temp_id,
            'email': email,
            'resume_url': resume_url,
            'resume_filename': resume_filename,
            'resume_text': extracted_text,  # Store the extracted text
            'analysis': analysis,
            'created_at': datetime.now(),
            'expires_at': datetime.now() + timedelta(days=1)  # Expire after 1 day
        })
        
        # Return success with temp_id and the S3 URL
        return JsonResponse({
            'status': 'success',
            'message': 'Resume analyzed successfully',
            'temp_id': temp_id,
            'resume_url': resume_url
        })
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


def resume_report(request):
    """Display resume analysis report for users"""
    valid = False
    data = {}
    
    if request.COOKIES.get('t'):
        valid, data = verify_token(request.COOKIES['t'])
        
    if not valid:
        return redirect('/')
    
    user_type = data.get('user_type')
    sub = data.get('sub')
    
    email = data.get('email')
    user_data = DB.ccp_users.find_one({'email': email})
    plan_type = user_data.get('plan_type') if user_data else None
    
    # If user is not temp_resume type, redirect to appropriate page
    if user_type != 'STUDENT':
         return redirect('/dashboard')
    
    # Get user data from database
    user_doc = DB.ccp_users.find_one({'sub': sub})
    
    if not user_doc:
        return redirect('/')
    
    # Check if user has a premium plan type that should get resume premium features
    premium_plan_types = ['basic', 'elite', 'perform', 'premium', 'mock']
    has_premium_plan = user_doc.get('plan_type') in premium_plan_types
    
    # Set resume_premium to True if user has resume_premium or a premium plan type
    resume_premium = user_doc.get('resume_premium', False) or has_premium_plan
    
    try:
        # Retrieve the analysis from temp_resume_analysis using sub instead of temp_id
        analysis_data = DB.temp_resume_analysis.find_one({'email': user_doc.get('email')})
        
        if not analysis_data:
            # Fallback to user's resume_analysis if no temp analysis found
            resume_analysis = user_doc.get('resume_analysis', {})
            resume_url = user_doc.get('resume_url', '')
            
            context = {
                'user_type': user_type,
                'sub': sub,
                'score': resume_analysis.get('score', 0),
                'key_findings': resume_analysis.get('key_findings', []),
                'improvement_areas': resume_analysis.get('improvement_areas', []),
                'resume_url': resume_url,
                'resume_premium': resume_premium,
                 'plan_type': plan_type,
                 'email': email,
            }
            
            return render(request, 'src/html/resume_dashboard.html', context)
        
        # Get analysis details from temp_resume_analysis
        analysis = analysis_data.get('analysis', {})
        score = analysis.get('score', 0)
        key_findings = analysis.get('key_findings', [])
        improvement_areas = analysis.get('improvement_areas', [])
        full_report = analysis.get('full_report', '')
        
        # Convert markdown to HTML
        full_report = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', full_report)
        full_report = re.sub(r'\*([^\*]+)\*', r'<em>\1</em>', full_report)
        full_report = full_report.replace('\n', '<br>')
        
        # Prepare context for the template
        context = {
            'user_type': user_type,
            'sub': sub,
            'resume_url': analysis_data.get('resume_url'),
            'score': score,
            'key_findings': key_findings,
            'improvement_areas': improvement_areas,
            'full_report': full_report,
            'resume_premium': resume_premium,
            'email': analysis_data.get('email'),
            'plan_type': plan_type,
        }
        
        return render(request, 'src/html/resume_dashboard.html', context)
        
    except Exception as e:
        return render(request, 'src/html/error.html', {'message': str(e)})
