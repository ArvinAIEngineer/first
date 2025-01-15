import streamlit as st
import asyncio
import asyncpg
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Database configuration
NEON_DB_USER = os.getenv("NEON_DB_USER")
NEON_DB_PASSWORD = os.getenv("NEON_DB_PASSWORD")
NEON_DB_HOST = os.getenv("NEON_DB_HOST")
NEON_DB_PORT = os.getenv("NEON_DB_PORT")
NEON_DB_NAME = os.getenv("NEON_DB_NAME")

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

def display_verification_status(status):
    """Format and display verification status with an icon"""
    if status == 'verified':
        return "✅ Verified"
    elif status == 'not verified':
        return "❌ Not Verified"
    else:
        return "⏳ Pending"

def main():
    
    # Username input
    username = st.text_input("Enter your username:")
    
    if username:
        # Create a loading spinner while fetching data
        with st.spinner("Fetching verification status..."):
            # Get user verification status
            user_data = asyncio.run(get_user_verification_status(username))
            
            if user_data:
                # Create a card-like container for the results
                with st.container():
                    st.subheader(f"Status for user: {username}")
                    
                    # Create three columns for each verification type
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
                    
                    # Add a horizontal line for visual separation
                    st.markdown("---")
                    
                    # Display verification progress
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
