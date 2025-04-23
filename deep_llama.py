import os
import hashlib
import requests
import pdfplumber
from bs4 import BeautifulSoup
from langchain_ollama import OllamaLLM
from tqdm import tqdm  # Progress bar

# Load the Ollama model
llm = OllamaLLM(model="deepseek-r1:14b")

# File to store extracted knowledge
KNOWLEDGE_FILE = "knowledge_base.txt"
HASH_FILE = "knowledge_hash.txt"

# Function to compute hash of a string
def compute_hash(data):
    return hashlib.md5(data.encode()).hexdigest()

# Function to save responses to a file
def save_response_to_txt(response, filename="response.txt"):
    with open(filename, "w", encoding="utf-8") as file:
        file.write(response)
    print(f"Response saved to {filename}")

# Function to extract text from a PDF URL
def extract_text_from_pdf(pdf_url):
    try:
        print("\n📥 Downloading PDF...")
        response = requests.get(pdf_url, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))
        block_size = 1024  # 1 KB
        progress_bar = tqdm(total=total_size, unit="B", unit_scale=True)

        # Save the PDF locally
        with open("knowledge_base.pdf", "wb") as f:
            for chunk in response.iter_content(chunk_size=block_size):
                progress_bar.update(len(chunk))
                f.write(chunk)
        progress_bar.close()

        print("\n📖 Extracting text from PDF...")
        extracted_text = ""
        with pdfplumber.open("knowledge_base.pdf") as pdf:
            num_pages = len(pdf.pages)
            for page in tqdm(pdf.pages, desc="Processing Pages", unit="page"):
                text = page.extract_text()
                if text:
                    extracted_text += text + "\n"

        return extracted_text.strip()
    except Exception as e:
        return f"Error extracting text from the PDF: {str(e)}"

# Function to scrape content from a webpage
def scrape_webpage(url):
    try:
        print("\n🌍 Scraping webpage...")
        response = requests.get(url)
        response.raise_for_status()
        
        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = soup.find_all('p')

        # Extract text from paragraphs
        extracted_text = ""
        for p in tqdm(paragraphs, desc="Extracting Paragraphs", unit="p"):
            extracted_text += p.get_text() + " "

        return extracted_text.strip()
    except Exception as e:
        return f"Error scraping the webpage: {str(e)}"

# Function to load saved knowledge
def load_saved_knowledge():
    if os.path.exists(KNOWLEDGE_FILE) and os.path.exists(HASH_FILE):
        with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return None

# Function to get AI response based on loaded knowledge
def get_ai_response(user_input, knowledge_base):
    prompt = f"""
    You are a helpful AI assistant. Answer user questions strictly based on the following knowledge base:

    {knowledge_base}

    If the question cannot be answered from the knowledge base, simply reply: 
    "I could not find an answer in the provided knowledge base."

    User: {user_input}
    AI:
    """

    # Call the local Ollama model to generate a response
    response = llm.invoke(prompt)

    # Ensure a valid response
    if not response or any(
        phrase in response.lower() for phrase in [
            "i don't understand", 
            "no answer found", 
            "i can't find an answer", 
            "sorry", 
            "not mentioned in the provided knowledge base"
        ]
    ):
        return "I could not find an answer in the provided knowledge base."

    return response

# Main function to handle loading or processing knowledge
def load_or_extract_knowledge(source_url, is_pdf=True):
    # Load existing knowledge if available
    saved_knowledge = load_saved_knowledge()

    if saved_knowledge:
        print("\n🔄 Checking if existing knowledge is up to date...")

        # Compute hash of saved knowledge
        saved_hash = open(HASH_FILE, "r").read().strip()

        # Compute hash of new knowledge
        new_knowledge = extract_text_from_pdf(source_url) if is_pdf else scrape_webpage(source_url)
        new_hash = compute_hash(new_knowledge)

        # If hashes match, use saved knowledge
        if saved_hash == new_hash:
            print("\n✅ Using previously saved knowledge base.")
            return saved_knowledge

    # If no saved knowledge or outdated data, extract and save new knowledge
    print("\n⚡ Extracting new knowledge...")
    knowledge_base = extract_text_from_pdf(source_url) if is_pdf else scrape_webpage(source_url)

    # Save new knowledge and hash
    with open(KNOWLEDGE_FILE, "w", encoding="utf-8") as f:
        f.write(knowledge_base)
    with open(HASH_FILE, "w", encoding="utf-8") as f:
        f.write(compute_hash(knowledge_base))

    return knowledge_base

# Specify knowledge source
knowledge_source = "https://www.hasanboy.uz/wp-content/uploads/2018/04/Harry-Potter-and-the-Philosophers-Stone.pdf"  # Change to your PDF or webpage URL
knowledge_base = load_or_extract_knowledge(knowledge_source, is_pdf=True)  # Set is_pdf=False if using a webpage

# Check if knowledge was successfully loaded
if not knowledge_base or "Error" in knowledge_base:
    print("⚠️ Error loading knowledge base. Please check the source URL.")
    exit()

print("\n✅ Knowledge base successfully loaded. Chatbot is ready to answer questions!")

# Chat loop
while True:
    user_input = input("\nYou: ")
    
    if user_input.lower() in ["/exit"]:
        print("🔴 Exiting chatbot.")
        break

    # Get AI response based on loaded knowledge
    bot_response = get_ai_response(user_input, knowledge_base)

    # Print and save the response
    print(f"\n🔵 AI: {bot_response}")
    save_response_to_txt(bot_response)


