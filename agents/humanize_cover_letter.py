
import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import AgentState

def humanize_cover_letter(state: AgentState):
    """
    Humanizes the generated cover letter text using a sophisticated prompt with GPT-4o.
    This avoids the need for a separate, paid humanizer service.
    """
    print("🤖 Self-humanizing cover letter text with GPT-4o...")
    
    fast = os.getenv("CCP_FAST_PIPELINE", "").strip().lower() in ("1", "true", "yes")
    cover_letter_text = state.get("cover_letter_text", "")
    if fast:
        # Speed mode: do not run LLM humanization.
        return {"humanized_cover_letter_text": cover_letter_text}

    model = os.getenv("CCP_OPENAI_MODEL") or ("gpt-4o-mini" if fast else "gpt-4o")
    llm = ChatOpenAI(model=model, temperature=0.75)  # Slightly higher temp for creativity
    
    if not cover_letter_text or len(cover_letter_text) < 100:
        print("⚠️ Cover letter text is too short to humanize. Skipping.")
        return {"humanized_cover_letter_text": cover_letter_text}

    system_prompt = """You are an expert editor tasked with rewriting an AI-generated cover letter to be indistinguishable from one written by a passionate, articulate human.
    Your goal is to pass AI detection tools by increasing the text's perplexity and burstiness.

    CRITICAL INSTRUCTIONS:
    1.  **Inject Personality:** The tone should be confident and professional, but with a conversational and enthusiastic spark. It should not sound robotic or generic.
    2.  **Vary Sentence Flow:** Mix short, punchy sentences with longer, more descriptive ones to create a natural rhythm.
    3.  **Use Human-like Transitions:** Avoid clunky words like "Furthermore," "Moreover," or "In conclusion." Use more natural connective phrases.
    4.  **Show, Don't Tell:** Instead of saying "I am a good fit," provide a specific, concise example or connection that proves it.
    5.  **Output ONLY the rewritten text.** Do not add any commentary before or after.
    """

    human_prompt = f"Please rewrite the following cover letter to make it sound like it was written by a real, enthusiastic person. Increase the perplexity and burstiness of the language, while retaining all key information and a professional tone:\n\n---\n\n{cover_letter_text}"

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]
    
    try:
        response = llm.invoke(messages)
        humanized_text = response.content
        print("✅ Cover letter text has been successfully self-humanized.")
        return {"humanized_cover_letter_text": humanized_text}
    except Exception as e:
        print(f"❌ Error during self-humanization: {e}. Returning original text.")
        return {"humanized_cover_letter_text": cover_letter_text}
