import requests

# Test the vendor products endpoint
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI5Iiwicm9sZSI6IlZFTkRPUiIsImV4cCI6MTc3Njc5NDQyNywidHlwZSI6ImFjY2VzcyJ9.MTqN_MM2JGkC3k4Ipr2VHxUPAdHrvyWrpNYin11mRGU"

try:
    response = requests.get(
        'http://localhost:8000/vendor/products',
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
except Exception as e:
    print(f"Error: {e}")
