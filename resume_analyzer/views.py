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

# New view to manage job descriptions
def manage_job_descriptions(request):
    if request.method == 'POST':
        job_title = request.POST.get('job_title')
        job_description = request.POST.get('job_description')
        edit_id = request.POST.get('edit_id')
        
        if edit_id:  # Editing existing job description
            try:
                object_id = ObjectId(edit_id)
                result = db.job_descriptions.update_one(
                    {'_id': object_id},
                    {'$set': {
                        'title': job_title,
                        'content': job_description,
                        'updated_at': datetime.datetime.now()
                    }}
                )
                
                if result.modified_count > 0:
                    messages.success(request, f"Job description '{job_title}' updated successfully.")
                else:
                    messages.error(request, "Job description not found.")
            except Exception as e:
                messages.error(request, f"Error updating job description: {str(e)}")
        else:  # Adding new job description
            try:
                jd_id = db.job_descriptions.insert_one({
                    'title': job_title,
                    'content': job_description,
                    'created_at': datetime.datetime.now()
                }).inserted_id
                messages.success(request, f"Job description '{job_title}' saved successfully.")
            except Exception as e:
                messages.error(request, f"Error saving job description: {str(e)}")
        
        return redirect('manage_job_descriptions')
    
    # Get all job descriptions from MongoDB
    job_descriptions = list(db.job_descriptions.find().sort('created_at', -1))
    
    # Convert MongoDB _id to string and add as id attribute
    for jd in job_descriptions:
        jd['id'] = str(jd['_id'])
    
    # Get all analysis results sorted by similarity score in descending order
    analysis_results = list(db.analysis_results.find().sort('similarity_score', -1))
    
    # Fetch related resume and job description data for each result
    applicants = []
    for result in analysis_results:
        try:
            resume = db.resumes.find_one({'_id': ObjectId(result['resume_id'])})
            job_desc = db.job_descriptions.find_one({'_id': ObjectId(result['job_description_id'])})
            
            if resume and job_desc:
                applicants.append({
                    'id': str(result['_id']),
                    'filename': resume['filename'],
                    'job_title': job_desc['title'],
                    'similarity_score': result['similarity_score'],
                    'extracted_skills': result['extracted_skills'],
                    'created_at': result['created_at']
                })
        except Exception as e:
            print(f"Error processing result: {str(e)}")
            continue
    
    return render(request, 'resume_analyzer/manage_job_descriptions.html', {
        'job_descriptions': job_descriptions,
        'applicants': applicants
    })

# New view to delete a job description
def delete_job_description(request, jd_id):
    try:
        object_id = ObjectId(jd_id)
        result = db.job_descriptions.delete_one({'_id': object_id})
        
        if result.deleted_count > 0:
            messages.success(request, "Job description deleted successfully.")
        else:
            messages.error(request, "Job description not found.")
    except Exception as e:
        messages.error(request, f"Error deleting job description: {str(e)}")
    
    return redirect('manage_job_descriptions')

# Modified upload_resume view
def upload_resume(request):
    # Get all job descriptions for selection
    job_descriptions = list(db.job_descriptions.find().sort('created_at', -1))
    
    # Convert MongoDB _id to string and add as id attribute
    for jd in job_descriptions:
        jd['id'] = str(jd['_id'])
    
    if len(job_descriptions) == 0:
        messages.warning(request, "No job descriptions available. Please add a job description first.")
        return redirect('manage_job_descriptions')
    
    if request.method == 'POST':
        if 'resume_file' not in request.FILES:
            messages.error(request, "Please select a resume file.")
            return render(request, 'resume_analyzer/upload_resume.html', {
                'job_descriptions': job_descriptions
            })
            
        resume_file = request.FILES['resume_file']
        selected_jd_id = request.POST.get('job_description')
        
        if not selected_jd_id:
            messages.error(request, "Please select a job description.")
            return render(request, 'resume_analyzer/upload_resume.html', {
                'job_descriptions': job_descriptions
            })
        
        try:
            # Get the selected job description
            jd_object_id = ObjectId(selected_jd_id)
            job_description = db.job_descriptions.find_one({'_id': jd_object_id})
            
            if not job_description:
                messages.error(request, "Selected job description not found.")
                return render(request, 'resume_analyzer/upload_resume.html', {
                    'job_descriptions': job_descriptions
                })
            
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
            
            # Store resume in MongoDB
            resume_id = db.resumes.insert_one({
                'filename': resume_file.name,
                'content': resume_content,
                'job_description_id': selected_jd_id,  # Store reference to selected JD
                'uploaded_at': datetime.datetime.now()
            }).inserted_id
            
            # Analyze using ATS with detailed error tracking
            try:
                print("Starting ATS analysis...")
                ats = ATS()
                
                print("Loading resume...")
                ats.load_resume(resume_content)
                
                print("Loading job description...")
                ats.load_job_description(job_description['content'])
                
                print("Extracting experience...")
                experience = ats.extract_experience()
                
                print("Cleaning experience...")
                ats.clean_experience(experience)
                
                print("Extracting skills...")
                skills = " ".join(ats.extract_skills())
                
                print("Cleaning skills...")
                ats.clean_skills(skills)
                
                print("Computing similarity score...")
                similarity_score = ats.compute_similarity()
                print(f"Analysis complete. Similarity score: {similarity_score}")
                
            except Exception as ats_error:
                print(f"ATS Analysis error: {str(ats_error)}")
                messages.error(request, f"Error during resume analysis: {str(ats_error)}")
                return render(request, 'resume_analyzer/upload_resume.html', {
                    'job_descriptions': job_descriptions
                })
            
            # Store results in MongoDB
            result_id = db.analysis_results.insert_one({
                'resume_id': str(resume_id),
                'job_description_id': selected_jd_id,
                'similarity_score': float(similarity_score.item() * 100),
                'extracted_skills': skills,
                'extracted_experience': experience,
                'created_at': datetime.datetime.now()
            }).inserted_id
            
            return redirect('analysis_result', result_id=str(result_id))
            
        except Exception as e:
            print(f"Resume upload error: {str(e)}")
            messages.error(request, f"Error processing resume: {str(e)}")
            return render(request, 'resume_analyzer/upload_resume.html', {
                'job_descriptions': job_descriptions
            })
    
    return render(request, 'resume_analyzer/upload_resume.html', {
        'job_descriptions': job_descriptions
    })

# Remove the old upload_job_description view as it's no longer needed
# def upload_job_description(request, resume_id):
#     ... (remove this function)

# Keep the analysis_result view as is
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

# Add this new view function
def edit_job_description(request, jd_id):
    try:
        object_id = ObjectId(jd_id)
        
        if request.method == 'POST':
            job_title = request.POST.get('job_title')
            job_description = request.POST.get('job_description')
            
            result = db.job_descriptions.update_one(
                {'_id': object_id},
                {'$set': {
                    'title': job_title,
                    'content': job_description,
                    'updated_at': datetime.datetime.now()
                }}
            )
            
            if result.modified_count > 0:
                messages.success(request, f"Job description '{job_title}' updated successfully.")
            else:
                messages.error(request, "Job description not found or no changes made.")
        else:
            messages.error(request, "Invalid request method.")
    except Exception as e:
        messages.error(request, f"Error updating job description: {str(e)}")
    
    return redirect('manage_job_descriptions')
