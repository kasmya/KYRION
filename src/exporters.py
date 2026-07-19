"""
Export audit results in various formats
"""
import json
from typing import Dict, Any


def to_json(results: Dict[str, Any]) -> str:
    """
    Export audit results as JSON with proper escaping.
    
    Args:
        results: Dictionary containing audit results
        
    Returns:
        str: JSON string of the results
    """
    # Use ensure_ascii=False to keep Unicode characters readable
    # Use default=str to handle non-serializable objects
    return json.dumps(results, indent=2, ensure_ascii=False, default=str)


def to_json_file(results: Dict[str, Any], filename: str) -> None:
    """
    Save audit results to a JSON file.
    
    Args:
        results: Dictionary containing audit results
        filename: Path to save the JSON file
    """
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
