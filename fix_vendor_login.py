import requests
import asyncio
import json

async def test_vendor_login():
    print("🔧 Testing Vendor Login System...")
    
    # Test 1: Valid vendor login
    print("\n1️⃣ Testing valid vendor login...")
    try:
        response = requests.post('http://localhost:8000/auth/login/vendor', json={
            "email": "reetu+3@gmail.com",
            "password": "12345678"
        })
        
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Success: Token received ({len(data.get('access_token', ''))} chars)")
            print(f"   ✅ Role: {data.get('role')}")
            print(f"   ✅ User ID: {data.get('user_id')}")
        else:
            print(f"   ❌ Failed: {response.json()}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 2: Invalid credentials
    print("\n2️⃣ Testing invalid credentials...")
    try:
        response = requests.post('http://localhost:8000/auth/login/vendor', json={
            "email": "wrong@email.com",
            "password": "wrongpassword"
        })
        
        print(f"   Status: {response.status_code}")
        if response.status_code == 401:
            print(f"   ✅ Correctly rejected: {response.json()}")
        else:
            print(f"   ❌ Unexpected response: {response.json()}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 3: Non-vendor user trying vendor login
    print("\n3️⃣ Testing non-vendor user login...")
    try:
        response = requests.post('http://localhost:8000/auth/login/vendor', json={
            "email": "manish@example.com",  # This is a regular user
            "password": "12345678"
        })
        
        print(f"   Status: {response.status_code}")
        if response.status_code == 403:
            print(f"   ✅ Correctly rejected: {response.json()}")
        else:
            print(f"   ❌ Unexpected response: {response.json()}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 4: Suspended vendor
    print("\n4️⃣ Testing suspended vendor...")
    try:
        response = requests.post('http://localhost:8000/auth/login/vendor', json={
            "email": "suspended@example.com",
            "password": "12345678"
        })
        
        print(f"   Status: {response.status_code}")
        if response.status_code == 403:
            print(f"   ✅ Correctly rejected: {response.json()}")
        else:
            print(f"   ❌ Unexpected response: {response.json()}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 5: Check if login endpoint exists
    print("\n5️⃣ Testing endpoint availability...")
    try:
        response = requests.get('http://localhost:8000/auth/login/vendor')
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   ✅ Endpoint available: {response.json()}")
        else:
            print(f"   ❌ Endpoint issue: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("\n🎯 Vendor Login Test Complete!")
    print("If you're experiencing issues, please:")
    print("1. Check your email and password")
    print("2. Ensure your account has VENDOR role")
    print("3. Verify your account is not suspended")
    print("4. Check if backend server is running")

if __name__ == "__main__":
    asyncio.run(test_vendor_login())
