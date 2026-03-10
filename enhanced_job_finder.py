import os
import pandas as pd
from apify_client import ApifyClient
from datetime import datetime
import json

class EnhancedJobFinder:
    def __init__(self, apify_api_key):
        self.client = ApifyClient(apify_api_key)
        self.results_df = pd.DataFrame()
        
    def analyze_resume_for_keywords(self, resume_text):
        """Extract keywords and skills from resume using NLP"""
        # This would use your existing job analyzer
        # For now, we'll extract basic keywords
        keywords = {
            'skills': [],
            'experience_level': '',
            'preferred_locations': [],
            'job_titles': []
        }
        
        # Extract skills (this would be enhanced with your existing NLP)
        common_skills = ['Python', 'Machine Learning', 'AI', 'AWS', 'TensorFlow', 'PyTorch', 'SQL', 'JavaScript']
        for skill in common_skills:
            if skill.lower() in resume_text.lower():
                keywords['skills'].append(skill)
                
        # Extract job titles
        if 'engineer' in resume_text.lower():
            keywords['job_titles'].extend(['AI Engineer', 'Machine Learning Engineer', 'Software Engineer'])
        if 'data scientist' in resume_text.lower():
            keywords['job_titles'].append('Data Scientist')
            
        # Extract locations
        if 'usa' in resume_text.lower() or 'united states' in resume_text.lower():
            keywords['preferred_locations'].extend(['USA', 'Remote', 'United States'])
            
        return keywords
    
    def find_jobs_with_apify(self, resume_text, max_results=50):
        """Find jobs using Apify based on resume analysis"""
        # Analyze resume for keywords
        keywords = self.analyze_resume_for_keywords(resume_text)
        
        if not keywords['job_titles']:
            keywords['job_titles'] = ['AI Engineer', 'Machine Learning Engineer', 'Data Scientist']
            
        if not keywords['skills']:
            keywords['skills'] = ['Python', 'Machine Learning', 'AI']
            
        if not keywords['preferred_locations']:
            keywords['preferred_locations'] = ['USA', 'Remote']
        
        # Use AI Deep Job Search actor
        run_input = {
            "target_job_titles": keywords['job_titles'][:3],  # Limit to 3 titles
            "locations": keywords['preferred_locations'][:3],  # Limit to 3 locations
            "preferred_skills": keywords['skills'][:10],  # Limit to 10 skills
            "undesirable_skills": [],
            "preferred_industries": ["Technology", "AI/ML", "Software"],
            "undesirable_industries": ["Defense", "Tobacco"],
            "experience_levels": ["Mid-level", "Senior", "Lead"],
            "max_results": max_results,
            "additional_requirements": f"Looking for roles that match this candidate's background: {resume_text[:500]}..."
        }
        
        print(f"Searching for jobs with titles: {keywords['job_titles']}")
        print(f"Locations: {keywords['preferred_locations']}")
        print(f"Skills: {keywords['skills']}")
        
        try:
            # Run the Apify actor
            run = self.client.actor("jobo.world/ai-deep-job-search").call(run_input=run_input)
            
            # Fetch results
            dataset = self.client.dataset(run["defaultDatasetId"])
            jobs = list(dataset.iterate_items())
            
            # Convert to DataFrame for better processing
            jobs_df = pd.DataFrame(jobs)
            
            # Add metadata
            jobs_df['search_date'] = datetime.now()
            jobs_df['resume_match_score'] = jobs_df.apply(lambda row: self.calculate_resume_match(row, keywords), axis=1)
            
            # Sort by match score
            jobs_df = jobs_df.sort_values('resume_match_score', ascending=False)
            
            print(f"Found {len(jobs_df)} jobs")
            
            return jobs_df
            
        except Exception as e:
            print(f"Error finding jobs: {e}")
            return pd.DataFrame()
    
    def calculate_resume_match(self, job_row, resume_keywords):
        """Calculate how well a job matches the resume"""
        match_score = 0
        
        # Check job title match
        job_title = str(job_row.get('title', '')).lower()
        for title in resume_keywords['job_titles']:
            if title.lower() in job_title:
                match_score += 30
                
        # Check skills match
        job_description = str(job_row.get('description', '')).lower()
        for skill in resume_keywords['skills']:
            if skill.lower() in job_description:
                match_score += 10
                
        # Check location match
        job_location = str(job_row.get('location', '')).lower()
        for location in resume_keywords['preferred_locations']:
            if location.lower() in job_location:
                match_score += 20
                
        return min(match_score, 100)  # Cap at 100
    
    def save_results_to_excel(self, jobs_df, filename='job_search_results.xlsx'):
        """Save job search results to Excel with multiple sheets"""
        if jobs_df.empty:
            print("No jobs to save")
            return
            
        # Create Excel writer object
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            # Main results sheet
            main_columns = ['title', 'company', 'location', 'description', 'url', 'resume_match_score', 'search_date']
            main_df = jobs_df[main_columns] if all(col in jobs_df.columns for col in main_columns) else jobs_df
            main_df.to_excel(writer, sheet_name='Job_Results', index=False)
            
            # Summary statistics sheet
            summary_data = {
                'Metric': ['Total Jobs Found', 'Average Match Score', 'Top Company', 'Top Location'],
                'Value': [
                    len(jobs_df),
                    jobs_df['resume_match_score'].mean() if 'resume_match_score' in jobs_df.columns else 0,
                    jobs_df['company'].mode().iloc[0] if 'company' in jobs_df.columns and not jobs_df['company'].mode().empty else 'N/A',
                    jobs_df['location'].mode().iloc[0] if 'location' in jobs_df.columns and not jobs_df['location'].mode().empty else 'N/A'
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Top matches sheet (jobs with score > 70)
            if 'resume_match_score' in jobs_df.columns:
                top_matches = jobs_df[jobs_df['resume_match_score'] > 70]
                if not top_matches.empty:
                    top_matches[main_columns].to_excel(writer, sheet_name='Top_Matches', index=False)
            
        print(f"Results saved to {filename}")
        return filename

if __name__ == '__main__':
    # Example usage
    apify_key = os.getenv("APIFY_API_KEY")
    if not apify_key:
        print("Error: APIFY_API_KEY environment variable not set.")
    else:
        finder = EnhancedJobFinder(apify_key)
        
        # Sample resume text (you would use your actual resume)
        sample_resume = """
        Santhakumar Ramesh
        AI/ML Engineer with 5+ years of experience in Python, Machine Learning, and Cloud technologies.
        Expertise in TensorFlow, PyTorch, AWS, and building scalable AI solutions.
        Looking for opportunities in USA, preferably remote.
        """
        
        jobs_df = finder.find_jobs_with_apify(sample_resume, max_results=20)
        
        if not jobs_df.empty:
            finder.save_results_to_excel(jobs_df)
            print("\nTop 5 matches:")
            print(jobs_df[['title', 'company', 'location', 'resume_match_score']].head())
