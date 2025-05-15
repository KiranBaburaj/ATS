from django.shortcuts import render
from .utils import get_resume_report_text_prompts, generate_and_get_resume_report

import re  
from .atslogic import ATS 
# Create your views here.
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.conf import settings
#from simple_ats.ats import ATS
import os
import datetime
from bson.objectid import ObjectId
import fitz  # PyMuPDF
import io
from django.contrib import messages
import jwt
import bcrypt
from django.views.decorators.csrf import csrf_exempt
import json
from functools import wraps

# Access the MongoDB connection from settings
db = settings.DB

# JWT Configuration
JWT_SECRET = 'your_jwt_secret_key'  # Store this in settings.py in production
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_DELTA = datetime.timedelta(days=7)




# JWT Authentication Decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        request = args[0]
        token = None
        
        # Get token from cookies or Authorization header
        if 'jwt_token' in request.COOKIES:
            token = request.COOKIES.get('jwt_token')
        elif 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
        
        if not token:
            messages.error(request, "Authentication token is missing!")
            return redirect('login')
        
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = payload['user_id']
            
            # Check if user exists in database
            user = db.users.find_one({'_id': ObjectId(user_id)})
            if not user:
                messages.error(request, "User not found!")
                return redirect('login')
                
            # Add user to request for use in the view
            request.user = user
            
        except jwt.ExpiredSignatureError:
            messages.error(request, "Token has expired. Please log in again.")
            return redirect('login')
        except jwt.InvalidTokenError:
            messages.error(request, "Invalid token. Please log in again.")
            return redirect('login')
            
        return f(*args, **kwargs)
    return decorated

# User Registration View
@csrf_exempt
def signup(request):
    if request.method == 'POST':
        try:
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                email = data.get('email')
                password = data.get('password')
                name = data.get('name')
            else:
                email = request.POST.get('email')
                password = request.POST.get('password')
                name = request.POST.get('name')
            
            # Validate input
            if not email or not password or not name:
                if request.content_type == 'application/json':
                    return JsonResponse({'error': 'Email, password, and name are required'}, status=400)
                messages.error(request, "Email, password, and name are required")
                return render(request, 'resume_analyzer/signup.html')
            
            # Check if user already exists
            existing_user = db.users.find_one({'email': email})
            if existing_user:
                if request.content_type == 'application/json':
                    return JsonResponse({'error': 'User with this email already exists'}, status=400)
                messages.error(request, "User with this email already exists")
                return render(request, 'resume_analyzer/signup.html')
            
            # Hash the password
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            
            # Create new user
            user_id = db.users.insert_one({
                'email': email,
                'password': hashed_password,
                'name': name,
                'created_at': datetime.datetime.now()
            }).inserted_id
            
            if request.content_type == 'application/json':
                return JsonResponse({'message': 'User registered successfully', 'user_id': str(user_id)}, status=201)
            
            messages.success(request, "Registration successful! Please log in.")
            return redirect('login')
            
        except Exception as e:
            if request.content_type == 'application/json':
                return JsonResponse({'error': str(e)}, status=500)
            messages.error(request, f"Registration error: {str(e)}")
            return render(request, 'resume_analyzer/signup.html')
    
    return render(request, 'resume_analyzer/signup.html')

# User Login View
@csrf_exempt
def login(request):
    if request.method == 'POST':
        try:
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                email = data.get('email')
                password = data.get('password')
            else:
                email = request.POST.get('email')
                password = request.POST.get('password')
            
            # Validate input
            if not email or not password:
                if request.content_type == 'application/json':
                    return JsonResponse({'error': 'Email and password are required'}, status=400)
                messages.error(request, "Email and password are required")
                return render(request, 'resume_analyzer/login.html')
            
            # Find user by email
            user = db.users.find_one({'email': email})
            if not user:
                if request.content_type == 'application/json':
                    return JsonResponse({'error': 'Invalid email or password'}, status=401)
                messages.error(request, "Invalid email or password")
                return render(request, 'resume_analyzer/login.html')
            
            # Check password
            if not bcrypt.checkpw(password.encode('utf-8'), user['password']):
                if request.content_type == 'application/json':
                    return JsonResponse({'error': 'Invalid email or password'}, status=401)
                messages.error(request, "Invalid email or password")
                return render(request, 'resume_analyzer/login.html')
            
            # Generate JWT token
            payload = {
                'user_id': str(user['_id']),
                'email': user['email'],
                'exp': datetime.datetime.utcnow() + JWT_EXPIRATION_DELTA
            }
            token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
            
            if request.content_type == 'application/json':
                return JsonResponse({
                    'message': 'Login successful',
                    'token': token,
                    'user': {
                        'id': str(user['_id']),
                        'email': user['email'],
                        'name': user['name']
                    }
                })
            
            # Set token in cookie and redirect
            response = redirect('home')
            response.set_cookie('jwt_token', token, max_age=JWT_EXPIRATION_DELTA.total_seconds(), httponly=True)
            messages.success(request, f"Welcome back, {user.get('name', 'User')}!")
            return response
            
        except Exception as e:
            if request.content_type == 'application/json':
                return JsonResponse({'error': str(e)}, status=500)
            messages.error(request, f"Login error: {str(e)}")
            return render(request, 'resume_analyzer/login.html')
    
    return render(request, 'resume_analyzer/login.html')

