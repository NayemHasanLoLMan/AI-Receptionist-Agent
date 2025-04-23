import google.generativeai as genai
from datetime import datetime
import json, re
from pathlib import Path
from typing import Optional, Dict, List
import dateparser
from datetime import datetime, timedelta
from rapidfuzz import process

class ConversationMemory:
    def __init__(self):
        self.history = []
        self.is_first_message = True
        self.history_file = Path('chat_history.json')
        self._load_history()

    def _load_history(self):
        """Load existing chat history from JSON file"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
            except json.JSONDecodeError:
                self.history = []

    def add_exchange(self, user_input: str, bot_response: str):
        """Add a new exchange to history and save to JSON"""
        exchange = {
            "user": user_input,
            "bot": bot_response,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.history.append(exchange)
        self._save_history()

    def _save_history(self):
        """Save chat history to JSON file"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Error saving chat history: {str(e)}")
        
    def get_recent_context(self, num_messages: int = 10) -> str:
        """Get the most recent conversation exchanges"""
        recent = self.history[-num_messages:] if len(self.history) > 0 else []
        context = ""
        for exchange in recent:
            context += f"User: {exchange['user']}\nBot: {exchange['bot']}\n\n"
        return context

class BookingSystem:
    def __init__(self, api_key: str, available_services_file: str):
        self.booking_data = {
            'package': None,
            'name': None,
            'dob': None,
            'date': None,
            'time': None
        }
        self.questions = [
            ("package", "Which service would you like to book?"),
            ("name", "Could you please provide your full name?"),
            ("dob", "What is your date of birth? (YYYY-MM-DD)"),
            ("date", "What date would you prefer for your appointment? (YYYY-MM-DD)"),
            ("time", "What time would you prefer? (HH:MM)")
        ]
        self.current_question_index = 0
        self.booking_file = Path('booking_data.json')


        # ✅ Load services from available_services.txt
        self.available_services_file = Path(available_services_file)
        self.available_services = self._load_services()

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")

    def _load_services(self):
        """Load service names from available_services.txt."""
        try:
            if not self.available_services_file.exists():
                raise FileNotFoundError(f"Services file not found: {self.available_services_file}")
            
            with open(self.available_services_file, 'r', encoding='utf-8') as f:
                services = [line.strip() for line in f.readlines() if line.strip()]
            
            if not services:
                raise ValueError("No services found in services file")
                
            print(f"✅ Loaded {len(services)} services")
            return services
            
        except Exception as e:
            print(f"⚠️ Error loading services: {str(e)}")
            return []


    def _match_service_name(self, user_input: str) -> str:
        """Find the best matching service name using fuzzy matching.
        
        Args:
            user_input (str): The service name provided by the user
            
        Returns:
            str: The best matching service name or original input if no good match
        """
        if not self.available_services:
            return user_input
            
        try:
            # Use rapidfuzz's process.extractOne to find best match
            match = process.extractOne(user_input, self.available_services)
            if match and len(match) >= 2:
                best_match, score = match[0], match[1]
                # Only return match if score is above threshold
                if score >= 80:
                    return best_match
            return user_input
            
        except Exception as e:
            print(f"⚠️ Error matching service: {str(e)}")
            return user_input


    def ask_next_question(self):
        """Ask the next unanswered question."""
        while self.current_question_index < len(self.questions):
            field, question = self.questions[self.current_question_index]
            if self.booking_data[field] is None:
                return question  # Ask this question
            self.current_question_index += 1
        return None  # All questions are answered


    def process_response(self, response):
        """Process user responses, parse dates and time, and store in JSON"""
        key, _ = self.questions[self.current_question_index]

        if key == "package":
            # Check if the service exists in available services
            matched_service = self._match_service_name(response)
            if matched_service == response and response not in self.available_services:
                return "Sorry, that service is not available. Please choose from our available services."
            self.booking_data[key] = matched_service

        elif key == "name":
            self.booking_data[key] = response.strip().title()  # Format name properly

        elif key == "dob":
            parsed_date = dateparser.parse(response)
            self.booking_data[key] = parsed_date.strftime("%Y-%m-%d") if parsed_date else response

        elif key == "date":
            self.booking_data[key] = self._convert_relative_date(response)

        elif key == "time":
            parsed_time = dateparser.parse(response)
            self.booking_data[key] = parsed_time.strftime("%H:%M") if parsed_time else response

        self._save_booking_data()
        self.current_question_index += 1

        next_question = self.ask_next_question()
        return next_question if next_question else self.confirm_booking()
    

    def _convert_relative_date(self, response):
        """Use AI to convert natural language dates into actual dates."""
        today = datetime.today()
        lower_response = response.lower().strip()

        # Handle basic relative dates first
        if lower_response in ["today"]:
            return today.strftime("%Y-%m-%d")
        elif lower_response in ["tomorrow"]:
            return (today + timedelta(days=1)).strftime("%Y-%m-%d")
        elif lower_response in ["day after tomorrow", "the day after tomorrow"]:
            return (today + timedelta(days=2)).strftime("%Y-%m-%d")

        # Use Gemini AI to process complex date expressions
        prompt = f"""
        Convert the following natural language date into a YYYY-MM-DD format based on today's date ({today.strftime('%Y-%m-%d')}):
        "{response}"
        Only return the date in YYYY-MM-DD format.
        """

        try:
            ai_response = self.model.generate_content(prompt)
            formatted_date = ai_response.text.strip()

            # Validate AI response
            parsed_date = dateparser.parse(formatted_date)
            if parsed_date:
                return parsed_date.strftime("%Y-%m-%d")

        except Exception as e:
            print(f"⚠️ Error using AI for date conversion: {str(e)}")

        # Fallback to dateparser if AI fails
        parsed_date = dateparser.parse(response)
        return parsed_date.strftime("%Y-%m-%d") if parsed_date else response

    def _save_booking_data(self):
        """Save structured booking data to JSON file"""
        try:
            with open(self.booking_file, 'w', encoding='utf-8') as f:
                json.dump(self.booking_data, f, indent=2, ensure_ascii=False)
            print("\n Booking details successfully saved.")
        except Exception as e:
            print(f"\n   Error saving booking data: {str(e)}")

    def confirm_booking(self):
        """Confirm booking and display details"""
        return f"""
        Your appointment has been successfully booked!

        Booking Details:
        - Service: {self.booking_data['package']}
        - Name: {self.booking_data['name']}
        - DOB: {self.booking_data['dob']}
        - Date: {self.booking_data['date']}
        - Time: {self.booking_data['time']}

        Thank you for booking with us!
        """



