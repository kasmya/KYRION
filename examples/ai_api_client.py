"""
API client for weather data - AI Generated
"""

import requests
from typing import Optional, Dict, Any
import time


def get_weather(city: str, api_key: str) -> Optional[Dict[str, Any]]:
    """
    Fetch weather data for a given city.
    
    Args:
        city: Name of the city
        api_key: API key for authentication
        
    Returns:
        Dictionary with weather data or None if error
    """
    if not city:
        print("City is required")
        return None
    
    if not api_key:
        print("API key is required")
        return None
    
    # TODO: Add rate limiting
    # FIXME: This doesn't handle API rate limits
    
    url = f"http://api.weather.com/data/{city}?key={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                'city': city,
                'temperature': data['temp'],
                'condition': data['weather'],
                'humidity': data.get('humidity', 'N/A')
            }
        else:
            print(f"Error: {response.status_code}")
            return None
            
    except requests.Timeout:
        print("Request timed out")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None
