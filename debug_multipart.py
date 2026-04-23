import requests
import json

def debug_multipart_request():
    print("Debugging multipart request...")
    
    # Get fresh token
    login_response = requests.post('http://localhost:8000/auth/login/vendor', json={
        "email": "reetu+3@gmail.com",
        "password": "12345678"
    })
    
    if login_response.status_code != 200:
        print("Failed to login")
        return
    
    token = login_response.json()['access_token']
    
    # Test with minimal data
    product_data = {
        "category_id": 6,
        "name": "Debug Product",
        "description": "Testing multipart",
        "brand": "Test",
        "price": 100,
        "stock": 10,
        "tags": ["test"],
        "variants": []
    }
    
    print(f"Product data: {json.dumps(product_data)}")
    
    # Try different multipart formats
    formats = [
        # Format 1: Standard FormData
        {
            'name': 'Standard FormData',
            'files': {
                'data': (None, json.dumps(product_data), 'application/json'),
            }
        },
        # Format 2: Data as string field
        {
            'name': 'Data as string field',
            'files': {
                'data': ('data.json', json.dumps(product_data), 'application/json'),
            }
        },
        # Format 3: Data without content type
        {
            'name': 'Data without content type',
            'files': {
                'data': (None, json.dumps(product_data)),
            }
        }
    ]
    
    for format_test in formats:
        print(f"\nTesting {format_test['name']}...")
        try:
            response = requests.post(
                'http://localhost:8000/vendor/products',
                headers={'Authorization': f'Bearer {token}'},
                files=format_test['files']
            )
            
            print(f"   Status: {response.status_code}")
            if response.status_code == 201:
                print("   Success!")
            else:
                print(f"   Error: {response.text}")
        except Exception as e:
            print(f"   Exception: {e}")

if __name__ == "__main__":
    debug_multipart_request()
