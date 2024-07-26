"""
Response parsing functionality for Groq API responses.
"""

import json
import re
import logging
from typing import Dict, Tuple

from job_board_aggregator.api.groq.models import ExperienceData, SkillsData, JobSummaryData, CombinedJobData

logger = logging.getLogger(__name__)


class ResponseParser:
    """Parses and validates responses from the Groq API."""
    
    def parse_groq_response(self, response: Dict, job_title: str = "") -> ExperienceData:
        """Parse the response from Groq API and extract experience data."""
        try:
            # Extract content from Groq response structure
            if 'choices' not in response or not response['choices']:
                logger.error(f"Malformed Groq response (no 'choices'): {response}")
                return self._create_failed_extraction("No choices in response", job_title)
            
            choice = response['choices'][0]
            if 'message' not in choice or 'content' not in choice['message']:
                logger.error(f"Malformed Groq response (no message content): {choice}")
                return self._create_failed_extraction("No message content", job_title)
            
            content = choice['message']['content'].strip()
            logger.debug(f"Raw Groq response content: {content[:200]}...")
            
            # Remove markdown code blocks if present
            content = self._clean_json_content(content)
            
            # Try to parse as JSON first
            try:
                data = json.loads(content)
                logger.debug(f"Successfully parsed JSON: {data}")
                
                # Apply validation and fixing
                data = self._validate_and_fix_groq_response(data, job_title)
                logger.debug(f"Validated and fixed Groq response: {data}")
                
            except json.JSONDecodeError as e:
                logger.warning(f"JSON decode failed: {e}, attempting regex extraction")
                # Fallback: extract JSON from text using regex
                json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
                if json_match:
                    try:
                        data = json.loads(json_match.group(0))
                        logger.debug(f"Successfully extracted JSON with regex: {data}")
                        
                        # Apply validation and fixing
                        data = self._validate_and_fix_groq_response(data, job_title)
                        logger.debug(f"Validated and fixed Groq response: {data}")
                        
                    except json.JSONDecodeError:
                        logger.warning("Regex extracted JSON is also invalid, using unstructured parsing")
                        return self._parse_unstructured_response(content, job_title)
                else:
                    logger.warning("No JSON found with regex, using unstructured parsing")
                    return self._parse_unstructured_response(content, job_title)
            
            # Validate and create ExperienceData
            result = ExperienceData(
                min_experience_years=data['min_experience_years'],
                experience_type=data['experience_type'],
                experience_details=data['experience_details'],
                experience_extracted=data['experience_extracted'],
                extraction_confidence=data['extraction_confidence']
            )
            
            logger.debug(f"Successfully created ExperienceData: {result}")
            return result
            
        except KeyError as e:
            logger.error(f"KeyError parsing Groq response - missing key {e}: {response}")
            return self._create_failed_extraction(f"Missing key: {e}", job_title)
        except Exception as e:
            logger.error(f"Unexpected error parsing Groq response: {e}")
            logger.error(f"Response was: {response}")
            return self._create_failed_extraction(f"Unexpected error: {e}", job_title)

    def parse_skills_response(self, response: Dict, job_title: str = "") -> SkillsData:
        """Parse the response from Groq API and extract skills data."""
        try:
            # Extract content from Groq response structure
            if 'choices' not in response or not response['choices']:
                logger.error(f"Malformed Groq skills response (no 'choices'): {response}")
                return self._create_failed_skills_extraction("No choices in response", job_title)
            
            choice = response['choices'][0]
            if 'message' not in choice or 'content' not in choice['message']:
                logger.error(f"Malformed Groq skills response (no message content): {choice}")
                return self._create_failed_skills_extraction("No message content", job_title)
            
            content = choice['message']['content'].strip()
            logger.debug(f"Raw Groq skills response content: {content[:200]}...")
            
            # Remove markdown code blocks if present
            content = self._clean_json_content(content)
            
            # Try to parse as JSON first
            try:
                data = json.loads(content)
                logger.debug(f"Successfully parsed skills JSON: {data}")
                
                # Apply validation and fixing
                data = self._validate_and_fix_skills_response(data, job_title)
                logger.debug(f"Validated and fixed skills response: {data}")
                
            except json.JSONDecodeError as e:
                logger.warning(f"Skills JSON decode failed: {e}, creating fallback")
                return self._create_failed_skills_extraction(f"JSON decode error: {e}", job_title)
            
            # Validate and create SkillsData
            result = SkillsData(
                skills=data.get('skills', []),
                skills_extracted=data.get('skills_extracted', False),
                extraction_confidence=data.get('extraction_confidence', 0.0)
            )
            
            logger.debug(f"Successfully created SkillsData: {len(result.skills)} skills found")
            return result
            
        except KeyError as e:
            logger.error(f"KeyError parsing skills response - missing key {e}: {response}")
            return self._create_failed_skills_extraction(f"Missing key: {e}", job_title)
        except Exception as e:
            logger.error(f"Unexpected error parsing skills response: {e}")
            logger.error(f"Response was: {response}")
            return self._create_failed_skills_extraction(f"Unexpected error: {e}", job_title)

    def _clean_json_content(self, content: str) -> str:
        """Clean JSON content by removing markdown blocks and explanatory text."""
        import re
        
        # Remove any explanatory text before the JSON and find the JSON block
        # Look for JSON structure starting with { and ending with }
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
        
        # Remove markdown code blocks if present
        if content.startswith('```json'):
            content = content[7:]  # Remove ```json
        if content.startswith('```'):
            content = content[3:]  # Remove ```
        if content.endswith('```'):
            content = content[:-3]  # Remove closing ```
        
        return content.strip()

    def _validate_and_fix_groq_response(self, data: Dict, job_title: str = "") -> Dict:
        """Validate and fix the experience response from Groq to ensure it matches the expected schema."""
        
        # Define required keys with defaults
        required_keys = {
            'min_experience_years': 0,
            'experience_type': 'minimum',
            'experience_details': 'Default extraction',
            'experience_extracted': False,
            'extraction_confidence': 0.0
        }
        
        # Ensure all required keys exist
        for key, default_value in required_keys.items():
            if key not in data:
                data[key] = default_value
                logger.debug(f"Added missing key '{key}' with default value")
        
        # Validate and fix experience years
        try:
            years = int(data['min_experience_years'])
            data['min_experience_years'] = max(0, min(years, 50))  # Clamp to reasonable range
        except (ValueError, TypeError):
            logger.warning(f"Invalid experience years: {data.get('min_experience_years')}, defaulting to 0")
            data['min_experience_years'] = 0
        
        # Validate experience type
        valid_types = ['minimum', 'preferred', 'total', 'relevant']
        if data['experience_type'] not in valid_types:
            logger.warning(f"Invalid experience type: {data['experience_type']}, defaulting to 'minimum'")
            data['experience_type'] = 'minimum'
        
        # Validate boolean
        if not isinstance(data['experience_extracted'], bool):
            data['experience_extracted'] = bool(data.get('experience_extracted', False))
        
        # Validate confidence
        try:
            confidence = float(data['extraction_confidence'])
            data['extraction_confidence'] = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
        except (ValueError, TypeError):
            logger.warning(f"Invalid confidence value: {data.get('extraction_confidence')}, defaulting to 0.0")
            data['extraction_confidence'] = 0.0
        
        # Validate details string
        if not isinstance(data['experience_details'], str):
            data['experience_details'] = str(data.get('experience_details', 'Default extraction'))
        
        return data

    def _validate_and_fix_skills_response(self, data: Dict, job_title: str = "") -> Dict:
        """Validate and fix the skills response from Groq to ensure it matches the expected schema."""
        
        # Define required keys with defaults
        required_keys = {
            'skills': [],
            'skills_extracted': False,
            'extraction_confidence': 0.0
        }
        
        # Ensure all required keys exist
        for key, default_value in required_keys.items():
            if key not in data:
                data[key] = default_value
                logger.debug(f"Added missing key '{key}' with default value")
        
        # Validate and fix skills list
        if not isinstance(data['skills'], list):
            logger.warning(f"Skills is not a list, converting: {data['skills']}")
            if isinstance(data['skills'], str):
                # Try to split by common delimiters
                data['skills'] = [skill.strip() for skill in re.split(r'[,;|]', data['skills']) if skill.strip()]
            else:
                data['skills'] = []
        
        # Clean up skill names, remove duplicates, and limit to 25
        cleaned_skills = []
        for skill in data['skills']:
            if isinstance(skill, str) and skill.strip():
                cleaned_skill = skill.strip().title()  # Normalize case
                if cleaned_skill not in cleaned_skills:
                    cleaned_skills.append(cleaned_skill)
                    
                # Limit to 25 skills max
                if len(cleaned_skills) >= 25:
                    break
        
        data['skills'] = cleaned_skills
        
        # Validate boolean
        if not isinstance(data['skills_extracted'], bool):
            data['skills_extracted'] = bool(data.get('skills_extracted', False))
        
        # Validate confidence
        try:
            confidence = float(data['extraction_confidence'])
            data['extraction_confidence'] = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
        except (ValueError, TypeError):
            logger.warning(f"Invalid confidence value: {data.get('extraction_confidence')}, defaulting to 0.0")
            data['extraction_confidence'] = 0.0
        
        # Set extraction flag based on whether we found any skills
        if len(data['skills']) > 0 and not data['skills_extracted']:
            data['skills_extracted'] = True
            if data['extraction_confidence'] < 0.5:
                data['extraction_confidence'] = 0.7  # Reasonable confidence if we found skills
        
        return data

    def _create_failed_extraction(self, reason: str, job_title: str = "") -> ExperienceData:
        """Create a failed extraction result with a specific reason, using title inference as fallback."""
        logger.warning(f"Creating failed extraction: {reason}")
        
        # Try to infer from job title as a fallback
        min_years, confidence = self._infer_experience_from_title(job_title)
        
        return ExperienceData(
            min_experience_years=min_years,
            experience_type="minimum",
            experience_details=f"Title-based inference ({reason}): {job_title}" if job_title else f"Failed extraction ({reason})",
            experience_extracted=False,
            extraction_confidence=confidence
        )
    
    def _parse_unstructured_response(self, content: str, job_title: str = "") -> ExperienceData:
        """Parse unstructured response as fallback with title-based inference."""
        logger.info("Parsing unstructured response with title-based inference")
        
        # Try to extract numbers from the text
        numbers = re.findall(r'\d+', content)
        min_years = 0
        confidence = 0.3
        
        if numbers:
            # Take the first reasonable number (between 0 and 20)
            for num_str in numbers:
                num = int(num_str)
                if 0 <= num <= 20:
                    min_years = num
                    confidence = 0.4
                    break
        
        # If no reasonable number found, infer from title
        if min_years == 0:
            min_years, confidence = self._infer_experience_from_title(job_title)
        
        return ExperienceData(
            min_experience_years=min_years,
            experience_type="minimum",
            experience_details=f"Unstructured parsing from {job_title}" if job_title else "Unstructured parsing",
            experience_extracted=min_years > 0 and confidence > 0.4,
            extraction_confidence=confidence
        )
    
    def _infer_experience_from_title(self, job_title: str) -> Tuple[int, float]:
        """Infer experience requirements from job title."""
        if not job_title:
            return 0, 0.2
        
        title_lower = job_title.lower()
        
        # Senior-level indicators (5-8 years)
        if any(keyword in title_lower for keyword in ['senior', 'sr.', 'sr ']):
            return 5, 0.8
        
        # Lead-level indicators (6-10 years)
        if any(keyword in title_lower for keyword in ['lead', 'principal', 'staff']):
            return 6, 0.8
        
        # Management-level indicators (7+ years)
        if any(keyword in title_lower for keyword in ['manager', 'director', 'head of']):
            return 7, 0.8
        
        # Junior-level indicators (0-2 years)
        if any(keyword in title_lower for keyword in ['junior', 'jr.', 'jr ', 'associate', 'entry', 'intern']):
            return 0, 0.8
        
        # Mid-level indicators (3-4 years)
        if any(keyword in title_lower for keyword in ['mid-level', 'mid level', 'intermediate']):
            return 3, 0.8
          # Default for standard titles (2-3 years)
        return 2, 0.6

    def _create_failed_skills_extraction(self, reason: str, job_title: str = "") -> SkillsData:
        """Create a fallback SkillsData when extraction fails."""
        logger.warning(f"Skills extraction failed for '{job_title}': {reason}")
        
        return SkillsData(
            skills=[],
            skills_extracted=False,
            extraction_confidence=0.0
        )

    def parse_summary_response(self, response: Dict, job_title: str = "") -> JobSummaryData:
        """Parse the response from Groq API and extract job summary data."""
        try:
            # Extract content from Groq response structure
            if 'choices' not in response or not response['choices']:
                logger.error(f"Malformed Groq summary response (no 'choices'): {response}")
                return self._create_failed_summary_extraction("No choices in response", job_title)
            
            choice = response['choices'][0]
            if 'message' not in choice or 'content' not in choice['message']:
                logger.error(f"Malformed Groq summary response (no message content): {choice}")
                return self._create_failed_summary_extraction("No message content", job_title)
            
            content = choice['message']['content'].strip()
            logger.debug(f"Raw Groq summary response content: {content[:200]}...")
            
            # Remove markdown code blocks if present
            content = self._clean_json_content(content)
            
            # Try to parse as JSON first
            try:
                data = json.loads(content)
                logger.debug(f"Successfully parsed summary JSON: {data}")
                
                # Validate and extract summary data
                return self._create_summary_from_data(data, job_title)
                
            except json.JSONDecodeError as e:
                logger.warning(f"Summary JSON decode failed: {e}, attempting regex extraction")
                # Fallback: extract JSON from text using regex
                json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
                if json_match:
                    try:
                        data = json.loads(json_match.group())
                        return self._create_summary_from_data(data, job_title)
                    except json.JSONDecodeError:
                        pass
                
                # Final fallback: create basic summary from content
                return self._create_failed_summary_extraction("JSON parsing failed", job_title)
                
        except Exception as e:
            logger.error(f"Unexpected error parsing summary response: {e}")
            return self._create_failed_summary_extraction(f"Parse error: {e}", job_title)

    def _create_summary_from_data(self, data: Dict, job_title: str = "") -> JobSummaryData:
        """Create JobSummaryData from parsed JSON data."""
        try:
            # Extract summary points
            summary_points = data.get('summary_points', [])
            
            # Validate summary points
            if not isinstance(summary_points, list):
                logger.warning(f"Invalid summary_points format in response: {summary_points}")
                return self._create_failed_summary_extraction("Invalid summary_points format", job_title)
            
            # Ensure we have exactly 5 points, or create generic ones if missing
            if len(summary_points) < 5:
                logger.warning(f"Less than 5 summary points extracted ({len(summary_points)}), padding with generic points")
                while len(summary_points) < 5:
                    summary_points.append(f"Additional information about {job_title or 'this position'}")
            elif len(summary_points) > 5:
                logger.warning(f"More than 5 summary points extracted ({len(summary_points)}), truncating to 5")
                summary_points = summary_points[:5]
            
            # Clean and validate each point
            cleaned_points = []
            for i, point in enumerate(summary_points):
                if isinstance(point, str) and point.strip():
                    cleaned_points.append(point.strip())
                else:
                    cleaned_points.append(f"Point {i+1}: Information about {job_title or 'this position'}")
            
            # Extract extraction metadata
            summary_extracted = data.get('summary_extracted', True)
            extraction_confidence = float(data.get('extraction_confidence', 0.8))
            
            # Validate confidence score
            if not (0.0 <= extraction_confidence <= 1.0):
                extraction_confidence = 0.8
            
            return JobSummaryData(
                summary_points=cleaned_points,
                summary_extracted=summary_extracted,
                extraction_confidence=extraction_confidence
            )
            
        except Exception as e:
            logger.error(f"Error creating summary from data: {e}")
            return self._create_failed_summary_extraction(f"Data processing error: {e}", job_title)

    def _create_failed_summary_extraction(self, reason: str, job_title: str = "") -> JobSummaryData:
        """Create a fallback JobSummaryData when extraction fails."""
        logger.warning(f"Job summary extraction failed for '{job_title}': {reason}")
        
        # Create generic 5-point summary
        generic_points = [
            f"This is a {job_title or 'professional'} position",
            "Specific requirements and qualifications apply",
            "The role involves various responsibilities and duties",
            "Experience and skills in relevant areas are needed",
            "Additional details are available in the full job description"
        ]
        
        return JobSummaryData(
            summary_points=generic_points,
            summary_extracted=False,
            extraction_confidence=0.1
        )

    def parse_combined_response(self, response: Dict, job_title: str = "") -> CombinedJobData:
        """Parse the response from Groq API for combined extraction."""
        
        try:
            # Extract content from Groq response structure
            if 'choices' not in response or not response['choices']:
                logger.error(f"Malformed Groq response (no 'choices'): {response}")
                return self._create_failed_combined_extraction("No choices in response", job_title)
            
            choice = response['choices'][0]
            if 'message' not in choice or 'content' not in choice['message']:
                logger.error(f"Malformed Groq response (no message content): {choice}")
                return self._create_failed_combined_extraction("No message content", job_title)
            
            content = choice['message']['content'].strip()
            logger.debug(f"Raw combined Groq response content: {content[:200]}...")
            
            # Remove markdown code blocks if present
            content = self._clean_json_content(content)
            
            # Try to parse as JSON
            try:
                data = json.loads(content)
                logger.debug(f"Successfully parsed combined JSON: {data}")
                
                # Validate and extract each component
                experience_data = self._extract_experience_from_combined(data, job_title)
                skills_data = self._extract_skills_from_combined(data, job_title)
                summary_data = self._extract_summary_from_combined(data, job_title)
                
                return CombinedJobData(
                    # Experience fields
                    min_experience_years=experience_data['min_experience_years'],
                    experience_type=experience_data['experience_type'],
                    experience_details=experience_data['experience_details'],
                    experience_extracted=experience_data['experience_extracted'],
                    experience_confidence=experience_data['experience_confidence'],
                    
                    # Skills fields
                    skills=skills_data['skills'],
                    skills_extracted=skills_data['skills_extracted'],
                    skills_confidence=skills_data['skills_confidence'],
                    
                    # Summary fields
                    summary_points=summary_data['summary_points'],
                    summary_extracted=summary_data['summary_extracted'],
                    summary_confidence=summary_data['summary_confidence']
                )
                
            except json.JSONDecodeError as e:
                logger.warning(f"Combined JSON decode failed: {e}")
                return self._create_failed_combined_extraction(f"JSON decode error: {e}", job_title)
                
            except Exception as e:
                logger.error(f"Error processing combined response: {e}")
                return self._create_failed_combined_extraction(f"Processing error: {e}", job_title)
                
        except Exception as e:
            logger.error(f"Unexpected error in combined response parsing: {e}")
            return self._create_failed_combined_extraction(f"Unexpected error: {e}", job_title)

    def _extract_experience_from_combined(self, data: Dict, job_title: str = "") -> Dict:
        """Extract and validate experience data from combined response."""
        try:
            # Extract experience fields with validation
            min_years = data.get('min_experience_years', 0)
            if not isinstance(min_years, int) or min_years < 0 or min_years > 50:
                min_years, confidence = self._infer_experience_from_title(job_title)
                extracted = False
            else:
                extracted = data.get('experience_extracted', False)
                confidence = data.get('experience_confidence', 0.5)
            
            return {
                'min_experience_years': min_years,
                'experience_type': data.get('experience_type', 'minimum'),
                'experience_details': data.get('experience_details', f"Extracted from job analysis for {job_title}"),
                'experience_extracted': extracted,
                'experience_confidence': max(0.1, min(1.0, confidence))
            }
        except Exception as e:
            logger.warning(f"Error extracting experience from combined response: {e}")
            min_years, confidence = self._infer_experience_from_title(job_title)
            return {
                'min_experience_years': min_years,
                'experience_type': 'minimum',
                'experience_details': f"Fallback: inferred from title '{job_title}'",
                'experience_extracted': False,
                'experience_confidence': confidence
            }

    def _extract_skills_from_combined(self, data: Dict, job_title: str = "") -> Dict:
        """Extract and validate skills data from combined response."""
        try:
            skills = data.get('skills', [])
            if not isinstance(skills, list):
                skills = []
            
            # Validate and clean skills
            clean_skills = []
            for skill in skills[:25]:  # Max 25 skills
                if isinstance(skill, str) and skill.strip():
                    clean_skills.append(skill.strip())
            
            # If no skills found, create fallback
            if not clean_skills:
                clean_skills = self._generate_fallback_skills(job_title)
                extracted = False
                confidence = 0.1
            else:
                extracted = data.get('skills_extracted', True)
                confidence = data.get('skills_confidence', 0.8)
            
            return {
                'skills': clean_skills,
                'skills_extracted': extracted,
                'skills_confidence': max(0.1, min(1.0, confidence))
            }
        except Exception as e:
            logger.warning(f"Error extracting skills from combined response: {e}")
            return {
                'skills': self._generate_fallback_skills(job_title),
                'skills_extracted': False,
                'skills_confidence': 0.1
            }

    def _extract_summary_from_combined(self, data: Dict, job_title: str = "") -> Dict:
        """Extract and validate summary data from combined response."""
        try:
            summary_points = data.get('summary_points', [])
            if not isinstance(summary_points, list):
                summary_points = []
            
            # Validate and clean summary points
            clean_points = []
            for point in summary_points:
                if isinstance(point, str) and point.strip():
                    clean_points.append(point.strip())
            
            # Ensure exactly 5 points
            if len(clean_points) < 5:
                # Pad with generic points if needed
                generic_additions = [
                    "The role involves specific responsibilities and duties",
                    "Relevant experience and skills are required",
                    "The position offers professional growth opportunities",
                    "Team collaboration and communication are important",
                    "Additional details are available in the full job description"
                ]
                while len(clean_points) < 5 and generic_additions:
                    clean_points.append(generic_additions.pop(0))
                extracted = False
                confidence = 0.3
            elif len(clean_points) > 5:
                clean_points = clean_points[:5]
                extracted = data.get('summary_extracted', True)
                confidence = data.get('summary_confidence', 0.8)
            else:
                extracted = data.get('summary_extracted', True)
                confidence = data.get('summary_confidence', 0.8)
            
            return {
                'summary_points': clean_points,
                'summary_extracted': extracted,
                'summary_confidence': max(0.1, min(1.0, confidence))
            }
        except Exception as e:
            logger.warning(f"Error extracting summary from combined response: {e}")
            return {
                'summary_points': [
                    f"Position: {job_title}" if job_title else "Professional role opportunity",
                    "Technical skills and experience required",
                    "Team-based work environment",
                    "Career development and growth potential",
                    "Additional details available in full job posting"
                ],
                'summary_extracted': False,
                'summary_confidence': 0.1
            }

    def _generate_fallback_skills(self, job_title: str = "") -> list:
        """Generate fallback skills based on job title."""
        if not job_title:
            return ["Communication", "Problem Solving", "Teamwork", "Time Management"]
        
        title_lower = job_title.lower()
        fallback_skills = ["Communication", "Problem Solving", "Teamwork"]
        
        # Add title-specific skills
        if any(term in title_lower for term in ['developer', 'engineer', 'programmer']):
            fallback_skills.extend(["Programming", "Software Development", "Debugging"])
        elif any(term in title_lower for term in ['data', 'analyst', 'analytics']):
            fallback_skills.extend(["Data Analysis", "SQL", "Excel"])
        elif any(term in title_lower for term in ['manager', 'lead', 'director']):
            fallback_skills.extend(["Leadership", "Project Management", "Strategic Planning"])
        elif any(term in title_lower for term in ['designer', 'ui', 'ux']):
            fallback_skills.extend(["Design", "User Experience", "Creative Problem Solving"])
        else:
            fallback_skills.extend(["Industry Knowledge", "Time Management"])
        
        return fallback_skills[:25]

    def _create_failed_combined_extraction(self, reason: str, job_title: str = "") -> CombinedJobData:
        """Create a fallback combined response when extraction fails."""
        
        # Generate fallback experience
        min_years, exp_confidence = self._infer_experience_from_title(job_title)
        
        # Generate fallback skills
        fallback_skills = self._generate_fallback_skills(job_title)
        
        # Generate fallback summary
        fallback_summary = [
            f"Position: {job_title}" if job_title else "Professional role opportunity",
            "Relevant experience and skills required for this position",
            "Work as part of a collaborative team environment",
            "Opportunities for professional development and growth",
            "Additional details available in the complete job description"
        ]
        
        return CombinedJobData(
            # Experience fields
            min_experience_years=min_years,
            experience_type="minimum",
            experience_details=f"Fallback: {reason}",
            experience_extracted=False,
            experience_confidence=exp_confidence,
            
            # Skills fields
            skills=fallback_skills,
            skills_extracted=False,
            skills_confidence=0.1,
            
            # Summary fields
            summary_points=fallback_summary,
            summary_extracted=False,
            summary_confidence=0.1
        )
