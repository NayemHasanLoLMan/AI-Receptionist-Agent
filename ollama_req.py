import requests
import json
from bs4 import BeautifulSoup
import pytesseract
import pdfplumber
import os
import re
import cv2
from PIL import Image
import numpy as np
import logging
import time
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from robotexclusionrulesparser import RobotExclusionRulesParser

# Set Tesseract path for Windows
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Configure logging to suppress unnecessary warnings
logging.basicConfig(level=logging.INFO)
logging.getLogger('absl').setLevel(logging.ERROR)

class OllamaChatbot:
    def __init__(self, model: str = "mistral", url: str = "http://127.0.0.1:11434/api/chat"):
        """Initialize the Ollama chatbot."""
        self.url = url
        self.model = model
        self.messages = []

    def get_response(self, prompt: str) -> str:
        """Send request to Ollama API and return the response."""
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True
        }
        
        try:
            response = requests.post(self.url, json=payload, stream=True)
            response.raise_for_status()
            
            full_response = ""
            for line in response.iter_lines(decode_unicode=True):
                if line:
                    try:
                        json_data = json.loads(line)
                        if "message" in json_data and "content" in json_data["message"]:
                            content = json_data["message"]["content"]
                            full_response += content
                    except json.JSONDecodeError:
                        logging.warning(f"Failed to parse line: {line}")
                        continue
            
            return full_response if full_response else "No response generated."
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to connect to Ollama API: {str(e)}")
            return f"Failed to generate response: {str(e)}"

