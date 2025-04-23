import pandas as pd
import re
from pathlib import Path
import requests
import os
import time

def validate_email(email):
    """Validate email format"""
    if pd.isna(email):
        return False
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(email_pattern, str(email).strip()))

def validate_phone(phone):
    """Validate phone number format (10-15 digits, optional +)"""
    if pd.isna(phone):
        return False
    phone_str = str(phone).strip()
    cleaned = re.sub(r'[-()\s.]', '', phone_str)
    return bool(re.match(r'^\+?\d{10,15}$', cleaned))

def clean_phone(phone):
    """Clean phone number, preserving full original format with leading zeros"""
    if pd.isna(phone) or not str(phone).strip():
        return None
    phone_str = str(phone).strip()  # Ensure it’s a string
    # Remove separators but keep all digits
    cleaned = re.sub(r'[-()\s.]', '', phone_str)
    # Check if it’s a valid phone number (10-15 digits)
    if re.match(r'^\+?\d{10,15}$', cleaned):
        # Return the original string if valid, preserving leading zeros
        return phone_str
    return None  # Return None if invalid

def convert_to_export_url(url):
    """Convert Google Sheets edit URL to export URL"""
    if 'docs.google.com/spreadsheets' not in url:
        return url
    
    sheet_id_match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
    gid_match = re.search(r'gid=(\d+)', url)
    
    if not sheet_id_match:
        raise ValueError("Could not extract sheet ID from URL")
    
    sheet_id = sheet_id_match.group(1)
    gid = gid_match.group(1) if gid_match else '0'
    
    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    print(f"Converted URL to: {export_url}")
    return export_url

def download_file(url, output_path):
    """Download file from URL to a specified location"""
    try:
        url = convert_to_export_url(url)
        print(f"Attempting to download from {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        content_type = response.headers.get('content-type', '').lower()
        print(f"Content-Type: {content_type}")

        if 'excel' in content_type or 'openxml' in content_type or url.endswith('.xlsx'):
            file_ext = '.xlsx'
        elif 'csv' in content_type or url.endswith('csv'):
            file_ext = '.csv'
        else:
            raise ValueError("Unexpected content type or URL format")

        temp_file = f"{output_path}_temp{file_ext}"
        with open(temp_file, 'wb') as f:
            f.write(response.content)
        
        time.sleep(0.5)
        if os.path.exists(temp_file):
            file_size = os.path.getsize(temp_file)
            print(f"Downloaded to {temp_file} (Size: {file_size} bytes)")
            if file_size == 0:
                raise ValueError("Downloaded file is empty")
            return temp_file
        else:
            raise FileNotFoundError(f"Temporary file {temp_file} was not created")
    except requests.exceptions.RequestException as e:
        print(f"Error downloading file from {url}: {str(e)}")
        return None
    except Exception as e:
        print(f"Error during download: {str(e)}")
        return None

def read_file(file_path_or_url):
    """Read different file types or URLs with robust handling"""
    temp_file = None
    try:
        if file_path_or_url.startswith(('http://', 'https://')):
            temp_file = download_file(file_path_or_url, "downloaded_file")
            if not temp_file:
                return None
            file_path = temp_file
        else:
            file_path = file_path_or_url
            if not os.path.exists(file_path):
                print(f"Error: File {file_path} does not exist")
                return None

        file_path = Path(file_path)
        ext = file_path.suffix.lower()
        print(f"Reading file: {file_path}")

        # Ensure phone numbers are read as strings
        if ext in ['.xlsx', '.xls']:
            df = pd.read_excel(file_path, dtype={'Phone Number': str, 'Phone': str, 'Mobile': str})
        elif ext == '.csv':
            try:
                df = pd.read_csv(file_path, dtype={'Phone Number': str, 'Phone': str, 'Mobile': str})
            except pd.errors.ParserError:
                print("Initial CSV parsing failed, trying alternative delimiters...")
                for delimiter in [',', '\t', ';']:
                    try:
                        df = pd.read_csv(file_path, sep=delimiter, dtype={'Phone Number': str, 'Phone': str, 'Mobile': str})
                        print(f"Success with delimiter: '{delimiter}'")
                        return df
                    except:
                        continue
                print("All delimiter attempts failed, attempting to skip bad lines...")
                df = pd.read_csv(file_path, on_bad_lines='skip', engine='python', dtype={'Phone Number': str, 'Phone': str, 'Mobile': str})
        else:
            raise ValueError(f"Unsupported file type: {ext}")
        
        return df
    
    except Exception as e:
        print(f"Error reading file {file_path}: {str(e)}")
        return None
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
                print(f"Cleaned up temporary file: {temp_file}")
            except Exception as e:
                print(f"Error cleaning up {temp_file}: {str(e)}")

def extract_and_clean_contacts(file_path_or_url):
    try:
        # Read the file
        df = read_file(file_path_or_url)
        if df is None or df.empty:
            print("Error: Could not read file or file is empty")
            return None

        # Expanded column name variations (case insensitive)
        name_variations = ['name', 'full name', 'contact name', 'first name', 'lastname', 
                           'last name', 'person', 'contact', 'customer name']
        email_variations = ['email', 'e-mail', 'email address', 'mail', 'email id', 
                            'contact email', 'e mail']
        phone_variations = ['phone', 'phone number', 'mobile', 'contact', 'tel', 
                            'telephone', 'mobile number', 'cell', 'cell phone', 
                            'contact number', 'ph']

        # Convert column names to lowercase for matching
        columns_lower = {col.lower(): col for col in df.columns}
        
        # Find matching columns
        name_col = next((columns_lower[col] for col in columns_lower if col in name_variations), None)
        email_col = next((columns_lower[col] for col in columns_lower if col in email_variations), None)
        phone_col = next((columns_lower[col] for col in columns_lower if col in phone_variations), None)
        
        # Create result dataframe
        result_df = pd.DataFrame()
        stats = {'total': 0, 'processed': 0}
        
        # Process each found column
        if name_col:
            result_df['Name'] = df[name_col].str.strip().replace('', None)
        else:
            print("Warning: No name column found")

        if email_col:
            emails = df[email_col].str.strip().str.lower()
            result_df['Email'] = emails.where(emails.apply(validate_email))
        else:
            print("Warning: No email column found")

        if phone_col:
            phones = df[phone_col].apply(clean_phone)
            result_df['Phone'] = phones.where(phones.apply(lambda x: validate_phone(x) if x else False))
        else:
            print("Warning: No phone column found")

        # Update statistics
        stats['total'] = len(df)
        stats['processed'] = len(result_df.dropna(how='all'))

        # Remove completely empty rows
        result_df = result_df.dropna(how='all')
        
        # Save to output file
        file_name = 'temp_file' if file_path_or_url.startswith(('http://', 'https://')) else Path(file_path_or_url).stem
        output_file = f"cleaned_contacts_{file_name}.xlsx"
        result_df.to_excel(output_file, index=False)
        
        # Print statistics
        print(f"Processed {stats['total']} records:")
        print(f"- Records with valid data: {stats['processed']}")
        print(f"Results saved to: {output_file}")
        
        return result_df

    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return None

# Example usage
if __name__ == "__main__":
    # Your original Google Sheets edit URL
    file_path_or_url = 'https://docs.google.com/spreadsheets/d/19Hl7FEBkW2I4GSpvw7JBFGCKFB49uroNmmzW7oGsgP4/edit?gid=1106999089#gid=1106999089'
    contacts = extract_and_clean_contacts(file_path_or_url)
    
    if contacts is not None and not contacts.empty:
        print("\nAll records:")
        print(contacts)  # Print all records instead of head()
