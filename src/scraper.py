import time
import logging
import re
import os
from datetime import datetime
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import json
import requests

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import *
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

@dataclass
class ScraperConfig:
    """Configuration settings for the scraper."""
    base_url: str
    page_load_delay: int = 7
    product_log_delay: float = 0.02
    max_retries: int = 3
    timeout: int = 20
    chrome_options: List[str] = None

    def __post_init__(self):
        if self.chrome_options is None:
            self.chrome_options = [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--start-maximized"
            ]

class WebDriverManager:
    """Manages WebDriver initialization and cleanup."""
    
    @staticmethod
    def get_driver(config: ScraperConfig) -> Optional[webdriver.Chrome]:
        options = Options()
        for option in config.chrome_options:
            options.add_argument(option)
            
        try:
            service = Service(ChromeDriverManager().install())
            return webdriver.Chrome(service=service, options=options)
        except Exception as e:
            logging.error(f"Error initializing WebDriver: {e}")
            return None

class BaseScraper(ABC):
    """Abstract base class for web scrapers."""
    
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.driver = None
        
    def __enter__(self):
        self.driver = WebDriverManager.get_driver(self.config)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.driver:
            self.driver.quit()

    @abstractmethod
    def fetch_categories(self) -> List[Dict[str, str]]:
        """Fetch all categories to be scraped."""
        pass

    @abstractmethod
    def extract_product_data(self, entry: BeautifulSoup, **kwargs) -> Optional[Dict]:
        """Extract product data from a BeautifulSoup element."""
        pass

    def wait_for_element(self, by: By, selector: str, timeout: Optional[int] = None) -> bool:
        """Wait for an element to be present and visible."""
        try:
            WebDriverWait(self.driver, timeout or self.config.timeout).until(
                EC.presence_of_element_located((by, selector))
            )
            return True
        except TimeoutException:
            return False

    def safe_get(self, url: str) -> bool:
        """Safely navigate to a URL with retries."""
        for attempt in range(self.config.max_retries):
            try:
                self.driver.get(url)
                time.sleep(self.config.page_load_delay)
                return True
            except Exception as e:
                logging.error(f"Error accessing {url} (attempt {attempt + 1}): {e}")
                if attempt == self.config.max_retries - 1:
                    return False
                time.sleep(self.config.page_load_delay)

    def get_page_source(self) -> Optional[BeautifulSoup]:
        """Get the current page source as BeautifulSoup object."""
        try:
            return BeautifulSoup(self.driver.page_source, "html.parser")
        except Exception as e:
            logging.error(f"Error getting page source: {e}")
            return None

    def scrape_products(self, url: str) -> List[Dict]:
        """Scrape all products from a given URL."""
        if not self.safe_get(url):
            return []

        products = []
        current_page = 1
        
        while True:
            soup = self.get_page_source()
            if not soup:
                break

            product_entries = self.find_product_entries(soup)
            if not product_entries:
                break

            for entry in product_entries:
                product = self.extract_product_data(entry)
                if product:
                    products.append(product)
                    time.sleep(self.config.product_log_delay)

            if not self.goto_next_page():
                break
                
            current_page += 1

        return products

    @abstractmethod
    def find_product_entries(self, soup: BeautifulSoup) -> List[Any]:
        """Find all product entries on the current page."""
        pass

    @abstractmethod
    def goto_next_page(self) -> bool:
        """Navigate to the next page if available."""
        pass

