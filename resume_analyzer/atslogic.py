import re
import spacy
from sentence_transformers import SentenceTransformer
import string
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize

class TextCleaner:
    """
    A class used to clean text by removing stopwords, punctuation, and performing lemmatization.

    Attributes:
    -----------
    raw_input_text : str
        The raw text input provided by the user.
    set_of_stopwords : set
        A set containing English stopwords and punctuation to be removed from the text.
    lemmatizer : WordNetLemmatizer
        An instance of the WordNetLemmatizer for lemmatizing words.

    Methods:
    --------
    clean_text() -> str:
        Cleans the raw input text by tokenizing, removing stopwords and punctuation, and lemmatizing the words.
    """

    def __init__(self) -> None:
        """
        Constructs all the necessary attributes for the TextCleaner object.
        """
        # Combine English stopwords and punctuation into a set for efficient lookup
        self.set_of_stopwords = set(stopwords.words("english") + list(string.punctuation))
        # Initialize the WordNetLemmatizer
        self.lemmatizer = WordNetLemmatizer()

    def clean_text(self, raw_text: str) -> str:
        """
        Cleans the raw input text by performing the following steps:
        1. Converts text to lowercase.
        2. Tokenizes the text into words.
        3. Removes stopwords and punctuation.
        4. Lemmatizes the remaining words.
        5. Joins the cleaned tokens back into a single string.

        Parameters:
        -----------
        raw_text : str
            The raw text input to be cleaned.

        Returns:
        --------
        str
            The cleaned text.
        """
        # Convert text to lowercase and tokenize into words
        tokens = word_tokenize(raw_text.lower())
        # Remove stopwords and punctuation
        tokens = [token for token in tokens if token not in self.set_of_stopwords]
        # Lemmatize the remaining words
        tokens = [self.lemmatizer.lemmatize(token) for token in tokens]
        # Join the tokens back into a single string
        cleaned_text = " ".join(tokens)
        return cleaned_text

