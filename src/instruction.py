"""
Instruction Adherence Module for AI Auditor
Detects if AI followed custom instructions using pattern matching (FREE!)

No API key required - works 100% offline!
Based on Offscript's research: https://ar5iv.labs.arxiv.org/html/2512.10172
"""

import re
from typing import List, Dict, Any


def check_instruction_violations(
    prompt: str,
    response: str,
    instructions: List[str]
) -> Dict[str, Any]:
    """
    Check instruction adherence using improved pattern matching.
    Only flags clear violations to avoid false positives.
    """
    
    violations = []
    score = 100
    response_lower = response.lower()
    
    for instruction in instructions:
        instruction_lower = instruction.lower()
        violated = False
        reason = ""
        
        # === Type Hints ===
        if "type hint" in instruction_lower:
            if ": " not in response and "->" not in response:
                violated = True
                reason = f"Instruction '{instruction}' - Type hints not found"
        
        # === Docstrings ===
        elif "docstring" in instruction_lower or "documentation" in instruction_lower:
            if '"""' not in response and "'''" not in response:
                violated = True
                reason = f"Instruction '{instruction}' - Docstring not found"
        
        # === Return Values ===
        elif "return" in instruction_lower and "function" in instruction_lower:
            if "return " not in response and "return" not in response_lower:
                violated = True
                reason = f"Instruction '{instruction}' - Missing return statement"
        
        # === Comments ===
        elif "comment" in instruction_lower:
            if "#" not in response and '"""' not in response and "'''" not in response:
                violated = True
                reason = f"Instruction '{instruction}' - No comments found"
        
        # === Spelling checks ===
        elif "spelling" in instruction_lower or "vocabulary" in instruction_lower:
            if "colour" in instruction_lower and "color" in response_lower and "colour" not in response_lower:
                violated = True
                reason = f"Instruction '{instruction}' - Used 'color' instead of 'colour'"
            elif "color" in instruction_lower and "colour" in response_lower and "color" not in response_lower:
                violated = True
                reason = f"Instruction '{instruction}' - Used 'colour' instead of 'color'"
        
        # === Markdown formatting ===
        elif "markdown" in instruction_lower:
            has_markdown = any([
                "##" in response,
                "- " in response,
                "1." in response,
                "**" in response,
                "* " in response,
                "`" in response
            ])
            if not has_markdown:
                violated = True
                reason = f"Instruction '{instruction}' - Markdown formatting not found"
        
        # === Word/character limits ===
        elif "under" in instruction_lower or "less than" in instruction_lower or "concise" in instruction_lower:
            import re
            numbers = re.findall(r'\d+', instruction)
            if numbers:
                limit = int(numbers[0])
                word_count = len(response.split())
                if word_count > limit:
                    violated = True
                    reason = f"Instruction '{instruction}' - Response has {word_count} words, exceeds {limit} word limit"
            elif "concise" in instruction_lower and len(response.split()) > 100:
                violated = True
                reason = f"Instruction '{instruction}' - Response has {len(response.split())} words, expected concise"
        
        # === Function/class/import checks ===
        elif "function" in instruction_lower and "def " not in response:
            violated = True
            reason = f"Instruction '{instruction}' - Expected function but not found"
        
        elif "class" in instruction_lower and "class " not in response:
            violated = True
            reason = f"Instruction '{instruction}' - Expected class but not found"
        
        elif "import" in instruction_lower and "import " not in response:
            violated = True
            reason = f"Instruction '{instruction}' - Expected import but not found"
        
        # === Generic instructions - SKIP (to avoid false positives) ===
        else:
            # Skip instructions like "Handle edge cases", "Error handling", etc.
            # These are too generic to check with pattern matching
            continue
        
        if violated:
            violations.append(reason)
            score -= 10
    
    score = max(0, score)
    
    return {
        'violations': violations,
        'score': score,
        'summary': f"Adherence score: {score}/100. {len(violations)} violation(s) found." if violations else f"✅ All instructions followed! Score: {score}/100",
        'mode': 'pattern-matching',
        'instructions_checked': len(instructions)
    }

