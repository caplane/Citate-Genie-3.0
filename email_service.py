"""
citeflex/email_service.py

Email service for sending admin reports.

Uses Resend (resend.com) - simple API, 3,000 free emails/month.

Setup:
    1. Sign up at resend.com
    2. Get API key
    3. Add RESEND_API_KEY to Railway environment variables
    4. Add ADMIN_EMAIL (your email address)
    5. Add ADMIN_SECRET (secret key for the /email-costs endpoint)

Usage:
    from email_service import send_cost_report
    
    success = send_cost_report()  # Sends to ADMIN_EMAIL

Version History:
    2025-12-13 V1.0: Initial implementation
"""

import os
import requests
import base64
from datetime import datetime
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================

RESEND_API_KEY = os.environ.get('CITEGENIE_EMAIL_KEY', '')
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '')
ADMIN_SECRET = os.environ.get('ADMIN_SECRET', '')

# Resend provides this sender for testing (no domain verification needed)
# Once you verify your own domain, you can change this
FROM_EMAIL = os.environ.get('FROM_EMAIL', 'CitateGenie <onboarding@resend.dev>')


# =============================================================================
# COST REPORT GENERATION
# =============================================================================

def generate_cost_summary() -> dict:
    """
    Generate a summary of API costs from costs.csv.
    
    Returns:
        Dict with summary statistics and CSV content
    """
    from cost_tracker import COST_LOG_PATH
    
    if not COST_LOG_PATH.exists():
        return {
            'total_cost': 0,
            'total_calls': 0,
            'by_provider': {},
            'csv_content': '',
            'period_start': None,
            'period_end': None,
        }
    
    # Read and parse CSV
    import csv
    
    totals = {
        'gemini': {'cost': 0.0, 'calls': 0},
        'openai': {'cost': 0.0, 'calls': 0},
        'claude': {'cost': 0.0, 'calls': 0},
        'serpapi': {'cost': 0.0, 'calls': 0},
    }
    
    timestamps = []
    
    with open(COST_LOG_PATH, 'r', encoding='utf-8') as f:
        csv_content = f.read()
    
    # Parse for statistics
    with open(COST_LOG_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            provider = row.get('provider', '').lower()
            cost = float(row.get('cost_usd', 0))
            timestamp = row.get('timestamp', '')
            
            if provider in totals:
                totals[provider]['cost'] += cost
                totals[provider]['calls'] += 1
            
            if timestamp:
                timestamps.append(timestamp)
    
    # Calculate totals
    total_cost = sum(p['cost'] for p in totals.values())
    total_calls = sum(p['calls'] for p in totals.values())
    
    # Get date range
    period_start = min(timestamps) if timestamps else None
    period_end = max(timestamps) if timestamps else None
    
    return {
        'total_cost': total_cost,
        'total_calls': total_calls,
        'by_provider': totals,
        'csv_content': csv_content,
        'period_start': period_start,
        'period_end': period_end,
    }


def format_cost_report_email(summary: dict) -> str:
    """
    Format the cost summary as an email body.
    
    Args:
        summary: Dict from generate_cost_summary()
        
    Returns:
        Formatted email body text
    """
    now = datetime.now().strftime('%B %d, %Y at %I:%M %p')
    
    # Format date range
    if summary['period_start'] and summary['period_end']:
        try:
            start = datetime.fromisoformat(summary['period_start']).strftime('%b %d, %Y')
            end = datetime.fromisoformat(summary['period_end']).strftime('%b %d, %Y')
            if start == end:
                period = start
            else:
                period = f"{start} - {end}"
        except:
            period = "Unknown"
    else:
        period = "No data yet"
    
    # Build provider breakdown
    provider_lines = []
    for provider, data in summary['by_provider'].items():
        if data['calls'] > 0:
            provider_lines.append(
                f"  {provider.capitalize():10} ${data['cost']:.4f} ({data['calls']} calls)"
            )
    
    provider_section = '\n'.join(provider_lines) if provider_lines else "  No API calls recorded"
    
    body = f"""CitateGenie API Cost Report
{'=' * 35}

Report generated: {now}
Data period: {period}

SUMMARY
{'-' * 35}
Total API calls: {summary['total_calls']}
Total cost: ${summary['total_cost']:.4f}

BY PROVIDER
{'-' * 35}
{provider_section}

{'=' * 35}

Full data attached as costs.csv
Open in Excel for detailed analysis.

--
CitateGenie Cost Tracker
"""
    
    return body


# =============================================================================
# EMAIL SENDING
# =============================================================================

def send_email(to: str, subject: str, body: str, attachment_content: str = None, 
               attachment_filename: str = None) -> bool:
    """
    Send an email via Resend API.
    
    Args:
        to: Recipient email address
        subject: Email subject
        body: Plain text email body
        attachment_content: Optional file content as string
        attachment_filename: Optional filename for attachment
        
    Returns:
        True if sent successfully, False otherwise
    """
    if not RESEND_API_KEY:
        print("[EmailService] ERROR: RESEND_API_KEY not configured")
        return False
    
    # Build request payload
    payload = {
        'from': FROM_EMAIL,
        'to': [to],
        'subject': subject,
        'text': body,
    }
    
    # Add attachment if provided
    if attachment_content and attachment_filename:
        # Resend expects base64-encoded attachments
        encoded_content = base64.b64encode(attachment_content.encode('utf-8')).decode('utf-8')
        payload['attachments'] = [{
            'filename': attachment_filename,
            'content': encoded_content,
        }]
    
    try:
        response = requests.post(
            'https://api.resend.com/emails',
            headers={
                'Authorization': f'Bearer {RESEND_API_KEY}',
                'Content-Type': 'application/json',
            },
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            print(f"[EmailService] Email sent successfully to {to}")
            return True
        else:
            print(f"[EmailService] Failed to send email: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"[EmailService] Error sending email: {e}")
        return False


def send_cost_report(to_email: str = None) -> bool:
    """
    Generate and send the cost report email.
    
    Args:
        to_email: Override recipient (defaults to ADMIN_EMAIL)
        
    Returns:
        True if sent successfully, False otherwise
    """
    recipient = to_email or ADMIN_EMAIL
    
    if not recipient:
        print("[EmailService] ERROR: No recipient email configured")
        return False
    
    # Generate summary
    summary = generate_cost_summary()
    
    # Format email
    body = format_cost_report_email(summary)
    subject = f"CitateGenie Cost Report - ${summary['total_cost']:.2f} total"
    
    # Send with CSV attachment
    return send_email(
        to=recipient,
        subject=subject,
        body=body,
        attachment_content=summary['csv_content'] if summary['csv_content'] else None,
        attachment_filename='citategenie_costs.csv' if summary['csv_content'] else None
    )


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("Testing email service...")
    print(f"RESEND_API_KEY configured: {bool(RESEND_API_KEY)}")
    print(f"ADMIN_EMAIL configured: {bool(ADMIN_EMAIL)}")
    print(f"ADMIN_SECRET configured: {bool(ADMIN_SECRET)}")
    
    # Test summary generation (doesn't require API key)
    summary = generate_cost_summary()
    print(f"\nCost summary: {summary['total_calls']} calls, ${summary['total_cost']:.4f}")
    
    # Print what the email would look like
    print("\n--- EMAIL PREVIEW ---")
    print(format_cost_report_email(summary))
