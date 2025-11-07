"""
Configuration Template for Law Firm Publications Scraper Suite

IMPORTANT INSTRUCTIONS:
1. Copy this file and rename it to 'config.py'
2. Fill in your actual database credentials in config.py
3. NEVER commit config.py to GitHub (it's in .gitignore)
4. Keep this template file (config_template.py) in the repository

Usage:
    from config import db_config
    scraper = MyScraper(db_config)
"""

# ============================================================================
# Database Configuration
# ============================================================================

# MySQL Database Configuration
db_config = {
    # Database host (usually 'localhost' for local development)
    'host': 'localhost',
    
    # MySQL username (create a dedicated user for this project)
    'user': 'your_username',  # Replace with your MySQL username
    
    # MySQL password (NEVER commit the actual password!)
    'password': 'your_password',  # Replace with your MySQL password
    
    # Database name (should be created beforehand)
    'database': 'publications_db',
    
    # MySQL port (default is 3306)
    'port': 3306,
    
    # Optional: Connection timeout in seconds
    'connection_timeout': 30,
    
    # Optional: Auto-reconnect if connection is lost
    'autocommit': False,
    
    # Optional: Character set
    'charset': 'utf8mb4',
    
    # Optional: Use unicode
    'use_unicode': True
}

# ============================================================================
# Alternative: Environment Variables Approach (RECOMMENDED)
# ============================================================================

# If you prefer using environment variables (more secure):
# 1. Install python-dotenv: pip install python-dotenv
# 2. Create a .env file (already in .gitignore)
# 3. Use the following code:

"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

db_config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME', 'publications_db'),
    'port': int(os.getenv('DB_PORT', 3306))
}
"""

# Then create a .env file with:
"""
DB_HOST=localhost
DB_USER=your_username
DB_PASSWORD=your_password
DB_NAME=publications_db
DB_PORT=3306
"""

# ============================================================================
# Scraper Settings (Optional)
# ============================================================================

# Rate limiting settings (requests per minute)
RATE_LIMIT = {
    'requests_per_minute': 30,
    'delay_between_pages': 2,  # seconds
    'retry_attempts': 3,
    'timeout': 30  # seconds
}

# Date range for scraping (can be overridden in individual scrapers)
DATE_RANGE = {
    'start_date': '2024-01-01',
    'end_date': '2025-12-31'
}

# Selenium settings
SELENIUM_CONFIG = {
    'headless': True,  # Run browser in headless mode
    'window_size': '1920,1080',
    'page_load_timeout': 30,  # seconds
    'implicit_wait': 10  # seconds
}

# Logging configuration
LOGGING_CONFIG = {
    'level': 'INFO',  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'log_to_file': True,
    'log_file': 'scraper.log',
    'max_log_size': 10485760,  # 10MB
    'backup_count': 5
}

# ============================================================================
# Database Setup SQL (for reference)
# ============================================================================

DATABASE_SETUP_COMMANDS = """
-- Run these commands in MySQL to set up the database and user

-- 1. Create database
CREATE DATABASE IF NOT EXISTS publications_db;

-- 2. Create a dedicated user for the scraper
CREATE USER 'scraper_user'@'localhost' IDENTIFIED BY 'strong_password_here';

-- 3. Grant necessary privileges
GRANT SELECT, INSERT, UPDATE, CREATE, ALTER, INDEX ON publications_db.* 
TO 'scraper_user'@'localhost';

-- 4. Apply changes
FLUSH PRIVILEGES;

-- 5. Verify user creation
SELECT User, Host FROM mysql.user WHERE User = 'scraper_user';

-- 6. Optional: Create read-only user for analytics
CREATE USER 'analytics_user'@'localhost' IDENTIFIED BY 'analytics_password';
GRANT SELECT ON publications_db.* TO 'analytics_user'@'localhost';
FLUSH PRIVILEGES;
"""

# ============================================================================
# Setup Instructions
# ============================================================================

SETUP_INSTRUCTIONS = """
SETUP INSTRUCTIONS:

1. Install MySQL:
   - Ubuntu/Debian: sudo apt-get install mysql-server
   - macOS: brew install mysql
   - Windows: Download from https://dev.mysql.com/downloads/mysql/

2. Start MySQL service:
   - Linux: sudo systemctl start mysql
   - macOS: brew services start mysql
   - Windows: Services → MySQL → Start

3. Create database and user (run the SQL commands in DATABASE_SETUP_COMMANDS above):
   mysql -u root -p
   (then paste the SQL commands)

4. Copy this file to config.py:
   cp config_template.py config.py

5. Edit config.py with your actual credentials:
   - Update 'user' with your MySQL username
   - Update 'password' with your MySQL password
   - Adjust other settings as needed

6. Test database connection:
   python -c "from config import db_config; import mysql.connector; 
   conn = mysql.connector.connect(**db_config); 
   print('✓ Connection successful!'); conn.close()"

7. Run scrapers:
   python azb_partners_publications_scrapper.py

SECURITY NOTES:
- NEVER commit config.py to GitHub
- Use strong passwords
- Consider using environment variables for production
- Regularly rotate database passwords
- Limit database user privileges to minimum required
- Use SSL/TLS for database connections in production
- Keep your .env file secure and never share it

TROUBLESHOOTING:
- Connection refused: Check if MySQL is running
- Access denied: Verify username and password
- Database doesn't exist: Run CREATE DATABASE command
- Port conflict: Check if another service is using port 3306
"""

# ============================================================================
# Example Usage in Scrapers
# ============================================================================

"""
# In your scraper file:

from config import db_config, RATE_LIMIT, DATE_RANGE

class MyScraper:
    def __init__(self):
        self.db_config = db_config
        self.rate_limit = RATE_LIMIT['requests_per_minute']
        self.start_date = DATE_RANGE['start_date']
    
    def connect_db(self):
        import mysql.connector
        return mysql.connector.connect(**self.db_config)
"""

# ============================================================================
# Security Checklist
# ============================================================================

SECURITY_CHECKLIST = """
Before committing to GitHub, verify:

□ config.py is NOT tracked by git (should be in .gitignore)
□ .env file is NOT tracked by git
□ No hardcoded passwords in any *.py files
□ Database credentials are in config.py or .env only
□ All sensitive files are listed in .gitignore
□ You're committing config_template.py (this file), not config.py

To check tracked files:
  git status
  git ls-files | grep config

To remove accidentally tracked sensitive file:
  git rm --cached config.py
  git commit -m "Remove sensitive config file"
"""

# Print instructions when this file is run directly
if __name__ == "__main__":
    print("=" * 80)
    print("LAW FIRM PUBLICATIONS SCRAPER - CONFIGURATION TEMPLATE")
    print("=" * 80)
    print(SETUP_INSTRUCTIONS)
    print("\n" + "=" * 80)
    print("SECURITY CHECKLIST")
    print("=" * 80)
    print(SECURITY_CHECKLIST)
    print("\n" + "=" * 80)
    print("\nNext steps:")
    print("1. cp config_template.py config.py")
    print("2. Edit config.py with your credentials")
    print("3. Never commit config.py to GitHub!")
    print("=" * 80)