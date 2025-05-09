from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.conf import settings
from simple_ats.ats import ATS
import os
import datetime
from bson.objectid import ObjectId  # Add this import

# Access the MongoDB connection from settings
db = settings.DB

def home(request):
    return render(request, 'resume_analyzer/home.html')

def upload_resume(request):
    if request.method == 'POST':
        if 'resume_file' in request.FILES:
            resume_file = request.FILES['resume_file']
            # Read the file content
            resume_content = resume_file.read().decode('utf-8', errors='ignore')
            
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
                # Handle case when resume is not found
                return render(request, 'resume_analyzer/error.html', {
                    'error_message': f"Resume with ID {resume_id} not found. Please upload your resume again."
                })
                
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
            # Handle invalid ObjectId format or other errors
            return render(request, 'resume_analyzer/error.html', {
                'error_message': f"Error processing resume: {str(e)}"
            })
    
    # Add this return statement for GET requests
    try:
        # Verify the resume exists before showing the form
        object_id = ObjectId(resume_id)
        resume = db.resumes.find_one({'_id': object_id})
        
        if resume is None:
            return render(request, 'resume_analyzer/error.html', {
                'error_message': f"Resume with ID {resume_id} not found. Please upload your resume again."
            })
            
        return render(request, 'resume_analyzer/upload_job_description.html')
    except Exception as e:
        return render(request, 'resume_analyzer/error.html', {
            'error_message': f"Error retrieving resume: {str(e)}"
        })

def analysis_result(request, result_id):
    try:
        # Convert string ID to ObjectId
        object_id = ObjectId(result_id)
        # Get result from MongoDB
        result = db.analysis_results.find_one({'_id': object_id})
        
        if result is None:
            return render(request, 'resume_analyzer/error.html', {
                'error_message': f"Analysis result with ID {result_id} not found."
            })
        
        # Convert string IDs to ObjectId
        resume_id = ObjectId(result['resume_id'])
        jd_id = ObjectId(result['job_description_id'])
        
        # Get related resume and job description
        resume = db.resumes.find_one({'_id': resume_id})
        job_description = db.job_descriptions.find_one({'_id': jd_id})
        
        context = {
            'result': result,
            'resume': resume,
            'job_description': job_description
        }
        
        return render(request, 'resume_analyzer/analysis_result.html', context)
    except Exception as e:
        return render(request, 'resume_analyzer/error.html', {
            'error_message': f"Error retrieving analysis result: {str(e)}"
        })