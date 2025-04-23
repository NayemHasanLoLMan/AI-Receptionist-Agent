import requests
from bs4 import BeautifulSoup
import pdfplumber
import os
from pathlib import Path
import google.generativeai as genai
import pytesseract
from PIL import Image
import io
import pytesseract



pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"



class KnowledgeBaseLoader:
    def __init__(self, business_url: str, api_key: str):
        self.business_url = business_url
        self.knowledge_base_file = "knowledge_base.txt"
        self.available_services_file = "available_services.txt"
        
        # Configure Google Gemini AI
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")

    def extract_text_from_url(self) -> str:
        """Extract text from URL (webpage or PDF) and generate a detailed knowledge base."""
        try:
            # Extract content based on URL type
            if self.business_url.lower().endswith('.pdf'):
                content = self._handle_pdf_with_ocr()
            else:
                content = self._handle_webpage()

            # Clean and prepare content
            cleaned_content = self._clean_content(content)

            # Generate a detailed summary
            summarized_content = self._summarize_content_detailed(cleaned_content)

            # Format into a highly structured text file
            structured_text = self._format_as_text(summarized_content)
            with open(self.knowledge_base_file, 'w', encoding='utf-8') as f:
                f.write(structured_text)
            print(f"✅ Detailed knowledge base saved to {self.knowledge_base_file}")

            # Extract and save services
            self.extract_services(structured_text)

            return structured_text

        except Exception as e:
            print(f"⚠️ Error extracting content: {str(e)}")
            return "Failed to extract content from URL"

    def _clean_content(self, content: str) -> str:
        """Clean content without losing information."""
        # Preserve all text, just remove excessive whitespace
        cleaned = '\n'.join(line.strip() for line in content.splitlines() if line.strip())
        cleaned = ' '.join(cleaned.split())
        return cleaned

    def _handle_pdf_with_ocr(self) -> str:
        """Extract text from PDF, using OCR for scanned pages."""
        print("\n📥 Downloading PDF...")
        response = requests.get(self.business_url, stream=True)
        response.raise_for_status()
        
        temp_pdf = "temp.pdf"
        with open(temp_pdf, "wb") as f:
            f.write(response.content)
        
        print("📖 Extracting PDF content with OCR...")
        print(f"DEBUG: Tesseract path: {pytesseract.pytesseract.tesseract_cmd}")
        text_content = []
        with pdfplumber.open(temp_pdf) as pdf:
            for page in pdf.pages:
                # Try extracting text directly
                text = page.extract_text()
                if text and len(text.strip()) > 10:  # If text is found, use it
                    text_content.append(text)
                else:  # Fallback to OCR
                    print(f"🔍 Performing OCR on page {page.page_number}...")
                    img = page.to_image().original  # Convert page to image
                    text = pytesseract.image_to_string(img)
                    text_content.append(text.strip() or "OCR failed for this page")

        os.remove(temp_pdf)
        return '\n'.join(text_content)

    def _handle_webpage(self) -> str:
        """Scrape all text from webpage."""
        print("\n🌍 Scraping webpage...")
        response = requests.get(self.business_url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Extract all meaningful text
        content_list = []
        for tag in ['p', 'h1', 'h2', 'h3', 'h4', 'li', 'div', 'span', 'article']:
            elements = soup.find_all(tag)
            for elem in elements:
                text = elem.get_text().strip()
                if text and len(text) > 5:  # Include shorter text for completeness
                    content_list.append(text)
        
        return '\n'.join(content_list)

    def _summarize_content_detailed(self, content: str) -> str:
        """Generate an exhaustive, detailed summary using AI, capturing all information."""
        print("\n🤖 Generating detailed summary...")

        prompt = f"""
        Create an exhaustive and highly detailed summary of the following business-related content.
        Your goal is to capture EVERY piece of information, no matter how minor, and present it in a comprehensive, structured format. Do not skip or omit any details. If information is vague, infer reasonable context or note it as unclear. The summary should be detailed enough to answer any possible question about the business.

        Organize the summary into the following sections, adding sub-details as needed:

        - Business Name: The exact name of the business
        - Business Description: A thorough overview of what the business does, its purpose, and its operations
        - History and Background: Any details about the business’s founding, milestones, or evolution (infer timeline if dates are missing)
        - Services Offered: A complete list of services with exhaustive descriptions, including duration, process, materials used, or any specifics mentioned
        - Key Features: Notable aspects like unique selling points, awards, certifications, or special offerings
        - Pricing Information: All details about costs, packages, fees, discounts, or payment terms (note if unavailable)
        - Availability: Full details on service hours, days, locations, booking processes, or seasonal variations
        - Facilities and Amenities: Information about physical locations, equipment, or additional offerings (e.g., parking, Wi-Fi)
        - Staff and Expertise: Details about employees, qualifications, or notable personnel
        - Contact Details: All contact methods (phone, email, address, social media, website links)
        - Customer Policies: Cancellation rules, refunds, dress codes, or other customer-facing guidelines
        - Additional Notes: Any miscellaneous details not covered above, including quotes, testimonials, or peripheral info

        Use clear, concise, and complete sentences. If a section has no direct information, state 'No specific details provided' and infer plausible details if possible. Ensure the output is optimized for an AI knowledge base, providing a robust foundation for answering any business-related question.

        Content to Summarize:
        {content}
        """

        try:
            ai_response = self.model.generate_content(prompt, stream=True)
            summary = "".join([chunk.text for chunk in ai_response])
            return summary
        except Exception as e:
            print(f"⚠️ AI summarization failed: {str(e)}")
            return "Failed to summarize content."

    def _format_as_text(self, summary: str) -> str:
        """Format the detailed summary into a highly organized plain text file."""
        print("\n📄 Formatting knowledge base...")

        prompt = f"""
        Format the following detailed summary into a highly structured plain text file optimized for an AI knowledge base.
        Use the following conventions:
        - Section headers in the format '=== Section Name ===' (e.g., '=== Business Name ===')
        - Subsections with '--- Subheading ---' if needed (e.g., '--- Service 1 ---')
        - Bullet points (-) for lists within sections, with consistent indentation (2 spaces)
        - Double line breaks between sections for clear separation
        - Preserve ALL details exactly as provided, ensuring readability and programmatic parsability

        Ensure the output is clean, organized, and retains every piece of information from the summary.

        Summary:
        {summary}
        """

        try:
            ai_response = self.model.generate_content(prompt, stream=True)
            structured_text = "".join([chunk.text for chunk in ai_response])
            return structured_text
        except Exception as e:
            print(f"⚠️ AI formatting failed: {str(e)}")
            return summary  # Fallback to raw summary
            


    def extract_services(self, structured_text: str):
        """Extract and save a list of services with names and prices (if available)."""
        print("\n🔍 Extracting services...")

        prompt = f"""
        From the following structured business summary, extract a concise list of all services offered.
        For each service, include:
        - Service name
        - Price (if available, otherwise leave blank)

        Format the output as a simple list with each entry on a new line in the form:
        'Service Name: Price' (e.g., 'Massage: €50' or 'Facial: ' if no price is provided)

        Summary:
        {structured_text}
        """

        try:
            ai_response = self.model.generate_content(prompt, stream=True)
            services = "".join([chunk.text for chunk in ai_response]).strip().split("\n")
            services = [s.strip() for s in services if s.strip()]
            if services:
                with open(self.available_services_file, 'w', encoding='utf-8') as f:
                    f.write("\n".join(services))
                print(f"✅ Services saved to {self.available_services_file}")
            else:
                print("⚠️ No services detected.")
        except Exception as e:
            print(f"⚠️ Service extraction failed: {str(e)}")


if __name__ == "__main__":
    # BUSINESS_URL = "https://monart.ie/Monart-Spa-Treatment-Brochure.pdf"
    BUSINESS_URL = "https://www.happy-bears.com/"
    API_KEY = os.getenv("GEMINI_API_KEY", "API KEY")  # Use env variable
    loader = KnowledgeBaseLoader(BUSINESS_URL, API_KEY)
    knowledge_base = loader.extract_text_from_url()
    print("✅ Knowledge base loaded successfully!")