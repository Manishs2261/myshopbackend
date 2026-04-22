import requests

# Test vendor login to get a valid token
login_data = {
    "email": "reetu+3@gmail.com",  # User ID 9 from the database check
    "password": "12345678"
}

try:
    response = requests.post('http://localhost:8000/auth/login/vendor', json=login_data)
    print(f"Login Status: {response.status_code}")
    print(f"Login Response: {response.json()}")
    
    if response.status_code == 200:
        token = response.json().get('access_token')
        print(f"Token: {token}")
        
        # Test vendor products endpoint
        products_response = requests.get(
            'http://localhost:8000/vendor/products',
            headers={'Authorization': f'Bearer {token}'}
        )
        print(f"\nProducts Status: {products_response.status_code}")
        print(f"Products Response: {products_response.json()}")
    
except Exception as e:
    print(f"Error: {e}")
