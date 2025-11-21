import requests
from bs4 import BeautifulSoup
import mysql.connector
from datetime import datetime
import re
from urllib.parse import urljoin
import time
import os
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DB_CONFIG = {
    'host' : os.getenv('DB_HOST'),
    'password' : os.getenv('DB_PASSWORD'),  # Replace with your MySQL password
    'user' : os.getenv('DB_USER'),
    'port' :  os.getenv('DB_PORT')
}

# Date range
START_DATE = datetime(2024, 1, 1)
END_DATE = datetime(2025, 12, 31)

# Month mapping for parsing dates
MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
}

def parse_date(date_str):
    """Parse date string to datetime object"""
    try:
        # Handle format: "16 September 2025"
        parts = date_str.strip().split()
        if len(parts) == 3:
            day = int(parts[0])
            month = MONTHS.get(parts[1].lower())
            year = int(parts[2])
            if month:
                return datetime(year, month, day)
    except:
        pass
    return None

def get_last_day_of_month(month_name, year):
    """Get the last day of a given month"""
    month_num = MONTHS.get(month_name.lower())
    if not month_num:
        return None
    
    # Days in each month
    days_in_month = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    
    return datetime(year, month_num, days_in_month[month_num - 1])

def parse_quarterly_date(title):
    """Parse date from quarterly update title"""
    # Pattern: "Corporate Practice: Quarterly Update 2025 (July - September)"
    match = re.search(r'(\w+)\s*-\s*(\w+)\)?.*?(\d{4})', title)
    if match:
        end_month = match.group(2)
        year = int(match.group(3))
        return get_last_day_of_month(end_month, year)
    return None

def parse_newsletter_date(title):
    """Parse date from newsletter title"""
    # Pattern: "Tax Amicus: June 2025"
    match = re.search(r':\s*(\w+)\s+(\d{4})', title)
    if match:
        month_name = match.group(1)
        year = int(match.group(2))
        return get_last_day_of_month(month_name, year)
    return None

def setup_database():
    """Create database and table if they don't exist"""
    conn = mysql.connector.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password']
    )
    cursor = conn.cursor()
    
    # Create database
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
    cursor.execute(f"USE {DB_CONFIG['database']}")
    
    # Create table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lks_publications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            company_name VARCHAR(50),
            publication_type VARCHAR(100),
            publishing_date DATE,
            practice_area VARCHAR(200),
            article_heading TEXT,
            article_link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_article (article_link(500))
        )
    """)
    
    conn.commit()
    cursor.close()
    conn.close()
    print("Database setup completed")

def check_duplicate(article_link):
    """Check if article link already exists in database"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        query = "SELECT COUNT(*) FROM lks_publications WHERE article_link = %s"
        cursor.execute(query, (article_link,))
        count = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        return count > 0
    except Exception as e:
        print(f"Error checking duplicate: {e}")
        return False

