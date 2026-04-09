"""Implements the LLM selector agent"""
from ollama import generate, GenerateResponse
from typing import Literal, Any
from functools import lru_cache

# TODO: make the caller async!
# TODO: Refine the SYSTEM prompts with context by providing the current rules and previous runs (if they exist)
# TODO: implement a better cache system
class LLMSelector:
    SYSTEM = r"""You are the "Selector," a specialized engine dedicated solely to generating Regular Expressions.

YOUR INSTRUCTIONS:
1. Analyze the user's request to identify the specific text pattern, validation rule, or extraction logic required.
2. If the request is valid, output ONLY the raw Regular Expression string.
   - Do NOT use Markdown formatting (no backticks or code blocks).
   - Do NOT provide explanations, introductions, or conclusions.
3. If the request is unrelated to pattern matching (e.g., general knowledge questions, creative writing, or casual conversation), you must return exactly: "Error".

EXAMPLES:
User: "All the Bs at the end of a sequence, but only if there are more than 3."
You: B{4,}$

User: "Find any pattern that matches ABB where A stands for any character and BB stands the sequence of two of the same characters."
You: .(.)\1

User: "What is the capital of France?"
You: Error"""

    def __init__(self):
        self.cache_results: Literal['file', 'program', False] = False
        self.log_results: bool = False

        # params for the call
        self.model: str = 'llama3.1:latest'
        self.temperature: float | None = 0.1
        self.seed: int | None = None

    @lru_cache
    def prompt(self, text) -> str:
        options: dict[str, Any] = {}
        for key in ('temperature', 'seed'):  # the options we care about
            if v:=getattr(self, key) is not None:
                options[key] = v
        response: GenerateResponse = generate(model=self.model, prompt=text, system=self.SYSTEM, options={'temperature': self.temperature, 'seed': self.seed})
        response_str: str = response.response
        if response_str == 'Error':
            raise ValueError('The LLMSelector prompt cannot be about non-selector subject.')
        if self.log_results:
            print(response_str)
        return response_str


if __name__ == '__main__':
    llm = LLMSelector()
    llm.temperature = 0
    print(llm.prompt('My name is isaac'))
