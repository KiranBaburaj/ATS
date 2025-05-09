from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.conf import settings
from simple_ats.ats import ATS
import os
import datetime
from bson.objectid import ObjectId
import fitz  # PyMuPDF
import io
from django.contrib import messages  # Add this import for flash messages

# Access the MongoDB connection from settings
db = settings.DB

def home(request):
    return render(request, 'resume_analyzer/home.html')

def upload_resume(request):
    if request.method == 'POST':
        if 'resume_file' in request.FILES:
            resume_file = request.FILES['resume_file']
            file_extension = os.path.splitext(resume_file.name)[1].lower()
            
            # Read the file content
            file_bytes = resume_file.read()
            
            # Extract text based on file type
            if file_extension == '.pdf':
                # Use PyMuPDF for PDF extraction
                try:
                    # Open the PDF from memory buffer
                    pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
                    
                    # Extract text from all pages
                    resume_content = ""
                    for page_num in range(len(pdf_document)):
                        page = pdf_document[page_num]
                        resume_content += page.get_text()
                    
                    pdf_document.close()
                except Exception as e:
                    # Fallback to simple decoding if PDF extraction fails
                    resume_content = file_bytes.decode('utf-8', errors='ignore')
                    print(f"PDF extraction error: {str(e)}")
            else:
                # For non-PDF files, use simple decoding
                resume_content = file_bytes.decode('utf-8', errors='ignore')
            
            # Store in MongoDB
            resume_id = db.resumes.insert_one({
                'filename': resume_file.name,
                'content': resume_content,
                'uploaded_at': datetime.datetime.now()
            }).inserted_id
            
            return redirect('upload_job_description', resume_id=str(resume_id))
    
    return render(request, 'resume_analyzer/upload_resume.html')

def upload_job_description(request, resume_id):
    if request.method == 'POST':
        job_title = request.POST.get('job_title')
        job_description = request.POST.get('job_description')
        
        # Store in MongoDB
        jd_id = db.job_descriptions.insert_one({
            'title': job_title,
            'content': job_description,
            'created_at': datetime.datetime.now()
        }).inserted_id
        
        try:
            # Convert string ID to ObjectId
            object_id = ObjectId(resume_id)
            # Get resume content from MongoDB
            resume = db.resumes.find_one({'_id': object_id})
            
            if resume is None:
                # Instead of error page, redirect to upload page with message
                messages.error(request, f"Resume not found. Please upload your resume again.")
                return redirect('upload_resume')
                
            resume_content = resume['content']
            
            # Analyze using ATS
            ats = ATS()
            ats.load_resume(resume_content)
            ats.load_job_description(job_description)
            
            experience = ats.extract_experience()
            ats.clean_experience(experience)
            
            skills = " ".join(ats.extract_skills())
            ats.clean_skills(skills)
            
            similarity_score = ats.compute_similarity()
            
            # Store results in MongoDB
            result_id = db.analysis_results.insert_one({
                'resume_id': resume_id,
                'job_description_id': str(jd_id),
                'similarity_score': float(similarity_score.item() * 100),
                'extracted_skills': skills,
                'extracted_experience': experience,
                'created_at': datetime.datetime.now()
            }).inserted_id
            
            return redirect('analysis_result', result_id=str(result_id))
        except Exception as e:
            # Instead of error page, redirect to home with error message
            messages.error(request, f"Error processing resume: {str(e)}")
            return redirect('home')
    
    # For GET requests
    try:
        # Verify the resume exists before showing the form
        object_id = ObjectId(resume_id)
        resume = db.resumes.find_one({'_id': object_id})
        
        if resume is None:
            # Instead of error page, redirect to upload page with message
            messages.error(request, f"Resume not found. Please upload your resume again.")
            return redirect('upload_resume')
            
        return render(request, 'resume_analyzer/upload_job_description.html')
    except Exception as e:
        # Instead of error page, redirect to home with error message
        messages.error(request, f"Error retrieving resume: {str(e)}")
        return redirect('home')

def analysis_result(request, result_id):
    try:
        print(f"Attempting to retrieve result with ID: {result_id}")
        # Convert string ID to ObjectId
        try:
            object_id = ObjectId(result_id)
            print(f"Successfully converted to ObjectId: {object_id}")
        except Exception as e:
            print(f"Failed to convert to ObjectId: {str(e)}")
            messages.error(request, f"Invalid result ID format: {str(e)}")
            return redirect('home')
            
        # Get result from MongoDB
        result = db.analysis_results.find_one({'_id': object_id})
        print(f"Database query result: {result is not None}")
        
        if result is None:
            messages.error(request, f"Analysis result with ID {result_id} not found in database.")
            return redirect('home')
        
        # Convert string IDs to ObjectId
        try:
            resume_id = ObjectId(result['resume_id'])
            jd_id = ObjectId(result['job_description_id'])
            print(f"Successfully converted related IDs")
        except Exception as e:
            print(f"Failed to convert related IDs: {str(e)}")
            messages.error(request, f"Error with related document references: {str(e)}")
            return redirect('home')
        
        # Get related resume and job description
        resume = db.resumes.find_one({'_id': resume_id})
        job_description = db.job_descriptions.find_one({'_id': jd_id})
        print(f"Related documents found - Resume: {resume is not None}, Job Description: {job_description is not None}")
        
        if resume is None or job_description is None:
            messages.error(request, "Could not find related resume or job description.")
            return redirect('home')
        
        context = {
            'result': result,
            'resume': resume,
            'job_description': job_description
        }
        
        return render(request, 'resume_analyzer/analysis_result.html', context)
    except Exception as e:
        print(f"Unexpected error in analysis_result view: {str(e)}")
        messages.error(request, f"Error retrieving analysis result: {str(e)}")
        return redirect('home')