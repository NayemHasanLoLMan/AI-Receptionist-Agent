import requests
from bs4 import BeautifulSoup
import pdfplumber
from tqdm import tqdm
import google.generativeai as genai
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from datetime import date, time
import json

# Configuration
API_KEY = "API KEY"  # Replace with your Gemini API key
BUSINESS_URL = "https://www.happy-bears.com/"  # Replace with your business URL




class ConversationMemory:
    def __init__(self):
        self.history = []
        self.is_first_message = True

    def add_exchange(self, user_input, bot_response):
        self.history.append({
            "user": user_input,
            "bot": bot_response,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
    def get_recent_context(self, num_messages=5):
        """Get the most recent conversation exchanges"""
        recent = self.history[-num_messages:] if len(self.history) > 0 else []
        context = ""
        for exchange in recent:
            context += f"User: {exchange['user']}\nBot: {exchange['bot']}\n\n"
        return context


def extract_text_from_url(url):
    """Extract text content from any URL (webpage or PDF) and save to knowledge base file"""
    try:
        if url.lower().endswith('.pdf'):
            # Handle PDF
            print("\n📥 Downloading PDF...")
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            # Save PDF temporarily
            with open("temp.pdf", "wb") as f:
                f.write(response.content)
            
            # Extract text from PDF
            print("📖 Reading PDF content...")
            text_content = []
            with pdfplumber.open("temp.pdf") as pdf:
                for page in pdf.pages:
                    text_content.append(page.extract_text() or '')
            
            # Clean up
            os.remove("temp.pdf")
            content = '\n'.join(text_content)
        else:
            # Handle webpage
            print("\n🌍 Scraping webpage...")
            response = requests.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text from common content tags
            content_list = []
            for tag in ['p', 'h1', 'h2', 'h3', 'h4', 'li', 'div']:
                elements = soup.find_all(tag)
                for elem in elements:
                    text = elem.get_text().strip()
                    if text and len(text) > 20:  # Only keep meaningful content
                        content_list.append(text)
            
            content = '\n'.join(content_list)

        # Save content to knowledge base file
        knowledge_base_file = "knowledge_base.txt"
        with open(knowledge_base_file, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ Knowledge base saved to {knowledge_base_file}")
        
        # Return the content
        return content
            
    except Exception as e:
        print(f"⚠️ Error extracting content: {str(e)}")
        return "Failed to extract content from URL"

def get_ai_response(user_input, knowledge_base_file, booking_data, conversation_memory):
    """Get response from Gemini AI"""
    try:
        # Initialize Gemini
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
        
        # Get recent conversation context
        recent_context = conversation_memory.get_recent_context()
        
        # Different prompt for first message
        if conversation_memory.is_first_message:
            prompt = f"""
            You are an AI receptionist for an appointment booking system.

            Knowledge Base:
            {knowledge_base_file}

            Instructions for first message:
            1. Start with "Welcome to [Business Name]!"
            2. Briefly list 2-3 main services with their prices
            3. End with: "Would you like to learn more about our services or book an appointment?"

            Keep the message under 60 words.
            """
            conversation_memory.is_first_message = False
        else:
            prompt = f"""
            You are an AI receptionist (Always response in english no matter the knowlagebase). Review the booking status and guide the conversation, Use this knowledge base to learn about the business:

            Knowledge Base:
            {knowledge_base_file}

            Conversation History:
            {recent_context}

            Current Booking Status:
            {get_booking_status(booking_data)}

            - Package: {booking_data.get('package', 'Not selected')}
            - Name: {booking_data.get('name', 'Not provided')}
            - Date of Birth: {booking_data.get('dob', 'Not provided')}
            - Appointment Date: {booking_data.get('date', 'Not selected')}
            - Appointment Time: {booking_data.get('time', 'Not selected')}

            Information Collection Rules:
            1. If package is None: Ask "Which service would you like to book? [List all possible option]"
            2. If name is None: Ask "Could you please provide your full name?"
            3. If dob is None: Ask "What is your date of birth?"
            4. If date is None: Ask "What date would you prefer for your appointment?"
            5. If time is None: Ask "What time would you prefer?"

            Only ask for ONE missing piece of information at a time.
            Validate each response matches the required format.
            Confirm each piece of information as a summary at the end.
            End conversation when the booking is complate.

            User message: {user_input}
            
            Return a JSON object with only the newly extracted or updated information.
            """

        response = model.generate_content(
            contents=[{"role": "user", "parts": [prompt]}],
            generation_config=genai.GenerationConfig(
                max_output_tokens=500,
                temperature=0.7
            )
        )
        
        return response.text.strip()
    except Exception as e:
        return f"⚠️ Error: {str(e)}"
    
def get_booking_status(booking_data):
    """Convert booking data to JSON formatted string"""
    status = {
        'package': booking_data.get('package', 'Not selected'),
        'name': booking_data.get('name', 'Not provided'),
        'dob': booking_data.get('dob', 'Not provided'),
        'date': booking_data.get('date', 'Not selected'),
        'time': booking_data.get('time', 'Not selected')
    }
    return json.dumps(status, indent=2)

def save_booking(booking_data: dict) -> str:
    """
    Save booking information to a JSON file.
    Returns the booking ID.
    """
    # Create a unique booking ID
    booking_id = f"BK{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    # Add booking ID and timestamp to the data
    booking_entry = {
        "booking_id": booking_id,
        "created_at": datetime.now().isoformat(),
        **booking_data
    }
    
    # Create bookings directory if it doesn't exist
    bookings_dir = Path("bookings")
    bookings_dir.mkdir(exist_ok=True)
    
    # Save to individual booking file
    booking_file = bookings_dir / f"{booking_id}.json"
    with open(booking_file, 'w') as f:
        json.dump(booking_entry, f, indent=2)
    
    return booking_id

# Update the main function
def process_booking(booking_data: dict) -> str:
    """Process and save booking data, return confirmation message"""
    booking_id = save_booking(booking_data)
    
    return f"""
✅ Booking Saved!
Booking ID: {booking_id}
Name: {booking_data.get('name')}
Service: {booking_data.get('package')}
Date: {booking_data.get('date')}
Time: {booking_data.get('time')}
"""


def main():
    print("🤖 Initializing appointment chatbot...")
    
    # Load knowledge base
    print("\n📚 Loading business information...")
    knowledge_base_file = extract_text_from_url(BUSINESS_URL)
    
    if not knowledge_base_file:
        print("⚠️ Failed to load business information. Please check the URL.")
        return
    
    print("✅ Knowledge base loaded successfully!")
    
    booking_data: dict[str, Optional[str | date | time]] = {
        'package': None,
        'name': None,
        'dob': None,
        'date': None,
        'time': None
    }

    conversation_memory = ConversationMemory()
    
    # Send initial greeting
    initial_response = get_ai_response("", knowledge_base_file, booking_data, conversation_memory)
    print(f"\n🤖 Bot: {initial_response}")
    conversation_memory.add_exchange("", initial_response)
    
    # Chat loop
    print("\n💬 Chat started! Type '/exit' to end the conversation.")
    while True:
        user_input = input("\nYou: ").strip()
        
        if user_input.lower() == '/exit':
            print("👋 Goodbye!")
            break
        
        # Get AI response with conversation_memory
        response = get_ai_response(user_input, knowledge_base_file, booking_data, conversation_memory)
        print(f"\n🤖 Bot: {response}")
        
        # Check if all booking data is complete
        if all(value is not None for value in booking_data.values()):
            booking_id = save_booking(booking_data)
            confirmation = f"""
✅ Booking Confirmed!
Booking ID: {booking_id}
Name: {booking_data['name']}
Service: {booking_data['package']}
Date: {booking_data['date']}
Time: {booking_data['time']}
Date of Birth: {booking_data['dob']}
"""
            print(confirmation)
            
            # Reset booking data for next booking
            booking_data = {
                'package': None,
                'name': None,
                'dob': None,
                'date': None,
                'time': None
            }
        
        # Save to conversation memory
        conversation_memory.add_exchange(user_input, response)
        
        # Save chat history
        with open('chat_history.txt', 'a', encoding='utf-8') as f:
            f.write(f"\nUser: {user_input}\nBot: {response}\n")

if __name__ == "__main__":
    main()
