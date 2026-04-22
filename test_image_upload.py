import requests
import os

# Get fresh token first
login_response = requests.post('http://localhost:8000/auth/login/vendor', json={
    "email": "reetu+3@gmail.com",
    "password": "12345678"
})

if login_response.status_code != 200:
    print("Failed to login")
    exit()

token = login_response.json()['access_token']
print(f"Got fresh token: {token[:20]}...")

# Test product creation with image

# Product data
product_data = {
    "category_id": 6,
    "name": "Test Product with Image",
    "description": "Testing image upload functionality",
    "brand": "Test Brand",
    "price": 100,
    "stock": 10,
    "tags": ["test"],
    "variants": []
}

# Create a simple test image file
test_image_path = "test_image.jpg"
with open(test_image_path, "wb") as f:
    # Create a simple 1x1 pixel JPEG
    f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xaa\xff\xd9')

try:
    # Prepare multipart form data
    files = {
        'data': (None, str(product_data), 'application/json'),
        'images': (test_image_path, open(test_image_path, 'rb'), 'image/jpeg')
    }
    
    response = requests.post(
        'http://localhost:8000/vendor/products',
        headers={'Authorization': f'Bearer {token}'},
        files=files
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    # Check if image URL is in response
    if response.status_code == 200:
        product = response.json()
        if 'images' in product and product['images']:
            print(f"Image URLs: {product['images']}")
            # Test if image is accessible
            for img_url in product['images']:
                img_response = requests.get(img_url)
                print(f"Image accessible: {img_response.status_code == 200}")
    
except Exception as e:
    print(f"Error: {e}")
finally:
    # Clean up test image
    if os.path.exists(test_image_path):
        os.remove(test_image_path)
