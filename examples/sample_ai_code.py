"""
Sample AI-generated code containing common hallucinations
Used for testing AI Auditor
"""

# This contains common AI hallucinations
import hallucinated_module  # Doesn't exist

def process_items(items=[]):  # Mutable default - AI001 
    items.append("new")
    return items

my_list = [1, 2, 3]
my_list.push(4)  # JS leakage - JS001 

def calculate():  # Missing return - logic hallucination
    x = 5 + 3
    # TODO: implement rest  # Placeholder code