class ATS:
    """
    A class to parse resumes and job descriptions, extract relevant information,
    and compute similarities between resumes and job descriptions.
    """
    
    RESUME_SECTIONS = [
        "Contact Information", "Objective", "Summary", "Education", "Experience", 
        "Skills", "Projects", "Certifications", "Licenses", "Awards", "Honors", 
        "Publications", "References", "Technical Skills", "Computer Skills", 
        "Programming Languages", "Software Skills", "Soft Skills", "Language Skills", 
        "Professional Skills", "Transferable Skills", "Work Experience", 
        "Professional Experience", "Employment History", "Internship Experience", 
        "Volunteer Experience", "Leadership Experience", "Research Experience", 
        "Teaching Experience",
    ]

    def __init__(self):
        """
        Initializes the ATS.
        """
        self.nlp = spacy.load('en_core_web_sm')
        # self.resume_content = None
        # self.jd_content = None
        # self.cleaned_experience = None
        # self.cleaned_skills = None

    def load_resume(self, resume_content):
        """
        Loads the resume content from a string.

        :param resume_content: Resume content as a string
        """
        self.resume_content = resume_content

    def load_job_description(self, jd_content):
        """
        Loads the job description content from a string.

        :param jd_content: Job description content as a string
        """
        self.jd_content = jd_content

    def extract_skills(self):
        """
        Extracts skills from the resume content using multiple strategies to handle
        different resume formats and layouts.
        """
        # Comprehensive pattern matching for different skill section formats
        skills_patterns = [
            r'(?:Technical\s+)?Skills\s*[:]\s*',
            r'TECHNICAL\s+SKILLS\s*\n',
            r'SKILLS\s*\n',
            r'SKILLS\s*', 
            r'\nSKILLS\s*\n',
            r'\nSKILLS\s*:',
            r'Technical\s+Skills\s*[:\n]',
            r'(?:Key|Professional|Computer|Programming)\s+Skills\s*[:\n]'
        ]
        
        # Find the skills section
        skills_section = ""
        found_skills = False
        
        # Strategy 1: Try to find skills section by header pattern
        for pattern in skills_patterns:
            skills_match = re.search(pattern, self.resume_content, re.IGNORECASE)
            if skills_match:
                skills_start = skills_match.end()
                
                # Look for next major section header
                next_section_pattern = re.compile(
                    r'\n\n[A-Z][A-Za-z\s]+[:]\s*|\n[A-Z][A-Z\s]{2,}(?:\n[-~]+)?|\n[A-Z][A-Za-z\s]+\n[-~]+|\nEDUCATION'
                )
                section_match = next_section_pattern.search(self.resume_content, skills_start)
                
                skills_end = section_match.start() if section_match else len(self.resume_content)
                skills_section = self.resume_content[skills_start:skills_end].strip()
                found_skills = True
                break
        
        # Strategy 2: If not found, try to find skills section by scanning the resume line by line
        if not found_skills:
            lines = self.resume_content.split('\n')
            for i, line in enumerate(lines):
                # Check for various skills section formats
                if re.search(r'\b(?:SKILLS|Skills|skills)\b', line):
                    # Found a potential skills section
                    start_idx = i
                    if ':' in line:  # If skills are on the same line after a colon
                        skills_section = line.split(':', 1)[1].strip()
                        found_skills = True
                    else:
                        # Skills are on the following lines
                        start_idx = i + 1
                        end_idx = len(lines)
                        
                        # Find where the skills section ends
                        for j in range(start_idx, len(lines)):
                            # Look for the next section header
                            if j + 1 < len(lines) and (
                                re.match(r'^[A-Z][A-Z\s]{2,}', lines[j].strip()) or
                                re.match(r'^EDUCATION', lines[j].strip()) or
                                re.match(r'^[A-Z][A-Za-z\s]+:', lines[j].strip())
                            ):
                                end_idx = j
                                break
                        
                        skills_section = '\n'.join(lines[start_idx:end_idx]).strip()
                        found_skills = True
                    break
        
        # Strategy 3: Try to directly extract skills from a resume format where skills are listed with categories
        if skills_section == "":
            # Look for patterns like "Frontend : JavaScript, React, HTML/CSS"
            category_skills_pattern = re.compile(
                r'(?:Frontend|Backend|Tools|Database|Integration|Deployment|Languages|Frameworks)\s*:\s*([^:]+?)(?=\n[A-Za-z]+\s*:|$)',
                re.IGNORECASE
            )
            
            matches = category_skills_pattern.finditer(self.resume_content)
            category_skills = []
            
            for match in matches:
                if match.group(1):
                    category_skills.append(match.group(1).strip())
            
            if category_skills:
                skills_section = ', '.join(category_skills)
                found_skills = True
        
        # Process the found skills section
        if skills_section:
            # Common non-skill words to exclude
            non_skill_words = {
                'and', 'the', 'with', 'for', 'in', 'on', 'of', 'to', 'a', 'an',
                'using', 'through', 'via', 'by', 'as', 'including', 'across',
                'various', 'other', 'etc', 'all', 'both', 'each', 'every',
                'some', 'any', 'many', 'few', 'several', 'various',
                'periods', 'present', 'education', 'projects', 'project',
                'orders', 'data', 'system'
            }
            
            # Extract skills from various formats
            extracted_skills = []
            
            # Process line by line for different formats
            for line in skills_section.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                # Remove bullet points and other list markers
                if line.startswith(('•', '*', '-', '◦')):
                    line = line[1:].strip()
                
                # Handle category headers (e.g., "Frontend : JavaScript, React, HTML/CSS")
                if ':' in line and not line.strip().endswith(':'):
                    category, skills_text = line.split(':', 1)
                    skills = re.split(r'[,/]', skills_text)
                    extracted_skills.extend([
                        skill.strip() for skill in skills 
                        if skill.strip() and len(skill.strip()) > 1 and skill.strip().lower() not in non_skill_words
                    ])
                    continue
                
                # Handle comma/semicolon/slash separated skill lists
                skills = re.split(r'[,;/]', line)
                for skill in skills:
                    skill = skill.strip()
                    if skill and skill.lower() not in non_skill_words:
                        # Filter out sentences and non-skill text
                        if (len(skill.split()) <= 3 and 
                            not any(w.lower() in non_skill_words for w in skill.split() if len(w) > 2) and
                            not re.match(r'^\d{4}\s*-\s*\d{4}|present', skill.lower())):
                            extracted_skills.append(skill)
            
            # Clean up skills list
            clean_skills = []
            for skill in extracted_skills:
                # Remove trailing punctuation
                skill = re.sub(r'[.,;:]\s*', '', skill).strip()
                
                # Skip if too short or contains invalid characters
                if len(skill) <= 1 or all(c.isdigit() or c in string.punctuation for c in skill):
                    continue
                    
                # Skip year ranges and bullet points
                if re.match(r'^\d{4}\s*-\s*\d{4}|^\d{4}|^•', skill):
                    continue
                
                # Skip specific words that might be misclassified as skills
                if skill.lower() in ['frontend', 'backend', 'tools', 'database', 'integration', 'deployment']:
                    continue
                    
                clean_skills.append(skill)
            
            return list(set(clean_skills))
        
        # One more attempt - direct search for skills categories from the resume
        direct_categories = {
            'frontend': [],
            'backend': [],
            'database': [],
            'tools': [],
            'integration': [],
            'deployment': []
        }
        
        for category in direct_categories.keys():
            pattern = rf'{category}\s*:\s*(.*?)(?=\n\w+\s*:|$)'
            match = re.search(pattern, self.resume_content, re.IGNORECASE)
            if match:
                skills_text = match.group(1).strip()
                skills = re.split(r'[,/]', skills_text)
                direct_categories[category] = [s.strip() for s in skills if s.strip()]
        
        # If we found skills through direct category search
        all_skills = []
        for skills in direct_categories.values():
            all_skills.extend(skills)
        
        if all_skills:
            # Clean up the skills
            clean_skills = []
            for skill in all_skills:
                # Remove trailing punctuation
                skill = re.sub(r'[.,;:]\s*', '', skill).strip()
                
                # Skip if too short or contains invalid characters
                if len(skill) <= 1 or all(c.isdigit() or c in string.punctuation for c in skill):
                    continue
                    
                # Skip year ranges
                if re.match(r'^\d{4}\s*-\s*\d{4}|^\d{4}', skill):
                    continue
                    
                clean_skills.append(skill)
            
            return list(set(clean_skills))
        
        return []

    def extract_experience(self):
        """
        Extracts the work experience section from the resume content.

        :return: Experience section as a string
        """
        experience_start = self.resume_content.find("Experience")
        if experience_start == -1:
            return ""

        experience_end = len(self.resume_content)
        for section in self.RESUME_SECTIONS:
            if section != "Experience":
                section_start = self.resume_content.find(section, experience_start)
                if section_start != -1:
                    experience_end = min(experience_end, section_start)

        experience_section = self.resume_content[experience_start:experience_end].strip()
        return experience_section

    def clean_experience(self, experience):
        """
        Cleans the extracted experience text from the resume.
        
        Parameters:
        -----------
        experience : str
            The raw experience text extracted from the resume.
        """
        cleaner = TextCleaner()
        self.cleaned_experience = cleaner.clean_text(experience)

    def clean_skills(self, skills):
        """
        Cleans the extracted skills text from the resume.
        
        Parameters:
        -----------
        skills : str
            The raw skills text extracted from the resume.
        """
        cleaner = TextCleaner()
        self.cleaned_skills = cleaner.clean_text(skills)

    def clean_jd(self):
        """
        Cleans the job description text by applying text cleaning techniques.

        Returns:
            str: The cleaned job description text.
        """
        cleaner = TextCleaner()
        cleaned_jd = cleaner.clean_text(self.jd_content)
        return cleaned_jd

    def compute_similarity(self):
        """
        Computes the similarity score between the cleaned resume and cleaned job description text using the SentenceTransformer model.

        Returns:
            float: The similarity score between the cleaned resume and cleaned job description text.
        """
        model = SentenceTransformer('all-MiniLM-L6-v2')
        cleaned_resume = self.cleaned_experience + self.cleaned_skills
        cleaned_jd_text = self.clean_jd()
        sentences = [cleaned_resume, cleaned_jd_text]
        embeddings1 = model.encode(sentences[0])
        embeddings2 = model.encode(sentences[1])
        
        similarity_score = model.similarity(embeddings1, embeddings2)

        return similarity_score

def main():
    # Get user input for resume and job description
    resume_content = input("\n\nPlease enter the resume content: ")
    jd_content = input("\n\nPlease enter the job description content: ")

    # Create an instance of ATS
    ats = ATS()

    # Load and process data
    ats.load_resume(resume_content)
    ats.load_job_description(jd_content)

    # Extract and clean experience
    experience = ats.extract_experience()
    ats.clean_experience(experience)

    # Extract and clean skills
    skills = " ".join(ats.extract_skills())
    ats.clean_skills(skills)

    # Compute and print the similarity score
    similarity_score = ats.compute_similarity()
    print(f"The similarity score between the resume and job description is: {round(similarity_score.item() * 100, 2)}%")

if __name__ == "__main__":
    main()