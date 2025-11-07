import requests
from bs4 import BeautifulSoup
import mysql.connector
from datetime import datetime
import time
from urllib.parse import urljoin
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class KhaitanScraper:
    def __init__(self, db_config, use_selenium=True):
        """Initialize scraper with database configuration"""
        self.db_config = db_config
        self.company_name = "Khaitan & Co."
        self.use_selenium = use_selenium
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
    def setup_database(self):
        """Create database and table if they don't exist"""
        try:
            conn = mysql.connector.connect(
                host=self.db_config['host'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                port=self.db_config.get('port', 3306)
            )
            cursor = conn.cursor()
            
            cursor.execute("CREATE DATABASE IF NOT EXISTS publications_db")
            cursor.execute("USE publications_db")
            
            create_table_query = """
            CREATE TABLE IF NOT EXISTS `Khaitan&Co_Publications` (
                id INT AUTO_INCREMENT PRIMARY KEY,
                company_name VARCHAR(255),
                publication_type VARCHAR(100),
                publishing_date DATE,
                practice_area VARCHAR(255),
                article_heading TEXT,
                article_link TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_article (article_link(500))
            )
            """
            cursor.execute(create_table_query)
            conn.commit()
            print("✓ Database and table setup completed successfully")
            
        except mysql.connector.Error as err:
            print(f"❌ Database setup error: {err}")
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    
    def init_selenium_driver(self):
        """Initialize Selenium Chrome driver"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument(f'user-agent={self.headers["User-Agent"]}')
        
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    
    def parse_date(self, date_str):
        """Parse date string to MySQL date format"""
        try:
            if "'" in date_str:
                date_str = date_str.replace("'", "20")
                date_obj = datetime.strptime(date_str.strip(), "%d %b %Y")
            elif any(month in date_str for month in ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']):
                date_obj = datetime.strptime(date_str.strip(), "%d %B %Y")
            else:
                return None
            
            return date_obj.strftime("%Y-%m-%d")
        except Exception as e:
            print(f"  ⚠ Date parsing error for '{date_str}': {e}")
            return None
    
    def is_from_jan_2024_onwards(self, date_str):
        """Check if date is from January 2024 onwards to present"""
        try:
            parsed_date = self.parse_date(date_str)
            if parsed_date:
                date_obj = datetime.strptime(parsed_date, "%Y-%m-%d")
                cutoff_date = datetime(2024, 1, 1)
                return date_obj >= cutoff_date
            return False
        except:
            return False
    
    def extract_practice_area_from_url(self, url):
        """Fetch individual article page and extract practice area"""
        # Skip PDF files
        if url.lower().endswith('.pdf'):
            print(f"    ⚠ Skipping PDF file (no practice area extraction)")
            return "Unknown"
            
        try:
            print(f"    🔍 Fetching practice area from: {url}")
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Method 1: Check for <div class="public-footer"><p>Practice Area</p></div>
            public_footer = soup.find('div', class_='public-footer')
            if public_footer:
                practice_p = public_footer.find('p')
                if practice_p:
                    practice_area = practice_p.get_text(strip=True)
                    if practice_area and len(practice_area) > 0:
                        print(f"    ✓ Practice Area (public-footer): {practice_area}")
                        return practice_area
            
            # Method 2: Check for tag list with practice areas
            tags_ul = soup.find('ul', class_=lambda x: x and 'flex' in str(x) and 'gap-2' in str(x))
            if tags_ul:
                tags = []
                for li in tags_ul.find_all('li'):
                    a_tag = li.find('a')
                    if a_tag:
                        tag_text = a_tag.get_text(strip=True)
                        if tag_text:
                            tags.append(tag_text)
                
                if tags:
                    practice_area = ', '.join(tags)
                    print(f"    ✓ Practice Area (tags): {practice_area}")
                    return practice_area
            
            # Method 3: Look for any class containing "practice"
            for elem in soup.find_all(['div', 'span', 'p', 'a']):
                class_attr = elem.get('class', [])
                if any('practice' in str(c).lower() for c in class_attr):
                    text = elem.get_text(strip=True)
                    if text and 5 < len(text) < 100:
                        print(f"    ✓ Practice Area (class match): {text}")
                        return text
            
            print(f"    ⚠ Practice area not found on page")
            return "Unknown"
            
        except Exception as e:
            print(f"    ❌ Error extracting practice area: {e}")
            return "Unknown"
    
    def scroll_to_load_all_content(self, driver, max_scrolls=40):
        """Scroll down the page to load all lazy-loaded content"""
        print("  🔄 Scrolling to load all content...")
        
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_count = 0
        no_change_count = 0
        
        while scroll_count < max_scrolls:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            new_height = driver.execute_script("return document.body.scrollHeight")
            
            scroll_count += 1
            print(f"  📜 Scroll {scroll_count}: Height {last_height} -> {new_height}")
            
            if new_height == last_height:
                no_change_count += 1
                if no_change_count >= 2:
                    print(f"  ✓ Reached bottom after {scroll_count} scrolls")
                    break
            else:
                no_change_count = 0
            
            last_height = new_height
        
        time.sleep(1)
        print(f"  ✓ Content loading complete")
    
    def scrape_thought_leadership(self):
        """Scrape thought-leadership with practice area extraction using Selenium"""
        url = "https://www.khaitanco.com/thought-leadership"
        articles = []
        
        driver = None
        try:
            print(f"\n🔍 Fetching URL: {url}")
            print("  🌐 Initializing browser...")
            
            driver = self.init_selenium_driver()
            driver.get(url)
            
            print("  ⏳ Waiting for page to load...")
            time.sleep(3)
            
            self.scroll_to_load_all_content(driver)
            
            # Get the fully loaded page source
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Find all article cards/blocks on the page
            # Look for links that contain /thought-leadership/
            article_links = soup.find_all('a', href=re.compile(r'/thought-leadership/[^/]+'))
            
            print(f"✓ Found {len(article_links)} article links")
            
            processed_urls = set()
            
            for link_elem in article_links:
                article_url = urljoin(url, link_elem.get('href'))
                
                # Skip duplicates
                if article_url in processed_urls:
                    continue
                processed_urls.add(article_url)
                
                # Get article title from link text or nearby elements
                article_title = link_elem.get_text(strip=True)
                
                # Try to find the parent card/container for more info
                parent = link_elem.find_parent(['div', 'article', 'li'])
                
                # Extract date
                date_str = None
                pub_type = "Unknown"
                
                if parent:
                    parent_text = parent.get_text()
                    
                    # Look for date pattern
                    date_match = re.search(r'\d{2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\'\d{2}', parent_text)
                    if date_match:
                        date_str = date_match.group()
                    
                    # Look for publication type
                    if 'Ergo Update' in parent_text:
                        pub_type = 'Ergo Update'
                    elif 'Ergo Newsflash' in parent_text:
                        pub_type = 'Ergo Newsflash'
                    elif 'Ergo Newsletter' in parent_text:
                        pub_type = 'Ergo Newsletter'
                    elif 'Article' in parent_text:
                        pub_type = 'Article'
                
                # Filter by date
                if date_str and not self.is_from_jan_2024_onwards(date_str):
                    continue
                
                print(f"\n--- Processing Article ---")
                print(f"  📰 Title: {article_title[:80]}...")
                print(f"  📅 Date: {date_str if date_str else 'Unknown'}")
                print(f"  📄 Type: {pub_type}")
                print(f"  🔗 URL: {article_url}")
                
                # Extract practice area from article page
                practice_area = self.extract_practice_area_from_url(article_url)
                time.sleep(0.5)
                
                print(f"  🏢 Practice Area: {practice_area}")
                
                articles.append({
                    'company_name': self.company_name,
                    'publication_type': pub_type,
                    'publishing_date': self.parse_date(date_str) if date_str else None,
                    'practice_area': practice_area,
                    'article_heading': article_title,
                    'article_link': article_url
                })
            
            print(f"\n✓ Total scraped from thought-leadership: {len(articles)}")
            
        except Exception as e:
            print(f"❌ Error scraping thought-leadership: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if driver:
                driver.quit()
                print("  🔒 Browser closed")
        
        return articles
    
    def scrape_news_and_events(self):
        """Scrape news-and-events page with practice area extraction"""
        url = "https://www.khaitanco.com/news-and-events"
        articles = []
        
        driver = None
        try:
            print(f"\n🔍 Fetching URL: {url}")
            print("  🌐 Initializing browser...")
            
            driver = self.init_selenium_driver()
            driver.get(url)
            
            print("  ⏳ Waiting for page to load...")
            time.sleep(3)
            
            self.scroll_to_load_all_content(driver)
            
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Find all article links
            article_links = soup.find_all('a', href=re.compile(r'/news-and-events/[^/]+'))
            
            print(f"✓ Found {len(article_links)} news/event links")
            
            processed_urls = set()
            
            for link_elem in article_links:
                article_url = urljoin(url, link_elem.get('href'))
                
                # Skip duplicates
                if article_url in processed_urls:
                    continue
                processed_urls.add(article_url)
                
                article_title = link_elem.get_text(strip=True)
                
                if not article_title or len(article_title) < 10:
                    continue
                
                # Try to find date in parent container
                parent = link_elem.find_parent(['div', 'article', 'li'])
                date_str = None
                
                if parent:
                    parent_text = parent.get_text()
                    date_match = re.search(r'\d{2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\'\d{2}', parent_text)
                    if date_match:
                        date_str = date_match.group()
                
                print(f"\n--- Processing News/Event ---")
                print(f"  📰 Title: {article_title[:80]}...")
                print(f"  📅 Date: {date_str if date_str else 'Unknown'}")
                print(f"  🔗 URL: {article_url}")
                
                # Extract practice area from article page
                practice_area = self.extract_practice_area_from_url(article_url)
                time.sleep(0.5)
                
                print(f"  🏢 Practice Area: {practice_area}")
                
                articles.append({
                    'company_name': self.company_name,
                    'publication_type': 'News/Event',
                    'publishing_date': self.parse_date(date_str) if date_str else None,
                    'practice_area': practice_area,
                    'article_heading': article_title,
                    'article_link': article_url
                })
            
            print(f"\n✓ Total scraped from news-and-events: {len(articles)}")
            
        except Exception as e:
            print(f"❌ Error scraping news-and-events: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if driver:
                driver.quit()
                print("  🔒 Browser closed")
        
        return articles
    
    def scrape_compass_blog(self):
        """Scrape compass blog"""
        base_url = "https://compass.khaitanco.com"
        url = f"{base_url}/blog/list/0"
        articles = []
        
        try:
            print(f"\n🔍 Fetching URL: {url}")
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            content = response.text
            soup = BeautifulSoup(content, 'html.parser')
            
            page_text = soup.get_text()
            lines = page_text.split('\n')
            
            print(f"✓ Processing blog content...")
            
            current_blog = {}
            for i, line in enumerate(lines):
                line = line.strip()
                if not line or len(line) < 5:
                    continue
                
                date_match = re.search(r'\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}', line)
                
                if date_match:
                    if current_blog and 'heading' in current_blog:
                        articles.append(current_blog)
                    
                    date_str = date_match.group()
                    
                    if not self.is_from_jan_2024_onwards(date_str):
                        current_blog = {}
                        continue
                    
                    print(f"\n--- Processing Blog (Date: {date_str}) ---")
                    current_blog = {'date': date_str}
                
                elif current_blog and 'date' in current_blog and 'heading' not in current_blog:
                    if len(line) > 30 and not any(skip in line.lower() for skip in ['the latest news', 'resources', 'http']):
                        current_blog['heading'] = line
                        print(f"  📰 Heading: {line[:100]}...")
            
            if current_blog and 'heading' in current_blog:
                articles.append(current_blog)
            
            final_articles = []
            for blog in articles:
                if 'heading' not in blog:
                    continue
                
                slug = blog['heading'].lower()
                slug = re.sub(r'[^a-z0-9\s-]', '', slug)
                slug = re.sub(r'\s+', '-', slug)
                slug = slug[:100]
                article_link = f"{base_url}/{slug}"
                
                print(f"\n✅ EXTRACTED:")
                print(f"  Date: {blog.get('date', 'Unknown')}")
                print(f"  Heading: {blog.get('heading', 'Unknown')[:80]}...")
                print(f"  Link: {article_link}")
                
                final_articles.append({
                    'company_name': self.company_name,
                    'publication_type': 'Blog',
                    'publishing_date': self.parse_date(blog.get('date', '')),
                    'practice_area': 'Unknown',
                    'article_heading': blog.get('heading', 'Unknown'),
                    'article_link': article_link
                })
            
            print(f"\n✓ Total scraped from compass blog: {len(final_articles)}")
            
        except Exception as e:
            print(f"❌ Error scraping compass blog: {e}")
            import traceback
            traceback.print_exc()
        
        return final_articles
    
    def save_to_database(self, articles):
        """Save articles to MySQL database"""
        if not articles:
            print("\n⚠ No articles to save")
            return
        
        try:
            conn = mysql.connector.connect(
                host=self.db_config['host'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database='publications_db'
            )
            cursor = conn.cursor()
            
            insert_query = """
            INSERT INTO `Khaitan&Co_Publications` 
            (company_name, publication_type, publishing_date, practice_area, article_heading, article_link)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            company_name=VALUES(company_name),
            publication_type=VALUES(publication_type),
            publishing_date=VALUES(publishing_date),
            practice_area=VALUES(practice_area),
            article_heading=VALUES(article_heading)
            """
            
            inserted = 0
            for article in articles:
                try:
                    cursor.execute(insert_query, (
                        article['company_name'],
                        article['publication_type'],
                        article['publishing_date'],
                        article['practice_area'],
                        article['article_heading'],
                        article['article_link']
                    ))
                    inserted += 1
                except mysql.connector.Error as err:
                    print(f"  ❌ Error inserting article: {err}")
            
            conn.commit()
            print(f"\n✅ Successfully saved {inserted} articles to database")
            
        except mysql.connector.Error as err:
            print(f"❌ Database error: {err}")
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    
    def run(self):
        """Main execution method with progressive saving"""
        print("=" * 60)
        print("🚀 Starting Khaitan & Co. Scraper")
        print("   Target: January 2024 to Present")
        print("   Scroll Limit: 40 scrolls per page")
        print("   Mode: Progressive Saving (saves after each source)")
        print("=" * 60)
        
        self.setup_database()
        
        total_saved = 0
        
        # Scrape and save Thought Leadership
        print("\n" + "=" * 60)
        print("📄 SCRAPING THOUGHT LEADERSHIP")
        print("=" * 60)
        articles_tl = self.scrape_thought_leadership()
        if articles_tl:
            print("\n💾 Saving Thought Leadership articles to database...")
            self.save_to_database(articles_tl)
            total_saved += len(articles_tl)
        time.sleep(2)
        
        # Scrape and save News & Events
        print("\n" + "=" * 60)
        print("📰 SCRAPING NEWS AND EVENTS")
        print("=" * 60)
        articles_news = self.scrape_news_and_events()
        if articles_news:
            print("\n💾 Saving News & Events articles to database...")
            self.save_to_database(articles_news)
            total_saved += len(articles_news)
        time.sleep(2)
        
        # Scrape and save Compass Blog
        print("\n" + "=" * 60)
        print("📝 SCRAPING COMPASS BLOG")
        print("=" * 60)
        articles_blog = self.scrape_compass_blog()
        if articles_blog:
            print("\n💾 Saving Compass Blog articles to database...")
            self.save_to_database(articles_blog)
            total_saved += len(articles_blog)
        
        # Final Summary
        print("\n" + "=" * 60)
        print(f"📊 FINAL SUMMARY")
        print("=" * 60)
        print(f"  Thought Leadership: {len(articles_tl)} articles (✅ Saved)")
        print(f"  News & Events:      {len(articles_news)} articles (✅ Saved)")
        print(f"  Compass Blog:       {len(articles_blog)} articles (✅ Saved)")
        print(f"  " + "-" * 56)
        print(f"  Total Saved:        {total_saved} articles")
        print("=" * 60)
        
        if total_saved > 0:
            print("\n✅ Scraping completed successfully!")
            print(f"   All {total_saved} articles have been saved to the database.")
        else:
            print("\n⚠ No articles found.")
        
        print("=" * 60)

# Example usage
if __name__ == "__main__":
    db_config = {
        'host': 'localhost',
        'user': 'your_username',
        'password': 'your_password',
        'port': 3306
    }
    
    scraper = KhaitanScraper(db_config, use_selenium=True)
    scraper.run()