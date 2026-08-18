"""
Core Socratic dialogue engine using Gemini multi-turn chat.
"""
import logging
from google import genai
from google.genai import types

from config import GEMINI_API_KEY
from cognitive_debugger.prompts import SYSTEM_PROMPT, ROUND_LABELS, FINAL_PROMPT

logger = logging.getLogger(__name__)
client = genai.Client(api_key=GEMINI_API_KEY)

TOTAL_ROUNDS = 5

class CognitiveDebuggerBot:
    """Manages a multi-turn Socratic questioning session."""
    
    def __init__(self):
        self.current_round = 0
        self.history = []  # List of {"role": "user"/"model", "text": str}
        self.is_complete = False
        self.final_report = None
        
    def _build_contents(self):
        """Build the contents list for the Gemini API call."""
        contents = []
        for msg in self.history:
            contents.append(types.Content(
                role=msg["role"],
                parts=[types.Part(text=msg["text"])]
            ))
        return contents
    
    def start_session(self, initial_worry: str) -> str:
        """Start a new debugging session with the user's initial worry."""
        self.current_round = 1
        self.history = [{"role": "user", "text": initial_worry}]
        
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=self._build_contents(),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.7
            )
        )
        
        reply = response.text
        self.history.append({"role": "model", "text": reply})
        return reply
    
    def next_round(self, user_response: str) -> str:
        """Process the user's response and advance to the next round."""
        self.current_round += 1
        self.history.append({"role": "user", "text": user_response})
        
        if self.current_round > TOTAL_ROUNDS:
            # All 5 rounds done, generate final report
            return self._generate_report()
        
        # Add a hint about which round we're on
        round_hint = f"\n[系统提示：现在进入{ROUND_LABELS[self.current_round - 1]}，请严格按照框架提问]"
        self.history[-1]["text"] += round_hint
        
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=self._build_contents(),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.7
            )
        )
        
        reply = response.text
        # Restore the user's original message by stripping the hint
        self.history[-1]["text"] = self.history[-1]["text"].replace(round_hint, "")
        self.history.append({"role": "model", "text": reply})
        return reply
    
    def _generate_report(self) -> str:
        """Generate the final cognitive debugging report."""
        # Append to the last user message instead of adding a new one
        self.history[-1]["text"] += f"\n\n[系统提示：{FINAL_PROMPT}]"
        
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=self._build_contents(),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.5
            )
        )
        
        report = response.text
        # Remove the final prompt from the last user message
        self.history[-1]["text"] = self.history[-1]["text"].replace(f"\n\n[系统提示：{FINAL_PROMPT}]", "")
        self.history.append({"role": "model", "text": report})
        self.is_complete = True
        self.final_report = report
        return report
    
    def get_round_label(self) -> str:
        """Get the current round label."""
        if self.current_round <= TOTAL_ROUNDS:
            return ROUND_LABELS[self.current_round - 1]
        return "认知调试报告"
    
    def get_full_dialogue_markdown(self) -> str:
        """Export the entire session as formatted Markdown for Obsidian."""
        md = "## 🧠 认知调试会话记录\n\n"
        round_num = 0
        for msg in self.history:
            if msg["role"] == "user" and not msg["text"].startswith("[系统提示") and not msg["text"].startswith("用户已经完成"):
                round_num += 1
                if round_num == 1:
                    md += f"### 初始烦恼\n> {msg['text']}\n\n"
                else:
                    md += f"### 第{round_num - 1}轮回答\n> {msg['text']}\n\n"
            elif msg["role"] == "model":
                md += f"{msg['text']}\n\n---\n\n"
        return md
