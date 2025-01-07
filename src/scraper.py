import time
import logging
import re
import os
from datetime import datetime
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, WebDriverException,
    SessionNotCreatedException, StaleElementReferenceException
)
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration (using environment variables for flexibility)
PAGE_LOAD_DELAY = int(os.environ.get("PAGE_LOAD_DELAY", 7))  # Default 7 seconds
PRODUCT_LOG_DELAY = float(os.environ.get("PRODUCT_LOG_DELAY", 0.02))  # Default 0.02 seconds

CHROME_OPTIONS = Options()
CHROME_OPTIONS.add_argument("--no-sandbox")
CHROME_OPTIONS.add_argument("--disable-dev-shm-usage")
CHROME_OPTIONS.add_argument("--start-maximized")

def get_driver():
    """Initializes and returns a Selenium WebDriver."""
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=CHROME_OPTIONS)
        return driver
    except (SessionNotCreatedException, WebDriverException) as e:
        logging.error(f"Error initializing WebDriver: {e}")
        return None

def extract_product_data(entry):
    """Extracts product data from a BeautifulSoup element."""
    try:
        product = {}
        h3_element = entry.select_one("h3[id*='-title']")
        if not h3_element:
            return None

        product["id"] = re.sub(r"\D", "", h3_element.get("id", ""))
        product["sourceSite"] = "woolworths.co.nz"
        product["lastChecked"] = datetime.now().isoformat()
        product["lastUpdated"] = datetime.now().isoformat()

        raw_name_size = h3_element.text.strip().lower().replace("  ", " ").replace("fresh fruit", "").replace("fresh vegetable", "").strip()
        size_match = re.search(r"(tray\s\d+)|(\d+(\.\d+)?(\-\d+\.\d+)?\s?(g|kg|l|ml|pack))\b", raw_name_size)
        if size_match:
            product["name"] = raw_name_size[:size_match.start()].strip().title()
            product["size"] = size_match.group(0).replace("l", "L").replace("tray", "Tray")
        else:
            product["name"] = raw_name_size.title()
            product["size"] = ""

        price_element = entry.select_one("product-price div h3")
        if price_element:
            dollar_element = price_element.select_one("em")
            cent_element = price_element.select_one("span")
            if dollar_element and cent_element:
                cent_text = re.sub(r"\D", "", cent_element.text.strip())
                product["currentPrice"] = float(f"{dollar_element.text}{'.' if cent_text else ''}{cent_text or '00'}")
            else:
                logging.warning(f"Price elements not found: {price_element.prettify()}")
                return None
        else:
            logging.warning("Price element not found.")
            return None

        unit_price_element = entry.select_one("span.cupPrice")
        if unit_price_element:
            raw_unit_price = unit_price_element.text.strip()
            unit_price_match = re.match(r"\$([\d.]+) \/ (\d+(g|kg|ml|l))", raw_unit_price)
            if unit_price_match:
                unit_price = float(unit_price_match.group(1))
                amount = int(unit_price_match.group(2)[:-2])
                unit = unit_price_match.group(2)[-2:]

                if unit == "g":
                    unit = "kg"
                    unit_price *= 1000
                elif unit == "ml":
                    unit = "L"
                    unit_price *= 1000

                product["unitPrice"] = unit_price
                product["unitName"] = unit
        return product
    except (AttributeError, ValueError) as e:
        logging.error(f"Error extracting data: {e}")
        return None

def fetch_categories(driver, base_url):
    """Fetches product data from a category page."""
    try:
        driver.get(base_url)
        time.sleep(PAGE_LOAD_DELAY)  # Wait for page to load initially

        try:
            # Wait for the filter section to be present
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "cdx-search-filters"))
            )
            
            # Wait for categories to be clickable
            WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "ul.ng-tns-c1842912979-7 li a.dasFacetHref"))
            )
        except TimeoutException:
            logging.error("Timeout waiting for elements to load")
            return []

        # Get updated page source after JavaScript execution
        soup = BeautifulSoup(driver.page_source, "html.parser")
        categories_list = soup.select("ul.ng-tns-c1842912979-7 li a.dasFacetHref")

        if not categories_list:
            logging.error("No categories found")
            return []

        categories = []
        for category_element in categories_list:
            category_name = category_element.text.strip().replace("&amp;", "&")
            category_url = category_element.get("href")
            if not category_url:
                continue

            category_name_split = category_name.split(" (", 1)
            if len(category_name_split) > 1:
                category_name = category_name_split[0]

            categories.append({
                "name": category_name, 
                "url": "https://www.woolworths.co.nz" + category_url
            })

        return categories
    except Exception as e:
        logging.error(f"Error extracting categories: {e}")
        return []

