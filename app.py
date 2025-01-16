import streamlit as st
import asyncio
import asyncpg
from dotenv import load_dotenv
import os
import requests
from groq import Groq
import json
from fuzzywuzzy import fuzz

# Load environment variables
load_dotenv()

# Database configuration
NEON_DB_USER = os.getenv("NEON_DB_USER")
NEON_DB_PASSWORD = os.getenv("NEON_DB_PASSWORD")
NEON_DB_HOST = os.getenv("NEON_DB_HOST")
NEON_DB_PORT = os.getenv("NEON_DB_PORT")
NEON_DB_NAME = os.getenv("NEON_DB_NAME")
BLAND_API_KEY = os.getenv("BLAND_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Initialize Groq client
groq_client = Groq(api_key=GROQ_API_KEY)

async def connect_to_neon():
    """Create a connection to Neon database"""
    return await asyncpg.connect(
        user=NEON_DB_USER,
        password=NEON_DB_PASSWORD,
        database=NEON_DB_NAME,
        host=NEON_DB_HOST,
        port=NEON_DB_PORT
    )

async def get_user_verification_status(username: str):
    """Fetch user verification status from database"""
    conn = await connect_to_neon()
    try:
        query = """
            SELECT 
                username,
                photo_verification,
                doc_verification,
                phone_verification
            FROM accounts 
            WHERE username = $1
        """
        row = await conn.fetchrow(query, username)
        return row
    finally:
        await conn.close()

async def get_user_details(username: str):
    """Fetch user details from users table"""
    conn = await connect_to_neon()
    try:
        query = "SELECT name, phone, address FROM users WHERE username = $1"
        row = await conn.fetchrow(query, username)
        return row
    finally:
        await conn.close()

async def update_phone_verification(username: str, status: str):
    """Update phone verification status in accounts table"""
    conn = await connect_to_neon()
    try:
        query = """
            UPDATE accounts 
            SET phone_verification = $1 
            WHERE username = $2
        """
        await conn.execute(query, status, username)
    finally:
        await conn.close()

def fetch_bland_calls():
    """Fetch all calls from Bland.ai API"""
    url = "https://api.bland.ai/v1/calls"
    headers = {"authorization": BLAND_API_KEY}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json().get('calls', [])
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching calls: {str(e)}")
        return []

def extract_info_from_summary(summary: str) -> dict:
    """Extract information from call summary using Groq with silent error handling"""
    prompt = f"""
    Extract the following information from the text below and return it as a JSON object:
    - username: Look for any mentioned username or user ID
    - name: The full name of the person
    - phone: The phone number
    - address: The complete address

    Text: {summary}

    Important: Return ONLY a valid JSON object in exactly this format:
    {{
        "username": "extracted username or null",
        "name": "extracted name or null",
        "phone": "extracted phone or null",
        "address": "extracted address or null"
    }}

    Do not include any additional text, explanation, or formatting - just the JSON object.
    """

    try:
        response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="mixtral-8x7b-32768",
            temperature=0.1,
            max_tokens=500,
        )
        
        # Get the response content
        content = response.choices[0].message.content.strip()
        
        # Clean up the response
        content = content.strip()
        if content.startswith('```json'):
            content = content.replace('```json', '', 1)
        if content.endswith('```'):
            content = content.replace('```', '', 1)
        content = content.strip()
        
        # Try to parse the JSON
        extracted_info = json.loads(content)
        
        # Check if we have any valid data (non-null values)
        if (extracted_info.get('username') and 
            extracted_info.get('name') and 
            extracted_info.get('phone') and 
            extracted_info.get('address')):
            return extracted_info
        else:
            # Silently skip if no valid data
            return None
            
    except Exception as e:
        # Silently handle any errors
        return None

def compare_with_fuzzy_match(str1: str, str2: str, threshold: int = 80) -> bool:
    """Compare two strings using fuzzy matching"""
    if not str1 or not str2:
        return False
    
    str1 = str1.lower().strip()
    str2 = str2.lower().strip()
    
    ratio = fuzz.ratio(str1, str2)
    token_sort_ratio = fuzz.token_sort_ratio(str1, str2)
    
    return max(ratio, token_sort_ratio) >= threshold

def display_verification_status(status):
    """Format and display verification status with an icon"""
    if status == 'verified':
        return "✅ Verified"
    elif status == 'not verified':
        return "❌ Not Verified"
    else:
        return "⏳ Pending"

def main():
    st.title("User Verification Status")
    
    # Username input
    username = st.text_input("Enter your username:")
    
    if username:
        # Add refresh button
        refresh = st.button("Refresh Status")
        
        if refresh:
            with st.spinner("Processing verification..."):
                # 1. Fetch Bland.ai calls
                calls = fetch_bland_calls()
                
                # 2. Process each call summary
                for call in calls:
                    summary = call.get('summary', '')
                    if summary:
                        # 3. Extract information using Groq
                        extracted_info = extract_info_from_summary(summary)
                        
                        # Only proceed if we have valid extracted information
                        if extracted_info:
                            # 4. If username matches, compare with user details
                            if extracted_info['username'] == username:
                                # Get user details from database
                                user_details = asyncio.run(get_user_details(username))
                                
                                if user_details:
                                    # Compare extracted info with stored details
                                    name_match = compare_with_fuzzy_match(extracted_info['name'], user_details['name'])
                                    phone_match = compare_with_fuzzy_match(extracted_info['phone'], user_details['phone'])
                                    address_match = compare_with_fuzzy_match(extracted_info['address'], user_details['address'])
                                    
                                    # If all match, update phone verification status
                                    if name_match and phone_match and address_match:
                                        asyncio.run(update_phone_verification(username, 'verified'))
                                        st.success("Phone verification completed successfully!")
                                        break
        
        # Display current verification status
        with st.spinner("Fetching verification status..."):
            user_data = asyncio.run(get_user_verification_status(username))
            
            if user_data:
                with st.container():
                    st.subheader(f"Status for user: {username}")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.markdown("### Photo Verification")
                        st.write(display_verification_status(user_data['photo_verification']))
                    
                    with col2:
                        st.markdown("### Document Verification")
                        st.write(display_verification_status(user_data['doc_verification']))
                    
                    with col3:
                        st.markdown("### Phone Verification")
                        st.write(display_verification_status(user_data['phone_verification']))
                    
                    st.markdown("---")
                    
                    verified_count = sum(1 for status in [
                        user_data['photo_verification'],
                        user_data['doc_verification'],
                        user_data['phone_verification']
                    ] if status == 'verified')
                    
                    progress = verified_count / 3
                    st.progress(progress)
                    st.write(f"Overall Progress: {int(progress * 100)}% verified")
                    
            else:
                st.error(f"No user found with username: {username}")
                st.info("Please check the username and try again.")

if __name__ == "__main__":
    main()
