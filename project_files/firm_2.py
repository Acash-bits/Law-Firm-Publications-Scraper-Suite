import requests
from bs4 import BeautifulSoup
import mysql.connector
from datetime import datetime
import time
from urllib.parse import urljoin
import re
import os
from dotenv import load_dotenv

class CAMScraper:
    def __init__(self, db_config, start_date="2024-01-01", end_date="2025-12-31"):
        """
        Initialize the scraper with database configuration
        db_config: dict with keys: host, user, password, database
        start_date: Start date for filtering (YYYY-MM-DD format)
        end_date: End date for filtering (YYYY-MM-DD format)
        """
        self.db_config = db_config
        self.company_name = "CAM"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d")
        self.end_date = datetime.strptime(end_date, "%Y-%m-%d")
        self.articles_scraped = 0
        self.articles_filtered = 0
        
    def connect_db(self):
        """Connect to MySQL database"""
        return mysql.connector.connect(**self.db_config)
    
    def create_table(self):
        """Create the publications table if it doesn't exist"""
        conn = self.connect_db()
        cursor = conn.cursor()
        
        create_table_query = """
        CREATE TABLE IF NOT EXISTS `cam_publications` (
            id INT AUTO_INCREMENT PRIMARY KEY,
            company_name VARCHAR(255),
            publication_type VARCHAR(255),
            publication_date DATE,
            practice_area VARCHAR(255),
            article_name TEXT,
            article_link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_article (article_link(500))
        )
        """
        cursor.execute(create_table_query)
        conn.commit()
        cursor.close()
        conn.close()
        print("Table created successfully")
    
    def insert_data(self, data):
        """Insert data into database"""
        conn = self.connect_db()
        cursor = conn.cursor()
        
        insert_query = """
        INSERT IGNORE INTO cam_publications 
        (company_name, publication_type, publication_date, practice_area, article_name, article_link)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        
        cursor.execute(insert_query, (
            data['company_name'],
            data['publication_type'],
            data['publication_date'],
            data['practice_area'],
            data['article_name'],
            data['article_link']
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
    
    def is_date_in_range(self, date_obj):
        """Check if a date is within the specified range"""
        if not date_obj:
            return False
        return self.start_date <= date_obj <= self.end_date
    
    def parse_date(self, date_str):
        """Parse date string to MySQL date format and return both string and datetime object"""
        try:
            # Handle various date formats
            date_str = date_str.strip()
            
            # Format: "October 15, 2025" or "October 2025"
            if ',' in date_str:
                date_obj = datetime.strptime(date_str, "%B %d, %Y")
            else:
                # Try "Month Year" format - assume first day of month
                date_obj = datetime.strptime(date_str, "%B %Y")
            
            return date_obj.strftime("%Y-%m-%d"), date_obj
        except:
            return None, None
    
    def scrape_publications(self):
        """Scrape publications page"""
        url = "https://www.cyrilshroff.com/campublication/"
        print(f"\nScraping Publications from: {url}")
        
        try:
            response = requests.get(url, headers=self.headers)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            blocks = soup.find_all('div', class_='block-content')
            
            for block in blocks:
                try:
                    h2 = block.find('h2')
                    if not h2:
                        continue
                    
                    article_name = h2.get_text(strip=True)
                    
                    # Get date
                    date_p = block.find('p')
                    date_text = None
                    if date_p:
                        date_text = date_p.find_next_sibling('p')
                        if date_text:
                            date_text = date_text.get_text(strip=True)
                    
                    publication_date, date_obj = self.parse_date(date_text) if date_text else (None, None)
                    
                    # Check if date is in range
                    if not self.is_date_in_range(date_obj):
                        self.articles_filtered += 1
                        continue
                    
                    # Get PDF link
                    download_link = block.find('a', href=re.compile(r'\.pdf'))
                    article_link = download_link['href'] if download_link else None
                    
                    if article_name and article_link:
                        data = {
                            'company_name': self.company_name,
                            'publication_type': 'Publications',
                            'publication_date': publication_date,
                            'practice_area': None,
                            'article_name': article_name,
                            'article_link': article_link
                        }
                        self.insert_data(data)
                        self.articles_scraped += 1
                        print(f"Inserted: {article_name} ({publication_date})")
                except Exception as e:
                    print(f"Error processing publication: {e}")
                    continue
                    
        except Exception as e:
            print(f"Error scraping publications: {e}")
    
    def scrape_newsletters(self):
        """Scrape newsletters page"""
        url = "https://www.cyrilshroff.com/newsletters/"
        print(f"\nScraping Newsletters from: {url}")
        
        try:
            response = requests.get(url, headers=self.headers)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            blocks = soup.find_all('div', class_='block-content')
            
            for block in blocks:
                try:
                    h4 = block.find('h4')
                    if not h4:
                        continue
                    
                    article_name = h4.get_text(strip=True)
                    
                    # Get date (in li tag)
                    date_li = block.find('li')
                    date_text = None
                    if date_li:
                        date_text = date_li.get_text(strip=True)
                        # Extract just the date part (after "Issue X")
                        if '\n' in date_text:
                            date_text = date_text.split('\n')[-1].strip()
                    
                    publication_date, date_obj = self.parse_date(date_text) if date_text else (None, None)
                    
                    # Check if date is in range
                    if not self.is_date_in_range(date_obj):
                        self.articles_filtered += 1
                        continue
                    
                    # Get PDF link
                    download_link = block.find('a', href=re.compile(r'\.pdf'))
                    article_link = download_link['href'] if download_link else None
                    
                    if article_name and article_link:
                        data = {
                            'company_name': self.company_name,
                            'publication_type': 'Newsletters',
                            'publication_date': publication_date,
                            'practice_area': None,
                            'article_name': article_name,
                            'article_link': article_link
                        }
                        self.insert_data(data)
                        self.articles_scraped += 1
                        print(f"Inserted: {article_name} ({publication_date})")
                except Exception as e:
                    print(f"Error processing newsletter: {e}")
                    continue
                    
        except Exception as e:
            print(f"Error scraping newsletters: {e}")
    
    def scrape_podcasts(self):
        """Scrape podcasts page"""
        url = "https://www.cyrilshroff.com/podcasts/"
        print(f"\nScraping Podcasts from: {url}")
        
        try:
            response = requests.get(url, headers=self.headers)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            blocks = soup.find_all('div', class_='block-content')
            
            for block in blocks:
                try:
                    h2 = block.find('h2')
                    if not h2:
                        continue
                    
                    article_name = h2.get_text(strip=True)
                    
                    # Get date from ul.dt li
                    date_text = None
                    dt_ul = block.find('ul', class_='dt')
                    if dt_ul:
                        date_li = dt_ul.find_all('li')
                        if len(date_li) > 1:
                            date_text = date_li[1].get_text(strip=True)
                    
                    publication_date, date_obj = self.parse_date(date_text) if date_text else (None, None)
                    
                    # Check if date is in range
                    if not self.is_date_in_range(date_obj):
                        self.articles_filtered += 1
                        continue
                    
                    # For podcasts, the article link might be in the h2's parent or the page itself
                    # Since structure shows no direct link in the example, we'll use the page URL
                    article_link = url
                    
                    if article_name:
                        data = {
                            'company_name': self.company_name,
                            'publication_type': 'Podcasts',
                            'publication_date': publication_date,
                            'practice_area': None,
                            'article_name': article_name,
                            'article_link': article_link
                        }
                        self.insert_data(data)
                        self.articles_scraped += 1
                        print(f"Inserted: {article_name} ({publication_date})")
                except Exception as e:
                    print(f"Error processing podcast: {e}")
                    continue
                    
        except Exception as e:
            print(f"Error scraping podcasts: {e}")
    
    def scrape_blog_page(self, url, practice_area, max_pages=50):
        """Scrape a blog category with pagination"""
        print(f"\nScraping Blog: {practice_area} from: {url}")
        
        page = 1
        continue_scraping = True
        
        while page <= max_pages and continue_scraping:
            try:
                if page == 1:
                    page_url = url
                else:
                    page_url = f"{url.rstrip('/')}/page/{page}/"
                
                print(f"  Scraping page {page}: {page_url}")
                response = requests.get(page_url, headers=self.headers)
                
                # Check if page exists
                if response.status_code == 404:
                    print(f"  Page {page} not found, stopping pagination")
                    break
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Find all post headers
                headers = soup.find_all('header', class_='lxb_af-post_header')
                
                if not headers:
                    print(f"  No posts found on page {page}, stopping pagination")
                    break
                
                for header in headers:
                    try:
                        # Get article name and link
                        h1 = header.find('h1', class_='lxb_af-template_tags-get_linked_post_title')
                        if not h1:
                            continue
                        
                        link_tag = h1.find('a')
                        if not link_tag:
                            continue
                        
                        article_name = link_tag.get_text(strip=True)
                        article_link = link_tag['href']
                        
                        # Get date
                        time_tag = header.find('time', class_='lxb_af-template_tags-get_post_date')
                        date_text = time_tag.get_text(strip=True) if time_tag else None
                        
                        # Parse date (format: "April 7, 2020")
                        publication_date, date_obj = None, None
                        if date_text:
                            try:
                                date_obj = datetime.strptime(date_text, "%B %d, %Y")
                                publication_date = date_obj.strftime("%Y-%m-%d")
                            except:
                                pass
                        
                        # Check if date is in range - if date is before range, stop pagination
                        if date_obj:
                            if date_obj < self.start_date:
                                print(f"  Reached articles before {self.start_date.strftime('%Y-%m-%d')}, stopping pagination")
                                continue_scraping = False
                                break
                            elif not self.is_date_in_range(date_obj):
                                self.articles_filtered += 1
                                continue
                        
                        # Get practice area from categories
                        cat_div = header.find('div', class_='lxb_af-template_tags-get_post_categories')
                        extracted_practice_area = practice_area  # Default to passed parameter
                        if cat_div:
                            cat_link = cat_div.find('a')
                            if cat_link:
                                extracted_practice_area = cat_link.get_text(strip=True)
                        
                        if article_name and article_link:
                            data = {
                                'company_name': self.company_name,
                                'publication_type': 'Blogs',
                                'publication_date': publication_date,
                                'practice_area': extracted_practice_area,
                                'article_name': article_name,
                                'article_link': article_link
                            }
                            self.insert_data(data)
                            self.articles_scraped += 1
                            print(f"  Inserted: {article_name} ({publication_date})")
                    except Exception as e:
                        print(f"  Error processing blog post: {e}")
                        continue
                
                page += 1
                time.sleep(1)  # Be polite to the server
                
            except Exception as e:
                print(f"  Error scraping blog page {page}: {e}")
                break
    
    def scrape_all_blogs(self):
        """Scrape all blog categories"""
        blog_categories = [
            {
                'url': 'https://disputeresolution.cyrilamarchandblogs.com/',
                'practice_area': 'Dispute Resolution'
            },
            {
                'url': 'https://corporate.cyrilamarchandblogs.com/',
                'practice_area': 'Corporate'
            },
            {
                'url': 'https://privateclient.cyrilamarchandblogs.com/',
                'practice_area': 'Private Client'
            },
            {
                'url': 'https://tax.cyrilamarchandblogs.com/',
                'practice_area': 'Tax'
            },
            {
                'url': 'https://competition.cyrilamarchandblogs.com/',
                'practice_area': 'Competition'
            }
        ]
        
        for category in blog_categories:
            self.scrape_blog_page(category['url'], category['practice_area'])
            time.sleep(2)  # Be polite between categories
    
    def run_full_scrape(self):
        """Run complete scraping process"""
        print("Starting CAM Web Scraper...")
        print(f"Date Range: {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}")
        print("=" * 50)
        
        # Reset counters
        self.articles_scraped = 0
        self.articles_filtered = 0
        
        # Create table
        self.create_table()
        
        # Scrape all sections
        self.scrape_publications()
        time.sleep(2)
        
        self.scrape_newsletters()
        time.sleep(2)
        
        self.scrape_podcasts()
        time.sleep(2)
        
        self.scrape_all_blogs()
        
        print("\n" + "=" * 50)
        print("Scraping completed!")
        print(f"Total articles scraped and inserted: {self.articles_scraped}")
        print(f"Total articles filtered (outside date range): {self.articles_filtered}")
        print(f"Total articles processed: {self.articles_scraped + self.articles_filtered}")

load_dotenv()

# Usage Example
if __name__ == "__main__":
    # Configure your database connection

    # Database configuration
    db_config = {
        'host': os.getenv('DB_HOST'),
        'user': os.getenv('DB_USER'),      # Replace with your MySQL username
        'password': os.getenv('DB_PASSWORD'),  # Replace with your MySQL password
        'database': os.getenv('DB_NAME')
    }
    
    # Create scraper instance with date range (Jan 1, 2024 to Dec 31, 2025)
    scraper = CAMScraper(db_config, start_date="2024-01-01", end_date="2025-12-31")
    
    # Run full scrape
    scraper.run_full_scrape()
    
    # Or scrape individual sections:
    # scraper.create_table()
    # scraper.scrape_publications()
    # scraper.scrape_newsletters()
    # scraper.scrape_podcasts()
    # scraper.scrape_all_blogs()
    
    # To use a different date range:
    # scraper = CAMScraper(db_config, start_date="2024-06-01", end_date="2024-12-31")