import time
import mysql.connector
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from datetime import datetime
from bs4 import BeautifulSoup
import re
import os
from dotenv import load_dotenv

class ELPScraper:
    def __init__(self, db_config):
    
        self.db_config = db_config
        self.company_name = "ELP"
        self.url = "https://elplaw.in/thought-leadership/"
        self.driver = None
        self.connection = None
        self.cursor = None
        
    def setup_driver(self):
        """Setup Chrome driver with options"""
        options = webdriver.ChromeOptions()
        options.add_argument('--start-maximized')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(options=options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
    def connect_database(self):
        """Connect to MySQL database and create table if not exists"""
        try:
            self.connection = mysql.connector.connect(**self.db_config)
            self.cursor = self.connection.cursor()
            
            # Create table if not exists
            create_table_query = """
            CREATE TABLE IF NOT EXISTS elp_publications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                company_name VARCHAR(255),
                publication_type VARCHAR(255),
                publication_date DATE,
                practice_area TEXT,
                article_name TEXT,
                article_link TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_article (article_link(500))
            )
            """
            self.cursor.execute(create_table_query)
            self.connection.commit()
            print("✓ Database connected and table ready")
            
        except mysql.connector.Error as err:
            print(f"✗ Database error: {err}")
            raise
            
    def parse_date(self, date_string):
        """Parse date string to MySQL date format"""
        try:
            # Remove extra whitespace
            date_string = date_string.strip()
            
            # Parse formats like "4th Nov 2025"
            date_obj = datetime.strptime(re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_string), '%d %b %Y')
            return date_obj.strftime('%Y-%m-%d')
        except Exception as e:
            print(f"✗ Date parsing error for '{date_string}': {e}")
            return None
            
    def is_date_in_range(self, date_string):
        """Check if date is between Jan 2024 and Nov 2025"""
        try:
            date_obj = datetime.strptime(date_string, '%Y-%m-%d')
            start_date = datetime(2024, 1, 1)
            end_date = datetime(2025, 12, 31)
            return start_date <= date_obj <= end_date
        except:
            return False
            
    def scroll_and_load(self, num_scrolls=50, delay=10):
        """Scroll the page to load more articles"""
        print(f"\n📜 Starting scroll sequence ({num_scrolls} scrolls with {delay}s delay)...")
        
        for i in range(num_scrolls):
            # Scroll to bottom
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            print(f"Scroll {i+1}/{num_scrolls} completed", end='\r')
            
            # Wait for content to load
            time.sleep(delay)
            
        print(f"\n✓ Scrolling completed - loaded dynamic content")
        
    def extract_articles(self):
        """Extract all articles from the page"""
        articles = []
        
        try:
            # Get page source and parse with BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Find all figcaption elements
            figcaptions = soup.find_all('figcaption')
            print(f"\n📊 Found {len(figcaptions)} articles on page")
            
            for idx, figcaption in enumerate(figcaptions, 1):
                try:
                    article_data = {}
                    
                    # Extract publication type and date
                    p_tags = figcaption.find_all('p')
                    if len(p_tags) >= 1:
                        first_p = p_tags[0]
                        spans = first_p.find_all('span')
                        
                        if len(spans) >= 2:
                            # Publication type
                            pub_type = spans[0].get_text(strip=True)
                            article_data['publication_type'] = pub_type
                            
                            # Publication date
                            pub_date_str = spans[1].get_text(strip=True)
                            pub_date = self.parse_date(pub_date_str)
                            
                            if not pub_date or not self.is_date_in_range(pub_date):
                                continue  # Skip articles outside date range
                                
                            article_data['publication_date'] = pub_date
                    
                    # Extract article name
                    if len(p_tags) >= 2:
                        article_name = p_tags[1].get_text(strip=True)
                        article_data['article_name'] = article_name
                    
                    # Extract practice areas
                    if len(p_tags) >= 3:
                        practice_area_p = p_tags[2]
                        practice_areas = []
                        for a_tag in practice_area_p.find_all('a'):
                            practice_areas.append(a_tag.get_text(strip=True))
                        article_data['practice_area'] = ' | '.join(practice_areas)
                    
                    # Extract article link
                    view_more_link = figcaption.find('a', class_='btn')
                    if view_more_link and view_more_link.get('href'):
                        article_data['article_link'] = view_more_link['href']
                    
                    # Add company name
                    article_data['company_name'] = self.company_name
                    
                    # Validate required fields
                    if all(key in article_data for key in ['publication_type', 'publication_date', 
                                                            'article_name', 'article_link']):
                        articles.append(article_data)
                    
                except Exception as e:
                    print(f"✗ Error parsing article {idx}: {e}")
                    continue
                    
        except Exception as e:
            print(f"✗ Error extracting articles: {e}")
            
        return articles
        
    def save_to_database(self, articles):
        """Save articles to MySQL database with rate limiting"""
        saved_count = 0
        duplicate_count = 0
        
        insert_query = """
        INSERT INTO elp_publications 
        (company_name, publication_type, publication_date, practice_area, article_name, article_link)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        
        print(f"\n💾 Saving {len(articles)} articles to database...")
        
        for idx, article in enumerate(articles, 1):
            try:
                values = (
                    article['company_name'],
                    article['publication_type'],
                    article['publication_date'],
                    article.get('practice_area', ''),
                    article['article_name'],
                    article['article_link']
                )
                
                self.cursor.execute(insert_query, values)
                self.connection.commit()
                saved_count += 1
                print(f"✓ Saved: {article['article_name'][:60]}... ({idx}/{len(articles)})")
                
                # Rate limiting: 20 second break after every 20 articles
                if saved_count % 20 == 0 and saved_count < len(articles):
                    print(f"\n⏸️  Taking 20 second break after {saved_count} articles...")
                    time.sleep(20)
                    print("▶️  Resuming...")
                
            except mysql.connector.IntegrityError:
                duplicate_count += 1
                print(f"⊘ Duplicate skipped: {article['article_name'][:60]}...")
            except Exception as e:
                print(f"✗ Error saving article: {e}")
                
        print(f"\n✅ Saved: {saved_count} | ⊘ Duplicates: {duplicate_count}")
        
    def run(self):
        """Main execution method"""
        try:
            print("="*70)
            print("ELP Thought Leadership Scraper")
            print("="*70)
            
            # Setup
            print("\n🔧 Setting up Chrome driver...")
            self.setup_driver()
            
            print("🔗 Connecting to database...")
            self.connect_database()
            
            # Navigate to page
            print(f"🌐 Navigating to {self.url}")
            self.driver.get(self.url)
            time.sleep(5)  # Initial page load
            
            # Scroll to load all articles
            self.scroll_and_load(num_scrolls=50, delay=10)
            
            # Extract articles
            articles = self.extract_articles()
            
            if articles:
                # Save to database
                self.save_to_database(articles)
            else:
                print("⚠️  No articles found in the specified date range")
            
            print("\n" + "="*70)
            print("✅ Scraping completed successfully!")
            print("="*70)
            
        except Exception as e:
            print(f"\n❌ Fatal error: {e}")
            raise
            
        finally:
            # Cleanup
            if self.cursor:
                self.cursor.close()
            if self.connection:
                self.connection.close()
            if self.driver:
                self.driver.quit()
            print("\n🧹 Cleanup completed")

load_dotenv()

# Usage Example
if __name__ == "__main__":
    # Database configuration
    db_config = {
        'host': os.getenv('DB_HOST'),
        'user': os.getenv('DB_USER'),      # Replace with your MySQL username
        'password': os.getenv('DB_PASSWORD'),  # Replace with your MySQL password
        'database': os.getenv('DB_NAME')
    }
    
    # Create and run scraper
    scraper = ELPScraper(db_config)
    scraper.run()