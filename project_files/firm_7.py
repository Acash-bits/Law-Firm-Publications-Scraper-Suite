import requests
from bs4 import BeautifulSoup
import mysql.connector
from mysql.connector import Error
import time
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Date range for filtering
START_DATE = datetime(2024, 1, 1)
END_DATE = datetime(2025, 12, 31)

class SAMScraper:
    def __init__(self, db_config):
        """Initialize the scraper with database configuration"""
        self.db_config = db_config
        self.company_name = "SAM"
        
        self.practices = {
            'General Corporate': 'https://www.amsshardul.com/insight-category/general-corporate/',
            'Private Equity': 'https://www.amsshardul.com/insight-category/private-equity/',
            'Banking & Finance': 'https://www.amsshardul.com/insight-category/banking-finance/',
            'Insolvency & Restructuring': 'https://www.amsshardul.com/insight-category/insolvency-restructuring-reports/',
            'Capital Markets': 'https://www.amsshardul.com/insight-category/capital-markets/',
            'Tax': 'https://www.amsshardul.com/insight-category/tax/',
            'Intellectual Property': 'https://www.amsshardul.com/insight-category/intellectual-property/'
        }
        
        self.publication_types = {
            'Articles/Alerts': '?category=alerts',
            'Reports': '?category=reports',
            'Research Papers': '?category=research-papers'
        }
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        
    def create_table(self):
        """Create the SAM_publications table if it doesn't exist"""
        try:
            connection = mysql.connector.connect(**self.db_config)
            cursor = connection.cursor()
            
            create_table_query = """
            CREATE TABLE IF NOT EXISTS SAM_publications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                company_name VARCHAR(10) NOT NULL,
                publication_type VARCHAR(50) NOT NULL,
                publication_date DATE,
                practice_area VARCHAR(100) NOT NULL,
                article_name TEXT NOT NULL,
                article_link VARCHAR(500) NOT NULL UNIQUE,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_practice (practice_area),
                INDEX idx_pub_type (publication_type),
                INDEX idx_pub_date (publication_date)
            )
            """
            
            cursor.execute(create_table_query)
            connection.commit()
            logger.info("Table SAM_publications created or already exists")
            
        except Error as e:
            logger.error(f"Error creating table: {e}")
        finally:
            if connection.is_connected():
                cursor.close()
                connection.close()
    
    def parse_date(self, date_string):
        """Parse date string to MySQL date format and datetime object"""
        try:
            date_obj = datetime.strptime(date_string.strip(), '%B %d, %Y')
            return date_obj.strftime('%Y-%m-%d'), date_obj
        except Exception as e:
            logger.warning(f"Error parsing date '{date_string}': {e}")
            return None, None
    
    def get_page_content(self, url):
        """Fetch page content with error handling"""
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
    
    def extract_articles(self, html_content):
        """Extract articles from HTML content - FIXED to find great-grandparent link"""
        articles = []
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all insight-text divs
        insight_divs = soup.find_all('div', class_='insight-text')
        logger.info(f"Found {len(insight_divs)} insight-text divs")
        
        for idx, insight_div in enumerate(insight_divs):
            try:
                # Get date from insight-text div
                date_text = None
                date_div = insight_div.find('div', class_='date')
                if date_div:
                    date_p = date_div.find('p')
                    date_text = date_p.text.strip() if date_p else None
                
                # Get title from insight-text div
                title_tag = insight_div.find('h3')
                article_name = title_tag.text.strip() if title_tag else None
                
                # THE FIX: Navigate up to find the <a> tag that wraps everything
                article_link = None
                current = insight_div
                
                # Go up the tree looking for an <a> tag (up to 5 levels)
                for level in range(5):
                    if current.parent:
                        current = current.parent
                        if current.name == 'a':
                            article_link = current.get('href', '').strip()
                            logger.debug(f"Found link at level {level+1}: {article_link[:50]}")
                            break
                
                if article_link and article_name and date_text:
                    mysql_date, date_obj = self.parse_date(date_text)
                    
                    articles.append({
                        'article_link': article_link,
                        'article_name': article_name,
                        'publication_date': mysql_date,
                        'date_obj': date_obj
                    })
                    logger.debug(f"Extracted: {article_name[:50]}... | {date_text}")
                else:
                    missing = []
                    if not article_link: missing.append("link")
                    if not article_name: missing.append("name")
                    if not date_text: missing.append("date")
                    logger.debug(f"Article {idx}: Missing {', '.join(missing)}")
                    
            except Exception as e:
                logger.warning(f"Error extracting article {idx}: {e}")
                continue
        
        logger.info(f"Successfully extracted {len(articles)} articles")
        return articles
    
    def scrape_practice_publication(self, practice_name, practice_url, pub_type, pub_param):
        """Scrape all pages for a specific practice area and publication type"""
        all_articles = []
        page = 1
        max_pages = 20
        consecutive_empty_pages = 0
        max_consecutive_empty = 2
        found_old_article = False
        
        while page <= max_pages:
            if page == 1:
                url = f"{practice_url}{pub_param}"
            else:
                url = f"{practice_url}page/{page}/{pub_param}"
            
            logger.info(f"Scraping: {practice_name} - {pub_type} - Page {page}")
            
            html_content = self.get_page_content(url)
            if not html_content:
                consecutive_empty_pages += 1
                logger.warning(f"Failed to fetch page {page}. Attempt {consecutive_empty_pages}/{max_consecutive_empty}")
                
                if consecutive_empty_pages >= max_consecutive_empty:
                    logger.info(f"No more pages found for {practice_name} - {pub_type}")
                    break
                
                time.sleep(3)
                continue
            
            articles = self.extract_articles(html_content)
            
            if not articles:
                consecutive_empty_pages += 1
                logger.info(f"No articles found on page {page}. Attempt {consecutive_empty_pages}/{max_consecutive_empty}")
                
                if consecutive_empty_pages >= max_consecutive_empty:
                    logger.info(f"No more articles found for {practice_name} - {pub_type}")
                    break
                
                time.sleep(2)
                page += 1
                continue
            
            consecutive_empty_pages = 0
            
            # Filter articles by date range
            filtered_articles = []
            for article in articles:
                date_obj = article.get('date_obj')
                
                if date_obj and START_DATE <= date_obj <= END_DATE:
                    article['practice_area'] = practice_name
                    article['publication_type'] = pub_type
                    article['company_name'] = self.company_name
                    filtered_articles.append(article)
                    
                    print(f"\n{'='*80}")
                    print(f"Found Article:")
                    print(f"  Practice: {practice_name}")
                    print(f"  Type: {pub_type}")
                    print(f"  Date: {article['publication_date']}")
                    print(f"  Title: {article['article_name']}")
                    print(f"  Link: {article['article_link']}")
                    print(f"{'='*80}")
                    
                    self.save_single_article(article)
                    
                elif date_obj and date_obj < START_DATE:
                    found_old_article = True
                    logger.info(f"Found article older than Jan 2024: {article['publication_date']}")
            
            all_articles.extend(filtered_articles)
            logger.info(f"Found {len(filtered_articles)} articles in date range on page {page}")
            
            if found_old_article:
                logger.info(f"Reached articles older than Jan 2024. Stopping pagination for {practice_name} - {pub_type}")
                break
            
            time.sleep(2)
            page += 1
        
        return all_articles
    
    def save_single_article(self, article):
        """Save a single article to MySQL database immediately"""
        try:
            connection = mysql.connector.connect(**self.db_config)
            cursor = connection.cursor()
            
            insert_query = """
            INSERT INTO SAM_publications 
            (company_name, publication_type, publication_date, practice_area, article_name, article_link)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                publication_date = VALUES(publication_date),
                article_name = VALUES(article_name)
            """
            
            cursor.execute(insert_query, (
                article['company_name'],
                article['publication_type'],
                article['publication_date'],
                article['practice_area'],
                article['article_name'],
                article['article_link']
            ))
            
            connection.commit()
            
            if cursor.rowcount > 0:
                print(f"  ✓ Saved to database")
            else:
                print(f"  ℹ Already exists in database")
            
        except Error as e:
            logger.error(f"Database error: {e}")
            print(f"  ✗ Failed to save to database: {e}")
        finally:
            if connection.is_connected():
                cursor.close()
                connection.close()
    
    def scrape_all(self):
        """Main method to scrape all practices and publication types"""
        logger.info("Starting SAM scraper...")
        logger.info(f"Date range: {START_DATE.strftime('%B %d, %Y')} to {END_DATE.strftime('%B %d, %Y')}")
        
        self.create_table()
        
        total_articles = []
        practice_count = 0
        
        for practice_name, practice_url in self.practices.items():
            practice_count += 1
            print(f"\n\n{'#'*80}")
            print(f"# PRACTICE {practice_count}/{len(self.practices)}: {practice_name}")
            print(f"{'#'*80}\n")
            logger.info(f"Scraping Practice: {practice_name}")
            
            practice_articles = 0
            
            for pub_type, pub_param in self.publication_types.items():
                print(f"\n{'-'*80}")
                print(f"Publication Type: {pub_type}")
                print(f"{'-'*80}")
                
                articles = self.scrape_practice_publication(
                    practice_name, 
                    practice_url, 
                    pub_type, 
                    pub_param
                )
                
                if articles:
                    logger.info(f"Found {len(articles)} articles for {practice_name} - {pub_type}")
                    total_articles.extend(articles)
                    practice_articles += len(articles)
                else:
                    logger.info(f"No articles found for {practice_name} - {pub_type}")
                
                time.sleep(3)
            
            print(f"\n{'='*80}")
            print(f"Practice Summary: {practice_name}")
            print(f"Total articles found: {practice_articles}")
            print(f"{'='*80}\n")
        
        print(f"\n\n{'#'*80}")
        print(f"# SCRAPING COMPLETED!")
        print(f"# Total articles scraped: {len(total_articles)}")
        print(f"# Date range: Jan 2024 to Dec 2025")
        print(f"{'#'*80}\n")
        logger.info(f"Scraping completed! Total articles found: {len(total_articles)}")
        
        return total_articles

import os
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    db_config = {
        'host' : os.getenv('DB_HOST'),
        'password' : os.getenv('DB_PASSWORD'),  # Replace with your MySQL password
        'user' : os.getenv('DB_USER'),
        'port' :  os.getenv('DB_PORT')
    }
    
    scraper = SAMScraper(db_config)
    articles = scraper.scrape_all()
    
    print(f"\nScraping Summary:")
    print(f"Total articles scraped: {len(articles)}")