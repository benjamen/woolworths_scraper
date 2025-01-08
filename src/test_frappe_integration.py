import requests
import os
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)

# Frappe API Configuration
FRAPPE_URL = os.environ.get('FRAPPE_URL', 'https://app.besty.nz/api/resource/Product%20Item')
FRAPPE_API_KEY = os.environ.get('FRAPPE_API_KEY', '32522add18495f4')
FRAPPE_API_SECRET = os.environ.get('FRAPPE_API_SECRET', '45236bb4ab1dcc0')

# Sample product data to test (updated with product categories)
# Sample product data to test (updated with product categories)
test_product = {
    "product_id": "133211",
    "productname": "Fresh Fruit Bananas Yellow",
    "source_site": "woolworths.co.nz",
    "size": "",
    "image_url": "https://assets.woolworths.com.au/images/2010/133211.jpg?impolicy=wowcdxwbjbx&w=200&h=200",
    "unit_price": 3.45,
    "unit_name": "kg",
    "original_unit_quantity": 1,
    "current_price": 3.45,
    "last_updated": "2025-01-08T15:31:50.126869",
    "last_checked": "2025-01-08T15:31:50.126869",
    "product_categories": [
        {"category_name": "Home"},
        {"category_name": "Fruit & Veg"},
        {"category_name": "Fruit"},
        {"category_name": "Bananas"},
        {"category_name": "Fresh Fruit Bananas Yellow"}
    ]
}

def check_product_exists(product_id):
    headers = {
        'Authorization': f'token {FRAPPE_API_KEY}:{FRAPPE_API_SECRET}',
        'Content-Type': 'application/json'
    }
    response = requests.get(f"{FRAPPE_URL}/{product_id}", headers=headers)
    if response.status_code == 200:
        return True, response.json()
    elif response.status_code == 404:
        return False, None
    else:
        logging.error(f"Error checking product existence: {response.status_code} - {response.content}")
        return False, None

def update_product(product_id, product):
    headers = {
        'Authorization': f'token {FRAPPE_API_KEY}:{FRAPPE_API_SECRET}',
        'Content-Type': 'application/json'
    }
    response = requests.put(f"{FRAPPE_URL}/{product_id}", json=product, headers=headers)
    response.raise_for_status()  # Raise an error for bad responses
    logging.info(f"Successfully updated product in Frappe: {product['productname']}")

def create_product(product):
    headers = {
        'Authorization': f'token {FRAPPE_API_KEY}:{FRAPPE_API_SECRET}',
        'Content-Type': 'application/json',
        'Expect': ''  # Disable the Expect header
    }
    response = requests.post(FRAPPE_URL, json=product, headers=headers)
    
    try:
        response.raise_for_status()  # Raise an error for bad responses
        logging.info(f"Successfully created product in Frappe: {product['productname']}")
    except requests.exceptions.HTTPError as e:
        logging.error(f"Failed to create product: {e}")
        logging.error(f"Response content: {response.content}")

def test_write_to_frappe(product):
    exists, existing_product = check_product_exists(product['product_id'])
    
    if exists:
        logging.info(f"Product {product['productname']} already exists. Updating...")
        update_product(product['product_id'], product)
    else:
        logging.info(f"Product {product['productname']} does not exist. Creating new entry...")
        create_product(product)

if __name__ == "__main__":
    # Print API key and secret for debugging
    print("API Key:", FRAPPE_API_KEY)
    print("API Secret:", FRAPPE_API_SECRET)
    
    test_write_to_frappe(test_product)