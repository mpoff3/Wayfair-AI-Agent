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
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Get API key directly
OPENAI_API_KEY = ""  # Replace with your actual API key

def clean_code(code):
    """Clean up the code returned by the LLM"""
    code = re.sub(r'```(?:python)?\n?(.*?)\n?```', r'\1', code, flags=re.DOTALL)
    lines = code.split('\n')
    cleaned_lines = []
    for line in lines:
        if not any(keyword in line.lower() for keyword in [
            'import', 'webdriver', 'driver =', 'driver=',
            'def try_multiple_selectors', 'driver.get', 'driver.quit'
        ]):
            cleaned_lines.append(line)
    code = '\n'.join(cleaned_lines).strip()
    code = '\n'.join(line for line in code.splitlines() if line.strip())
    return code

def try_multiple_selectors(driver, element_description):
    """Try multiple selector strategies to find an element with improved logging and validation"""
    selectors = [
        f"//button[contains(., '{element_description}')]",
        f"//a[contains(., '{element_description}')]",
        f"//div[contains(., '{element_description}')]",
        f"//*[contains(text(), '{element_description}')]",
        f"//button[contains(@aria-label, '{element_description}')]",
        f"//button[contains(@title, '{element_description}')]",
        f"//a[contains(@aria-label, '{element_description}')]",
        "//button[contains(@class, 'close')]",
        "//button[contains(@class, 'dismiss')]",
        "//div[contains(@class, 'modal')]//button",
        "//div[contains(@class, 'popup')]//button",
        "//input[@type='search']",
        "//input[contains(@placeholder, 'Search')]",
        "//input[contains(@placeholder, 'Find')]",
        "//input[contains(@class, 'search')]",
        "//input[@type='text' and contains(@class, 'search')]",
        "//input[@type='text' and contains(@placeholder, 'search')]",
        "//form//input[@type='text']"
    ]
    
    for selector in selectors:
        try:
            element = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, selector))
            )
            
            # Log detailed element information
            logging.info(f"Found element with selector: {selector}")
            logging.info(f"Tag name: {element.tag_name}")
            logging.info(f"Enabled: {element.is_enabled()}")
            logging.info(f"Displayed: {element.is_displayed()}")
            logging.info(f"Disabled attribute: {element.get_attribute('disabled')}")
            logging.info(f"Class: {element.get_attribute('class')}")
            
            # For search inputs, verify it's actually an input element
            if 'search' in element_description.lower():
                if element.tag_name != 'input':
                    logging.warning("Found element is not an input field, skipping...")
                    continue
                    
                # Try to make the element interactive
                try:
                    # Scroll element into view
                    driver.execute_script("arguments[0].scrollIntoView(true);", element)
                    time.sleep(1)
                    
                    # Wait for element to be clickable
                    element = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    
                    # Try to click it to ensure it's focusable
                    element.click()
                    time.sleep(0.5)
                    
                except Exception as e:
                    logging.warning(f"Element not interactive: {str(e)}")
                    continue
            
            return element
            
        except Exception as e:
            logging.debug(f"Selector {selector} failed: {str(e)}")
            continue
            
    logging.error(f"No suitable element found for: {element_description}")
    return None

