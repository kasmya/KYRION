import requests
from bs4 import BeautifulSoup
from urllib.parse import urlsplit
from typing import Dict, List

def extract_page_info(url: str) -> Dict:
    """
    Extracts page title, meta description, headings, hyperlinks, and images from a given URL.

    Args:
    url (str): The URL of the webpage to extract information from.

    Returns:
    Dict: A dictionary containing the extracted page information.
    """

    # Validate URL
    try:
        result = urlsplit(url)
        if not all([result.scheme, result.netloc]):
            raise ValueError("Invalid URL")
    except ValueError as e:
        raise ValueError("Invalid URL") from e

    try:
        # Send HTTP request with a timeout
        response = requests.get(url, timeout=5)
        response.raise_for_status()
    except requests.RequestException as e:
        raise Exception("Failed to retrieve the webpage") from e

    # Parse HTML content
    soup = BeautifulSoup(response.text, "html.parser")

    # Extract page title
    title = soup.find("title").text if soup.find("title") else None

    # Extract meta description
    meta_description = soup.find("meta", attrs={"name": "description"}).get("content") if soup.find("meta", attrs={"name": "description"}) else None

    # Extract headings
    headings = []
    for heading in soup.find_all(["h1", "h2", "h3"]):
        headings.append(heading.text.strip())

    # Extract hyperlinks
    hyperlinks = []
    for link in soup.find_all("a", href=True):
        # Get the href attribute value
        href = link.get("href")
        # Check if the href is a valid URL
        try:
            result = urlsplit(href)
            if not all([result.scheme, result.netloc]):
                href = url + href if href.startswith("/") else href
        except ValueError:
            # If href is not a valid URL, skip it
            continue
        hyperlinks.append(href)

    # Extract images
    images = []
    for img in soup.find_all("img", src=True):
        # Get the src attribute value
        src = img.get("src")
        # Check if the src is a valid URL
        try:
            result = urlsplit(src)
            if not all([result.scheme, result.netloc]):
                src = url + src if src.startswith("/") else src
        except ValueError:
            # If src is not a valid URL, skip it
            continue
        images.append(src)

    # Return extracted information
    return {
        "title": title,
        "meta_description": meta_description,
        "headings": headings,
        "hyperlinks": hyperlinks,
        "images": images
    }

# Example usage:
if __name__ == "__main__":
    url = "http://example.com"
    try:
        page_info = extract_page_info(url)
        print(page_info)
    except Exception as e:
        print(f"An error occurred: {e}")