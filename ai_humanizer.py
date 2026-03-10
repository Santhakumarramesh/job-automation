
import os
import requests

class AIHumanizer:
    def __init__(self, api_key, email):
        self.api_key = api_key
        self.email = email
        self.base_url = "https://aihumanize.io/api/v1"

    def humanize(self, text, model="0"):
        """
        Calls the aihumanize.io API to humanize the given text.
        Model: "0" for quality, "1" for balance, "2" for enhanced.
        """
        if not all([self.api_key, self.email, text]):
            print("API key, email, or text is missing. Skipping humanization.")
            return text

        if len(text) < 100:
            print("Text is too short for humanization (< 100 chars). Skipping.")
            return text

        print(f"🤖 Calling aihumanize.io API to humanize text (model: {model})...")

        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "mail": self.email,
            "data": text
        }

        try:
            response = requests.post(f"{self.base_url}/rewrite", headers=headers, json=payload, timeout=60)
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

            result = response.json()

            if result.get("code") == 200 and "data" in result:
                print("✅ Text humanized successfully.")
                return result["data"]
            else:
                print(f"⚠️ API Error: {result.get('msg', 'Unknown error')} (Code: {result.get('code')})")
                return text # Return original text on failure

        except requests.exceptions.RequestException as e:
            print(f"❌ HTTP Request failed: {e}")
            return text # Return original text on failure

if __name__ == '__main__':
    # Example Usage
    api_key = os.getenv("AIHUMANIZE_API_KEY")
    email = os.getenv("AIHUMANIZE_EMAIL")

    if not api_key or not email:
        print("Error: Please set AIHUMANIZE_API_KEY and AIHUMANIZE_EMAIL environment variables.")
    else:
        humanizer = AIHumanizer(api_key, email)
        
        ai_text = "Frequent exercise has numerous benefits for the body. It is imperative for individuals to engage in physical activity to maintain optimal health and well-being. Furthermore, the consumption of a balanced diet is crucial."
        
        humanized_text = humanizer.humanize(ai_text)

        print("\n--- Original Text ---")
        print(ai_text)
        print("\n--- Humanized Text ---")
        print(humanized_text)