def get_all_products_from_category(driver, url):
    """Gets all products from a category including pagination."""
    try:
        driver.get(url)
        time.sleep(PAGE_LOAD_DELAY)  # Wait for initial page load
        
        # Get total number of pages at the start
        soup = BeautifulSoup(driver.page_source, "html.parser")
        max_pages = get_last_page_number(str(soup))
        logging.info(f"Total pages to process: {max_pages}")
        
        all_products = []
        current_page = 1
        has_next_page = True

        while has_next_page and current_page <= max_pages:
            logging.info(f"Processing page {current_page} of {max_pages}")
            
            try:
                # Wait for products to load
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "cdx-card product-stamp-grid div.product-entry"))
                )
            except TimeoutException:
                logging.error(f"Timeout waiting for products to load on page {current_page}")
                break

            # Get updated page source
            soup = BeautifulSoup(driver.page_source, "html.parser")
            product_entries = soup.select("cdx-card product-stamp-grid div.product-entry")
            
            if not product_entries:
                logging.warning(f"No products found on page {current_page}")
                break

            for entry in product_entries:
                product = extract_product_data(entry)
                if product:
                    all_products.append(product)
                    time.sleep(PRODUCT_LOG_DELAY)

            # Don't try to go to next page if we're on the last page
            if current_page >= max_pages:
                logging.info("Reached maximum page number")
                break

            try:
                # Check if next page exists
                next_page_element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "li.next a"))
                )
                
                if not next_page_element.is_displayed() or 'disabled' in next_page_element.get_attribute('class'):
                    logging.info("Reached last page")
                    break

                # Scroll to the next page button to make it clickable
                driver.execute_script("arguments[0].scrollIntoView(true);", next_page_element)
                time.sleep(1)  # Small delay after scrolling
                
                # Click using JavaScript to avoid potential intercepted click issues
                driver.execute_script("arguments[0].click();", next_page_element)
                
                # Wait for URL or page content to change
                current_url = driver.current_url
                WebDriverWait(driver, 10).until(
                    lambda driver: driver.current_url != current_url or 
                    len(driver.find_elements(By.CSS_SELECTOR, "cdx-card product-stamp-grid div.product-entry")) > 0
                )
                
                current_page += 1
                time.sleep(PAGE_LOAD_DELAY)
                
            except (TimeoutException, NoSuchElementException, StaleElementReferenceException) as e:
                logging.info(f"Pagination ended: {str(e)}")
                break
            except Exception as e:
                logging.error(f"Error during pagination: {str(e)}")
                break

        logging.info(f"Completed category with {len(all_products)} products across {current_page} of {max_pages} total pages")
        return all_products
    except Exception as e:
        logging.error(f"Error getting products from category: {e}")
        return []

def get_last_page_number(html):
    soup = BeautifulSoup(html, 'html.parser')
    page_numbers = [int(a.text.strip()) for a in soup.find_all('a') if a.text.strip().isdigit()]
    return max(page_numbers) if page_numbers else 0

def main():
    driver = get_driver()
    if not driver:
        return

    try:
        base_url = "https://www.woolworths.co.nz/shop/browse"
        categories = fetch_categories(driver, base_url)

        if not categories:
            logging.error("No categories found to process")
            return

        all_products = []
        for category in categories:
            logging.info(f"Fetching products from category: {category['name']}")
            products = get_all_products_from_category(driver, category["url"])
            if products:
                logging.info(f"Found {len(products)} products in category {category['name']}")
                all_products.extend(products)
            time.sleep(PAGE_LOAD_DELAY)

        if all_products:
            filename = f"woolworths_products_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
            with open(filename, 'w') as outfile:
                import json
                json.dump(all_products, outfile, indent=4)
            logging.info(f"Successfully wrote {len(all_products)} products to {filename}")
        else:
            logging.error("No products were collected")

    except Exception as e:
        logging.error(f"An error occurred in main: {e}")

    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    main()