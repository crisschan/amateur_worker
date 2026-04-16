---
name: ai-news-fetcher
description: Fetch latest AI news using Python requests and BeautifulSoup from DuckDuckGo
type: custom
created: 2026-04-16T08:50:34.276383
---

# AI News Fetcher Skill

## Overview
This skill fetches the latest AI news headlines using Python with the `requests` library and `BeautifulSoup` for web scraping from DuckDuckGo search results.

## Prerequisites
```bash
pip install requests beautifulsoup4
```

## Python Implementation

### Basic Search Function
```python
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

def fetch_ai_news(query="latest artificial intelligence news 2024", num_results=10):
    """
    Fetch AI news from DuckDuckGo HTML interface
    """
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }
    params = {"q": query}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching news: {e}")
        return None

def parse_news_results(html_content, max_results=7):
    """
    Parse DuckDuckGo search results to extract news headlines and links
    """
    if not html_content:
        return []
    
    soup = BeautifulSoup(html_content, 'html.parser')
    results = []
    
    # DuckDuckGo HTML results are in .result elements
    result_elements = soup.find_all('div', class_='result', limit=max_results)
    
    for result in result_elements:
        try:
            # Extract title and link
            title_elem = result.find('a', class_='result__a')
            if not title_elem:
                continue
                
            title = title_elem.get_text(strip=True)
            link = title_elem.get('href', '')
            
            # Extract snippet/description
            snippet_elem = result.find('a', class_='result__snippet')
            description = snippet_elem.get_text(strip=True) if snippet_elem else "No description available"
            
            # Clean up the URL (DuckDuckGo redirects through their domain)
            if link.startswith('/'):
                link = f"https://duckduckgo.com{link}"
            
            results.append({
                'title': title,
                'description': description,
                'link': link,
                'source': extract_domain(link)
            })
        except Exception as e:
            continue
    
    return results

def extract_domain(url):
    """Extract domain name from URL"""
    match = re.search(r'https?://(?:www\.)?([^/]+)', url)
    return match.group(1) if match else "Unknown"

def categorize_news(results):
    """Categorize news by common AI themes"""
    categories = {
        'LLMs & Generative AI': [],
        'AI Safety & Ethics': [],
        'AI Business & Funding': [],
        'AI Research': [],
        'AI Applications': [],
        'Other': []
    }
    
    keywords = {
        'LLMs & Generative AI': ['gpt', 'llm', 'large language', 'generative', 'chatbot', 'openai', 'anthropic', 'claude', 'gemini'],
        'AI Safety & Ethics': ['safety', 'ethics', 'regulation', 'bias', 'alignment', 'risk', 'concern'],
        'AI Business & Funding': ['funding', 'investment', 'billion', 'startup', 'acquisition', 'ipo', 'revenue'],
        'AI Research': ['research', 'paper', 'study', 'breakthrough', 'model', 'algorithm', 'arxiv'],
        'AI Applications': ['healthcare', 'medical', 'autonomous', 'robot', 'vision', 'image', 'video']
    }
    
    for result in results:
        text = f"{result['title']} {result['description']}".lower()
        categorized = False
        
        for category, words in keywords.items():
            if any(word in text for word in words):
                categories[category].append(result)
                categorized = True
                break
        
        if not categorized:
            categories['Other'].append(result)
    
    return categories

# Main execution
def main():
    print("=" * 60)
    print("LATEST AI NEWS FETCHER")
    print(f"Fetched at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Fetch news
    html = fetch_ai_news("latest artificial intelligence news 2024")
    results = parse_news_results(html, max_results=7)
    
    if not results:
        print("No results found. DuckDuckGo may be blocking automated requests.")
        print("\nAlternative: Try using NewsAPI (requires free API key):")
        print("  https://newsapi.org/")
        return
    
    # Display results
    print(f"\nFound {len(results)} news items:\n")
    
    for i, item in enumerate(results, 1):
        print(f"{i}. {item['title']}")
        print(f"   Source: {item['source']}")
        print(f"   Description: {item['description'][:150]}...")
        print(f"   Link: {item['link']}")
        print()
    
    # Categorize and show trends
    print("=" * 60)
    print("KEY TRENDS & THEMES")
    print("=" * 60)
    
    categories = categorize_news(results)
    
    for category, items in categories.items():
        if items:
            print(f"\n{category} ({len(items)} items):")
            for item in items[:3]:  # Show top 3 per category
                print(f"  • {item['title'][:70]}...")

if __name__ == "__main__":
    main()
```

## Alternative: Using NewsAPI (More Reliable)

```python
import requests
from datetime import datetime, timedelta

def fetch_ai_news_newsapi(api_key, days_back=7):
    """
    Fetch AI news using NewsAPI (requires free API key from newsapi.org)
    """
    url = "https://newsapi.org/v2/everything"
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    params = {
        "q": "artificial intelligence OR AI OR machine learning",
        "from": start_date.strftime("%Y-%m-%d"),
        "to": end_date.strftime("%Y-%m-%d"),
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 10,
        "apiKey": api_key
    }
    
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        data = response.json()
        
        if data.get("status") == "ok":
            return data.get("articles", [])
        else:
            print(f"API Error: {data.get('message')}")
            return []
    except Exception as e:
        print(f"Error: {e}")
        return []

# Usage:
# articles = fetch_ai_news_newsapi("your-api-key-here")
# for article in articles:
#     print(f"{article['title']} - {article['source']['name']}")
#     print(f"  {article['description']}")
#     print(f"  {article['url']}\n")
```

## Expected Output Format

```
============================================================
LATEST AI NEWS FETCHER
Fetched at: 2024-01-15 10:30:00
============================================================

Found 7 news items:

1. OpenAI Announces GPT-5 Development Progress
   Source: techcrunch.com
   Description: OpenAI reveals new advancements in their upcoming...
   Link: https://techcrunch.com/...

2. Google DeepMind Releases New AI Safety Framework
   Source: deepmind.google
   Description: New guidelines for responsible AI development...
   Link: https://deepmind.google/...

...

============================================================
KEY TRENDS & THEMES
============================================================

LLMs & Generative AI (3 items):
  • OpenAI Announces GPT-5 Development Progress...
  • Anthropic's Claude 3 Shows Improved Reasoning...
  • Meta Releases New Open Source Language Model...

AI Safety & Ethics (2 items):
  • Google DeepMind Releases New AI Safety Framework...
  • EU AI Act Implementation Begins Next Month...
```

## Notes
- DuckDuckGo HTML interface may block automated requests; use appropriate delays
- NewsAPI provides more reliable results but requires a free API key
- Respect robots.txt and terms of service when scraping
- Consider adding rate limiting (time.sleep(1-2 seconds) between requests)
