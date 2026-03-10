import pandas as pd
import numpy as np
from datetime import datetime
import re
import json
import os

class EnhancedATSChecker:
    def __init__(self):
        self.ats_score = 0
        self.feedback = []
        self.keyword_matches = {}
        self.formatting_issues = []
        
    def comprehensive_ats_check(self, resume_text, job_description, job_title, company_name, location):
        """Perform comprehensive ATS check with detailed scoring"""
        
        # Initialize scoring
        self.ats_score = 0
        self.feedback = []
        self.keyword_matches = {}
        self.formatting_issues = []
        
        # 1. Keyword Analysis (40 points)
        keyword_score = self.analyze_keywords(resume_text, job_description, job_title)
        self.ats_score += keyword_score
        
        # 2. Formatting Check (20 points)
        formatting_score = self.check_formatting(resume_text)
        self.ats_score += formatting_score
        
        # 3. Content Structure (20 points)
        structure_score = self.check_structure(resume_text)
        self.ats_score += structure_score
        
        # 4. Location Optimization (10 points)
        location_score = self.check_location_optimization(resume_text, location)
        self.ats_score += location_score
        
        # 5. Company-Specific Optimization (10 points)
        company_score = self.check_company_optimization(resume_text, company_name)
        self.ats_score += company_score
        
        # Ensure we don't exceed 100
        self.ats_score = min(self.ats_score, 100)
        
        # Generate comprehensive feedback
        self.generate_comprehensive_feedback()
        
        return {
            'ats_score': self.ats_score,
            'feedback': self.feedback,
            'keyword_matches': self.keyword_matches,
            'formatting_issues': self.formatting_issues,
            'detailed_breakdown': {
                'keyword_score': keyword_score,
                'formatting_score': formatting_score,
                'structure_score': structure_score,
                'location_score': location_score,
                'company_score': company_score
            }
        }
    
    def analyze_keywords(self, resume_text, job_description, job_title):
        """Analyze keyword matches between resume and job description"""
        score = 0
        
        # Extract keywords from job description
        job_keywords = self.extract_keywords(job_description)
        title_keywords = self.extract_keywords(job_title)
        
        # Combine all target keywords
        all_target_keywords = list(set(job_keywords + title_keywords))
        
        # Check for exact matches
        resume_lower = resume_text.lower()
        matches = 0
        total_keywords = len(all_target_keywords)
        
        for keyword in all_target_keywords:
            if len(keyword) > 2:  # Only check meaningful keywords
                if keyword.lower() in resume_lower:
                    matches += 1
                    self.keyword_matches[keyword] = True
                else:
                    self.keyword_matches[keyword] = False
        
        # Calculate keyword score (max 40 points)
        if total_keywords > 0:
            keyword_percentage = (matches / total_keywords) * 100
            score = min(keyword_percentage * 0.4, 40)  # 40 points max
            
            if keyword_percentage < 50:
                self.feedback.append(f"❌ Only {keyword_percentage:.1f}% of job keywords found in resume")
            elif keyword_percentage < 80:
                self.feedback.append(f"⚠️ {keyword_percentage:.1f}% keyword match - consider adding more relevant keywords")
            else:
                self.feedback.append(f"✅ Excellent keyword match: {keyword_percentage:.1f}%")
        
        return score
    
    def extract_keywords(self, text):
        """Extract important keywords from text"""
        # Common stop words to remove
        stop_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'them', 'their', 'what', 'which', 'who', 'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 's', 't', 'just', 'now'}
        
        # Clean and split text
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        
        # Filter out stop words and short words
        keywords = [word for word in words if word not in stop_words and len(word) > 2]
        
        # Get unique keywords and sort by frequency
        keyword_freq = {}
        for word in keywords:
            keyword_freq[word] = keyword_freq.get(word, 0) + 1
        
        # Return top keywords (limit to avoid too many)
        sorted_keywords = sorted(keyword_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, freq in sorted_keywords[:50]]  # Top 50 keywords
    
    def check_formatting(self, resume_text):
        """Check for ATS-friendly formatting"""
        score = 20  # Start with full score
        
        # Check for problematic formatting
        issues = []
        
        # Check for tables (ATS may struggle)
        if '|' in resume_text or 'table' in resume_text.lower():
            issues.append("Tables detected - may cause parsing issues")
            score -= 5
        
        # Check for images (ATS can't read)
        if 'image' in resume_text.lower() or 'img' in resume_text.lower():
            issues.append("Images detected - ATS cannot process images")
            score -= 10
        
        # Check for special characters that may cause issues
        special_chars = set('!@#$%^&*()+=[]{};:"<>?')
        special_char_count = sum(1 for char in resume_text if char in special_chars)
        if special_char_count > 10:
            issues.append("Excessive special characters may cause parsing issues")
            score -= 3
        
        # Check for consistent formatting
        lines = resume_text.split('\n')
        if len(lines) < 10:
            issues.append("Resume seems too short")
            score -= 5
        
        self.formatting_issues = issues
        
        if not issues:
            self.feedback.append("✅ Excellent ATS-friendly formatting")
        else:
            self.feedback.append(f"⚠️ Formatting issues found: {', '.join(issues)}")
        
        return max(score, 0)
    
    def check_structure(self, resume_text):
        """Check for proper resume structure"""
        score = 20  # Start with full score
        
        # Check for essential sections
        required_sections = ['experience', 'education', 'skills']
        found_sections = []
        
        for section in required_sections:
            if section in resume_text.lower():
                found_sections.append(section)
        
        if len(found_sections) == len(required_sections):
            self.feedback.append("✅ All essential resume sections present")
        else:
            missing = set(required_sections) - set(found_sections)
            self.feedback.append(f"⚠️ Missing sections: {', '.join(missing)}")
            score -= (len(missing) * 5)
        
        # Check for contact information
        contact_patterns = [
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
            r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',  # Phone
        ]
        
        contact_found = 0
        for pattern in contact_patterns:
            if re.search(pattern, resume_text):
                contact_found += 1
        
        if contact_found == 0:
            self.feedback.append("❌ No contact information found")
            score -= 10
        elif contact_found == 1:
            self.feedback.append("⚠️ Limited contact information")
            score -= 5
        else:
            self.feedback.append("✅ Contact information present")
        
        return max(score, 0)
    
    def check_location_optimization(self, resume_text, job_location):
        """Check if resume is optimized for job location"""
        score = 10  # Start with full score
        
        if not job_location:
            return score
        
        # Check if job location is mentioned in resume
        job_location_lower = job_location.lower()
        resume_lower = resume_text.lower()
        
        # Check for exact location match
        if job_location_lower in resume_lower:
            self.feedback.append(f"✅ Job location '{job_location}' found in resume")
            return score
        
        # Check for broader location terms
        location_terms = ['remote', 'usa', 'united states', 'on-site', 'hybrid']
        found_terms = [term for term in location_terms if term in resume_lower]
        
        if found_terms:
            self.feedback.append(f"✅ Location flexibility indicated: {', '.join(found_terms)}")
            score -= 2  # Slight deduction for not exact match
        else:
            self.feedback.append(f"⚠️ Consider adding location information for '{job_location}'")
            score -= 5
        
        return max(score, 0)
    
    def check_company_optimization(self, resume_text, company_name):
        """Check if resume is optimized for specific company"""
        score = 10  # Start with full score
        
        if not company_name:
            return score
        
        company_lower = company_name.lower()
        resume_lower = resume_text.lower()
        
        # Check for company name mention
        if company_lower in resume_lower:
            self.feedback.append(f"✅ Company name '{company_name}' found in resume")
            return score
        
        # Check for industry-related terms (basic check)
        industry_terms = ['technology', 'software', 'ai', 'machine learning', 'data']
        found_terms = [term for term in industry_terms if term in resume_lower]
        
        if found_terms:
            self.feedback.append("✅ Industry-relevant terms present")
            score -= 2
        else:
            self.feedback.append(f"⚠️ Consider tailoring for '{company_name}'")
            score -= 5
        
        return max(score, 0)
    
    def generate_comprehensive_feedback(self):
        """Generate detailed feedback for improvement"""
        if self.ats_score >= 95:
            self.feedback.insert(0, "🎉 EXCELLENT! Your resume is ATS-optimized (95%+)")
        elif self.ats_score >= 85:
            self.feedback.insert(0, "✅ VERY GOOD! Minor improvements needed (85-94%)")
        elif self.ats_score >= 75:
            self.feedback.insert(0, "⚠️ GOOD! Some improvements recommended (75-84%)")
        elif self.ats_score >= 60:
            self.feedback.insert(0, "⚠️ FAIR! Significant improvements needed (60-74%)")
        else:
            self.feedback.insert(0, "❌ NEEDS WORK! Major improvements required (<60%)")
        
        # Add specific improvement suggestions
        if self.ats_score < 100:
            self.feedback.append("\n📋 IMPROVEMENT SUGGESTIONS:")
            
            if self.ats_score < 85:
                self.feedback.append("• Add more relevant keywords from the job description")
            
            if self.formatting_issues:
                self.feedback.append("• Fix formatting issues: " + ", ".join(self.formatting_issues))
            
            if self.ats_score < 90:
                self.feedback.append("• Ensure all essential resume sections are present")
                self.feedback.append("• Include complete contact information")
            
            if any('location' in feedback.lower() for feedback in self.feedback):
                self.feedback.append("• Optimize location information for better chances")
            
            if any('company' in feedback.lower() for feedback in self.feedback):
                self.feedback.append("• Add company-specific information for better targeting")
    
    def save_ats_results_to_excel(self, results, filename='ats_check_results.xlsx'):
        """Save comprehensive ATS check results to Excel"""
        
        # Create main results DataFrame
        main_data = {
            'Check Date': [datetime.now()],
            'ATS Score': [results['ats_score']],
            'Keyword Score': [results['detailed_breakdown']['keyword_score']],
            'Formatting Score': [results['detailed_breakdown']['formatting_score']],
            'Structure Score': [results['detailed_breakdown']['structure_score']],
            'Location Score': [results['detailed_breakdown']['location_score']],
            'Company Score': [results['detailed_breakdown']['company_score']]
        }
        main_df = pd.DataFrame(main_data)
        
        # Create feedback DataFrame
        feedback_data = {
            'Feedback': results['feedback']
        }
        feedback_df = pd.DataFrame(feedback_data)
        
        # Create keyword matches DataFrame
        keyword_data = {
            'Keyword': list(results['keyword_matches'].keys()),
            'Found': list(results['keyword_matches'].values())
        }
        keyword_df = pd.DataFrame(keyword_data)
        
        # Save to Excel with multiple sheets
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            main_df.to_excel(writer, sheet_name='ATS_Score', index=False)
            feedback_df.to_excel(writer, sheet_name='Feedback', index=False)
            keyword_df.to_excel(writer, sheet_name='Keyword_Matches', index=False)
        
        print(f"✅ ATS check results saved to {filename}")
        return filename

