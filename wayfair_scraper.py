import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ActionChains
import os
from datetime import datetime
import time
import base64
import requests
import json
import re
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variables
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    raise ValueError("OpenAI API key not found. Please make sure you have a .env file with OPENAI_API_KEY set.")

def clean_code(code):
    """Clean up the code returned by the LLM"""
    # Remove markdown code blocks if present
    code = re.sub(r'```(?:python)?\n?(.*?)\n?```', r'\1', code, flags=re.DOTALL)
    
    # Remove any imports or driver initialization
    lines = code.split('\n')
    cleaned_lines = []
    for line in lines:
        if not any(keyword in line.lower() for keyword in [
            'import', 
            'webdriver', 
            'driver =', 
            'driver=',
            'def try_multiple_selectors',
            'driver.get',
            'driver.quit'
        ]):
            cleaned_lines.append(line)
    
    # Remove any leading/trailing whitespace
    code = '\n'.join(cleaned_lines).strip()
    
    # Ensure the code doesn't have any empty lines at start/end
    code = '\n'.join(line for line in code.splitlines() if line.strip())
    
    return code

def try_multiple_selectors(driver, element_description):
    """Try multiple selector strategies to find an element"""
    selectors = [
        # Text-based selectors
        f"//button[contains(., '{element_description}')]",
        f"//a[contains(., '{element_description}')]",
        f"//div[contains(., '{element_description}')]",
        f"//*[contains(text(), '{element_description}')]",
        
        # Common attribute selectors
        f"//button[contains(@aria-label, '{element_description}')]",
        f"//button[contains(@title, '{element_description}')]",
        f"//a[contains(@aria-label, '{element_description}')]",
        
        # Class-based selectors for common elements
        "//button[contains(@class, 'close')]",
        "//button[contains(@class, 'dismiss')]",
        "//div[contains(@class, 'modal')]//button",
        "//div[contains(@class, 'popup')]//button",
        
        # Input-specific selectors
        "//input[@type='search']",
        "//input[contains(@placeholder, 'Search')]",
        "//input[contains(@placeholder, 'Find')]",
        "//input[contains(@class, 'search')]"
    ]
    
    for selector in selectors:
        try:
            element = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, selector))
            )
            return element
        except:
            continue
    return None