class KnowledgeBaseLoader:
    def __init__(self, source: str, is_file: bool = False, max_depth: int = 3, max_pages: int = 50):
        self.source = source
        self.is_file = is_file
        self.max_depth = max_depth
        self.max_pages = max_pages
        
        self.model = OllamaChatbot(model="mistral")
        
        # Initialize Selenium driver options
        self.chrome_options = Options()
        self.chrome_options.headless = True
        self.driver = None

    def _setup_driver(self):
        """Initialize or reuse the Selenium WebDriver."""
        if not self.driver:
            self.driver = webdriver.Chrome(options=self.chrome_options)
        return self.driver

    def _close_driver(self):
        """Close the Selenium WebDriver if it exists."""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def _respect_robots(self, url: str) -> bool:
        """Check if the URL is allowed by robots.txt."""
        try:
            parsed = urlparse(url)
            robots_url = f"http://{parsed.netloc}/robots.txt"
            resp = requests.get(robots_url, timeout=5)
            if resp.status_code == 200:
                robot_parser = RobotExclusionRulesParser()
                robot_parser.parse(resp.text)
                return robot_parser.is_allowed('*', url)
            return True
        except Exception as e:
            logging.warning(f"Could not check robots.txt for {url}: {str(e)}")
            return True

    def _fetch_dynamic_content(self, url: str) -> str:
        """Fetch content from a webpage using Selenium for dynamic content."""
        driver = self._setup_driver()
        try:
            driver.get(url)
            WebDriverWait(driver, 15).until(
                EC.presence_of_all_elements_located((By.TAG_NAME, 'body'))
            )
            
            last_height = driver.execute_script("return document.body.scrollHeight")
            scroll_attempts = 0
            max_scroll_attempts = 25
            while scroll_attempts < max_scroll_attempts:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(10)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
                scroll_attempts += 1
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            return soup.get_text(strip=True)
        except Exception as e:
            logging.error(f"Error fetching dynamic content from {url}: {str(e)}")
            return ""
        finally:
            pass

    def _fetch_static_content(self, url: str) -> str:
        """Fetch content from a webpage using requests for static content."""
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
                tag.decompose()
            
            all_content = [soup.get_text(strip=True)]
            page_num = 2
            while True:
                next_url = f"{url}?page={page_num}" if '?' in url else f"{url}?page={page_num}"
                try:
                    response = requests.get(next_url, timeout=10)
                    response.raise_for_status()
                    response.encoding = response.apparent_encoding or 'utf-8'
                    next_soup = BeautifulSoup(response.text, 'html.parser')
                    for tag in next_soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
                        tag.decompose()
                    next_text = next_soup.get_text(strip=True)
                    if not next_text or len(all_content) >= self.max_pages:
                        break
                    all_content.append(next_text)
                    page_num += 1
                except requests.RequestException:
                    break
            
            return '\n\n'.join(all_content)
        except requests.RequestException as e:
            logging.error(f"Error fetching static content from {url}: {str(e)}")
            return ""

    def _extract_relevant_text(self, text: str) -> list:
        """Extract all text, removing only noise and duplicates."""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        content_list = []
        for line in lines:
            if len(line) > 0 and not re.match(r'^\W+$', line):
                cleaned_line = ' '.join(line.split())
                content_list.append(cleaned_line)
        return list(dict.fromkeys(content_list))

    def _crawl_related_pages(self, base_url: str, depth: int = 0) -> list:
        """Recursively crawl all related pages."""
        if depth > self.max_depth or len(self.crawled_urls) >= self.max_pages:
            return []

        parsed_url = urlparse(base_url)
        base_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
        if base_url not in self.crawled_urls:
            self.crawled_urls.add(base_url)
        else:
            return []

        if not self._respect_robots(base_url):
            logging.warning(f"Skipping {base_url} due to robots.txt restrictions")
            return []

        content = self._fetch_dynamic_content(base_url) if 'javascript' in base_url.lower() or any(p in base_url.lower() for p in ['product', 'category', 'blog', 'news']) else self._fetch_static_content(base_url)
        if not content:
            return []

        relevant_text = self._extract_relevant_text(content)
        all_text = relevant_text

        soup = BeautifulSoup(content, 'html.parser')
        links = soup.find_all('a', href=True)
        for link in links:
            href = link['href']
            absolute_url = urljoin(base_url, href)
            parsed_link = urlparse(absolute_url)
            if parsed_link.netloc == parsed_url.netloc and absolute_url not in self.crawled_urls:
                try:
                    related_text = self._crawl_related_pages(absolute_url, depth + 1)
                    if related_text:
                        all_text.extend(related_text)
                except Exception as e:
                    logging.warning(f"Error crawling related link {absolute_url}: {str(e)}")

        return all_text[:50000]

    def _handle_webpage(self) -> str:
        """Scrape all text from a website."""
        print("\n🌍 Scraping website and all related pages...")
        self.crawled_urls = set()
        try:
            all_content = self._crawl_related_pages(self.source)
            if not all_content:
                logging.warning(f"No content found in {self.source} and related pages")
                return "No content extracted from webpage"
            return '\n\n'.join(all_content)
        except Exception as e:
            print(f"⚠️ Error scraping website {self.source}: {str(e)}")
            return f"Failed to scrape webpage: {str(e)}"
        finally:
            self._close_driver()
            time.sleep(10)

    def extract_text_from_source(self) -> str:
        """Extract text from the source and return a detailed knowledge base."""
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

            return f"{structured_text}\n\n=== Extracted Services ===\n{services_text}"

        except Exception as e:
            print(f"⚠️ Error extracting content: {str(e)}")
            return f"Failed to extract content from source: {str(e)}"

    def _handle_local_pdf(self) -> str:
        """Extract text from a local PDF file with enhanced OCR."""
        print(f"\n📖 Extracting content from local PDF: {self.source}")
        text_content = []
        with pdfplumber.open(self.source) as pdf:
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
        return '\n'.join(text_content)

    def _clean_content(self, content: str) -> str:
        """Clean content without losing information."""
        cleaned = '\n'.join(line.strip() for line in content.splitlines() if line.strip())
        cleaned = ' '.join(cleaned.split())
        return cleaned

    def _handle_pdf(self) -> str:
        """Extract text from PDF URL with enhanced OCR."""
        print("\n📥 Downloading PDF...")
        response = requests.get(self.source, stream=True)
        response.raise_for_status()
        
        temp_pdf = "temp.pdf"
        with open(temp_pdf, "wb") as f:
            f.write(response.content)
        
        print("📖 Extracting PDF content with OCR...")
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

    def _summarize_content(self, content: str) -> str:
        """Generate an exhaustive summary using Ollama Llama3."""
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

        Use clear, concise, and complete sentences. If a section has no direct information, state 'No specific details provided' and infer plausible details if possible.

        Content to Summarize:
        {content}
        """
        return self.model.get_response(prompt)

    def _format_as_text(self, summary: str) -> str:
        """Format the detailed summary into a structured plain text file."""
        print("\n📄 Formatting knowledge base...")
        prompt = f"""
        Format the following detailed summary into a highly structured plain text file optimized for an AI knowledge base.
        Use the following conventions:
        - Section headers in the format '=== Section Name ===' (e.g., '=== Business Name ===')
        - Subsections with '--- Subheading ---' if needed (e.g., '--- Service 1 ---')
        - Bullet points (-) for lists within sections, with consistent indentation (2 spaces)
        - Double line breaks between sections for clear separation
        - Preserve ALL details exactly as provided, ensuring readability and programmatic parsability

        Summary:
        {summary}
        """
        return self.model.get_response(prompt)

    def extract_services(self, structured_text: str):
        """Extract a list of services with names and prices."""
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
        return self.model.get_response(prompt)

if __name__ == "__main__":
    # Test with a website URL
    loader = KnowledgeBaseLoader("https://www.bdspecializedhospital.com/", is_file=False)
    result = loader.extract_text_from_source()
    print(result)