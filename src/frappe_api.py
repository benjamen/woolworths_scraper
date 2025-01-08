import requests
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

# Frappe API Configuration
FRAPPE_URL = os.environ.get('FRAPPE_URL', 'https://app.besty.nz/api/resource/Product%20Item')
FRAPPE_API_KEY = os.environ.get('FRAPPE_API_KEY', '32522add18495f4')
FRAPPE_API_SECRET = os.environ.get('FRAPPE_API_SECRET', '45236bb4ab1dcc0')

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
    response.raise_for_status()
    logging.info(f"Successfully updated product in Frappe: {product['productname']}")

def create_product(product):
    headers = {
        'Authorization': f'token {FRAPPE_API_KEY}:{FRAPPE_API_SECRET}',
        'Content-Type': 'application/json',
        'Expect': ''
    }
    response = requests.post(FRAPPE_URL, json=product, headers=headers)
    
    try:
        response.raise_for_status()
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