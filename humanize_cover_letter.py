
import os
from ai_humanizer import AIHumanizer

class CoverLetterHumanizer:
    def __init__(self, api_key, email):
        self.humanizer = AIHumanizer(api_key, email)

    def humanize(self, text_to_humanize):
        """
        Uses the AIHumanizer class to make the cover letter sound more natural.
        """
        return self.humanizer.humanize(text_to_humanize, model="1") # Using "balance" model

if __name__ == '__main__':
    # Example usage
    api_key = os.getenv("AIHUMANIZE_API_KEY")
    email = os.getenv("AIHUMANIZE_EMAIL")

    if not api_key or not email:
        print("Error: Please set AIHUMANIZE_API_KEY and AIHUMANIZE_EMAIL environment variables.")
    else:
        humanizer_wrapper = CoverLetterHumanizer(api_key, email)
        
        ai_text = """
        As a highly skilled AI/ML Engineer, I am writing to express my interest in the AI Engineer position at TechCorp. My experience in Python, TensorFlow, and AWS aligns perfectly with the job requirements. I am confident that I can contribute significantly to your team.
        """
        
        humanized_version = humanizer_wrapper.humanize(ai_text)
        
        print("\n--- Original Text ---")
        print(ai_text)
        print("\n--- Humanized Text ---")
        print(humanized_version)