def close_popup_if_present(driver):
    """
    Enhanced popup detection and closing function
    """
    popup_selectors = [
        # Close buttons
        "//button[contains(@class, 'CloseButton')]",
        "//button[contains(@class, 'close-button')]",
        "//button[contains(@class, 'dismiss')]",
        "//button[contains(@aria-label, 'Close')]",
        "//button[contains(@aria-label, 'close')]",
        "//button[contains(@title, 'Close')]",
        # X symbols
        "//button[contains(text(), '×')]",
        "//button[contains(text(), 'X')]",
        # Modal close buttons
        "//div[contains(@class, 'modal')]//button[contains(@class, 'close')]",
        "//div[contains(@class, 'popup')]//button",
        # Newsletter/email popups
        "//div[contains(@class, 'email-signup')]//button",
        "//div[contains(@class, 'newsletter')]//button",
        # Generic overlay close buttons
        "//*[contains(@class, 'overlay')]//button",
        # Specific Wayfair selectors
        "//button[@data-testid='overlay-close']",
        "//button[@data-testid='close-button']"
    ]

    try:
        # First check if there's any overlay/popup present
        overlay_selectors = [
            "//div[contains(@class, 'overlay')]",
            "//div[contains(@class, 'modal')]",
            "//div[contains(@class, 'popup')]",
            "//div[@role='dialog']"
        ]
        
        for overlay_selector in overlay_selectors:
            try:
                overlay = driver.find_element(By.XPATH, overlay_selector)
                if overlay.is_displayed():
                    logging.info(f"Detected visible overlay/popup: {overlay_selector}")
                    break
            except:
                continue

        # Try each close button selector
        for selector in popup_selectors:
            try:
                # Use a shorter wait time to keep things moving
                close_button = WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                
                if close_button and close_button.is_displayed():
                    logging.info(f"Found close button with selector: {selector}")
                    
                    # Try JavaScript click first
                    try:
                        driver.execute_script("arguments[0].click();", close_button)
                        logging.info("Closed popup using JavaScript click")
                    except:
                        # Fall back to regular click
                        close_button.click()
                        logging.info("Closed popup using regular click")
                    
                    # Wait for popup to disappear
                    time.sleep(1)
                    
                    # Verify the popup is gone
                    try:
                        if not close_button.is_displayed():
                            logging.info("Popup successfully closed")
                            return True
                    except:
                        return True
            except Exception as e:
                continue

        return False

    except Exception as e:
        logging.error(f"Error in close_popup_if_present: {str(e)}")
        return False

def get_basic_steps(instructions):
    """
    Break down the provided paragraph of instructions into an 
    extremely basic step-by-step list using OpenAI API.
    """
    prompt = (
        "Break down the following instructions into extremely basic, single-sentence steps. "
        "Each step should describe one simple action (for example, 'click on the search bar', "
        "'type in couch', or 'select the first search suggestion').\n\n"
        f"Instructions: {instructions}\n\nSteps:"
    )
    headers = {
         "Content-Type": "application/json",
         "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    payload = {
         "model": "gpt-4o-mini",
         "messages": [
              {"role": "user", "content": prompt}
         ],
         "max_tokens": 200,
         "temperature": 0.2
    }
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        output = result['choices'][0]['message']['content'].strip()
        steps = [line.strip(" -") for line in output.split("\n") if line.strip()]
        logging.info(f"Extracted {len(steps)} basic step(s) from instructions.")
        for idx, step in enumerate(steps, start=1):
            logging.info(f"Step {idx}: {step}")
        return steps
    except Exception as e:
        logging.error(f"Error getting basic steps: {str(e)}")
        return []

def get_selenium_code(driver, user_command):
    """Convert natural language command to Selenium code using GPT-4o-mini with visual context"""
    logging.info("Taking screenshot for visual context...")
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    temp_screenshot = os.path.join(outputs_dir, f'temp_screenshot_{timestamp}.png')
    driver.save_screenshot(temp_screenshot)
    with open(temp_screenshot, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode('utf-8')
    os.remove(temp_screenshot)
    logging.info("Converting your command to Selenium code...")
    
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
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "text", "text": f"Looking at this screenshot of the current page, generate ONLY the specific Selenium action code to: {user_command}"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]}
        ],
        "max_tokens": 500,
        "temperature": 0.3
    }
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        code = result['choices'][0]['message']['content'].strip()
        cleaned_code = clean_code(code)
        logging.info("Generated Selenium code:")
        logging.info(cleaned_code)
        return cleaned_code
    except Exception as e:
        logging.error(f"Error getting Selenium code: {str(e)}")
        return None

