import requests
from bs4 import BeautifulSoup
import pdfplumber
import os
from pathlib import Path
import google.generativeai as genai
import re

class KnowledgeBaseLoader:
    def __init__(self, business_url: str, api_key: str):
        
        self.business_url = business_url
        self.knowledge_base_file = "knowledge_base.txt"  # ✅ Save as TXT
        self.available_services_file = "available_services.txt"
 

        # ✅ Initialize Google Gemini AI
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")

    def extract_text_from_url(self) -> str:
        """Extract text content from URL and save to a structured text file"""
        try:
            # Extract content from webpage or PDF
            if self.business_url.lower().endswith('.pdf'):
                content = self._handle_pdf()
            else:
                content = self._handle_webpage()

            # ✅ Limit content size to avoid AI timeout
            cleaned_content = self._clean_content(content)  # Truncate large text

            # ✅ Summarize content using AI
            summarized_content = self._summarize_content(cleaned_content)

            # ✅ Extract and save structured knowledge base as plain text
            structured_text = self._format_as_text(summarized_content)
            with open(self.knowledge_base_file, 'w', encoding='utf-8') as f:
                f.write(structured_text)
            print(f"✅ Summarized knowledge base saved to {self.knowledge_base_file}")

            # ✅ Extract and save available services
            self.extract_services(structured_text)

            return structured_text
                
        except Exception as e:
            print(f"⚠️ Error extracting content: {str(e)}")
            return "Failed to extract content from URL"

    def _clean_content(self, content: str) -> str:
        """Clean and format extracted content"""
        cleaned = '\n'.join(line.strip() for line in content.splitlines() if line.strip())
        cleaned = ' '.join(cleaned.split())
        cleaned = cleaned.replace('. ', '.\n')
        return cleaned

    def _handle_pdf(self) -> str:
        """Extract text from PDF"""
        print("\n📥 Downloading PDF...")
        response = requests.get(self.business_url, stream=True)
        response.raise_for_status()
        
        with open("temp.pdf", "wb") as f:
            f.write(response.content)
        
        print("📖 Reading PDF content...")
        text_content = []
        with pdfplumber.open("temp.pdf") as pdf:
            for page in pdf.pages:
                text_content.append(page.extract_text() or '')
        
        os.remove("temp.pdf")
        return '\n'.join(text_content)

    def _handle_webpage(self) -> str:
        """Scrape text from webpage"""
        print("\n🌍 Scraping webpage...")
        response = requests.get(self.business_url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for script in soup(["script", "style"]):
            script.decompose()
        
        content_list = []
        for tag in ['p', 'h1', 'h2', 'h3', 'h4', 'li', 'div']:
            elements = soup.find_all(tag)
            for elem in elements:
                text = elem.get_text().strip()
                if text and len(text) > 20:
                    content_list.append(text)
        
        return '\n'.join(content_list)

    def _summarize_content(self, content: str) -> str:
        """Use AI to summarize extracted content into structured text"""
        print("\n🤖 Summarizing extracted content...")

        prompt = f"""
        Summarize the following business information in a structured text format.
        Include:
        - Business Name
        - Overview of services
        - Key Features
        - Service Categories with descriptions
        - Pricing and availability details
        - Contact Information

        Format the response in a **clean, readable text format**.

        Extracted Content:
        {content}
        """

        try:
            ai_response = self.model.generate_content(prompt, stream=True)  # ✅ Use streaming
            summary = "".join([chunk.text for chunk in ai_response])  # ✅ Process chunks
            return summary
        except Exception as e:
            print(f"⚠️ AI summarization failed: {str(e)}")
            return "Failed to summarize content."

    def _format_as_text(self, summary: str) -> str:
        """Format AI summary into a structured plain text file"""
        print("\n📄 Formatting knowledge base as text...")

        prompt = f"""
        Convert the following summary into a **well-structured plain text file** with:
        - Clear section titles
        - Bullet points for key features
        - Proper spacing and formatting

        Summary:
        {summary}
        """

        try:
            ai_response = self.model.generate_content(prompt, stream=True)  # ✅ Use streaming
            structured_text = "".join([chunk.text for chunk in ai_response])  # ✅ Process chunks
            return structured_text
        except Exception as e:
            print(f"⚠️ AI text formatting failed: {str(e)}")
            return summary  # Fallback to original summary

    def extract_services(self, structured_text: str):
        """Extract available services from structured text and save them."""
        print("\n🔍 Extracting services from structured text...")

        prompt = f"""
        Identify and list the specific services offered in the following business summary.
        Provide a **simple list** with each service on a new line.

        Business Summary:
        {structured_text}
        """

        try:
            ai_response = self.model.generate_content(prompt, stream=True)  # ✅ Use streaming
            services = "".join([chunk.text for chunk in ai_response]).strip().split("\n")

            # Remove empty lines and save
            services = [s.strip() for s in services if s.strip()]
            if services:
                with open(self.available_services_file, 'w', encoding='utf-8') as f:
                    f.write("\n".join(services))
                print(f"✅ Services extracted and saved to {self.available_services_file}")
            else:
                print("⚠️ No services detected.")
        except Exception as e:
            print(f"⚠️ Service extraction failed: {str(e)}")


if __name__ == "__main__":
    # BUSINESS_URL = "https://www.happy-bears.com/"  
    BUSINESS_URL = "https://monart.ie/Monart-Spa-Treatment-Brochure.pdf"
    API_KEY = "API KEY"  # Replace with your actual API key
    loader = KnowledgeBaseLoader(BUSINESS_URL, API_KEY)
    knowledge_base = loader.extract_text_from_url()
    print("✅ Knowledge base loaded successfully!")