# Logout View
def logout(request):
    response = redirect('login')
    response.delete_cookie('jwt_token')
    messages.success(request, "You have been logged out successfully.")
    return response

# User Profile View
@token_required
def profile(request):
    user = request.user
    return render(request, 'resume_analyzer/profile.html', {'user': user})

# Protect existing views with the token_required decorator

def home(request):
    return render(request, 'resume_analyzer/home.html')

@token_required
def manage_job_descriptions(request):
    if request.method == 'POST':
        job_title = request.POST.get('job_title')
        job_description = request.POST.get('job_description')
        edit_id = request.POST.get('edit_id')
        
        if edit_id:  # Editing existing job description
            try:
                object_id = ObjectId(edit_id)
                # Check if the job description belongs to the current user
                existing_jd = db.job_descriptions.find_one({'_id': object_id})
                if not existing_jd or existing_jd.get('user_id') != str(request.user['_id']):
                    messages.error(request, "You don't have permission to edit this job description.")
                    return redirect('manage_job_descriptions')
                    
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
                    'user_id': str(request.user['_id']),  # Associate with current user
                    'created_at': datetime.datetime.now()
                }).inserted_id
                messages.success(request, f"Job description '{job_title}' saved successfully.")
            except Exception as e:
                messages.error(request, f"Error saving job description: {str(e)}")
        
        return redirect('manage_job_descriptions')
    
    # Get job descriptions for the current user only
    job_descriptions = list(db.job_descriptions.find({'user_id': str(request.user['_id'])}).sort('created_at', -1))
    
    # Convert MongoDB _id to string and add as id attribute
    for jd in job_descriptions:
        jd['id'] = str(jd['_id'])
    
    return render(request, 'resume_analyzer/manage_job_descriptions.html', {
        'job_descriptions': job_descriptions
    })

@token_required
def delete_job_description(request, jd_id):
    try:
        object_id = ObjectId(jd_id)
        # Check if the job description belongs to the current user
        existing_jd = db.job_descriptions.find_one({'_id': object_id})
        if not existing_jd or existing_jd.get('user_id') != str(request.user['_id']):
            messages.error(request, "You don't have permission to delete this job description.")
            return redirect('manage_job_descriptions')
            
        result = db.job_descriptions.delete_one({'_id': object_id})
        
        if result.deleted_count > 0:
            messages.success(request, "Job description deleted successfully.")
        else:
            messages.error(request, "Job description not found.")
    except Exception as e:
        messages.error(request, f"Error deleting job description: {str(e)}")
    
    return redirect('manage_job_descriptions')