class WoolworthsScraper(BaseScraper):
    """Woolworths specific implementation of the BaseScraper."""

    def fetch_categories(self) -> List[Dict[str, str]]:
        if not self.safe_get(self.config.base_url):
            return []

        if not self.wait_for_element(By.CSS_SELECTOR, "cdx-search-filters"):
            return []

        soup = self.get_page_source()
        if not soup:
            return []

        categories_list = soup.select("ul.ng-tns-c1842912979-7 li a.dasFacetHref")
        
        categories = []
        for category_element in categories_list:
            category_name = category_element.text.strip().split(" (", 1)[0]
            category_url = category_element.get("href")
            if category_url:
                categories.append({
                    "name": category_name,
                    "url": f"https://www.woolworths.co.nz{category_url}"
                })

        return categories

    def fetch_product_page(self, url: str) -> BeautifulSoup:
        self.driver.get(url)
        time.sleep(5)  # Wait for the page to load completely
        return BeautifulSoup(self.driver.page_source, "html.parser")

    def extract_breadcrumbs(self, soup: BeautifulSoup) -> Dict[str, str]:
        breadcrumbs = {}
        try:
            # Print the HTML content for debugging
            logging.debug(f"HTML content: {soup.prettify()}")
            
            # Find the breadcrumb container
            breadcrumb_container = soup.find('cdx-breadcrumb')
            if not breadcrumb_container:
                logging.warning("Breadcrumb container not found")
                logging.debug(f"Full HTML: {soup.prettify()}")  # Debugging line
                return breadcrumbs

            # Find all li elements within the breadcrumb
            breadcrumb_items = breadcrumb_container.find_all('li')
            
            for i, item in enumerate(breadcrumb_items, 1):
                # Handle home link
                home_link = item.find('a', attrs={'aria-label': 'Home'})
                if home_link:
                    breadcrumbs[f"breadcrumb_{i}"] = "Home"
                    continue
                
                # Handle regular links
                link = item.find('a', class_='ng-star-inserted')
                if link and link.text.strip():
                    breadcrumbs[f"breadcrumb_{i}"] = link.text.strip()
                    continue
                
                # Handle span (usually the last item)
                span = item.find('span', class_='ng-star-inserted')
                if span and span.text.strip():
                    breadcrumbs[f"breadcrumb_{i}"] = span.text.strip()

            logging.info(f"Extracted breadcrumbs: {breadcrumbs}")
            return breadcrumbs
            
        except Exception as e:
            logging.error(f"Error extracting breadcrumbs: {str(e)}")
            return breadcrumbs

    def extract_product_data(self, entry: BeautifulSoup, **kwargs) -> Optional[Dict]:
        try:
            h3_element = entry.select_one("h3[id*='-title']")
            if not h3_element:
                return None

            product = {
                "id": re.sub(r"\D", "", h3_element.get("id", "")),
                "sourceSite": "woolworths.co.nz",
                "lastChecked": datetime.now().isoformat(),
                "lastUpdated": datetime.now().isoformat()
            }

            # Extract name and size
            raw_name_size = h3_element.text.strip().lower()
            raw_name_size = re.sub(r"\s+", " ", raw_name_size)
            size_match = re.search(r"(tray\s\d+)|(\d+(\.\d+)?(\-\d+\.\d+)?\s?(g|kg|l|ml|pack))\b", raw_name_size)
            if size_match:
                product["name"] = raw_name_size[:size_match.start()].strip().title()
                product["size"] = size_match.group(0).replace("l", "L").replace("tray", "Tray")
            else:
                product["name"] = raw_name_size.title()
                product["size"] = ""

            # Extract image URL
            img_element = entry.select_one("img[alt]")
            if img_element:
                product["imageUrl"] = img_element.get("src")

            # Extract price
            self._extract_price(entry, product)  # Assuming these methods are defined
            self._extract_unit_price(entry, product)

            logging.info(f"Fetching product: {product['name']}")

            # Navigate to individual product page and extract breadcrumbs
            product_url = entry.select_one("a[href*='productdetails']")
            if product_url and 'href' in product_url.attrs:
                full_product_url = f"https://www.woolworths.co.nz{product_url['href']}"
                try:
                    logging.info(f"Fetching product page: {full_product_url}")
                    product_page = self.fetch_product_page(full_product_url)
                    breadcrumb_info = self.extract_breadcrumbs(product_page)
                    if breadcrumb_info:
                        product.update(breadcrumb_info)
                        logging.info(f"Successfully added breadcrumbs for {product['name']}")
                    else:
                        logging.warning(f"No breadcrumbs found for product: {product['name']}")
                except Exception as e:
                    logging.error(f"Error fetching product page: {e}")

            return product
        except Exception as e:
            logging.error(f"Error extracting product data: {e}")
            return None

    def _extract_price(self, entry: BeautifulSoup, product: Dict) -> None:
        price_element = entry.select_one("product-price div h3")
        if price_element:
            dollar_element = price_element.select_one("em")
            cent_element = price_element.select_one("span")
            if dollar_element and cent_element:
                cent_text = re.sub(r"\D", "", cent_element.text.strip())
                product["currentPrice"] = float(f"{dollar_element.text}{'.' if cent_text else ''}{cent_text or '00'}")

    def _extract_unit_price(self, entry: BeautifulSoup, product: Dict) -> None:
        unit_price_element = entry.select_one("span.cupPrice")
        if unit_price_element:
            raw_unit_price = unit_price_element.text.strip()
            unit_price_match = re.match(r"\$([\d.]+) \/ (\d+(g|kg|ml|l))", raw_unit_price)
            if unit_price_match:
                self._process_unit_price(unit_price_match, product)

    def _process_unit_price(self, match: re.Match, product: Dict) -> None:
        unit_price = float(match.group(1))
        unit = match.group(2)[-2:]
        
        if unit == "g":
            unit = "kg"
            unit_price *= 1000
        elif unit == "ml":
            unit = "L"
            unit_price *= 1000

        product["unitPrice"] = unit_price
        product["unitName"] = unit


    def find_product_entries(self, soup: BeautifulSoup) -> List[Any]:
        return soup.select("cdx-card product-stamp-grid div.product-entry")

    def goto_next_page(self) -> bool:
        try:
            next_button = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "li.next a"))
            )
            
            if not next_button.is_displayed() or 'disabled' in next_button.get_attribute('class'):
                return False

            self.driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", next_button)
            time.sleep(self.config.page_load_delay)
            
            return True
        except Exception as e:
            logging.error(f"Error navigating to next page: {e}")
            return False

def main():
    config = ScraperConfig(
        base_url="https://www.woolworths.co.nz/shop/browse",
        page_load_delay=int(os.environ.get("PAGE_LOAD_DELAY", 7)),
        product_log_delay=float(os.environ.get("PRODUCT_LOG_DELAY", 0.02))
    )

    with WoolworthsScraper(config) as scraper:
        categories = scraper.fetch_categories()
        if not categories:
            logging.error("No categories found to process")
            return

        all_products = []
        for category in categories:
            logging.info(f"Fetching products from category: {category['name']}")
            products = scraper.scrape_products(category["url"])
            if products:
                logging.info(f"Found {len(products)} products in category {category['name']}")
                all_products.extend(products)
            time.sleep(config.page_load_delay)

        if all_products:
            filename = f"woolworths_products_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
            with open(filename, 'w') as outfile:
                json.dump(all_products, outfile, indent=4)
            logging.info(f"Successfully wrote {len(all_products)} products to {filename}")

if __name__ == "__main__":
    main()