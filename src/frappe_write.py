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
    response = requests.get(f"{FRAPPE_URL}/{product_id}", headers=headers, verify=False)
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
    # Extract necessary fields
    product_id = product.get('id')
    product_name = product.get('name')

    # Set category to the 3rd value from product_categories (index 2)
    product_categories = product.get('product_categories', [])
    category = product_categories[2] if len(product_categories) > 2 else ''  # Get the 3rd item

    frappe_product = {
        'product_id': product_id,  # Required field
        'productname': product_name,  # Required field
        'source_site': product.get('sourceSite'),
        'size': product.get('size', ''),
        'image_url': product.get('imageUrl'),
        'unit_price': product.get('unitPrice'),
        'unit_name': product.get('unitName'),
        'original_unit_quantity': 1,  # Default value
        'current_price': product.get('currentPrice'),
        'price_history': '',  # You can populate this if needed
        'last_updated': product.get('lastUpdated'),
        'last_checked': product.get('lastChecked'),
        'category': category,  # Include the 3rd category here
        'product_categories': [{'category_name': category} for category in product_categories]  # Include all categories
    }

    # Check if product exists
    exists, existing_product = check_product_exists(product_id)
    
    if exists:
        logging.info(f"Product {product_name} already exists. Updating...")
        update_product(product_id, frappe_product)
    else:
        logging.info(f"Product {product_name} does not exist. Creating new entry...")
        create_product(frappe_product)

if __name__ == "__main__":
    # Example product to test with
    mock_product = {
        "id": "133211",
        "sourceSite": "woolworths.co.nz",
        "lastChecked": "2025-01-08T18:31:43.042304",
        "lastUpdated": "2025-01-08T18:31:43.042304",
        "name": "Fresh Fruit Bananas Yellow",
        "size": "",
        "imageUrl": "https://assets.woolworths.com.au/images/2010/133211.jpg?impolicy=wowcdxwbjbx&w=200&h=200",
        "currentPrice": 3.45,
        "unitPrice": 3.45,
        "unitName": "kg",
        "product_categories": ["Fruit & Veg", "Fruit", "Bananas", "Fresh Fruit Bananas Yellow"]
    }

    # Call the function to test writing to Frappe
    test_write_to_frappe(mock_product)