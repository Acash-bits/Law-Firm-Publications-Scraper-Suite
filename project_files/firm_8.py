from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import mysql.connector
from datetime import datetime
import time

class TrilegalScraperSelenium:
    def __init__(self, db_config, headless=True):
        """
        Initialize the scraper with database configuration
        
        db_config should contain: host, user, password, database
        headless: Run browser in headless mode (default: True)
        """
        self.base_url = "https://trilegal.com/knowledge-repository/"
        self.company_name = "Trilegal"
        self.db_config = db_config
        self.cutoff_date = datetime(2024, 1, 1)
        self.headless = headless
        self.driver = None
        
    def setup_driver(self):
        """Setup Selenium WebDriver"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.maximize_window()
        
    def close_driver(self):
        """Close Selenium WebDriver"""
        if self.driver:
            self.driver.quit()
    
    def connect_db(self):
        """Establish database connection"""
        return mysql.connector.connect(**self.db_config)
    
    def create_table(self):
        """Create the publications table if it doesn't exist"""
        conn = self.connect_db()
        cursor = conn.cursor()
        
        create_table_query = """
        CREATE TABLE IF NOT EXISTS trilegal_publications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            company_name VARCHAR(255),
            article_type VARCHAR(100),
            article_date DATE,
            practice_area TEXT,
            article_heading TEXT,
            article_link TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_article (article_link(500))
        )
        """
        
        cursor.execute(create_table_query)
        conn.commit()
        cursor.close()
        conn.close()
        print("Table created or already exists.")
    
    def parse_date(self, date_str):
        """Convert date string to datetime object"""
        try:
            return datetime.strptime(date_str.strip(), "%d %b %Y")
        except:
            return None
    
    def handle_cookie_consent(self):
        """Handle cookie consent popup if present"""
        try:
            # Wait for potential cookie consent button and click it
            # Adjust selectors based on actual site structure
            wait = WebDriverWait(self.driver, 5)
            
            # Try common cookie consent button selectors
            consent_selectors = [
                "//button[contains(text(), 'Accept')]",
                "//button[contains(text(), 'I agree')]",
                "//button[contains(text(), 'Agree')]",
                "//a[contains(text(), 'Accept')]",
                "//button[@id='accept']",
                "//button[@class*='accept']"
            ]
            
            for selector in consent_selectors:
                try:
                    button = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                    button.click()
                    print("Cookie consent accepted")
                    time.sleep(2)
                    return
                except:
                    continue
                    
        except TimeoutException:
            # No cookie consent found, continue
            pass
    
    def scrape_page(self, url):
        """Scrape a single page and return articles data"""
        try:
            print(f"Loading page: {url}")
            self.driver.get(url)
            
            # Handle cookie consent on first page
            if url == self.base_url:
                self.handle_cookie_consent()
            
            # Wait for articles to load
            wait = WebDriverWait(self.driver, 15)
            
            try:
                # Wait for article items to be present
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='knowledge_repository']")))
                time.sleep(3)  # Additional wait for dynamic content
            except TimeoutException:
                print("Timeout waiting for articles to load")
                return [], False
            
            articles = []
            
            # Find all article items
            # Try multiple selectors
            article_elements = []
            
            # Try finding by item class
            try:
                article_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.item")
                print(f"Found {len(article_elements)} article items with class 'item'")
            except:
                pass
            
            # If no items found, try finding by article structure
            if not article_elements:
                try:
                    article_elements = self.driver.find_elements(By.CSS_SELECTOR, "article")
                    print(f"Found {len(article_elements)} article elements")
                except:
                    pass
            
            # Last resort: find all links containing knowledge_repository
            if not article_elements:
                links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='knowledge_repository']")
                print(f"Found {len(links)} knowledge repository links")
                
                for link in links:
                    article_data = self._parse_article_from_link_element(link)
                    if article_data:
                        articles.append(article_data)
                        if article_data['article_date'] and article_data['article_date'] < self.cutoff_date:
                            return articles, True
            else:
                # Parse each article item
                for item in article_elements:
                    article_data = self._parse_article_item_element(item)
                    if article_data:
                        articles.append(article_data)
                        if article_data['article_date'] and article_data['article_date'] < self.cutoff_date:
                            return articles, True
            
            return articles, False
            
        except Exception as e:
            print(f"Error scraping page {url}: {e}")
            import traceback
            traceback.print_exc()
            return [], False
    
    def _parse_article_item_element(self, item):
        """Parse an article from an item element"""
        try:
            # Find the link
            link = item.find_element(By.CSS_SELECTOR, "a[href*='knowledge_repository']")
            article_link = link.get_attribute('href')
            
            if not article_link or 'knowledge-repository/page' in article_link:
                return None
            
            # Extract info div (type and date)
            try:
                info_div = item.find_element(By.CSS_SELECTOR, "div.info")
                type_span = info_div.find_element(By.CSS_SELECTOR, "span.type")
                date_span = info_div.find_element(By.CSS_SELECTOR, "span.date")
                
                article_type = type_span.text.strip()
                date_str = date_span.text.strip()
                article_date = self.parse_date(date_str)
            except NoSuchElementException:
                return None
            
            # Extract heading
            try:
                heading_tag = item.find_element(By.CSS_SELECTOR, "h3")
                article_heading = heading_tag.text.strip()
            except NoSuchElementException:
                article_heading = ""
            
            # Extract practice areas from tags div
            practice_area = ""
            try:
                tags_div = item.find_element(By.CSS_SELECTOR, "div.tags")
                tags = tags_div.find_elements(By.TAG_NAME, "a")
                practice_area = " | ".join([tag.text.strip() for tag in tags if tag.text.strip()])
            except NoSuchElementException:
                pass
            
            print(f"Parsed: {article_heading[:50]}... | Type: {article_type} | Areas: {practice_area}")
            
            return {
                'company_name': self.company_name,
                'article_type': article_type,
                'article_date': article_date,
                'practice_area': practice_area,
                'article_heading': article_heading,
                'article_link': article_link
            }
            
        except Exception as e:
            print(f"Error parsing article item: {e}")
            return None
    
    def _parse_article_from_link_element(self, link):
        """Fallback: Parse article from link element"""
        try:
            article_link = link.get_attribute('href')
            
            if not article_link or 'knowledge-repository/page' in article_link:
                return None
            
            # Get parent element
            parent = self.driver.execute_script("return arguments[0].parentElement;", link)
            
            # Try to find info div
            try:
                info_div = parent.find_element(By.CSS_SELECTOR, "div.info")
                type_span = info_div.find_element(By.CSS_SELECTOR, "span.type")
                date_span = info_div.find_element(By.CSS_SELECTOR, "span.date")
                
                article_type = type_span.text.strip()
                date_str = date_span.text.strip()
                article_date = self.parse_date(date_str)
            except NoSuchElementException:
                return None
            
            # Extract heading
            try:
                heading_tag = link.find_element(By.CSS_SELECTOR, "h3")
                article_heading = heading_tag.text.strip()
            except NoSuchElementException:
                article_heading = ""
            
            # Extract practice areas
            practice_area = ""
            try:
                # Try in parent
                tags_div = parent.find_element(By.CSS_SELECTOR, "div.tags")
                tags = tags_div.find_elements(By.TAG_NAME, "a")
                practice_area = " | ".join([tag.text.strip() for tag in tags if tag.text.strip()])
            except NoSuchElementException:
                # Try in grandparent
                try:
                    grandparent = self.driver.execute_script("return arguments[0].parentElement.parentElement;", link)
                    tags_div = grandparent.find_element(By.CSS_SELECTOR, "div.tags")
                    tags = tags_div.find_elements(By.TAG_NAME, "a")
                    practice_area = " | ".join([tag.text.strip() for tag in tags if tag.text.strip()])
                except:
                    pass
            
            return {
                'company_name': self.company_name,
                'article_type': article_type,
                'article_date': article_date,
                'practice_area': practice_area,
                'article_heading': article_heading,
                'article_link': article_link
            }
            
        except Exception as e:
            return None
    
    def save_to_db(self, articles):
        """Save articles to database"""
        if not articles:
            return 0
        
        conn = self.connect_db()
        cursor = conn.cursor()
        
        insert_query = """
        INSERT INTO trilegal_publications 
        (company_name, article_type, article_date, practice_area, article_heading, article_link)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        company_name = VALUES(company_name),
        article_type = VALUES(article_type),
        article_date = VALUES(article_date),
        practice_area = VALUES(practice_area),
        article_heading = VALUES(article_heading)
        """
        
        inserted = 0
        for article in articles:
            try:
                cursor.execute(insert_query, (
                    article['company_name'],
                    article['article_type'],
                    article['article_date'],
                    article['practice_area'],
                    article['article_heading'],
                    article['article_link']
                ))
                inserted += cursor.rowcount
            except Exception as e:
                print(f"Error inserting article: {e}")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return inserted
    
    def run(self, max_pages=None, stop_at_date=True):
        """
        Main scraping function
        
        Args:
            max_pages (int, optional): Maximum number of pages to scrape
            stop_at_date (bool): If True, stops when reaching articles before January 2024
        """
        print("Starting Trilegal Knowledge Repository Scraper (Selenium)...")
        if max_pages:
            print(f"Maximum pages to scrape: {max_pages}")
        if stop_at_date:
            print(f"Will stop at articles before January 2024")
        
        try:
            # Setup driver
            self.setup_driver()
            
            # Create table
            self.create_table()
            
            total_articles = 0
            page = 1
            
            while True:
                # Check if we've reached max_pages limit
                if max_pages and page > max_pages:
                    print(f"\nReached maximum page limit ({max_pages}). Stopping.")
                    break
                
                if page == 1:
                    url = self.base_url
                else:
                    url = f"{self.base_url}page/{page}/"
                
                print(f"\n{'='*60}")
                print(f"Scraping page {page}: {url}")
                print('='*60)
                
                articles, should_stop = self.scrape_page(url)
                
                if articles:
                    inserted = self.save_to_db(articles)
                    total_articles += len(articles)
                    print(f"\nFound {len(articles)} articles on page {page}")
                    print(f"Inserted/Updated {inserted} records")
                else:
                    print(f"\nNo articles found on page {page}")
                
                # Check if we should stop based on date
                if stop_at_date and should_stop:
                    print("\nReached articles from before January 2024. Stopping.")
                    break
                
                # If no articles found, we might have reached the end
                if not articles:
                    print("\nNo more articles found. Reached the end.")
                    break
                
                page += 1
                time.sleep(3)  # Be polite to the server
            
            print(f"\n{'='*60}")
            print(f"Scraping completed!")
            print(f"Total articles processed: {total_articles}")
            print(f"Total pages scraped: {page}")
            print(f"{'='*60}")
            
        finally:
            # Always close the driver
            self.close_driver()

import os
from dotenv import load_dotenv

load_dotenv()

# Usage Example
if __name__ == "__main__":
    # Database configuration
    db_config = {
        'host' : os.getenv('DB_HOST'),
        'password' : os.getenv('DB_PASSWORD'),  # Replace with your MySQL password
        'user' : os.getenv('DB_USER'),
        'port' :  os.getenv('DB_PORT')
    }
    
    # Create scraper instance (headless=False to see browser, headless=True to hide)
    scraper = TrilegalScraperSelenium(db_config, headless=False)
    
    # Run with different options
    scraper.run()  # Default: all pages until Jan 2024
    # scraper.run(max_pages=5)  # First 5 pages
    # scraper.run(max_pages=10, stop_at_date=False)  # Exactly 10 pages