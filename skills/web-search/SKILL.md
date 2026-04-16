---
name: web-search
description: Search for information from the internet using web search APIs. Use when the user needs to find current information, facts, news, or data that is not in the training data. Triggers: "search for", "look up", "find information about", "what is the latest", "current news about", "search online", "web search", "google", "bing search".
type: custom
created: 2026-04-16T08:46:56.101214
---

# Web Search Skill

Search for current information from the internet using web search capabilities.

## When to Use This Skill

This skill is already triggered by the description. Use it when:
- User asks for current information not in training data
- User needs real-time data, news, or facts
- User asks to "search", "look up", or "find" something online

## How to Search

### Method 1: Using Python with requests (Recommended)

Use Python with `requests` library to call search APIs:

```python
import requests
import json

def search_web(query, num_results=5):
    """
    Search the web using a search API.
    
    Args:
        query: Search query string
        num_results: Number of results to return (default: 5)
    
    Returns:
        List of search results with title, link, and snippet
    """
    # Example using DuckDuckGo API (no API key required)
    url = "https://duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    params = {"q": query}
    
    response = requests.get(url, headers=headers, params=params)
    # Parse results...
    return results
```

### Method 2: Using search engines directly

For simple searches, construct search URLs:
- Google: `https://www.google.com/search?q={query}`
- Bing: `https://www.bing.com/search?q={query}`
- DuckDuckGo: `https://duckduckgo.com/?q={query}`

### Method 3: Using SerpAPI (if API key available)

```python
import requests

def search_with_serpapi(query, api_key):
    url = "https://serpapi.com/search"
    params = {
        "q": query,
        "api_key": api_key,
        "engine": "google"
    }
    response = requests.get(url, params=params)
    return response.json()
```

## Best Practices

1. **Be specific** - Use detailed queries for better results
2. **Verify sources** - Check the credibility of sources
3. **Summarize** - Provide concise summaries of findings
4. **Cite sources** - Always include links to sources
5. **Handle errors** - Gracefully handle API failures or rate limits

## Example Usage

**User:** "Search for the latest news about AI"

**Action:**
```python
import requests
from bs4 import BeautifulSoup

def search_news(query):
    # Implementation here
    results = search_web(f"latest news {query}")
    return format_results(results)
```

**Response:** "Here are the latest news about AI: [summarized results with sources]"

## Limitations

- Some search APIs require API keys
- Rate limits may apply
- Results depend on search engine used
- Real-time data may have slight delays
