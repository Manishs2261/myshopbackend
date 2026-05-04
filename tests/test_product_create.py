import requests
import json

# Test product creation with the data you provided
product_data = {
    "name": "key board",
    "description": "my key board", 
    "price": 1000,
    "discount_percentage": 10,
    "category_id": "6",
    "subcategory_id": "",
    "brand": "apple ",
    "tags": [],
    "sku": "56899",
    "stock": 8,
    "variations": [
        {"color": "Blue", "hex": "#3b82f6", "stock": 0, "images": []},
        {"color": "Green", "hex": "#10b981", "stock": 0, "images": []},
        {"color": "Black", "hex": "#111", "stock": 0, "images": []},
        {"color": "White", "hex": "#f5f5f5", "stock": 0, "images": []}
    ],
    "status": "ACTIVE"
}

try:
    # Simulate the multipart form data that the frontend sends
    files = {
        'data': (None, json.dumps(product_data), 'application/json'),
        # Note: We're not sending actual images for this test
    }
    
    response = requests.post('http://localhost:8000/vendor/products', files=files)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    
except Exception as e:
    print(f"Error: {e}")
