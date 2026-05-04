import requests
import json
from io import BytesIO

def test_multipart_upload():
    print("Testing multipart upload fix...")
    
    # Get fresh token
    login_response = requests.post('http://localhost:8000/auth/login/vendor', json={
        "email": "reetu+3@gmail.com",
        "password": "12345678"
    })
    
    if login_response.status_code != 200:
        print("Failed to login")
        return
    
    token = login_response.json()['access_token']
    
    # Test 1: Product without images (text only)
    print("\n1. Testing product without images...")
    product_data = {
        "category_id": 6,
        "name": "Test Product No Images",
        "description": "Testing text-only product creation",
        "brand": "Test Brand",
        "price": 100,
        "stock": 10,
        "tags": ["test"],
        "variants": []
    }
    
    try:
        files = {
            'data': (None, json.dumps(product_data), 'application/json'),
        }
        
        response = requests.post(
            'http://localhost:8000/vendor/products',
            headers={'Authorization': f'Bearer {token}'},
            files=files
        )
        
        print(f"   Status: {response.status_code}")
        if response.status_code == 201:
            print("   Success: Product created without images")
        else:
            print(f"   Error: {response.json()}")
    except Exception as e:
        print(f"   Exception: {e}")
    
    # Test 2: Product with images
    print("\n2. Testing product with images...")
    
    # Create a simple test image
    test_image_content = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xaa\xff\xd9'
    
    try:
        files = {
            'data': (None, json.dumps(product_data), 'application/json'),
            'images': ('test.jpg', BytesIO(test_image_content), 'image/jpeg')
        }
        
        response = requests.post(
            'http://localhost:8000/vendor/products',
            headers={'Authorization': f'Bearer {token}'},
            files=files
        )
        
        print(f"   Status: {response.status_code}")
        if response.status_code == 201:
            print("   Success: Product created with images")
            product = response.json()
            print(f"   Image URLs: {product.get('images', [])}")
        else:
            print(f"   Error: {response.json()}")
    except Exception as e:
        print(f"   Exception: {e}")
    
    print("\nMultipart upload test complete!")

if __name__ == "__main__":
    test_multipart_upload()
