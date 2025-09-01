import pandas as pd
from typing import Dict, List, Set


def clean_and_validate_emails(raw_data: List[Dict], ignore_domains: Set[str]) -> List[Dict]:
    if not raw_data:
        return []

    df = pd.DataFrame(raw_data)

    # Basic Cleaning
    df.dropna(subset=['email'], inplace=True)
    df = df[df['email'].str.strip() != '']

    # Filtering Irrelevant Emails
    df['domain'] = df['email'].str.split('@').str[-1].str.lower()
    df = df[~df['domain'].isin(ignore_domains)]

    # Filter out emails with common image file patterns
    image_patterns = ('.webp', '.jpg', '.jpeg', '.png', '.gif', '.svg', '@2x-')
    df = df[~df['email'].str.contains('|'.join(image_patterns))]

    #Filter out TLDs that don't make sense
    df['tld'] = df['domain'].str.rsplit('.', n=1).str[-1].str.lower()
    df = df[df['tld'].str.len() >= 2]
    df = df[~df['tld'].str.contains(r'[0-9]')]
    df = df[df['tld'].str.isalpha()]

    # Deduplication
    df.drop_duplicates(subset=['email'], keep='first', inplace=True)

    # dropping duplicates by company name.
    # df.drop_duplicates(subset=['company_name'], keep='first', inplace=True)

    # Formatting
    final_df = df.rename(columns={"name": "company_name"}).copy()
    final_df = final_df[['company_name', 'country', 'email']]

    return final_df.to_dict('records')