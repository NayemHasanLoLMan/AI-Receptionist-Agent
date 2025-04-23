import google.generativeai as genai
from bs4 import BeautifulSoup
import pytesseract
import pdfplumber
import requests
import os
import re
import cv2
from PIL import Image
import numpy as np
import logging



pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


# Configure logging to suppress Abseil warnings
logging.basicConfig(level=logging.INFO)
logging.getLogger('absl').setLevel(logging.ERROR)

class KnowledgeBaseLoader:
    def __init__(self, source: str, api_key: str, is_file: bool = False):
        self.source = source
        self.is_file = is_file
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")

    def extract_text_from_source(self) -> str:
        """Extract text from the source (URL or local PDF) and return a detailed knowledge base and services as a string."""
        try:
            if self.is_file:
                content = self._handle_local_pdf()
            elif self.source.lower().endswith('.pdf'):
                content = self._handle_pdf()
            else:
                content = self._handle_webpage()

            cleaned_content = self._clean_content(content)
            summarized_content = self._summarize_content(cleaned_content)
            structured_text = self._format_as_text(summarized_content)
            print("✅ Knowledge base generated")

            services_text = self.extract_services(structured_text)
            if services_text:
                print("✅ Services extracted")
            else:
                print("⚠️ No services detected")

            combined_output = f"{structured_text}\n\n=== Extracted Services ===\n{services_text}"
            return combined_output

        except Exception as e:
            print(f"⚠️ Error extracting content: {str(e)}")
            return f"Failed to extract content from source: {str(e)}"

    def _handle_local_pdf(self) -> str:
        """Extract text from a local PDF file with enhanced OCR for complex layouts like spa menus."""
        print(f"\n📖 Extracting content from local PDF: {self.source}")

        text_content = []
        with pdfplumber.open(self.source) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text and len(text.strip()) > 10:
                    text_content.append(text)
                else:
                    print(f"🔍 Performing enhanced OCR on page {page.page_number}...")
                    img = page.to_image(resolution=600).original  # Higher resolution for small text
                    
                    # Convert to grayscale
                    img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
                    
                    # Noise reduction
                    img_cv = cv2.GaussianBlur(img_cv, (5, 5), 0)
                    
                    # Adaptive thresholding for better contrast on low-quality scans
                    img_cv = cv2.adaptiveThreshold(img_cv, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                                 cv2.THRESH_BINARY, 11, 2)
                    
                    # Deskew and detect rotation
                    coords = cv2.findNonZero(cv2.bitwise_not(img_cv))
                    if coords is not None:
                        angle = cv2.minAreaRect(coords)[-1]
                        if angle < -45:
                            angle = -(90 + angle)
                        else:
                            angle = -angle
                        (h, w) = img_cv.shape[:2]
                        center = (w // 2, h // 2)
                        M = cv2.getRotationMatrix2D(center, angle, 1.0)
                        img_cv = cv2.warpAffine(img_cv, M, (w, h), flags=cv2.INTER_CUBIC, 
                                               borderMode=cv2.BORDER_REPLICATE)
                    
                    # Increase resolution for small text
                    img_cv = cv2.resize(img_cv, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
                    
                    # Handle multi-column layout by splitting the image
                    # Detect horizontal lines to separate columns (simplified approach)
                    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
                    horizontal_lines = cv2.morphologyEx(img_cv, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
                    coords = cv2.findNonZero(horizontal_lines)
                    if coords is not None:
                        y_coords = coords[:, 0, 1]
                        if len(y_coords) > 0:
                            column_y = int(np.median(y_coords))
                            left_col = img_cv[:, :column_y]
                            right_col = img_cv[:, column_y:]
                            
                            # OCR each column separately
                            left_pil = Image.fromarray(left_col)
                            right_pil = Image.fromarray(right_col)
                            
                            left_text = pytesseract.image_to_string(left_pil, config='--psm 3 -l eng --oem 1')
                            right_text = pytesseract.image_to_string(right_pil, config='--psm 3 -l eng --oem 1')
                            text = f"{left_text}\n{right_text}"
                        else:
                            # Fallback: OCR the whole image
                            img_pil = Image.fromarray(img_cv)
                            text = pytesseract.image_to_string(img_pil, config='--psm 3 -l eng --oem 1')
                    else:
                        # Fallback: OCR the whole image
                        img_pil = Image.fromarray(img_cv)
                        text = pytesseract.image_to_string(img_pil, config='--psm 3 -l eng --oem 1')
                    

                    
                    text_content.append(text.strip() or "OCR failed for this page")
        return '\n'.join(text_content)

    def _clean_content(self, content: str) -> str:
        """Clean content without losing information."""
        cleaned = '\n'.join(line.strip() for line in content.splitlines() if line.strip())
        cleaned = ' '.join(cleaned.split())
        return cleaned

    def _handle_pdf(self) -> str:
        """Extract text from PDF URL with enhanced OCR for complex layouts."""
        print("\n📥 Downloading PDF...")
        response = requests.get(self.source, stream=True)
        response.raise_for_status()
        
        temp_pdf = "temp.pdf"
        with open(temp_pdf, "wb") as f:
            f.write(response.content)
        
        print("📖 Extracting PDF content with OCR...")
        print(f"DEBUG: Tesseract path: {pytesseract.pytesseract.tesseract_cmd}")
        text_content = []
        with pdfplumber.open(temp_pdf) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text and len(text.strip()) > 10:
                    text_content.append(text)
                else:
                    print(f"🔍 Performing enhanced OCR on page {page.page_number}...")
                    img = page.to_image(resolution=600).original
                    
                    img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
                    img_cv = cv2.GaussianBlur(img_cv, (5, 5), 0)
                    img_cv = cv2.adaptiveThreshold(img_cv, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                                 cv2.THRESH_BINARY, 11, 2)
                    coords = cv2.findNonZero(cv2.bitwise_not(img_cv))
                    if coords is not None:
                        angle = cv2.minAreaRect(coords)[-1]
                        if angle < -45:
                            angle = -(90 + angle)
                        else:
                            angle = -angle
                        (h, w) = img_cv.shape[:2]
                        center = (w // 2, h // 2)
                        M = cv2.getRotationMatrix2D(center, angle, 1.0)
                        img_cv = cv2.warpAffine(img_cv, M, (w, h), flags=cv2.INTER_CUBIC, 
                                               borderMode=cv2.BORDER_REPLICATE)
                    
                    img_cv = cv2.resize(img_cv, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
                    
                    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
                    horizontal_lines = cv2.morphologyEx(img_cv, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
                    coords = cv2.findNonZero(horizontal_lines)
                    if coords is not None:
                        y_coords = coords[:, 0, 1]
                        if len(y_coords) > 0:
                            column_y = int(np.median(y_coords))
                            left_col = img_cv[:, :column_y]
                            right_col = img_cv[:, column_y:]
                            
                            left_pil = Image.fromarray(left_col)
                            right_pil = Image.fromarray(right_col)
                            
                            left_text = pytesseract.image_to_string(left_pil, config='--psm 3 -l eng --oem 1')
                            right_text = pytesseract.image_to_string(right_pil, config='--psm 3 -l eng --oem 1')
                            text = f"{left_text}\n{right_text}"
                        else:
                            img_pil = Image.fromarray(img_cv)
                            text = pytesseract.image_to_string(img_pil, config='--psm 3 -l eng --oem 1')
                    else:
                        img_pil = Image.fromarray(img_cv)
                        text = pytesseract.image_to_string(img_pil, config='--psm 3 -l eng --oem 1')
                    
                    
                    text_content.append(text.strip() or "OCR failed for this page")
        
        os.remove(temp_pdf)
        return '\n'.join(text_content)

    def _handle_webpage(self) -> str:
        print("\n🌍 Scraping webpage...")
        response = requests.get(self.source)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        
        content_list = []
        for tag in ['p', 'h1', 'h2', 'h3', 'h4', 'li', 'div', 'span', 'article']:
            elements = soup.find_all(tag)
            for elem in elements:
                text = elem.get_text().strip()
                if text and len(text) > 5:
                    content_list.append(text)
        
        return '\n'.join(content_list)
    


    def _summarize_content(self, content: str) -> str:
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
            return f"Failed to summarize content: {str(e)}"

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
            return summary

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
                return "\n".join(services)
            else:
                print("⚠️ No services detected in the summary")
                return ""
        except Exception as e:
            print(f"⚠️ Service extraction failed: {str(e)}")
            return ""


if __name__ == "__main__":
    api_key = "Api key"
    # Test with a website URL
    loader = KnowledgeBaseLoader("https://www.bdspecializedhospital.com/", api_key, is_file=False)
    result = loader.extract_text_from_source()
    print(result)