def audit_instruction_adherence(
    prompt: str,
    response: str,
    instructions: List[str],
    model: str = "gpt-4o-mini"  # Kept for compatibility, not used without API
) -> Dict[str, Any]:
    """
    Audit whether an AI response follows the given instructions.
    Uses FREE pattern matching by default.
    """
    
    # Try to use OpenAI if available, otherwise fall back to pattern matching
    import os
    if os.getenv("OPENAI_API_KEY"):
        try:
            import openai
            client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            
            instructions_text = "\n".join(f"- {i}" for i in instructions)
            
            auditor_prompt = f"""
You are an expert auditor. Your job is to check if an AI response follows ALL given instructions.

--- ORIGINAL PROMPT ---
{prompt}

--- INSTRUCTIONS TO CHECK ---
{instructions_text}

--- AI RESPONSE TO AUDIT ---
{response}

--- YOUR TASK ---
Check the response against EACH instruction. For each instruction:
1. Say whether it was followed or violated
2. Provide evidence from the response
3. Explain why

Format your response as:
1. [Instruction X]: [FOLLOWED/VIOLATED] - [evidence and explanation]

Finally, give an overall score from 0-100 where 100 means all instructions were perfectly followed.
"""
            
            audit_response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a strict compliance auditor."},
                    {"role": "user", "content": auditor_prompt}
                ],
                temperature=0.1
            )
            
            audit_text = audit_response.choices[0].message.content
            
            violations = []
            for line in audit_text.split('\n'):
                if 'VIOLATED' in line.upper() or 'FAILED' in line.upper():
                    violations.append(line.strip())
            
            import re
            scores = re.findall(r'\b([0-9]{1,3})\b', audit_text)
            score = int(scores[-1]) if scores else 50
            
            return {
                'violations': violations,
                'score': score,
                'summary': f"Adherence score: {score}/100. {len(violations)} violation(s) found." if violations else f"✅ All instructions followed! Score: {score}/100",
                'mode': 'live-api',
                'instructions_checked': len(instructions)
            }
            
        except Exception as e:
            print(f"⚠️  Falling back to pattern matching due to: {e}")
    
    # Default: FREE pattern matching
    return check_instruction_violations(prompt, response, instructions)


def test_instruction_adherence():
    """Test function to demonstrate instruction adherence auditing (FREE!)"""
    
    print("=" * 60)
    print("🧪 Testing Instruction Adherence Auditing (Free Mode)")
    print("=" * 60)
    print("No API key required - using pattern matching! 🎉\n")
    
    # Test case 1: Code examples
    prompt = "Write a Python function to add two numbers"
    instructions = [
        "Use type hints in the function signature",
        "Add a docstring"
    ]
    
    response_good = """def add_numbers(a: int, b: int) -> int:
    \"\"\"Add two numbers together.\"\"\"
    return a + b"""
    
    response_bad = """def add_numbers(a, b):
    # add two numbers
    return a + b"""
    
    print("📝 Test 1: Good Response (following instructions)")
    result = audit_instruction_adherence(prompt, response_good, instructions)
    print(f"   Mode: {result['mode']}")
    print(f"   Score: {result['score']}/100")
    print(f"   Summary: {result['summary']}")
    
    print("\n📝 Test 2: Bad Response (violating instructions)")
    result = audit_instruction_adherence(prompt, response_bad, instructions)
    print(f"   Mode: {result['mode']}")
    print(f"   Score: {result['score']}/100")
    print(f"   Summary: {result['summary']}")
    if result['violations']:
        print("   Violations:")
        for v in result['violations']:
            print(f"     - {v}")
    
    # Test case 2: Multiple instructions
    print("\n📝 Test 3: Complex Instructions")
    instructions = [
        "Use Australian spelling (colour instead of color)",
        "Be concise, under 20 words",
        "Include markdown formatting"
    ]
    
    response_mixed = "Here is a **concise** response using colour with markdown."
    result = audit_instruction_adherence(prompt, response_mixed, instructions)
    print(f"   Mode: {result['mode']}")
    print(f"   Score: {result['score']}/100")
    print(f"   Summary: {result['summary']}")
    if result['violations']:
        print("   Violations:")
        for v in result['violations']:
            print(f"     - {v}")
    
    print("\n✅ All tests complete!")


if __name__ == "__main__":
    test_instruction_adherence()