def get_selenium_code(driver, user_command):
    """Convert natural language command to Selenium code using GPT-4o-mini with visual context"""
    print("\nTaking screenshot for visual context...")
    
    # Take a screenshot of the current page
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    temp_screenshot = os.path.join(outputs_dir, f'temp_screenshot_{timestamp}.png')
    driver.save_screenshot(temp_screenshot)
    
    # Encode the screenshot
    with open(temp_screenshot, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode('utf-8')
    
    # Clean up temporary screenshot
    os.remove(temp_screenshot)
    
    print("Converting your command to Selenium code...")
    
    system_prompt = """You are a Selenium code generator that can see the current webpage. Generate Python code to interact with the visible elements.
    IMPORTANT: DO NOT include any imports, driver initialization, or browser setup. The driver instance already exists.
    
    Rules:
    1. Output ONLY the specific action code needed (no imports, no driver creation)
    2. Use the existing 'driver' instance that's already running
    3. Use try_multiple_selectors(driver, "element name") for finding elements
    4. For any interaction, use this pattern:
       element = try_multiple_selectors(driver, "element name")
       if element:
           element.click()  # or other action
    5. For search and input:
       element = try_multiple_selectors(driver, "search")
       if element:
           element.clear()
           element.send_keys("your text")
    6. For scrolling:
       driver.execute_script("window.scrollBy(0, pixels);")
    7. Always add time.sleep(2) after actions
    8. DO NOT include any function definitions or browser setup code
    9. DO NOT use driver.get() or driver.quit()"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Looking at this screenshot of the Wayfair website, generate ONLY the specific Selenium action code to: {user_command}"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 500,
        "temperature": 0.3
    }
    
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        code = result['choices'][0]['message']['content'].strip()
        
        # Clean up the code
        cleaned_code = clean_code(code)
        
        # Print the code for debugging
        print("\nGenerated Selenium code:")
        print(cleaned_code)
        
        return cleaned_code
    except Exception as e:
        print(f"Error getting Selenium code: {str(e)}")
        return None

def execute_selenium_code(driver, code):
    """Safely execute the generated Selenium code"""
    try:
        # Add all necessary functions and variables to the local scope
        locals_dict = {
            'driver': driver,
            'By': By,
            'Keys': Keys,
            'WebDriverWait': WebDriverWait,
            'EC': EC,
            'time': time,
            'try_multiple_selectors': try_multiple_selectors
        }
        
        # Execute the code with the provided context
        exec(code, globals(), locals_dict)
        time.sleep(1)  # Small delay after execution
        return True
    except Exception as e:
        print(f"Error executing Selenium code: {str(e)}")
        if hasattr(e, 'msg'):
            print(f"Detailed error: {e.msg}")
        return False

def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def analyze_image_with_gpt4(image_path):
    print("\nAnalyzing image with GPT-4o-mini...")
    
    # Encode the image
    base64_image = encode_image_to_base64(image_path)
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Describe in a few sentences what you see in this image."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 300
    }
    
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        
        result = response.json()
        description = result['choices'][0]['message']['content']
        print("\nGPT-4o-mini's Description:")
        print(description)
        
    except requests.exceptions.RequestException as e:
        print(f"\nError calling OpenAI API: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"API Response: {e.response.text}")
        elif 'response' in locals():
            print(f"API Response: {response.text}")

def handle_bot_detection(driver):
    """Handle the 'Press & Hold' bot detection if it appears"""
    try:
        # Wait for the press & hold button with a timeout
        press_hold_button = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'Press & Hold')]"))
        )
        
        print("\nBot detection found. Attempting to verify...")
        
        # Create an action chain for press and hold
        actions = ActionChains(driver)
        
        # Move to the button, press and hold for 3 seconds
        actions.move_to_element(press_hold_button)
        actions.click_and_hold()
        actions.pause(3)  # Hold for 3 seconds
        actions.release()
        
        # Perform the action
        actions.perform()
        
        # Wait for the verification to complete
        time.sleep(4)
        return True
        
    except Exception as e:
        print(f"No bot detection found or error handling it: {str(e)}")
        return False

# Create outputs directory if it doesn't exist
outputs_dir = 'outputs'
if not os.path.exists(outputs_dir):
    os.makedirs(outputs_dir)
    print(f"Created outputs directory at: {os.path.abspath(outputs_dir)}")

try:
    # Create undetected Chrome browser instance with specific version
    options = uc.ChromeOptions()
    driver = uc.Chrome(
        options=options,
        version_main=133
    )
    driver.maximize_window()
    
    # Navigate to Wayfair
    print("\nNavigating to Wayfair...")
    driver.get('https://www.wayfair.com')
    time.sleep(5)  # Initial page load
    
    # Handle any initial bot detection
    handle_bot_detection(driver)

    while True:
        print("\nWhat would you like to do on Wayfair? (Type 'quit' to exit)")
        user_command = input("> ").strip()
        
        if user_command.lower() == 'quit':
            break
            
        # Check for bot detection before executing command
        handle_bot_detection(driver)
            
        # Get Selenium code for the command with visual context
        selenium_code = get_selenium_code(driver, user_command)
        if selenium_code:
            print("\nExecuting your command...")
            success = execute_selenium_code(driver, selenium_code)
            
            if success:
                print("Command executed successfully!")
                time.sleep(2)  # Give time for any page updates
                # Check for bot detection after command execution
                handle_bot_detection(driver)
            else:
                print("Command execution failed. Please try again or rephrase your command.")
                # Check for bot detection after failed command
                handle_bot_detection(driver)

except Exception as e:
    print(f"An error occurred: {str(e)}")
    import traceback
    print("Full error trace:")
    print(traceback.format_exc())

finally:
    # Close the browser
    if 'driver' in locals():
        print("\nClosing browser...")
        driver.quit() 