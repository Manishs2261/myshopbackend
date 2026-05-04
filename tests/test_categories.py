import asyncio
import aiohttp
import json

async def test_categories_endpoint():
    """Test the categories endpoint to see if it's working"""
    
    # Test without authentication
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get('http://localhost:8000/categories') as response:
                print(f"Status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    print(f"Categories found: {len(data)}")
                    for cat in data[:3]:  # Show first 3 categories
                        print(f"  - {cat['name']} (ID: {cat['id']})")
                else:
                    text = await response.text()
                    print(f"Error: {text}")
        except Exception as e:
            print(f"Connection error: {e}")

if __name__ == "__main__":
    asyncio.run(test_categories_endpoint())
