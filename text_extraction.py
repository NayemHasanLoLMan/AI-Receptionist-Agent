import PyPDF2
import openai
import os

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file."""
    text = ""
    with open(pdf_path, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    return text

def organize_text_with_gpt(text, api_key):
    """Use OpenAI GPT to organize the extracted text into proper sections."""
    openai.api_key = api_key
    response = openai.ChatCompletion.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": "You are an assistant that organizes text into well-structured sections."},
            {"role": "user", "content": f"Organize the following text into structured sections with headings and details:\n{text}"}
        ]
    )
    return response["choices"][0]["message"]["content"]

def main():
    """Main function to extract, organize, and save text from PDF."""
    api_key = "Api key "  # Replace with your OpenAI API key
    pdf_path = "C:/Users/hasan/Downloads/Alanbrb/ELD Standards Board Approved UA.pdf"
    output_file = "C:/Users/hasan/Downloads/Alanbrb/organized_text.txt"
    
    print("Extracting text from PDF...")
    extracted_text = extract_text_from_pdf(pdf_path)
    
    print("Organizing text using GPT...")
    organized_text = organize_text_with_gpt(extracted_text, api_key)
    
    print("Saving organized text...")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(organized_text)
    
    print(f"Organized text saved to: {output_file}")

if __name__ == "__main__":
    main()
