
from rest_framework.response import Response
import google.generativeai as genai
from ATS.settings import DB
import os



def get_next_api_key():
    data = DB.gen_ai.find_one({'active': True})
    api_key = data.get('API_KEY')
    return api_key

def get_genai_model():
	api_key = get_next_api_key()
	genai.configure(api_key=api_key)
	model = genai.GenerativeModel('gemini-1.5-flash')
	return model


def get_resume_report_text_prompts(extracted_text):
    """
    Generate a prompt for the AI to analyze a resume
    """
    input_text_prompt = '''
    You are an expert resume analyst with years of experience in HR and recruitment. 
    Analyze the following resume content and provide a detailed report that includes:
    
    1. An overall ATS compatibility score (as a percentage)
    2. 3-5 key strengths of the resume
    3. 3-5 specific areas for improvement
    4. Suggestions for keywords that could be added based on industry standards
    5. Formatting and structure recommendations
    
    Format your response with clear sections and bullet points.
    
    RESUME CONTENT:
    {0}
    '''.format(extracted_text)
    
    return input_text_prompt

def generate_and_get_resume_report(input_promt):
	"""
	output remark basis your report
	"""
	model = get_genai_model()
	response = model.generate_content(input_promt, generation_config=genai.GenerationConfig(max_output_tokens=1000))
	output = response.text
	output_remark  = output.strip()
	return output_remark

