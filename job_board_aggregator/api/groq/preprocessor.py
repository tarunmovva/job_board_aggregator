"""
Text preprocessing functionality for job descriptions.
"""

import re
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


class JobDescriptionPreprocessor:
    """Handles preprocessing of job descriptions for experience and skills extraction."""
    
    def __init__(self):
        """Initialize preprocessor with keyword lists."""
        self._load_keywords()
    
    def _load_keywords(self):
        """Load comprehensive keyword lists for preprocessing."""
        # Comprehensive experience-related keywords with better coverage
        self.experience_keywords = [
            'years', 'year', 'yrs', 'months', 'month', 'experience', 'experienced', 'background',
            'minimum', 'maximum', 'required', 'requirements', 'qualifications', 'preferred', 
            'must have', 'should have', 'ideal', 'looking for', 'seeking',
            'senior', 'junior', 'lead', 'principal', 'staff', 'entry', 'associate', 
            'manager', 'director', 'supervisor', 'head', 'chief', 'mid-level', 'entry-level',
            'degree', 'bachelor', 'bachelors', 'master', 'masters', 'phd', 'doctorate', 
            'education', 'certification', 'certificate', 'diploma',
            'knowledge', 'expertise', 'proficiency', 'familiarity', 'skills', 'ability'
        ]
        
        # Skills-related keywords for enhanced extraction (massively expanded)
        self.skills_keywords = [
            # Programming languages
            'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'go', 'rust', 'ruby', 'php',
            'swift', 'kotlin', 'scala', 'r', 'matlab', 'sql', 'html', 'css', 'perl', 'haskell',
            'erlang', 'elixir', 'clojure', 'f#', 'dart', 'lua', 'shell', 'bash', 'powershell',
            'objective-c', 'assembly', 'cobol', 'fortran', 'pascal', 'vb.net', 'vba', 'apex',
            'groovy', 'julia', 'nim', 'crystal', 'zig', 'solidity', 'move', 'cairo',
            
            # Web frameworks & libraries
            'react', 'angular', 'vue', 'svelte', 'ember', 'backbone', 'jquery', 'node', 'express',
            'koa', 'fastify', 'next.js', 'nuxt.js', 'gatsby', 'remix', 'astro', 'sveltekit',
            'webpack', 'vite', 'rollup', 'parcel', 'babel', 'eslint', 'prettier', 'jest',
            'cypress', 'playwright', 'selenium', 'storybook', 'lerna', 'nx', 'turborepo',
            'sass', 'scss', 'less', 'stylus', 'tailwind', 'bootstrap', 'bulma', 'foundation',
            'material-ui', 'chakra-ui', 'ant-design', 'semantic-ui', 'styled-components',
            
            # Backend frameworks
            'django', 'flask', 'fastapi', 'spring', 'spring boot', 'laravel', 'symfony',
            'rails', 'sinatra', 'express.js', 'koa.js', 'nest.js', 'adonis.js', 'meteor',
            'phoenix', 'gin', 'echo', 'fiber', 'beego', 'iris', 'actix', 'rocket',
            'axum', 'warp', 'tower', 'hyper', 'tokio', 'async-std', 'rayon',
            
            # AI & ML
            'artificial intelligence', 'machine learning', 'deep learning', 'neural networks',
            'computer vision', 'natural language processing', 'nlp', 'speech recognition',
            'reinforcement learning', 'supervised learning', 'unsupervised learning',
            'tensorflow', 'pytorch', 'keras', 'scikit-learn', 'pandas', 'numpy', 'scipy',
            'opencv', 'matplotlib', 'seaborn', 'plotly', 'streamlit', 'gradio',
            
            # Databases
            'mysql', 'postgresql', 'mongodb', 'redis', 'elasticsearch', 'oracle', 'sqlite',
            'cassandra', 'dynamodb', 'neo4j', 'arangodb', 'couchdb', 'rethinkdb',
            'influxdb', 'timescaledb', 'clickhouse', 'snowflake', 'bigquery', 'redshift',
            
            # Cloud platforms
            'aws', 'azure', 'gcp', 'google cloud', 'kubernetes', 'docker', 'terraform',
            'ansible', 'puppet', 'chef', 'saltstack', 'vagrant', 'packer', 'consul',
            'vault', 'nomad', 'istio', 'linkerd', 'envoy', 'prometheus', 'grafana',
            
            # DevOps & CI/CD
            'git', 'github', 'gitlab', 'bitbucket', 'jenkins', 'github actions', 'gitlab ci',
            'azure devops', 'circleci', 'travis ci', 'bamboo', 'teamcity', 'buildkite',
            
            # Testing
            'jest', 'mocha', 'chai', 'jasmine', 'karma', 'protractor', 'cypress',
            'playwright', 'selenium', 'webdriver', 'puppeteer', 'testcafe',
            'pytest', 'unittest', 'nose', 'tox', 'coverage', 'hypothesis',
            
            # Security
            'oauth', 'jwt', 'saml', 'ldap', 'active directory', 'keycloak',
            'auth0', 'okta', 'cognito', 'firebase auth', 'passport', 'bcrypt',
            
            # Soft skills
            'communication', 'leadership', 'teamwork', 'collaboration', 'problem solving',
            'analytical thinking', 'critical thinking', 'adaptability', 'time management'
        ]
        
        # Priority section headers that often contain experience requirements
        self.section_headers = [
            'requirements', 'qualifications', 'experience', 'skills', 'education', 
            'what you', 'who you', 'ideal candidate', 'we are looking for', 'you should have',
            'must have', 'required', 'preferred', 'responsibilities', 'about you'
        ]
    
    def preprocess_job_description(self, job_description: str, job_title: str = "", extract_skills: bool = False) -> str:
        """
        Enhanced preprocessing to preserve experience and skills-related information with minimal loss.
        Increased context and better pattern preservation for accurate extraction.
        """
        if not job_description:
            return ""
        
        # Clean HTML tags but preserve structure
        clean_text = re.sub(r'<[^>]+>', ' ', job_description)
        clean_text = re.sub(r'&[a-zA-Z0-9]+;', ' ', clean_text)  # Remove HTML entities
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # Split into sentences for analysis
        sentences = re.split(r'[.!?\n]+', clean_text)
        scored_sentences = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:  # Skip very short sentences
                continue
                
            score = self._score_sentence(sentence, extract_skills)
            
            # Only include sentences with meaningful scores
            if score > 0:
                scored_sentences.append((sentence, score))
        
        # Sort by score (highest first)
        scored_sentences.sort(key=lambda x: x[1], reverse=True)
        
        # Build result with job title
        result_parts = []
        if job_title:
            result_parts.append(f"Job: {job_title}")
        
        # INCREASED LIMIT: Target 1200-1500 characters instead of 800
        current_length = len(' '.join(result_parts))
        target_length = 1400  # Increased from 800
        
        # Add highest scoring sentences first
        for sentence, score in scored_sentences:
            sentence_to_add = sentence
            
            # If adding this sentence would exceed limit, try to truncate smartly
            if current_length + len(sentence_to_add) + 1 > target_length:
                remaining_space = target_length - current_length - 4  # Space for "..."
                
                # Only truncate if we have meaningful space and this is a high-value sentence
                if remaining_space > 100 and score >= 70:
                    # Try to truncate at a natural break point
                    truncate_pos = sentence_to_add.rfind(' ', 0, remaining_space)
                    if truncate_pos > remaining_space * 0.7:  # Good break point found
                        sentence_to_add = sentence_to_add[:truncate_pos] + "..."
                    else:
                        sentence_to_add = sentence_to_add[:remaining_space] + "..."
                    
                    result_parts.append(sentence_to_add)
                    break
                else:
                    break  # No more space
            else:
                result_parts.append(sentence_to_add)
                current_length += len(sentence_to_add) + 1
        
        # Join all parts
        result = ' '.join(result_parts)
        
        # Hard limit safety check (should rarely be needed now)
        max_chars = 1500  # Increased from 800
        if len(result) > max_chars:
            result = result[:max_chars-3] + "..."
        
        return result
    
    def _score_sentence(self, sentence: str, extract_skills: bool = False) -> int:
        """Score a sentence based on relevance for experience/skills extraction."""
        sentence_lower = sentence.lower()
        score = 0
        
        # HIGHEST PRIORITY: Explicit numeric experience patterns
        if re.search(r'\d+\s*[-+–—]?\s*(years?|yrs?|months?)', sentence_lower):
            score += 100  # Very high priority
            
        # HIGH PRIORITY: Range patterns (e.g., "3-5 years", "2 to 4 years")
        if re.search(r'\d+\s*[-–—]\s*\d+\s*(years?|yrs?)', sentence_lower):
            score += 90
            
        # HIGH PRIORITY: Minimum/maximum patterns
        if re.search(r'\b(minimum|min|maximum|max|at least|requires?)\s*\d+\s*(years?|yrs?)', sentence_lower):
            score += 85
            
        # HIGH PRIORITY: Section headers
        for header in self.section_headers:
            if header in sentence_lower and len(sentence) < 200:  # Likely header
                score += 80
                break
                
        # CRITICAL: Seniority indicators
        seniority_terms = ['senior', 'junior', 'lead', 'principal', 'staff', 'manager', 
                         'director', 'supervisor', 'head', 'chief', 'associate', 'entry']
        for term in seniority_terms:
            if term in sentence_lower:
                score += 75  # High priority for seniority
                
        # IMPORTANT: Education requirements
        education_terms = ['degree', 'bachelor', 'master', 'phd', 'education', 'certification']
        for term in education_terms:
            if term in sentence_lower:
                score += 70
        
        # MEDIUM PRIORITY: General experience keywords
        keyword_count = sum(1 for keyword in self.experience_keywords if keyword in sentence_lower)
        score += keyword_count * 8
        
        # SKILLS PRIORITY: Skills-related content (when extract_skills is True)
        if extract_skills:
            skills_count = sum(1 for skill in self.skills_keywords if skill in sentence_lower)
            score += skills_count * 12  # Higher weight for skills extraction
            
            # BONUS: Multiple skills in same sentence
            if skills_count >= 2:
                score += 30
                
            # BONUS: Technical skill patterns
            if re.search(r'\b(proficient|expert|experienced)\s+in\b', sentence_lower):
                score += 25
            if re.search(r'\b(knowledge|experience)\s+of\b', sentence_lower):
                score += 20
        
        # BONUS: Multiple relevant terms in same sentence
        if keyword_count >= 3:
            score += 25
            
        # BONUS: Contains both experience and education
        education_terms = ['degree', 'bachelor', 'master', 'phd', 'education', 'certification']
        if any(edu in sentence_lower for edu in education_terms) and \
           any(exp in sentence_lower for exp in ['experience', 'years', 'background']):
            score += 20
            
        # PENALTY: Very long sentences (might be less focused)
        if len(sentence) > 300:
            score -= 10
        
        return score
