import google.generativeai as genai
from datetime import datetime
import json, re
from pathlib import Path
from typing import List
import dateparser
from datetime import datetime, timedelta
from rapidfuzz import process
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variable
API_KEY = "Api Key"  # Replace with your actual API key

class ConversationMemory:
    def __init__(self):
        self.history = []
        self.is_first_message = True

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
        try:
            exchange = {
                "user": user_input,
                "bot": bot_response,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.history.append(exchange)
            return True
        except Exception as e:
            print(f"Failed to add exchange: {e}")
            return False

    def _save_history(self):
        """Save chat history to JSON file"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Error saving chat history: {str(e)}")
        
    def get_recent_context(self, num_messages: int = 10) -> str:
        """Get most recent conversation exchanges"""
        try:
            recent = self.history[-num_messages:] if self.history else []
            context = ""
            for exchange in recent:
                context += f"User: {exchange['user']}\nBot: {exchange['bot']}\n\n"
            return context
        except Exception as e:
            print(f"Error getting context: {e}")
            return ""

class BookingSystem:
    def __init__(self, available_services_content: str, appointments_content: str = "[]"):
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
        
        self.available_services = self._load_services(available_services_content)
        self.appointments_content = appointments_content
        self.appointments = self._load_appointments()

        genai.configure(api_key=API_KEY)
        self.model = genai.GenerativeModel("gemini-2.0-flash")

    def start_booking(self, initial_service=None):
        if initial_service is None:
            services_list = "\n".join(f"- {service}" for service in sorted(self.available_services))
            return f"Here are our available services:\n\n{services_list}\n\nWhich service would you like to book?"
            
        matched_service = self._match_service_name(initial_service)
        if matched_service in self.available_services:
            self.booking_data['package'] = matched_service
            self.current_question_index = 1
            return f"Great! I'll help you book a {matched_service}.\n\n" + self.questions[1][1]
        else:
            services_list = "\n".join(f"- {service}" for service in sorted(self.available_services))
            return f"I couldn't find an exact match for '{initial_service}'. Here are our available services:\n\n{services_list}\n\nWhich service would you like to book?"

    def _load_services(self, services_content: str):
        try:
            services = [line.strip() for line in services_content.split('\n') if line.strip()]
            if not services:
                raise ValueError("No services found in content")
            print(f"✅ Loaded {len(services)} services")
            return services
        except Exception as e:
            print(f"⚠️ Error loading services: {str(e)}")
            return []

    def _load_appointments(self):
        try:
            appointments = json.loads(self.appointments_content)
            if not isinstance(appointments, list):
                raise ValueError("Appointments content must be a JSON array")
            return appointments
        except json.JSONDecodeError:
            print("⚠️ Invalid JSON in appointments content, initializing empty list")
            return []
        except Exception as e:
            print(f"⚠️ Error loading appointments: {str(e)}")
            return []

    def _save_appointment(self):
        try:
            appointments = self._load_appointments()
            appointment = self.booking_data.copy()
            appointment['id'] = len(appointments) + 1
            appointment['created_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            appointments.append(appointment)
            with open(self.appointments_file, 'w', encoding='utf-8') as f:
                json.dump(appointments, f, indent=2, ensure_ascii=False)
            print("✅ Appointment saved successfully")
            return True
        except Exception as e:
            print(f"⚠️ Error saving appointment: {str(e)}")
            return False
        
    def get_appointments(self):
        return self._load_appointments()

    def _check_availability(self, date: str, time: str, service: str) -> bool:
        appointments = self._load_appointments()
        conflicting_appointments = [
            a for a in appointments 
            if a['date'] == date and a['time'] == time
        ]
        if conflicting_appointments:
            return False
        try:
            hour = int(time.split(':')[0])
            if hour < 9 or hour >= 17:
                return False
        except (ValueError, IndexError):
            return False
        return True

    def _suggest_alternative_times(self, date: str, service: str) -> List[str]:
        available_times = []
        for hour in range(9, 17):
            time_slot = f"{hour:02d}:00"
            if self._check_availability(date, time_slot, service):
                available_times.append(time_slot)
        return available_times

    def _match_service_name(self, user_input: str) -> str:
        if not self.available_services:
            return user_input
        try:
            user_input = user_input.lower().strip()
            for service in self.available_services:
                if user_input == service.lower():
                    return service
            for service in self.available_services:
                if user_input in service.lower() or service.lower() in user_input:
                    return service
            match = process.extractOne(
                user_input, 
                self.available_services,
                score_cutoff=70
            )
            if match and match[1] >= 70:
                return match[0]
            return user_input
        except Exception as e:
            print(f"⚠️ Error matching service: {str(e)}")
            return user_input

    def ask_next_question(self):
        while self.current_question_index < len(self.questions):
            field, question = self.questions[self.current_question_index]
            if self.booking_data[field] is None:
                return question
            self.current_question_index += 1
        return None

    def process_response(self, response):
        key, _ = self.questions[self.current_question_index]
        if key == "package":
            matched_service = self._match_service_name(response)
            if matched_service == response and response not in self.available_services:
                return "Sorry, that service is not available. Please choose from our available services."
            self.booking_data[key] = matched_service
        elif key == "name":
            self.booking_data[key] = response.strip().title()
        elif key == "dob":
            parsed_date = dateparser.parse(response)
            if parsed_date:
                self.booking_data[key] = parsed_date.strftime("%Y-%m-%d")
            else:
                return "I couldn't understand that date format. Please provide your date of birth in YYYY-MM-DD format."
        elif key == "date":
            date_str = self._convert_relative_date(response)
            try:
                selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                today = datetime.now().date()
                if selected_date < today:
                    return "Sorry, you cannot book appointments in the past. Please select a future date."
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
        today = datetime.today()
        lower_response = response.lower().strip()
        if lower_response in ["today"]:
            return today.strftime("%Y-%m-%d")
        elif lower_response in ["tomorrow"]:
            return (today + timedelta(days=1)).strftime("%Y-%m-%d")
        elif lower_response in ["day after tomorrow", "the day after tomorrow"]:
            return (today + timedelta(days=2)).strftime("%Y-%m-%d")
        prompt = f"""
        Convert the following natural language date into a YYYY-MM-DD format based on today's date ({today.strftime('%Y-%m-%d')}):
        "{response}"
        Only return the date in YYYY-MM-DD format.
        """
        try:
            ai_response = self.model.generate_content(prompt)
            formatted_date = ai_response.text.strip()
            parsed_date = dateparser.parse(formatted_date)
            if parsed_date:
                return parsed_date.strftime("%Y-%m-%d")
        except Exception as e:
            print(f"⚠️ Error using AI for date conversion: {str(e)}")
        parsed_date = dateparser.parse(response)
        return parsed_date.strftime("%Y-%m-%d") if parsed_date else response

    def _save_booking_data(self):
        try:
            with open(self.booking_file, 'w', encoding='utf-8') as f:
                json.dump(self.booking_data, f, indent=2, ensure_ascii=False)
            print("\n Booking details successfully saved.")
        except Exception as e:
            print(f"\n   Error saving booking data: {str(e)}")

    def confirm_booking(self):
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
    def __init__(self, knowledge_base_content: str, available_services_content: str, user_instruction_content: str, Faq_content: list,  appointments_content: str = "[]"):
        self.api_key = API_KEY
        self.user_instruction_content = user_instruction_content
        self.knowledge_base_content = knowledge_base_content
        self.Faq_content = Faq_content
        self.conversation_memory = ConversationMemory()
        self.booking_system = BookingSystem(available_services_content, appointments_content)
        self.is_booking_in_progress = False
        
        genai.configure(api_key=API_KEY)
        self.model = genai.GenerativeModel("gemini-2.0-flash")

    def _format_faq_content(self) -> str:
        if not self.Faq_content:
            return "No FAQ information available."
        formatted_faq = "FAQ Information:\n"
        for faq in self.Faq_content:
            formatted_faq += f"- Q: {faq['question']}\n  A: {faq['answer']}\n"
        return formatted_faq
        
    def _extract_service_from_message(self, message):
        booking_phrases = [
            "book the", "book a", "book an",
            "schedule the", "schedule a", "schedule an",
            "like to book", "want to book",
            "like to schedule", "want to schedule"
        ]
        message = message.lower()
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
                return None
        for phrase in booking_phrases:
            if phrase in message:
                service = message[message.find(phrase) + len(phrase):].strip()
                service = re.sub(r'\s*(appointment|session|booking).*$', '', service)
                return service if service else None
        return None
    
    def process_booking_request(self, user_input):
        service = self._extract_service_from_message(user_input)
        if service is None:
            return "I'll help you book an appointment. " + self.booking_system.start_booking(None)
        return self.booking_system.start_booking(service)
        
    def _load_knowledge_base(self) -> str:
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

        FAQ Information:
        {self.Faq_content}

        Behavior Instructions:
        {self.user_instruction_content}

        Instructions for first message:
        1. Start with "Welcome to \n[Business Name]!\n"
        2. Briefly list 2-3 main services with their prices (if avaliable)
        3. End with: "Would you like to learn more about our services or book an appointment?"
        4. Only provide information from the knowledge base and FAQ
        5. Follow the tone and style specified in the Behavior Instructions above
        6. Respond to any natural gesture, greeting, or conversational statement using polite, professional, and natural-sounding language."
        
        Keep the message under 60 words.

        Reminder:
        Answare of the question based on the knowledge Base, if it's not avalable in the the knowledge base or FAQ always return with this exact response "I'm sorry, I am an AI receptionist and do not have access to the information." (Do not mention the name of the business)
        """

    def _get_conversation_prompt(self, user_input: str, recent_context: str) -> str:
        return f"""
        You are an AI receptionist (Always respond in English).

        Knowledge Base:
        {self.knowledge_base_content}

        FAQ Guidelines:
        {self.Faq_content}
        - When answering FAQ questions, provide direct and specific answers
        - Use bullet points for multi-part answers
        - Include relevant pricing and timing information
        - Reference specific FAQ entries when available

        Behavior Instructions:
        {self.user_instruction_content}

        Conversation History:
        {recent_context}

        Core Instructions:
        1. If the user wants to book an appointment, respond with "Great! I'll help you book the [service]. [START_BOOKING]" and do not repeat similar phrases in the same response
        2. If the previous message included "[START_BOOKING]" and the user responds with "ok", "yes", "sure", or similar affirmations, respond with "[CONTINUE_BOOKING]"
        3. Otherwise, provide information from the knowledge base and faq 
        4. Keep responses concise and professional
        5. Do not make up information not in the knowledge base
        6. Always respond in English unless explicitly asked otherwise
        7. Follow the tone and style specified in the Behavior Instructions above
        8. Respond to any natural gesture, greeting, or conversational statement using polite, professional, and natural-sounding language.

        Reminder:  
        Answer based on the knowledge Base, if it's not available in the knowledge base or FAQ always return with this exact response "I'm sorry, I am an AI receptionist and do not have access to the information." (Do not mention the name of the business)

        Note: Follow the Instruction carefully for a better understanding of AI behavior and response tone. Ensure that the AI response aligns with the given guidelines and incorporates any additional changes as required.

        User message: {user_input}
        """

    def run(self):
        print("💬 Type '/exit' to end the conversation\n")
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
                    bot_response = self.booking_system.process_response(user_input)
                    if "successfully booked" in bot_response:
                        self.is_booking_in_progress = False
                    response_data = {
                        "success": True,
                        "message": bot_response
                    }
                    print("\nBot Response:", json.dumps(response_data, indent=2, ensure_ascii=False))
                    self.conversation_memory.add_exchange(user_input, bot_response)
                    if not self.is_booking_in_progress:
                        continue
                else:
                    recent_context = self.conversation_memory.get_recent_context()
                    prompt = self._get_conversation_prompt(user_input, recent_context)
                    response = self.model.generate_content(prompt)
                    bot_response = response.text.strip()
                    if "[START_BOOKING]" in bot_response:
                        self.is_booking_in_progress = True
                        bot_response = bot_response.replace("[START_BOOKING]", "").strip()
                        booking_response = self.process_booking_request(user_input)
                        bot_response = booking_response
                    elif "[CONTINUE_BOOKING]" in bot_response:
                        self.is_booking_in_progress = True
                        bot_response = bot_response.replace("[CONTINUE_BOOKING]", "").strip()
                        service = self._extract_service_from_message(recent_context) or self._extract_service_from_message(user_input) or "default_service"
                        bot_response = self.booking_system.start_booking(service)
                    restricted_message = "I'm sorry, I am an AI receptionist"
                    response_success = not bool(re.search(re.escape(restricted_message), bot_response))
                    response_data = {
                        "success": response_success,
                        "message": bot_response
                    }
                    print("\nBot Response:", json.dumps(response_data, indent=2, ensure_ascii=False))
                    self.conversation_memory.add_exchange(user_input, bot_response)
            except Exception as e:
                print(f"\n⚠️ Error generating response: {str(e)}")
                print("Bot: I apologize, but I'm having trouble processing that. Could you try rephrasing?")

def process_user_input(
    knowledge_base_content: str,
    available_services_content: str,
    user_instruction_content: str,
    Faq_content: list,
    appointments_content: str,
    user_input: str,
    chat_history: list = None
) -> dict:
    try:
        chatbot = AppointmentChatbot(
            knowledge_base_content=knowledge_base_content.strip(),
            available_services_content=available_services_content.strip(),
            Faq_content=Faq_content,
            appointments_content=appointments_content.strip(),
            user_instruction_content=user_instruction_content.strip()
        )
        
        if chat_history:
            chatbot.conversation_memory.history = chat_history
            last_bot_msg = chat_history[-1]["bot"] if chat_history else ""
            if "[START_BOOKING]" in last_bot_msg or "[CONTINUE_BOOKING]" in last_bot_msg or any(q[1] in last_bot_msg for q in chatbot.booking_system.questions):
                chatbot.is_booking_in_progress = True
                # Restore booking data only if not already set
                for exchange in reversed(chat_history):
                    if "Great! I'll help you book" in exchange["bot"] and not chatbot.booking_system.booking_data["package"]:
                        service = chatbot._extract_service_from_message(exchange["user"])
                        if service:
                            chatbot.booking_system.booking_data["package"] = chatbot.booking_system._match_service_name(service)
                            chatbot.booking_system.current_question_index = 1
                    elif "Could you please provide your full name?" in exchange["bot"] and exchange["user"] and exchange["user"].lower() not in ["ok", "yes", "sure"] and not chatbot.booking_system.booking_data["name"]:
                        chatbot.booking_system.booking_data["name"] = exchange["user"]
                        chatbot.booking_system.current_question_index = 2
                    elif "What is your date of birth?" in exchange["bot"] and exchange["user"] and not chatbot.booking_system.booking_data["dob"]:
                        chatbot.booking_system.booking_data["dob"] = exchange["user"]
                        chatbot.booking_system.current_question_index = 3
                    elif "What date would you prefer" in exchange["bot"] and exchange["user"] and not chatbot.booking_system.booking_data["date"]:
                        chatbot.booking_system.booking_data["date"] = exchange["user"]
                        chatbot.booking_system.current_question_index = 4
                    elif "What time would you prefer" in exchange["bot"] and exchange["user"] and not chatbot.booking_system.booking_data["time"]:
                        chatbot.booking_system.booking_data["time"] = exchange["user"]
                        chatbot.booking_system.current_question_index = 5
        
        if not user_input.strip():  # Handle empty input
            bot_response = "How may I assist you today?"
            response_data = {
                "success": True,
                "message": bot_response,
                "is_booking": chatbot.is_booking_in_progress,
                "booking_data": chatbot.booking_system.booking_data,
                "appointments": chatbot.booking_system.get_appointments()
            }
            chatbot.conversation_memory.add_exchange(user_input, bot_response)
            response_data["chat_history"] = chatbot.conversation_memory.history
            return response_data

        if chatbot.is_booking_in_progress:
            if user_input.lower() in ["ok", "yes", "sure"] and chatbot.booking_system.current_question_index == 1:
                bot_response = "Could you please provide your full name?"
            else:
                bot_response = chatbot.booking_system.process_response(user_input)
                if "successfully booked" in bot_response:
                    chatbot.is_booking_in_progress = False
            response_data = {
                "success": True,
                "message": bot_response,
                "is_booking": chatbot.is_booking_in_progress,
                "booking_data": chatbot.booking_system.booking_data,
                "appointments": chatbot.booking_system.get_appointments()
            }
        else:
            recent_context = chatbot.conversation_memory.get_recent_context()
            prompt = chatbot._get_conversation_prompt(user_input, recent_context)
            response = chatbot.model.generate_content(prompt)
            bot_response = response.text.strip()
            if "[START_BOOKING]" in bot_response:
                chatbot.is_booking_in_progress = True
                bot_response = bot_response.replace("[START_BOOKING]", "").strip()
                bot_response = chatbot.process_booking_request(user_input)
            elif "[CONTINUE_BOOKING]" in bot_response:
                chatbot.is_booking_in_progress = True
                bot_response = bot_response.replace("[CONTINUE_BOOKING]", "").strip()
                service = (chatbot._extract_service_from_message(recent_context) or 
                         chatbot._extract_service_from_message(user_input) or 
                         "appointment")
                if not chatbot.booking_system.booking_data["package"]:
                    bot_response = chatbot.booking_system.start_booking(service)
                else:
                    bot_response = chatbot.booking_system.ask_next_question() or chatbot.booking_system.confirm_booking()
            restricted_message = "I'm sorry, I am an AI receptionist"
            response_success = not bool(re.search(re.escape(restricted_message), bot_response))
            response_data = {
                "success": response_success,
                "message": bot_response,
                "is_booking": chatbot.is_booking_in_progress,
                "booking_data": chatbot.booking_system.booking_data,
                "appointments": chatbot.booking_system.get_appointments()
            }
        
        chatbot.conversation_memory.add_exchange(user_input, bot_response)
        response_data["chat_history"] = chatbot.conversation_memory.history
        return response_data
    except Exception as e:
        return {
            "success": False,
            "message": f"Error processing request: {str(e)}",
            "is_booking": False,
            "booking_data": None,
        }





def main(
    knowledge_base_content: str,
    available_services_content: str,
    user_instruction_content: str,
    Faq_content: list,
    user_input: str,
    appointments_content: str = "[]",
    chat_history: list = None
) -> dict:
    if not API_KEY:
        return {
            "success": False,
            "message": "API key not configured",
            "is_booking": False,
            "booking_data": None,
            "appointments": []
        }
    return process_user_input(
        knowledge_base_content=knowledge_base_content,
        available_services_content=available_services_content,
        user_instruction_content=user_instruction_content,
        Faq_content=Faq_content,
        appointments_content=appointments_content,
        user_input=user_input,
        chat_history=chat_history
    )























if __name__ == "__main__":
    # Test data
    test_knowledge_base = """
    Welcome to Beauty & Care Salon!
    
    Our Services and Prices:
    - Massage Therapy: $80/hour (Relaxation and Deep Tissue)
    - Facial Treatment: $60/session (Classic and Premium)
    - Hair Styling: Starting from $45
    - Nail Care: Starting from $30
    
    Business Hours: 9 AM to 5 PM Monday through Friday
    Location: 123 Main Street
    Phone: (555) 123-4567
    """
    
    test_services = """
    Massage Therapy
    Facial Treatment
    Hair Styling
    Nail Care
    """
    
    test_instructions = """
    Tone: Professional and welcoming
    Language Style: Formal but friendly
    Response Format: Clear and concise
    Key Behaviors:
    - Always greet customers warmly
    - Provide specific pricing when asked
    - Use polite language at all times
    - Guide customers through the booking process
    """
    
    test_faq = [
        {
            "question": "What are your hours?",
            "answer": "We are open from 9 AM to 5 PM, Monday to Friday."
        },
        {
            "question": "What services do you offer?",
            "answer": "We offer Massage Therapy ($80/hour), Facial Treatment ($60/session), Hair Styling (from $45), and Nail Care (from $30)."
        },
        {
            "question": "How can I book an appointment?",
            "answer": "You can book an appointment by telling me which service you'd like to schedule. I'll help you through the booking process."
        }
    ]
    
    # Initialize the chatbot
    chatbot = AppointmentChatbot(
        knowledge_base_content=test_knowledge_base.strip(),
        available_services_content=test_services.strip(),
        user_instruction_content=test_instructions.strip(),
        Faq_content=test_faq,
        appointments_content="[]"  # Add empty appointments list
    )
    
    # Run the chatbot
    chatbot.run()