if __name__ == '__main__':
    # Example usage
    checker = EnhancedATSChecker()
    
    sample_resume = """
    Santhakumar Ramesh
    AI/ML Engineer with 5+ years of experience in Python, Machine Learning, and Cloud technologies.
    Expertise in TensorFlow, PyTorch, AWS, and building scalable AI solutions.
    Email: santhakumar@example.com
    Phone: (123) 456-7890
    
    EXPERIENCE:
    - Senior AI Engineer at Tech Company (2020-2024)
    - Machine Learning Engineer at Startup (2018-2020)
    
    SKILLS:
    Python, Machine Learning, AI, TensorFlow, PyTorch, AWS, SQL
    
    EDUCATION:
    - Master's in Computer Science
    """
    
    sample_job = {
        'description': 'We are looking for an AI Engineer with expertise in Python, Machine Learning, TensorFlow, and AWS. Experience with PyTorch and cloud technologies required.',
        'title': 'AI Engineer',
        'company': 'TechCorp',
        'location': 'San Francisco, CA'
    }
    
    results = checker.comprehensive_ats_check(
        sample_resume, 
        sample_job['description'], 
        sample_job['title'], 
        sample_job['company'], 
        sample_job['location']
    )
    
    print(f"ATS Score: {results['ats_score']}%")
    print("\nFeedback:")
    for feedback in results['feedback']:
        print(feedback)
    
    # Save results to Excel
    checker.save_ats_results_to_excel(results, 'sample_ats_check.xlsx')