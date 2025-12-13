"""
citeflex/cost_tracker.py

Lightweight API cost logging for CitateGenie.

Logs every paid API call (Gemini, OpenAI, Claude, SerpAPI) to a CSV file
for cost analysis. Open in Excel to analyze costs per citation/document.

Usage:
    from cost_tracker import log_api_call
    
    # After an OpenAI call:
    log_api_call('openai', input_tokens=847, output_tokens=312, query='Simonton, 1992')
    
    # After a SerpAPI call:
    log_api_call('serpapi', query='creativity psychology')

Output: costs.csv in the application root directory

Version History:
    2025-12-13 V1.0: Initial implementation - CSV logging with cost calculation
"""

import os
import csv
from datetime import datetime
from pathlib import Path

# =============================================================================
# PRICING (per 1M tokens, updated Dec 2024)
# =============================================================================

PRICING = {
    'gemini': {
        'input': 0.075,    # $0.075 per 1M input tokens (Gemini 2.0 Flash)
        'output': 0.30,    # $0.30 per 1M output tokens
    },
    'openai': {
        'input': 2.50,     # $2.50 per 1M input tokens (GPT-4o)
        'output': 10.00,   # $10.00 per 1M output tokens
    },
    'claude': {
        'input': 3.00,     # $3.00 per 1M input tokens (Claude 3.5 Sonnet)
        'output': 15.00,   # $15.00 per 1M output tokens
    },
    'serpapi': {
        'per_search': 0.01,  # ~$0.01 per search (varies by plan)
    },
}

# =============================================================================
# CSV FILE SETUP
# =============================================================================

# Store costs.csv in the app root directory
COST_LOG_PATH = Path(__file__).parent / 'costs.csv'

CSV_HEADERS = [
    'timestamp',
    'provider',
    'input_tokens',
    'output_tokens',
    'cost_usd',
    'query',
    'function',
]

def _ensure_csv_exists():
    """Create CSV file with headers if it doesn't exist."""
    if not COST_LOG_PATH.exists():
        with open(COST_LOG_PATH, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADERS)
        print(f"[CostTracker] Created cost log: {COST_LOG_PATH}")


# =============================================================================
# COST CALCULATION
# =============================================================================

def calculate_cost(provider: str, input_tokens: int = 0, output_tokens: int = 0) -> float:
    """
    Calculate cost in USD for an API call.
    
    Args:
        provider: 'gemini', 'openai', 'claude', or 'serpapi'
        input_tokens: Number of input/prompt tokens
        output_tokens: Number of output/completion tokens
        
    Returns:
        Cost in USD (float)
    """
    provider = provider.lower()
    
    if provider == 'serpapi':
        return PRICING['serpapi']['per_search']
    
    if provider not in PRICING:
        return 0.0
    
    pricing = PRICING[provider]
    
    # Cost = (tokens / 1,000,000) * price_per_million
    input_cost = (input_tokens / 1_000_000) * pricing['input']
    output_cost = (output_tokens / 1_000_000) * pricing['output']
    
    return round(input_cost + output_cost, 8)  # Keep precision for small costs


# =============================================================================
# LOGGING FUNCTION
# =============================================================================

def log_api_call(
    provider: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    query: str = '',
    function: str = ''
) -> float:
    """
    Log an API call to costs.csv and return the calculated cost.
    
    Args:
        provider: 'gemini', 'openai', 'claude', or 'serpapi'
        input_tokens: Number of input tokens (0 for SerpAPI)
        output_tokens: Number of output tokens (0 for SerpAPI)
        query: The citation/search query being processed
        function: Which function made the call (e.g., 'classify', 'lookup')
        
    Returns:
        Cost in USD for this call
    """
    _ensure_csv_exists()
    
    cost = calculate_cost(provider, input_tokens, output_tokens)
    
    # Clean query for CSV (remove newlines, limit length)
    clean_query = query.replace('\n', ' ').replace('\r', '')[:200]
    
    row = [
        datetime.now().isoformat(),
        provider.lower(),
        input_tokens,
        output_tokens,
        f'{cost:.8f}',  # Keep precision
        clean_query,
        function,
    ]
    
    try:
        with open(COST_LOG_PATH, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(row)
    except Exception as e:
        print(f"[CostTracker] Warning: Could not write to log: {e}")
    
    # Also print for visibility during development
    if provider == 'serpapi':
        print(f"[CostTracker] {provider}: 1 search = ${cost:.4f}")
    else:
        print(f"[CostTracker] {provider}: {input_tokens} in + {output_tokens} out = ${cost:.6f}")
    
    return cost


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_total_cost() -> dict:
    """
    Read costs.csv and return summary statistics.
    
    Returns:
        Dict with total_cost, by_provider breakdown, and call_count
    """
    if not COST_LOG_PATH.exists():
        return {'total_cost': 0, 'by_provider': {}, 'call_count': 0}
    
    totals = {
        'gemini': 0.0,
        'openai': 0.0,
        'claude': 0.0,
        'serpapi': 0.0,
    }
    call_count = 0
    
    with open(COST_LOG_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            provider = row.get('provider', '').lower()
            cost = float(row.get('cost_usd', 0))
            if provider in totals:
                totals[provider] += cost
            call_count += 1
    
    return {
        'total_cost': sum(totals.values()),
        'by_provider': totals,
        'call_count': call_count,
    }


def print_summary():
    """Print a cost summary to console."""
    stats = get_total_cost()
    
    print("\n" + "="*50)
    print("CITATEGENIE API COST SUMMARY")
    print("="*50)
    print(f"Total API calls: {stats['call_count']}")
    print(f"Total cost: ${stats['total_cost']:.4f}")
    print("\nBy provider:")
    for provider, cost in stats['by_provider'].items():
        if cost > 0:
            print(f"  {provider:10} ${cost:.4f}")
    print("="*50 + "\n")


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("Testing cost tracker...")
    
    # Simulate some API calls
    log_api_call('gemini', input_tokens=500, output_tokens=200, 
                 query='Simonton, 1992', function='classify')
    log_api_call('openai', input_tokens=847, output_tokens=312, 
                 query='Zimbardo, Johnson, & McCann, 2009', function='lookup')
    log_api_call('serpapi', query='creativity psychology Simonton', 
                 function='google_scholar')
    log_api_call('claude', input_tokens=1000, output_tokens=500,
                 query='caplan trains brains', function='lookup_fragment')
    
    print_summary()
    print(f"\nLog file: {COST_LOG_PATH}")
