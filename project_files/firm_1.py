import requests
from bs4 import BeautifulSoup
import mysql.connector
from datetime import datetime
import time
import logging
import os
from dotenv import load_dotenv 

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AZBResourceScraper:
    def __init__(self, db_config):
        """
        Initialize the scraper with database configuration
        
        Args:
            db_config (dict): MySQL database configuration
                {
                    'host': os.getenv('DB_HOST'),
                    'user': os.getenv('DB_USER'),
                    'password': os.getenv('DB_PASSWORD'),
                    'database': os.getenv('DB_NAME')
                }
        """
        self.base_url = "https://www.azbpartners.com/resource/"
        self.db_config = db_config
        self.connection = None
        self.cursor = None
        self.company_name = "AZB Partners"
        
    def connect_db(self):
        """Establish database connection"""
        try:
            self.connection = mysql.connector.connect(**self.db_config)
            self.cursor = self.connection.cursor()
            logger.info("Database connection established")
        except mysql.connector.Error as err:
            logger.error(f"Database connection error: {err}")
            raise
    
    def create_table(self):
        """Create azb_partners_publications table if it doesn't exist"""
        create_table_query = """
        CREATE TABLE IF NOT EXISTS azb_partners_publications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            company_name VARCHAR(255) NOT NULL,
            publication_type VARCHAR(255) NOT NULL,
            publication_date DATE NOT NULL,
            practice_area VARCHAR(255),
            article_heading VARCHAR(1000) NOT NULL,
            article_link VARCHAR(500) UNIQUE NOT NULL,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_date (publication_date),
            INDEX idx_type (publication_type),
            INDEX idx_practice (practice_area)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        try:
            self.cursor.execute(create_table_query)
            self.connection.commit()
            logger.info("Table 'azb_partners_publications' ready")
        except mysql.connector.Error as err:
            logger.error(f"Error creating table: {err}")
            raise
    
    def parse_date(self, date_str):
        """
        Parse date string to MySQL DATE format
        
        Args:
            date_str (str): Date string like "Oct 08, 2025"
            
        Returns:
            str: Date in YYYY-MM-DD format
        """
        try:
            # Clean the date string
            date_str = date_str.strip()
            dt = datetime.strptime(date_str, "%b %d, %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError as e:
            logger.warning(f"Error parsing date '{date_str}': {e}")
            return None
    
    def scrape_page(self, page_num=1):
        """
        Scrape a single page
        
        Args:
            page_num (int): Page number to scrape
            
        Returns:
            list: List of publication dictionaries
        """
        if page_num == 1:
            url = self.base_url
        else:
            url = f"{self.base_url}page/{page_num}/"
        
        logger.info(f"Scraping page {page_num}: {url}")
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            publications = []
            
            # Find all resource blocks
            resource_blocks = soup.find_all('div', class_='resource-blk')
            
            logger.info(f"Found {len(resource_blocks)} resource blocks on page {page_num}")
            
            for block in resource_blocks:
                try:
                    # Extract publication type
                    label_span = block.find('span', class_='label-span')
                    if not label_span:
                        continue
                    
                    publication_type = label_span.get_text(strip=True)
                    
                    # Skip if it's a deal
                    if publication_type.lower() == 'deals':
                        logger.info(f"Skipping deal: {publication_type}")
                        continue
                    
                    # Extract article heading and link
                    h3_tag = block.find('h3')
                    if not h3_tag:
                        continue
                    
                    article_heading = h3_tag.get_text(strip=True)
                    
                    # Get the link from the parent anchor tag
                    link_tag = block.find('a', href=True)
                    if not link_tag:
                        continue
                    
                    article_link = link_tag['href']
                    if not article_link.startswith('http'):
                        article_link = f"https://www.azbpartners.com{article_link}"
                    
                    # Extract date and practice area from resource-tags
                    resource_tags = block.find('div', class_='resource-tags')
                    publication_date = None
                    practice_area = None
                    
                    if resource_tags:
                        # Get the date (first span)
                        date_span = resource_tags.find('span')
                        if date_span:
                            date_str = date_span.get_text(strip=True)
                            publication_date = self.parse_date(date_str)
                        
                        # Get practice area (anchor tag)
                        practice_link = resource_tags.find('a')
                        if practice_link:
                            practice_area = practice_link.get_text(strip=True)
                    
                    # Create publication dictionary
                    publication = {
                        'company_name': self.company_name,
                        'publication_type': publication_type,
                        'publication_date': publication_date,
                        'practice_area': practice_area,
                        'article_heading': article_heading,
                        'article_link': article_link
                    }
                    
                    publications.append(publication)
                    logger.debug(f"Extracted: {article_heading}")
                    
                except Exception as e:
                    logger.error(f"Error parsing resource block: {e}")
                    continue
            
            logger.info(f"Successfully extracted {len(publications)} publications from page {page_num}")
            return publications
            
        except requests.RequestException as e:
            logger.error(f"Error fetching page {page_num}: {e}")
            return []
    
    def save_publication(self, publication):
        """
        Save a single publication to database
        
        Args:
            publication (dict): Publication data
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        insert_query = """
        INSERT INTO azb_partners_publications 
        (company_name, publication_type, publication_date, practice_area, article_heading, article_link)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            company_name = VALUES(company_name),
            publication_type = VALUES(publication_type),
            publication_date = VALUES(publication_date),
            practice_area = VALUES(practice_area),
            article_heading = VALUES(article_heading),
            scraped_at = CURRENT_TIMESTAMP
        """
        
        try:
            self.cursor.execute(insert_query, (
                publication['company_name'],
                publication['publication_type'],
                publication['publication_date'],
                publication['practice_area'],
                publication['article_heading'],
                publication['article_link']
            ))
            self.connection.commit()
            logger.debug(f"Saved: {publication['article_heading']}")
            return True
        except mysql.connector.Error as err:
            logger.error(f"Error saving publication '{publication['article_heading']}': {err}")
            return False
    
    def scrape_all(self, max_pages=None):
        """
        Scrape all pages until no more data is found
        
        Args:
            max_pages (int, optional): Maximum number of pages to scrape
        """
        self.connect_db()
        self.create_table()
        
        page_num = 1
        total_saved = 0
        consecutive_empty = 0
        
        while True:
            if max_pages and page_num > max_pages:
                logger.info(f"Reached maximum page limit: {max_pages}")
                break
            
            publications = self.scrape_page(page_num)
            
            if not publications:
                consecutive_empty += 1
                logger.info(f"No publications found on page {page_num}")
                if consecutive_empty >= 2:
                    logger.info("No more publications found on consecutive pages. Stopping.")
                    break
            else:
                consecutive_empty = 0
                for pub in publications:
                    if self.save_publication(pub):
                        total_saved += 1
            
            page_num += 1
            time.sleep(2)  # Be polite, wait 2 seconds between requests
        
        logger.info(f"Scraping complete. Total publications saved: {total_saved}")
        self.close_db()
    
    def get_statistics(self):
        """Get statistics about scraped publications"""
        self.connect_db()
        
        queries = {
            'total': "SELECT COUNT(*) FROM azb_partners_publications",
            'by_type': "SELECT publication_type, COUNT(*) as count FROM azb_partners_publications GROUP BY publication_type",
            'by_practice': "SELECT practice_area, COUNT(*) as count FROM azb_partners_publications GROUP BY practice_area ORDER BY count DESC LIMIT 10",
            'recent': "SELECT article_heading, publication_date FROM azb_partners_publications ORDER BY publication_date DESC LIMIT 5"
        }
        
        print("\n" + "="*80)
        print("SCRAPING STATISTICS")
        print("="*80)
        
        # Total count
        self.cursor.execute(queries['total'])
        total = self.cursor.fetchone()[0]
        print(f"\nTotal Publications: {total}")
        
        # By type
        print("\nPublications by Type:")
        self.cursor.execute(queries['by_type'])
        for row in self.cursor.fetchall():
            print(f"  - {row[0]}: {row[1]}")
        
        # By practice area
        print("\nTop 10 Practice Areas:")
        self.cursor.execute(queries['by_practice'])
        for row in self.cursor.fetchall():
            print(f"  - {row[0]}: {row[1]}")
        
        # Recent publications
        print("\nMost Recent Publications:")
        self.cursor.execute(queries['recent'])
        for row in self.cursor.fetchall():
            print(f"  - {row[1]}: {row[0]}")
        
        print("\n" + "="*80)
        
        self.close_db()
    
    def close_db(self):
        """Close database connection"""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        logger.info("Database connection closed")

load_dotenv()

def main():
    # Database configuration
    db_config = {
        'host': os.getenv('DB_HOST'),
        'user': os.getenv('DB_USER'),      # Replace with your MySQL username
        'password': os.getenv('DB_PASSWORD'),  # Replace with your MySQL password
        'database': os.getenv('DB_NAME')
    }
    
    # Create scraper instance
    scraper = AZBResourceScraper(db_config)
    
    # Scrape all pages (or set max_pages to limit)
    scraper.scrape_all(max_pages=None)  # Set to None for all pages, or a number to limit
    
    # Show statistics
    scraper.get_statistics()


if __name__ == "__main__":
    main()