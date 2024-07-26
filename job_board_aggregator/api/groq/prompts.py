"""
Prompt generation for Groq API requests.
"""

import logging

logger = logging.getLogger(__name__)


class PromptGenerator:
    """Generates prompts for experience and skills extraction."""
    
    def create_extraction_prompt(self, job_text: str, job_title: str = "") -> str:
        """Create a comprehensive prompt for extracting experience requirements."""
        
        prompt = f"""You are an expert HR analyst specializing in extracting precise experience requirements from job postings. You MUST always return valid JSON with no additional text or explanation.

JOB TITLE: {job_title}
JOB DESCRIPTION: {job_text}

EXTRACTION INSTRUCTIONS:
1. First, scan the job description for explicit experience requirements (e.g., "3+ years", "minimum 5 years", "2-4 years experience")
2. If explicit experience is found, use the MINIMUM value from any range (e.g., "2-4 years" = 2, "3+" = 3)
3. If NO explicit experience is mentioned in the description, you MUST infer based on the job title using these guidelines:
   - "Senior" roles = 5-8 years minimum experience
   - "Lead" roles = 6-10 years minimum experience 
   - "Principal" or "Staff" roles = 8+ years minimum experience
   - "Manager" or "Director" roles = 7+ years minimum experience
   - "Junior" or "Associate" roles = 0-2 years minimum experience
   - "Entry Level" or "Intern" roles = 0 years experience
   - Standard role titles without seniority indicators = 2-3 years minimum experience
4. Always provide a confidence score based on how explicit the information was

RESPONSE FORMAT - Return ONLY this JSON structure with NO additional text:
{{"min_experience_years": <integer 0-50>, "experience_type": "minimum", "experience_details": "<brief explanation of how you determined this number>", "experience_extracted": <true if found in description, false if inferred from title>, "extraction_confidence": <0.1-1.0 where 1.0=explicitly stated, 0.8=clearly inferred from title, 0.5=general inference>}}

CRITICAL RULES:
- NEVER return null, undefined, or empty values
- ALWAYS return a valid integer for min_experience_years (0-50)
- ALWAYS return valid strings for experience_type and experience_details
- ALWAYS return a boolean for experience_extracted
- ALWAYS return a number between 0.0 and 1.0 for extraction_confidence
- ALWAYS infer experience from job title if not found in description
- NO explanatory text outside the JSON object
- NO markdown formatting or code blocks
- Response must be parseable as valid JSON
- The JSON must contain exactly these 5 keys: min_experience_years, experience_type, experience_details, experience_extracted, extraction_confidence

EXAMPLES:
Job with "3+ years experience required" → {{"min_experience_years": 3, "experience_type": "minimum", "experience_details": "Explicitly stated 3+ years required", "experience_extracted": true, "extraction_confidence": 1.0}}

Senior Software Engineer (no experience mentioned) → {{"min_experience_years": 5, "experience_type": "minimum", "experience_details": "Inferred from Senior level title", "experience_extracted": false, "extraction_confidence": 0.8}}

Software Developer (no experience mentioned) → {{"min_experience_years": 2, "experience_type": "minimum", "experience_details": "Standard developer role typically requires 2-3 years", "experience_extracted": false, "extraction_confidence": 0.6}}"""
        return prompt
    
    def create_skills_extraction_prompt(self, job_text: str, job_title: str = "") -> str:
        """Create a comprehensive prompt for extracting skills from job postings."""
        
        prompt = f"""You are an expert HR analyst specializing in extracting skills from job postings. You MUST always return valid JSON with no additional text or explanation.

JOB TITLE: {job_title}
JOB DESCRIPTION: {job_text}

EXTRACTION INSTRUCTIONS:
Extract ALL relevant skills mentioned in the job description. Include:
- Programming languages (Python, Java, JavaScript, etc.)
- Frameworks & libraries (React, Django, TensorFlow, etc.)
- Databases (MySQL, PostgreSQL, MongoDB, etc.)
- Cloud platforms (AWS, Azure, GCP, etc.)
- Tools & technologies (Git, Docker, Jenkins, etc.)
- Technical skills (API development, machine learning, etc.)
- Soft skills (communication, leadership, teamwork, etc.)

RULES:
1. Extract up to 25 most important skills
2. Prioritize technical skills over soft skills
3. Use consistent naming (e.g., "JavaScript" not "JS")
4. Remove duplicates and similar variations
5. Include both required and preferred skills in one list

RESPONSE FORMAT (JSON only):
{{
    "skills": ["skill1", "skill2", "skill3", ...],
    "skills_extracted": true,
    "extraction_confidence": 0.95
}}

EXAMPLES:

"Experience with Python, Django, and PostgreSQL required. Knowledge of AWS preferred. Strong communication skills." → {{
    "skills": ["Python", "Django", "PostgreSQL", "AWS", "Communication"],
    "skills_extracted": true,
    "extraction_confidence": 0.95
}}

"React developer needed. Must know TypeScript, Node.js, and Git. MongoDB experience a plus." → {{
    "skills": ["React", "TypeScript", "Node.js", "Git", "MongoDB"],
    "skills_extracted": true,    "extraction_confidence": 0.9
}}"""
        return prompt

    def create_job_summary_prompt(self, job_text: str, job_title: str = "") -> str:
        """Create a comprehensive prompt for extracting 5-point job summary."""
        
        prompt = f"""You are an expert HR analyst specializing in creating concise, informative job summaries. You MUST always return valid JSON with no additional text or explanation.

JOB TITLE: {job_title}
JOB DESCRIPTION: {job_text}

EXTRACTION INSTRUCTIONS:
Create exactly 5 key bullet points that summarize the most important aspects of this job. Focus on:
1. Primary role responsibilities and main purpose
2. Key technical skills or domain expertise required
3. Team/organizational context and reporting structure
4. Experience level and qualifications needed
5. Notable benefits, company culture, or unique aspects

RULES:
1. Each point should be 1-2 sentences maximum
2. Use clear, professional language
3. Prioritize the most essential information
4. Avoid redundancy between points
5. Make it useful for job seekers to quickly understand the role

RESPONSE FORMAT (JSON only):
{{
    "summary_points": [
        "Point 1: Main role and responsibilities...",
        "Point 2: Key technical requirements...",
        "Point 3: Team and organizational context...",
        "Point 4: Experience and qualifications...",
        "Point 5: Benefits or unique aspects..."
    ],
    "summary_extracted": true,
    "extraction_confidence": 0.95
}}

EXAMPLES:

Software Engineer role → {{
    "summary_points": [
        "Develop and maintain scalable web applications using modern frameworks and cloud technologies",
        "Required: 3+ years experience with Python, React, and AWS cloud services",
        "Join a cross-functional agile team of 8 engineers reporting to Engineering Manager",
        "Bachelor's degree in Computer Science or equivalent experience required",
        "Competitive salary, remote-first culture, and comprehensive health benefits"
    ],
    "summary_extracted": true,
    "extraction_confidence": 0.9
}}

Data Analyst role → {{
    "summary_points": [
        "Analyze large datasets to drive business insights and support strategic decision-making",
        "Expertise required in SQL, Python, Tableau, and statistical analysis methods",
        "Work closely with product and marketing teams in a collaborative environment",
        "2-4 years of analytics experience with advanced degree preferred",
        "Fast-growing startup with equity compensation and flexible work arrangements"
    ],
    "summary_extracted": true,
    "extraction_confidence": 0.85
}}"""
        return prompt

    def create_combined_extraction_prompt(self, job_text: str, job_title: str = "") -> str:
        """Create a comprehensive prompt for extracting experience, skills, and summary in one call."""
        
        prompt = f"""You are an expert HR analyst. Extract experience requirements, skills, and a 5-point summary from this job posting in a single structured JSON response.

JOB TITLE: {job_title}
JOB DESCRIPTION: {job_text}

EXTRACTION REQUIREMENTS:

1. EXPERIENCE EXTRACTION:
   - Find explicit experience requirements (e.g., "3+ years", "minimum 5 years")
   - If explicit experience found, use MINIMUM value from ranges
   - If NO explicit experience, infer from job title:
     * "Senior" = 5-8 years, "Lead" = 6-10 years, "Principal/Staff" = 8+ years
     * "Manager/Director" = 7+ years, "Junior/Associate" = 0-2 years
     * "Entry Level/Intern" = 0 years, Standard titles = 2-3 years

2. SKILLS EXTRACTION:
   - Extract max 25 most important skills from the job description
   - Include programming languages, frameworks, tools, technologies, databases
   - Include relevant soft skills and methodologies
   - Focus on skills that are explicitly mentioned or clearly required

3. SUMMARY EXTRACTION:
   - Create exactly 5 bullet points summarizing the job
   - Point 1: Primary role responsibilities and main purpose
   - Point 2: Key technical skills or domain expertise required
   - Point 3: Team/organizational context and reporting structure
   - Point 4: Experience level and qualifications needed
   - Point 5: Notable benefits, company culture, or unique aspects

RESPONSE FORMAT - Return ONLY this JSON structure:
{{
    "min_experience_years": <integer 0-50>,
    "experience_type": "minimum",
    "experience_details": "<brief explanation>",
    "experience_extracted": <true if found in description, false if inferred>,
    "experience_confidence": <0.1-1.0>,
    
    "skills": ["skill1", "skill2", "..."], 
    "skills_extracted": <true/false>,
    "skills_confidence": <0.1-1.0>,
    
    "summary_points": [
        "Point 1: Primary responsibilities...",
        "Point 2: Technical requirements...", 
        "Point 3: Team context...",
        "Point 4: Experience needed...",
        "Point 5: Benefits/culture..."
    ],
    "summary_extracted": <true/false>,
    "summary_confidence": <0.1-1.0>
}}

CRITICAL RULES:
- Return ONLY valid JSON with NO additional text
- ALWAYS provide all fields with valid values
- skills array must contain 1-25 strings
- summary_points must contain exactly 5 strings
- All confidence scores between 0.1-1.0
- experience_extracted = true only if explicitly found in description
- skills_extracted = true if meaningful skills found
- summary_extracted = true if comprehensive summary possible"""

        return prompt