def insert_record(data):
    """Insert record into database"""
    try:
        # Check for duplicate first
        if check_duplicate(data['article_link']):
            print(f"⊗ Duplicate skipped: {data['article_heading'][:50]}...")
            return False
        
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        query = """
            INSERT INTO lks_publications 
            (company_name, publication_type, publishing_date, practice_area, article_heading, article_link)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        
        cursor.execute(query, (
            data['company_name'],
            data['publication_type'],
            data['publishing_date'],
            data['practice_area'],
            data['article_heading'],
            data['article_link']
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error inserting record: {e}")
        return False

def scrape_articles(base_url, page_param=True):
    """Scrape articles from the given URL"""
    page = 1
    total_scraped = 0
    max_pages = 50
    
    while page <= max_pages:
        if page_param:
            url = f"{base_url}?page={page}" if page > 1 else base_url
        else:
            url = base_url
            
        print(f"Scraping: {url}")
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            articles = soup.find_all('div', class_='inner_sec')
            
            if not articles:
                print(f"No more articles found on page {page}")
                break
            
            found_old_date = False
            page_has_valid_dates = False
            
            for article in articles:
                try:
                    # Extract practice area
                    practice_elem = article.find('p', class_='typePractice')
                    practice_area = practice_elem.text.strip() if practice_elem else 'N/A'
                    
                    # Extract title and link
                    title_elem = article.find('h2')
                    if title_elem:
                        link_elem = title_elem.find('a')
                        article_heading = link_elem.text.strip() if link_elem else title_elem.text.strip()
                        article_link = link_elem['href'] if link_elem and link_elem.get('href') else ''
                        article_link = urljoin(base_url, article_link)
                    else:
                        continue
                    
                    # Extract date
                    date_elem = article.find('p', class_='date')
                    if date_elem:
                        date_str = date_elem.text.strip()
                        pub_date = parse_date(date_str)
                        
                        if pub_date:
                            # Check if date is before Jan 1, 2024
                            if pub_date < START_DATE:
                                found_old_date = True
                                continue
                            elif pub_date > END_DATE:
                                continue
                            
                            page_has_valid_dates = True
                            
                            # Insert into database
                            data = {
                                'company_name': 'LKS',
                                'publication_type': 'Articles',
                                'publishing_date': pub_date.strftime('%Y-%m-%d'),
                                'practice_area': practice_area,
                                'article_heading': article_heading,
                                'article_link': article_link
                            }
                            
                            if insert_record(data):
                                total_scraped += 1
                                print(f"✓ Added: {article_heading[:50]}... ({pub_date.strftime('%Y-%m-%d')})")
                    
                except Exception as e:
                    print(f"Error processing article: {e}")
                    continue
            
            # Stop if we've reached articles before Jan 1, 2024
            if found_old_date and not page_has_valid_dates:
                print("Reached articles before Jan 1, 2024, stopping pagination")
                break
            
            if not page_param:
                break
            
            if page >= max_pages:
                print(f"Reached maximum page limit ({max_pages})")
                break
                
            page += 1
            time.sleep(1)  # Be polite to the server
            
        except Exception as e:
            print(f"Error scraping page {page}: {e}")
            break
    
    print(f"Total articles scraped: {total_scraped}")
    return total_scraped

def scrape_alerts(base_url):
    """Scrape alerts/updates"""
    page = 1
    total_scraped = 0
    max_pages = 50
    
    while page <= max_pages:
        url = f"{base_url}?page={page}" if page > 1 else base_url
        print(f"Scraping: {url}")
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            articles = soup.find_all('div', class_='inner_sec')
            
            if not articles:
                print(f"No more alerts found on page {page}")
                break
            
            found_old_date = False
            page_has_valid_dates = False
            
            for article in articles:
                try:
                    # Extract title and link
                    title_elem = article.find('h2')
                    if title_elem:
                        link_elem = title_elem.find('a')
                        article_heading = link_elem.text.strip() if link_elem else title_elem.text.strip()
                        article_link = link_elem['href'] if link_elem and link_elem.get('href') else ''
                        article_link = urljoin(base_url, article_link)
                    else:
                        continue
                    
                    # Extract date
                    date_elem = article.find('p', class_='date')
                    if date_elem:
                        date_str = date_elem.text.strip()
                        pub_date = parse_date(date_str)
                        
                        if pub_date:
                            if pub_date < START_DATE:
                                found_old_date = True
                                continue
                            elif pub_date > END_DATE:
                                continue
                            
                            page_has_valid_dates = True
                            
                            data = {
                                'company_name': 'LKS',
                                'publication_type': 'Alerts/Updates',
                                'publishing_date': pub_date.strftime('%Y-%m-%d'),
                                'practice_area': 'N/A',
                                'article_heading': article_heading,
                                'article_link': article_link
                            }
                            
                            if insert_record(data):
                                total_scraped += 1
                                print(f"✓ Added: {article_heading[:50]}... ({pub_date.strftime('%Y-%m-%d')})")
                    
                except Exception as e:
                    print(f"Error processing alert: {e}")
                    continue
            
            if found_old_date and not page_has_valid_dates:
                print("Reached alerts before Jan 1, 2024, stopping pagination")
                break
            
            if page >= max_pages:
                print(f"Reached maximum page limit ({max_pages})")
                break
            
            page += 1
            time.sleep(1)
            
        except Exception as e:
            print(f"Error scraping page {page}: {e}")
            break
    
    print(f"Total alerts scraped: {total_scraped}")
    return total_scraped

def scrape_newsletters(base_url, newsletter_type):
    """Scrape newsletters"""
    page = 1
    total_scraped = 0
    max_pages = 50
    is_quarterly = 'quarterly' in newsletter_type.lower()
    
    while page <= max_pages:
        url = f"{base_url}?page={page}" if page > 1 else base_url
        print(f"Scraping: {url}")
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            articles = soup.find_all('div', class_='news_sec')
            
            if not articles:
                print(f"No more newsletters found on page {page}")
                break
            
            found_old_date = False
            page_has_valid_dates = False
            
            for article in articles:
                try:
                    # Extract title and link
                    link_elem = article.find('a', class_='desc_title')
                    if link_elem:
                        article_heading = link_elem.text.strip()
                        article_link = link_elem['href'] if link_elem.get('href') else ''
                        article_link = urljoin(base_url, article_link)
                    else:
                        continue
                    
                    # Parse date based on type
                    if is_quarterly:
                        pub_date = parse_quarterly_date(article_heading)
                    else:
                        pub_date = parse_newsletter_date(article_heading)
                    
                    if pub_date:
                        if pub_date < START_DATE:
                            found_old_date = True
                            continue
                        elif pub_date > END_DATE:
                            continue
                        
                        page_has_valid_dates = True
                        
                        data = {
                            'company_name': 'LKS',
                            'publication_type': f'Newsletter - {newsletter_type}',
                            'publishing_date': pub_date.strftime('%Y-%m-%d'),
                            'practice_area': newsletter_type,
                            'article_heading': article_heading,
                            'article_link': article_link
                        }
                        
                        if insert_record(data):
                            total_scraped += 1
                            print(f"✓ Added: {article_heading[:50]}... ({pub_date.strftime('%Y-%m-%d')})")
                    
                except Exception as e:
                    print(f"Error processing newsletter: {e}")
                    continue
            
            if found_old_date and not page_has_valid_dates:
                print(f"Reached newsletters before Jan 1, 2024, stopping pagination")
                break
            
            if page >= max_pages:
                print(f"Reached maximum page limit ({max_pages})")
                break
            
            page += 1
            time.sleep(1)
            
        except Exception as e:
            print(f"Error scraping page {page}: {e}")
            break
    
    print(f"Total newsletters scraped: {total_scraped}")
    return total_scraped

def main():
    print("Starting Lakshmisri Web Scraper...")
    print(f"Date range: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print("=" * 80)
    
    # Setup database
    setup_database()
    
    total_records = 0
    
    # 1. Scrape Articles
    print("\n" + "=" * 80)
    print("SCRAPING ARTICLES")
    print("=" * 80)
    total_records += scrape_articles("https://www.lakshmisri.com/insights/articles/")
    
    # 2. Scrape Alerts/Updates
    print("\n" + "=" * 80)
    print("SCRAPING ALERTS/UPDATES")
    print("=" * 80)
    total_records += scrape_alerts("https://www.lakshmisri.com/newsroom/news-briefings/")
    
    # 3. Scrape Newsletters
    newsletters = [
        ("https://www.lakshmisri.com/insights/newsletters/tax-amicus/", "Tax"),
        ("https://www.lakshmisri.com/insights/newsletters/direct-tax-amicus/", "Direct Tax"),
        ("https://www.lakshmisri.com/insights/newsletters/international-trade-amicus/", "International Trade"),
        ("https://www.lakshmisri.com/insights/newsletters/ipr-amicus/", "IPR"),
        ("https://www.lakshmisri.com/insights/newsletters/corporate-amicus/", "Corporate"),
        ("https://www.lakshmisri.com/insights/newsletters/competition-law/", "Competition Law"),
        ("https://www.lakshmisri.com/insights/newsletters/quarterly-update/", "Corporate Quarterly Updates"),
        ("https://www.lakshmisri.com/insights/newsletters/lks-bis-amicus/", "BIS"),
        ("https://www.lakshmisri.com/insights/newsletters/technolawgy-bulletin/", "Technology"),
        ("https://www.lakshmisri.com/insights/newsletters/hyma-newsletter/", "M&A")
    ]
    
    for url, newsletter_type in newsletters:
        print("\n" + "=" * 80)
        print(f"SCRAPING NEWSLETTER: {newsletter_type}")
        print("=" * 80)
        total_records += scrape_newsletters(url, newsletter_type)
    
    print("\n" + "=" * 80)
    print(f"SCRAPING COMPLETE!")
    print(f"Total records added to database: {total_records}")
    print("=" * 80)

if __name__ == "__main__":
    main()