def execute_selenium_code(driver, code):
    """Safely execute the generated Selenium code with enhanced popup handling"""
    try:
        # Check for and close any popups before executing the code
        if close_popup_if_present(driver):
            logging.info("Closed popup before executing action")
            time.sleep(1)  # Wait for popup animation to complete
        
        locals_dict = {
            'driver': driver,
            'By': By,
            'Keys': Keys,
            'WebDriverWait': WebDriverWait,
            'EC': EC,
            'time': time,
            'try_multiple_selectors': try_multiple_selectors
        }
        
        # Execute the code
        exec(code, globals(), locals_dict)
        time.sleep(1)
        
        # Check for popups again after execution
        if close_popup_if_present(driver):
            logging.info("Closed popup after executing action")
            time.sleep(1)
        
        return True
        
    except Exception as e:
        logging.error(f"Error executing Selenium code: {str(e)}")
        if hasattr(e, 'msg'):
            logging.error(f"Detailed error: {e.msg}")
        
        # Try to close popup if the error might be related to element overlap
        if "element click intercepted" in str(e).lower() or "element not interactable" in str(e).lower():
            logging.info("Detected possible popup interference, attempting to close...")
            if close_popup_if_present(driver):
                logging.info("Popup closed after error, retrying action...")
                # Retry the action once
                try:
                    exec(code, globals(), locals_dict)
                    return True
                except:
                    pass
        return False

def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def analyze_image_with_gpt4(image_path):
    logging.info("Analyzing image with GPT-4o-mini...")
    base64_image = encode_image_to_base64(image_path)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": "Describe in a few sentences what you see in this image."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]}
        ],
        "max_tokens": 300
    }
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        description = result['choices'][0]['message']['content']
        logging.info("GPT-4o-mini's Description:")
        logging.info(description)
    except requests.exceptions.RequestException as e:
        logging.error(f"Error calling OpenAI API: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logging.error(f"API Response: {e.response.text}")
        elif 'response' in locals():
            logging.error(f"API Response: {response.text}")

def handle_bot_detection(driver):
    """Handle the 'Press & Hold' bot detection if it appears"""
    try:
        press_hold_button = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'Press & Hold')]"))
        )
        logging.info("Bot detection found. Attempting to verify...")
        actions = ActionChains(driver)
        actions.move_to_element(press_hold_button)
        actions.click_and_hold()
        actions.pause(3)
        actions.release()
        actions.perform()
        time.sleep(4)
        return True
    except Exception as e:
        logging.info(f"No bot detection found or error handling it: {str(e)}")
        return False

# Create outputs directory if it doesn't exist
outputs_dir = 'outputs'
if not os.path.exists(outputs_dir):
    os.makedirs(outputs_dir)
    logging.info(f"Created outputs directory at: {os.path.abspath(outputs_dir)}")

try:
    options = uc.ChromeOptions()
    driver = uc.Chrome(options=options, version_main=135)
    driver.maximize_window()
    
    logging.info("Navigating to Wayfair...")
    driver.get('https://www.wayfair.com')
    time.sleep(5)
    
    handle_bot_detection(driver)

    while True:
        logging.info("\nPlease enter a paragraph of instructions to execute on Wayfair (or type 'quit' to exit):")
        user_paragraph = input("> ").strip()
        if user_paragraph.lower() == 'quit':
            break
        
        # Break the paragraph into extremely basic steps
        steps = get_basic_steps(user_paragraph)
        if not steps:
            logging.error("No basic steps were extracted. Please try rephrasing your instructions.")
            continue
        
        for idx, step in enumerate(steps, start=1):
            logging.info(f"Executing Step {idx}/{len(steps)}: {step}")
            
            # Check for bot detection before each step
            handle_bot_detection(driver)
            
            step_code = get_selenium_code(driver, step)
            if step_code:
                success = execute_selenium_code(driver, step_code)
                if success:
                    logging.info(f"Step {idx} executed successfully!")
                    time.sleep(2)
                    
                    # After each step, check if a popup is present.
                    if close_popup_if_present(driver):
                        logging.info(f"A popup was detected and closed after step {idx}.")
                    else:
                        logging.info(f"No popup to close after step {idx}.")
                    
                    handle_bot_detection(driver)
                else:
                    logging.error(f"Step {idx} execution failed. Aborting further steps.")
                    break
            else:
                logging.error(f"Failed to generate Selenium code for step {idx}: {step}")
                break

except Exception as e:
    logging.error(f"An error occurred: {str(e)}")
    import traceback
    logging.error("Full error trace:")
    logging.error(traceback.format_exc())
finally:
    if 'driver' in locals():
        logging.info("Closing browser...")
        driver.quit()
            