class AppointmentChatbot:
    def __init__(self, api_key: str, knowledge_base_file: str, available_services_file: str, user_instruction_file: str):
        self.api_key = api_key
        self.user_instruction_file = Path(user_instruction_file)
        self.knowledge_base_file = Path(knowledge_base_file)
        self.knowledge_base_content = self._load_knowledge_base()
        self.conversation_memory = ConversationMemory()
        self.booking_system = BookingSystem(api_key, available_services_file)  # Pass API key to booking system
        self.is_booking_in_progress = False
        
        # Initialize Gemini
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        

    def _load_knowledge_base(self) -> str:
        """Load and read the knowledge base file"""
        try:
            if not self.knowledge_base_file.exists():
                raise FileNotFoundError(f"Knowledge base file not found: {self.knowledge_base_file}")
            
            with open(self.knowledge_base_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            if not content:
                raise ValueError("Knowledge base file is empty")
                
            return content
        except Exception as e:
            error_msg = f"Error loading knowledge base: {str(e)}"
            print(f"⚠️ {error_msg}")
            return f"ERROR: {error_msg}"

    def _get_initial_prompt(self) -> str:
        return f"""
        You are an AI receptionist for an appointment booking system.

        Knowledge Base:
        {self.knowledge_base_content}

        Instruction:
        {self.user_instruction_file}

        Instructions for first message:
        1. Start with "Welcome to \n[Business Name]!\n"
        2. Briefly list 2-3 main services with their prices (if avaliable)
        3. End with: "Would you like to learn more about our services or book an appointment?"
        4. Do not provide information out of the knowlage base, Only provide information from the knowlage base.
        
        
    Note: Follow the Instruction carefully for a better understanding of AI behavior and response tone. Ensure that the AI response aligns with the given guidelines and incorporates any additional changes as required.
        
        Keep the message under 60 words.

        IF the a answare of the question is not avalable in the the database always return with this exact response "I'm sorry, I am an AI receptionist and do not have access to the information." (Do not mention the name of the business)

        
        """

    def _get_conversation_prompt(self, user_input: str, recent_context: str) -> str:
        return f"""
        You are an AI receptionist (Always respond in English). Review the conversation and guide the user.

        Knowledge Base:
        {self.knowledge_base_content}

        Instruction:
        {self.user_instruction_file}

        Conversation History:
        {recent_context}

        Instructions:
        1. If the user wants to book an appointment, respond with "[START_BOOKING]"
        2. Otherwise, provide information from the knowledge base
        3. Keep responses concise and professional
        4. Do not make up information not in the knowledge base
        5. Always respond in English unless the user explicitly switches to another language.


        Note: Follow the Instruction carefully for a better understanding of AI behavior and response tone. Ensure that the AI response aligns with the given guidelines and incorporates any additional changes as required.

        User message: {user_input}
        """
    




    def run(self):
        """Main chat loop to handle user interactions"""
        print("💬 Type '/exit' to end the conversation\n")
        
        # Send initial welcome message
        if self.conversation_memory.is_first_message:
            response = self.model.generate_content(self._get_initial_prompt())
            print("Bot:", response.text)
            self.conversation_memory.add_exchange("", response.text)
            self.conversation_memory.is_first_message = False
        
        while True:
            user_input = input("\nYou: ").strip()
            
            if user_input.lower() in ['/exit']:
                print("\nBot: Thank you for chatting! Have a great day! 👋")
                break
                
            if not user_input:
                continue
                
            try:
                if self.is_booking_in_progress:
                    # Handle booking flow
                    bot_response = self.booking_system.process_response(user_input)
                    
                    # Check if booking is complete
                    if "successfully booked" in bot_response:
                        self.is_booking_in_progress = False
                    
                    # Construct the JSON response for backend
                    response_data = {
                        "success": True,
                        "message": bot_response
                    }
                    
                    # Print response in JSON format
                    print("\nBot Response:", json.dumps(response_data, indent=2, ensure_ascii=False))

                    # Save the exchange
                    self.conversation_memory.add_exchange(user_input, bot_response)
                    
                    # If booking is complete, continue to the next iteration
                    if not self.is_booking_in_progress:
                        continue
                else:
                    # Regular conversation flow
                    recent_context = self.conversation_memory.get_recent_context()
                    prompt = self._get_conversation_prompt(user_input, recent_context)
                    response = self.model.generate_content(prompt)
                    bot_response = response.text.strip()
                    
                    # Check if we should start booking process
                    if "[START_BOOKING]" in bot_response:
                        self.is_booking_in_progress = True
                        bot_response = self.booking_system.ask_next_question()
                    
                    # Check if response contains restricted message
                    restricted_message = "I'm sorry, I am an AI receptionist"
                    response_success = not bool(re.search(re.escape(restricted_message), bot_response))

                    # Construct the JSON response for backend
                    response_data = {
                        "success": response_success,
                        "message": bot_response
                    }
                    
                    # Print response in JSON format
                    print("\nBot Response:", json.dumps(response_data, indent=2, ensure_ascii=False))

                    # Save the exchange
                    self.conversation_memory.add_exchange(user_input, bot_response)
                    
            except Exception as e:
                print(f"\n⚠️ Error generating response: {str(e)}")
                print("Bot: I apologize, but I'm having trouble processing that. Could you try rephrasing?")




def main():
    """Main function to initialize and run the chatbot"""
    try:
        # Configuration
        API_KEY = "API KEY"
        AVAILABLE_SERVICES_FILE = "available_services.txt"
        KNOWLEDGE_BASE_PATH = Path(__file__).parent / "knowledge_base.txt"
        USER_INSTRUCTION_FILE = "user_instruction.txt"

        # Initialize chatbot
        print("🤖 Initializing chatbot...")
        chatbot = AppointmentChatbot(API_KEY, str(KNOWLEDGE_BASE_PATH), available_services_file=AVAILABLE_SERVICES_FILE, user_instruction_file= USER_INSTRUCTION_FILE)
        
        # Verify knowledge base loaded correctly
        if chatbot.knowledge_base_content.startswith("ERROR:"):
            raise ValueError("Failed to load knowledge base properly")
            
        print("✅ Knowledge base loaded successfully")
        print("\n=== Starting Chatbot ===\n")
        
        # Run the chatbot
        chatbot.run()
        
    except ValueError as ve:
        print(f"⚠️ Configuration error: {str(ve)}")
    except Exception as e:
        print(f"⚠️ Unexpected error: {str(e)}")
        import traceback
        print(traceback.format_exc())
    finally:
        print("\n=== Chatbot Terminated ===")

if __name__ == "__main__":
    main()



def chat(api_key: str, 
         knowledge_base_content: str, 
         available_services_file: str,
         user_instruction_file: str,
         chat_history: list,
         user_input: str) -> dict:
    """
    Process a single chat interaction for the appointment chatbot.
    
    Args:
        api_key (str): Google AI API key
        knowledge_base_content (str): Content of knowledge base as string
        available_services_file (str): Path to available services file
        user_instruction_file (str): Path to user instruction file
        chat_history (list): List of previous chat exchanges
        user_input (str): Current user message
        
    Returns:
        dict: Response containing success status and message
        {
            "success": bool,
            "message": str,
            "is_booking": bool
        }
    """
    try:
        # Initialize chatbot with provided configuration
        chatbot = AppointmentChatbot(
            api_key=api_key,
            knowledge_base_file=knowledge_base_content,
            available_services_file=available_services_file,
            user_instruction_file=user_instruction_file
        )
        
        # Load previous chat history
        chatbot.conversation_memory.history = chat_history
        
        # Process user input
        if chatbot.is_booking_in_progress:
            # Handle booking flow
            bot_response = chatbot.booking_system.process_response(user_input)
            
            # Check if booking is complete
            if "successfully booked" in bot_response:
                chatbot.is_booking_in_progress = False
                
            response = {
                "success": True,
                "message": bot_response,
                "is_booking": chatbot.is_booking_in_progress
            }
            
        else:
            # Regular conversation flow
            recent_context = chatbot.conversation_memory.get_recent_context()
            prompt = chatbot._get_conversation_prompt(user_input, recent_context)
            ai_response = chatbot.model.generate_content(prompt)
            bot_response = ai_response.text.strip()
            
            # Check if we should start booking process
            if "[START_BOOKING]" in bot_response:
                chatbot.is_booking_in_progress = True
                bot_response = chatbot.booking_system.ask_next_question()
            
            # Check if response contains restricted message
            restricted_message = "I'm sorry, I am an AI receptionist"
            response_success = not bool(re.search(re.escape(restricted_message), bot_response))
            
            response = {
                "success": response_success,
                "message": bot_response,
                "is_booking": chatbot.is_booking_in_progress
            }

        # Save the exchange
        chatbot.conversation_memory.add_exchange(user_input, bot_response)
        
        return response

    except Exception as e:
        return {
            "success": False,
            "message": f"Error processing request: {str(e)}",
            "is_booking": False
        }




