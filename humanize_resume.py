
import os
from ai_humanizer import AIHumanizer

class ResumeHumanizer:
    def __init__(self, api_key, email):
        self.humanizer = AIHumanizer(api_key, email)

    def humanize(self, text_to_humanize):
        """
        Uses the AIHumanizer class to make the resume sound more natural.
        """
        return self.humanizer.humanize(text_to_humanize, model="0") # Using "quality" model for resumes

if __name__ == '__main__':
    # Example usage
    api_key = os.getenv("AIHUMANIZE_API_KEY")
    email = os.getenv("AIHUMANIZE_EMAIL")

    if not api_key or not email:
        print("Error: Please set AIHUMANIZE_API_KEY and AIHUMANIZE_EMAIL environment variables.")
    else:
        humanizer_wrapper = ResumeHumanizer(api_key, email)
        
        ai_text = """
        Highly motivated and results-oriented AI/ML Engineer with over 5 years of demonstrated experience in designing, developing, and deploying machine learning models. Proficient in Python, TensorFlow, and PyTorch. Proven ability to lead projects and collaborate with cross-functional teams to deliver innovative AI solutions.
        """
        
        humanized_version = humanizer_wrapper.humanize(ai_text)
        
        print("\n--- Original Text ---")
        print(ai_text)
        print("\n--- Humanized Text ---")
        print(humanized_version)
