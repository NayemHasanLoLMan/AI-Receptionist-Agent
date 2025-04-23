import google.generativeai as genai
from datetime import datetime
import json, re
from pathlib import Path
from typing import Optional, Dict, List
import dateparser
from datetime import datetime, timedelta
from rapidfuzz import process

import os
from dotenv import load_dotenv

# Add this at the top of your file with other imports
load_dotenv()





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
        self.appointments_file = Path('appointments.json')

        # ✅ Load services from available_services.txt
        self.available_services_file = Path(available_services_file)
        self.available_services = self._load_services()

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")


    def start_booking(self, initial_service=None):
        """Start the booking process, optionally with a pre-selected service"""
        if initial_service is None:
            # Show available services list
            services_list = "\n".join(f"- {service}" for service in sorted(self.available_services))
            return f"Here are our available services:\n\n{services_list}\n\nWhich service would you like to book?"
            
        # Try to match the service name
        matched_service = self._match_service_name(initial_service)
        if matched_service in self.available_services:
            self.booking_data['package'] = matched_service
            self.current_question_index = 1  # Skip to name question
            return f"Great! I'll help you book a {matched_service}.\n\n" + self.questions[1][1]  # Return name question
        else:
            # If no match found, ask user to choose from available services
            services_list = "\n".join(f"- {service}" for service in sorted(self.available_services))
            return f"I couldn't find an exact match for '{initial_service}'. Here are our available services:\n\n{services_list}\n\nWhich service would you like to book?"

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

    def _load_appointments(self):
        """Load existing appointments from JSON file"""
        if not self.appointments_file.exists():
            return []
            
        try:
            with open(self.appointments_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
        except Exception as e:
            print(f"⚠️ Error loading appointments: {str(e)}")
            return []

    def _save_appointment(self):
        """Save the current booking as a confirmed appointment"""
        try:
            # Load existing appointments
            appointments = self._load_appointments()
            
            # Add current booking as a new appointment
            appointment = self.booking_data.copy()
            appointment['id'] = len(appointments) + 1
            appointment['created_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            appointments.append(appointment)
            
            # Save updated appointments list
            with open(self.appointments_file, 'w', encoding='utf-8') as f:
                json.dump(appointments, f, indent=2, ensure_ascii=False)
                
            print("✅ Appointment saved successfully")
            return True
        except Exception as e:
            print(f"⚠️ Error saving appointment: {str(e)}")
            return False

    def _check_availability(self, date: str, time: str, service: str) -> bool:
        """Check if the requested time slot is available"""
        appointments = self._load_appointments()
        
        # Filter appointments for the same date and time
        conflicting_appointments = [
            a for a in appointments 
            if a['date'] == date and a['time'] == time
        ]
        
        # Check for service-specific constraints
        # This could be enhanced with service-specific logic (e.g., some services might allow multiple bookings)
        if conflicting_appointments:
            return False
            
        # Check business hours (9 AM to 5 PM)
        try:
            hour = int(time.split(':')[0])
            if hour < 9 or hour >= 17:
                return False
        except (ValueError, IndexError):
            # If time format is invalid, assume it's not available
            return False
            
        return True

    def _suggest_alternative_times(self, date: str, service: str) -> List[str]:
        """Suggest alternative available time slots for the same date"""
        available_times = []
        
        # Check standard hourly slots between 9 AM and 5 PM
        for hour in range(9, 17):
            time_slot = f"{hour:02d}:00"
            if self._check_availability(date, time_slot, service):
                available_times.append(time_slot)
                
        return available_times

    def _match_service_name(self, user_input: str) -> str:
        """Find the best matching service name using fuzzy matching and partial matches."""
        if not self.available_services:
            return user_input
            
        try:
            user_input = user_input.lower().strip()
            
            # First try exact matches (case insensitive)
            for service in self.available_services:
                if user_input == service.lower():
                    return service
            
            # Then try partial matches
            for service in self.available_services:
                if user_input in service.lower() or service.lower() in user_input:
                    return service
            
            # Finally try fuzzy matching
            match = process.extractOne(
                user_input, 
                self.available_services,
                score_cutoff=70  # Lower threshold for better matching
            )
            
            if match and match[1] >= 70:
                return match[0]
                    
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
            if parsed_date:
                self.booking_data[key] = parsed_date.strftime("%Y-%m-%d")
            else:
                return "I couldn't understand that date format. Please provide your date of birth in YYYY-MM-DD format."

        elif key == "date":
            date_str = self._convert_relative_date(response)
            # Validate the date is not in the past
            try:
                selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                today = datetime.now().date()
                if selected_date < today:
                    return "Sorry, you cannot book appointments in the past. Please select a future date."
                # Check if the date is too far in the future (e.g., more than 3 months)
                max_date = today + timedelta(days=90)
                if selected_date > max_date:
                    return f"Sorry, you can only book appointments up to {max_date.strftime('%Y-%m-%d')}. Please select an earlier date."
                self.booking_data[key] = date_str
            except ValueError:
                return "I couldn't understand that date format. Please provide a date in YYYY-MM-DD format."

        elif key == "time":
            try:
                parsed_time = dateparser.parse(response)
                if not parsed_time:
                    return "I couldn't understand that time format. Please provide a time in HH:MM format (e.g., 14:30)."
                
                time_str = parsed_time.strftime("%H:%M")
                date_str = self.booking_data["date"]
                
                # Check availability for the requested time
                if not self._check_availability(date_str, time_str, self.booking_data["package"]):
                    alternative_times = self._suggest_alternative_times(date_str, self.booking_data["package"])
                    if alternative_times:
                        time_options = ', '.join(alternative_times)
                        return f"Sorry, that time slot is not available. Available times on {date_str} are: {time_options}. Please select one."
                    else:
                        return f"Sorry, there are no available time slots on {date_str}. Please try a different date."
                
                self.booking_data[key] = time_str
            except Exception as e:
                print(f"⚠️ Error processing time: {str(e)}")
                return "There was an error processing your time selection. Please try again with a time in HH:MM format."

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
        """Confirm booking, save it as an appointment, and display details"""
        # Save as a confirmed appointment
        appointment_saved = self._save_appointment()
        
        if not appointment_saved:
            return "There was an error confirming your booking. Please try again later."
            
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
        

    def _extract_service_from_message(self, message):
        """Extract service name from booking request"""
        # Common booking phrases
        booking_phrases = [
            "book the", "book a", "book an",
            "schedule the", "schedule a", "schedule an",
            "like to book", "want to book",
            "like to schedule", "want to schedule"
        ]
        
        message = message.lower()
        
        # First check if it's just a general booking request
        general_booking_phrases = [
            "book an appointment",
            "schedule an appointment",
            "like to book an appointment",
            "want to book an appointment",
            "make an appointment",
            "get an appointment"
        ]
        
        for phrase in general_booking_phrases:
            if phrase in message:
                return None  # Indicate this is a general booking request
        
        # Then check for specific service booking
        for phrase in booking_phrases:
            if phrase in message:
                # Get the text after the booking phrase
                service = message[message.find(phrase) + len(phrase):].strip()
                # Remove common endings like "appointment", "session", etc.
                service = re.sub(r'\s*(appointment|session|booking).*$', '', service)
                return service if service else None
        return None
    

    def process_booking_request(self, user_input):
        """Process the initial booking request and determine next steps"""
        service = self._extract_service_from_message(user_input)
        
        if service is None:
            # This is a general booking request, show services list
            return "I'll help you book an appointment. " + self.booking_system.start_booking(None)
        else:
            # User specified a service
            return self.booking_system.start_booking(service)
        
        

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

        Behavior Instructions:
        {self.user_instruction_file}

        Instructions for first message:
        1. Start with "Welcome to \n[Business Name]!\n"
        2. Briefly list 2-3 main services with their prices (if avaliable)
        3. End with: "Would you like to learn more about our services or book an appointment?"
        4. Do not provide information out of the knowlage base, Only provide information from the knowlage base.
        5. Follow the tone and style specified in the Behavior Instructions above
        
        
        Keep the message under 60 words.

        IF the a answare of the question is not avalable in the the database always return with this exact response "I'm sorry, I am an AI receptionist and do not have access to the information." (Do not mention the name of the business)

        
        """

    def _get_conversation_prompt(self, user_input: str, recent_context: str) -> str:
        return f"""
        You are an AI receptionist (Always respond in English). Review the conversation and guide the user.

        Knowledge Base:
        {self.knowledge_base_content}

        Behavior Instructions:
        {self.user_instruction_file}

        Conversation History:
        {recent_context}

        Core Instructions:
        1. If the user wants to book an appointment, respond with "[START_BOOKING]"
        2. For booking requests, use transitions like:
           - "Great choice! Let me help you book the [service]. [START_BOOKING]"
           - "I'll assist you with booking the [service] right away. [START_BOOKING]"
        3. Otherwise, provide information from the knowledge base
        4. Keep responses concise and professional
        5. Do not make up information not in the knowledge base
        6. Always respond in English unless explicitly asked otherwise
        7. Follow the tone and style specified in the Behavior Instructions above


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
                    # if "[START_BOOKING]" in bot_response:
                    #     self.is_booking_in_progress = True
                    #     bot_response = self.booking_system.ask_next_question()


                    if "[START_BOOKING]" in bot_response:
                        self.is_booking_in_progress = True
                        # Remove the [START_BOOKING] tag
                        bot_response = bot_response.replace("[START_BOOKING]", "").strip()
                        # Process the booking request
                        booking_response = self.process_booking_request(user_input)
                        bot_response = f"{bot_response}\n\n{booking_response}"
                    
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






def chat(knowledge_base_content: str, 
         available_services_file: str,
         user_instruction_file: str,  
         chat_history: list,
         user_input: str) -> dict:
    """
    Process a single chat interaction for the appointment chatbot.
    """
    try:
        # Get API key from environment variables
        api_key = os.getenv('GOOGLE_AI_API_KEY')
        if not api_key:
            return {
                "success": False,
                "message": "API key not found in environment variables",
                "is_booking": False
            }

        # Initialize chatbot with provided configuration
        chatbot = AppointmentChatbot(
            api_key=api_key,
            knowledge_base_file=knowledge_base_content,
            available_services_file=available_services_file,
            user_instruction_file=user_instruction_file
        )
        
        # Load previous chat history
        chatbot.conversation_memory.history = chat_history
        
        # Check if this is the first message
        if not chat_history:
            # Generate initial welcome message
            initial_prompt = chatbot._get_initial_prompt()
            response = chatbot.model.generate_content(initial_prompt)
            bot_response = response.text.strip()
            
            # Save the welcome message to chat history
            chatbot.conversation_memory.add_exchange("", bot_response)
            
            return {
                "success": True,
                "message": bot_response,
                "is_booking": False
            }
        
        # Rest of the existing code for processing user input
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




def start_chat():
    """Initialize and start a chat session with string content instead of file paths"""
    
    # Example knowledge base content as string
    knowledge_base_content = """
    Welcome to our service!
    We offer various treatments and services.
    Our business hours are 9 AM to 5 PM Monday through Friday.
    """

    # Example available services as string
    available_services_content = """
    Massage Therapy
    Facial Treatment
    Hair Styling
    Nail Care
    """

    # Example user instructions as string
    user_instruction_content = """
    Be polite and professional
    Use formal language
    Respond clearly and concisely
    """
    
    # First interaction - empty chat history and input
    response = chat(
        knowledge_base_content=knowledge_base_content.strip(),
        available_services_file=available_services_content.strip(),
        user_instruction_file=user_instruction_content.strip(),
        chat_history=[],  # Empty history for first message
        user_input=""     # Empty input for first message
    )
    
    print("Bot:", response["message"])

    # Continue chat loop if needed
    while True:
        user_input = input("\nYou: ").strip()
        
        if user_input.lower() == '/exit':
            print("\nBot: Goodbye! Have a great day! 👋")
            break
            
        response = chat(
            knowledge_base_content=knowledge_base_content.strip(),
            available_services_file=available_services_content.strip(),
            user_instruction_file=user_instruction_content.strip(),
            chat_history=response.get("chat_history", []),
            user_input=user_input
        )
        
        print("Bot:", response["message"])


if __name__ == "__main__":
    start_chat()