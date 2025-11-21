import requests
from bs4 import BeautifulSoup
import mysql.connector
from mysql.connector import Error
import time
from datetime import datetime
from urllib.parse import urljoin

class PublicationScraper:
    def __init__(self, host='localhost', user='root', password='1234', database='publications_db', cutoff_date='2024-01-01'):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.base_url = "https://induslaw.com"
        self.cutoff_date = datetime.strptime(cutoff_date, '%Y-%m-%d')
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.connection = None
        self.setup_database()
        print(f"📅 Scraping articles published on or after: {cutoff_date}")
    
    def get_connection(self):
        """Create database connection"""
        try:
            connection = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database
            )
            return connection
        except Error as e:
            print(f"Error connecting to MySQL: {e}")
            return None
    
    def setup_database(self):
        """Create the database and table if they don't exist"""
        try:
            # First connect without database to create it
            connection = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password
            )
            cursor = connection.cursor()
            
            # Create database if not exists
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.database}")
            print(f"✓ Database '{self.database}' ready")
            
            cursor.close()
            connection.close()
            
            # Now connect to the database and create table
            connection = self.get_connection()
            if connection:
                cursor = connection.cursor()
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS publications (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        company_name VARCHAR(255) NOT NULL,
                        published_date DATE,
                        practice_area VARCHAR(255),
                        heading TEXT NOT NULL,
                        link TEXT NOT NULL,
                        scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE KEY unique_publication (company_name(100), link(255))
                    )
                ''')
                
                connection.commit()
                cursor.close()
                connection.close()
                print("✓ Table 'publications' ready")
        except Error as e:
            print(f"Error setting up database: {e}")
    
    def parse_date(self, date_str):
        """Convert date from DD/MM/YYYY to YYYY-MM-DD for database"""
        try:
            date_obj = datetime.strptime(date_str.strip(), '%d/%m/%Y')
            return date_obj.strftime('%Y-%m-%d'), date_obj
        except:
            return date_str, None
    
    def is_date_valid(self, date_obj):
        """Check if date is on or after cutoff date"""
        if date_obj is None:
            return True  # Include if date parsing failed
        return date_obj >= self.cutoff_date
    
    def scrape_induslaw(self):
        """Scrape publications from IndusLaw website"""
        url = "https://induslaw.com/publication"
        company_name = "IndusLaw"
        
        print(f"\n{'='*60}")
        print(f"Starting scrape for {company_name}")
        print(f"URL: {url}")
        print(f"{'='*60}\n")
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all publication items
            publications = []
            article_count = 0
            skipped_count = 0
            processed_count = 0
            
            # Find all title links
            title_links = soup.find_all('a', class_='mediatitle', target='_blank')
            
            print(f"Found {len(title_links)} publications on page\n")
            
            for idx, title_link in enumerate(title_links, 1):
                try:
                    processed_count += 1
                    
                    # Extract heading and link
                    heading = title_link.get_text(strip=True)
                    link = urljoin(self.base_url, title_link.get('href', ''))
                    
                    # Find the parent container to get practice area and date
                    parent = title_link.find_parent()
                    while parent and parent.name != 'div':
                        parent = parent.find_parent()
                    
                    practice_area = "N/A"
                    published_date = "N/A"
                    date_obj = None
                    
                    if parent:
                        # Find practice area
                        practice_area_elem = parent.find('strong', string='Practice Area :')
                        if practice_area_elem and practice_area_elem.parent:
                            practice_span = practice_area_elem.find_next('span')
                            if practice_span:
                                practice_link = practice_span.find('a')
                                if practice_link:
                                    practice_area = practice_link.get_text(strip=True)
                        
                        # Find published date
                        date_elem = parent.find('strong', string='Published on  :')
                        if date_elem and date_elem.parent:
                            date_text = date_elem.parent.get_text(strip=True)
                            date_str = date_text.replace('Published on  :', '').strip()
                            published_date, date_obj = self.parse_date(date_str)
                    
                    # Check if date is within range
                    if not self.is_date_valid(date_obj):
                        skipped_count += 1
                        print(f"⏭ Skipped Article #{processed_count} (published before cutoff date)")
                        print(f"  Published Date: {published_date}")
                        print(f"  Heading: {heading[:60]}...")
                        print("-" * 60)
                        continue
                    
                    publication = {
                        'company_name': company_name,
                        'heading': heading,
                        'link': link,
                        'practice_area': practice_area,
                        'published_date': published_date
                    }
                    
                    publications.append(publication)
                    article_count += 1
                    
                    # Print to terminal
                    print(f"✓ Article #{article_count} (Processed #{processed_count})")
                    print(f"  Heading: {heading}")
                    print(f"  Practice Area: {practice_area}")
                    print(f"  Published Date: {published_date}")
                    print(f"  Link: {link}")
                    print("-" * 60)
                    
                    # Save to database
                    self.save_to_database(publication)
                    
                    # Stop for 10 seconds after every 20 articles
                    if article_count % 20 == 0:
                        print(f"\n⏸ Processed {article_count} valid articles. Pausing for 10 seconds...\n")
                        time.sleep(10)
                    
                except Exception as e:
                    print(f"✗ Error processing article {processed_count}: {str(e)}")
                    continue
            
            print(f"\n{'='*60}")
            print(f"✓ Scraping complete!")
            print(f"  Total articles found: {processed_count}")
            print(f"  Articles scraped (after {self.cutoff_date.strftime('%Y-%m-%d')}): {article_count}")
            print(f"  Articles skipped (before cutoff): {skipped_count}")
            print(f"{'='*60}\n")
            
            return publications
            
        except requests.RequestException as e:
            print(f"✗ Error fetching {url}: {str(e)}")
            return []
    
    def save_to_database(self, publication):
        """Save publication to MySQL database"""
        connection = self.get_connection()
        if not connection:
            return
        
        try:
            cursor = connection.cursor()
            
            sql = '''
                INSERT IGNORE INTO publications 
                (company_name, published_date, practice_area, heading, link)
                VALUES (%s, %s, %s, %s, %s)
            '''
            
            values = (
                publication['company_name'],
                publication['published_date'],
                publication['practice_area'],
                publication['heading'],
                publication['link']
            )
            
            cursor.execute(sql, values)
            connection.commit()
            cursor.close()
            connection.close()
        except Error as e:
            print(f"Database error: {str(e)}")
    
    def view_data(self, limit=10):
        """View saved publications from database"""
        connection = self.get_connection()
        if not connection:
            return
        
        try:
            cursor = connection.cursor()
            
            sql = '''
                SELECT company_name, heading, practice_area, published_date, link
                FROM publications
                ORDER BY published_date DESC, scraped_at DESC
                LIMIT %s
            '''
            
            cursor.execute(sql, (limit,))
            results = cursor.fetchall()
            
            cursor.close()
            connection.close()
            
            print(f"\n{'='*60}")
            print(f"Latest {limit} Publications in Database")
            print(f"{'='*60}\n")
            
            for idx, row in enumerate(results, 1):
                print(f"{idx}. Company: {row[0]}")
                print(f"   Heading: {row[1]}")
                print(f"   Practice Area: {row[2]}")
                print(f"   Published: {row[3]}")
                print(f"   Link: {row[4]}")
                print("-" * 60)
        except Error as e:
            print(f"Error viewing data: {e}")
    
    def get_statistics(self):
        """Get statistics about scraped data"""
        connection = self.get_connection()
        if not connection:
            return
        
        try:
            cursor = connection.cursor()
            
            # Total count
            cursor.execute('SELECT COUNT(*) FROM publications')
            total = cursor.fetchone()[0]
            
            # By company
            cursor.execute('''
                SELECT company_name, COUNT(*) 
                FROM publications 
                GROUP BY company_name
            ''')
            by_company = cursor.fetchall()
            
            # By practice area
            cursor.execute('''
                SELECT practice_area, COUNT(*) 
                FROM publications 
                GROUP BY practice_area
                ORDER BY COUNT(*) DESC
                LIMIT 5
            ''')
            by_practice = cursor.fetchall()
            
            cursor.close()
            connection.close()
            
            print(f"\n{'='*60}")
            print(f"Database Statistics")
            print(f"{'='*60}\n")
            print(f"Total Publications: {total}\n")
            
            print("By Company:")
            for company, count in by_company:
                print(f"  {company}: {count}")
            
            print(f"\nTop 5 Practice Areas:")
            for practice, count in by_practice:
                print(f"  {practice}: {count}")
            print(f"{'='*60}\n")
        except Error as e:
            print(f"Error getting statistics: {e}")


import os
from dotenv import load_dotenv

load_dotenv()

# Usage Example
if __name__ == "__main__":
    # Initialize scraper with MySQL credentials
    scraper = PublicationScraper(
        host = os.getenv('DB_HOST'),
        password = os.getenv('DB_PASSWORD'),  # Replace with your MySQL password
        database = os.getenv('DB_NAME'),
        user = os.getenv('DB_USER'),      # Replace with your MySQL username
        cutoff_date='2024-01-01'
    )
    
    # Scrape IndusLaw publications
    publications = scraper.scrape_induslaw()
    
    # View statistics
    scraper.get_statistics()
    
    # View the latest data
    scraper.view_data(limit=5)