@token_required
def upload_resume(request):
    # Get job descriptions for the current user only
    job_descriptions = list(db.job_descriptions.find({'user_id': str(request.user['_id'])}).sort('created_at', -1))
    
    # Convert MongoDB _id to string and add as id attribute
    for jd in job_descriptions:
        jd['id'] = str(jd['_id'])
    
    if len(job_descriptions) == 0:
        messages.warning(request, "No job descriptions available. Please add a job description first.")
        return redirect('manage_job_descriptions')
    
    if request.method == 'POST':
        if 'resume_files' not in request.FILES:
            messages.error(request, "Please select at least one resume file.")
            return render(request, 'resume_analyzer/upload_resume.html', {
                'job_descriptions': job_descriptions
            })
            
        resume_files = request.FILES.getlist('resume_files')
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
            
            # Verify the job description belongs to the current user
            if not job_description or job_description.get('user_id') != str(request.user['_id']):
                messages.error(request, "You don't have permission to use this job description.")
                return render(request, 'resume_analyzer/upload_resume.html', {
                    'job_descriptions': job_descriptions
                })
            
            # Process multiple files
            result_ids = []
            
            for resume_file in resume_files:
                # Extract text from resume
                file_extension = os.path.splitext(resume_file.name)[1].lower()
                file_bytes = resume_file.read()
                
                try:
                    if file_extension == '.pdf':
                        pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
                        resume_content = ""
                        for page_num in range(len(pdf_document)):
                            page = pdf_document[page_num]
                            resume_content += page.get_text()
                        pdf_document.close()
                    else:
                        resume_content = file_bytes.decode('utf-8', errors='ignore')
                    
                    # Store resume in MongoDB
                    resume_id = db.resumes.insert_one({
                        'filename': resume_file.name,
                        'content': resume_content,
                        'job_description_id': selected_jd_id,
                        'user_id': str(request.user['_id']),
                        'uploaded_at': datetime.datetime.now()
                    }).inserted_id
                    
                    # Generate AI analysis
                    input_prompt = get_resume_report_text_prompts(resume_content)
                    ai_report = generate_and_get_resume_report(input_prompt)
                    
                    # Extract score from AI report
                    score_match = re.search(r'(\d{1,3})%', ai_report)
                    similarity_score = float(score_match.group(1)) if score_match else 65.0
                    
                    # Extract skills and experience sections from AI report
                    skills_section = ""
                    experience_section = ""
                    is_fresher = False
                    
                    # Parse AI report sections
                    sections = ai_report.split('\n\n')
                    for section in sections:
                        if 'skills' in section.lower():
                            skills_section = section
                        elif 'experience' in section.lower():
                            experience_section = section
                            # Check if candidate is a fresher
                            is_fresher = any(keyword in section.lower() for keyword in 
                                ['fresher', 'entry level', 'recent graduate', 'no experience'])
                    
                    # Store analysis results
                    result_id = db.analysis_results.insert_one({
                        'resume_id': str(resume_id),
                        'job_description_id': selected_jd_id,
                        'user_id': str(request.user['_id']),
                        'similarity_score': similarity_score,
                        'extracted_skills': skills_section,
                        'extracted_experience': experience_section,
                        'is_fresher': is_fresher,
                        'ai_report': ai_report,
                        'created_at': datetime.datetime.now(),
                        'filename': resume_file.name
                    }).inserted_id
                    
                    result_ids.append(str(result_id))
                    
                except Exception as analysis_error:
                    print(f"Analysis error for {resume_file.name}: {str(analysis_error)}")
                    messages.error(request, f"Error analyzing {resume_file.name}: {str(analysis_error)}")
            
            # Handle results
            if not result_ids:
                messages.error(request, "No resumes were successfully analyzed.")
                return render(request, 'resume_analyzer/upload_resume.html', {
                    'job_descriptions': job_descriptions
                })
            
            # Redirect based on number of results
            if len(result_ids) == 1:
                return redirect('analysis_result', result_id=result_ids[0])
            return redirect('bulk_analysis_results', result_ids=','.join(result_ids))
            
        except Exception as e:
            print(f"Resume upload error: {str(e)}")
            messages.error(request, f"Error processing resumes: {str(e)}")
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
@token_required
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
        
        # Verify the result belongs to the current user
        if result.get('user_id') != str(request.user['_id']):
            messages.error(request, "You don't have permission to view this analysis result.")
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

@token_required
def bulk_analysis_results(request, result_ids):
    try:
        # Split the comma-separated result IDs
        result_id_list = result_ids.split(',')
        results = []
        
        for result_id in result_id_list:
            try:
                object_id = ObjectId(result_id)
                result = db.analysis_results.find_one({'_id': object_id})
                
                # Verify the result belongs to the current user
                if result and result.get('user_id') == str(request.user['_id']):
                    # Get related resume and job description
                    resume_id = ObjectId(result['resume_id'])
                    jd_id = ObjectId(result['job_description_id'])
                    
                    resume = db.resumes.find_one({'_id': resume_id})
                    job_description = db.job_descriptions.find_one({'_id': jd_id})
                    
                    if resume and job_description:
                        # Add additional info to result
                        result['resume'] = resume
                        result['job_description'] = job_description
                        result['id'] = result_id
                        results.append(result)
            except Exception as e:
                print(f"Error processing result {result_id}: {str(e)}")
        
        if not results:
            messages.error(request, "No valid analysis results found.")
            return redirect('home')
        
        # Sort results by similarity score (highest first)
        results.sort(key=lambda x: x.get('similarity_score', 0), reverse=True)
        
        return render(request, 'resume_analyzer/bulk_analysis_results.html', {
            'results': results,
            'job_description': results[0]['job_description']  # All results use the same job description
        })
        
    except Exception as e:
        print(f"Error in bulk_analysis_results view: {str(e)}")
        messages.error(request, f"Error retrieving analysis results: {str(e)}")
        return redirect('home')

# Add this new view function after the existing ones
@token_required
def view_applicants(request):
    # Get all analysis results sorted by similarity score in descending order
    analysis_results = list(db.analysis_results.find({'user_id': str(request.user['_id'])}).sort('similarity_score', -1))
    print(f"User ID being used for query: {str(request.user['_id'])}")
    print(f"Number of results found: {len(analysis_results)}")
    
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
    
    return render(request, 'resume_analyzer/view_applicants.html', {
        'applicants': applicants
    })
    

# Add this new view function
def edit_job_description(request, jd_id):
    try:
        object_id = ObjectId(jd_id)
        
        # Check if the job description belongs to the current user
        existing_jd = db.job_descriptions.find_one({'_id': object_id})
        if not existing_jd or existing_jd.get('user_id') != str(request.user['_id']):
            messages.error(request, "You don't have permission to edit this job description.")
            return redirect('manage_job_descriptions')
        
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
