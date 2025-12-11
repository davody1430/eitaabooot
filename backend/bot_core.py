# backend/bot_core.py
import os
import json
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

def convert_phone_number_format(phone_number_str):
    if phone_number_str and phone_number_str.startswith('09') and len(phone_number_str) == 11 and phone_number_str.isdigit():
        return '98' + phone_number_str[1:]
    return phone_number_str

class EitaaBot:
    def __init__(self, session_file='session.json'):
        self.session_file = session_file
        self.selectors = {
            'login_page': 'https://web.eitaa.com/',
            'phone_input': 'div.input-field-phone div.input-field-input[contenteditable="true"]',
            'search_box': 'input.input-search-input[placeholder="جستجو"]',
        }

    def launch_and_wait_for_login(self, phone_number, timeout=300000): # 5 minutes timeout
        with sync_playwright() as p:
            # Always launch in non-headless mode for manual intervention
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()

            try:
                page.goto(self.selectors['login_page'], timeout=60000)

                # Check if already logged in from a previous session file
                try:
                    page.wait_for_selector(self.selectors['search_box'], timeout=5000)
                    # If selector is found, we are already logged in. Save state and exit.
                    storage = context.storage_state()
                    with open(self.session_file, 'w') as f:
                        json.dump(storage, f)
                    browser.close()
                    return "already_logged_in"
                except PlaywrightTimeoutError:
                    # Not logged in, proceed with phone number entry
                    pass

                phone_input = page.locator(self.selectors['phone_input'])
                phone_input.wait_for(timeout=30000)
                phone_input.fill(phone_number)
                phone_input.press('Enter')

                # Now, we wait for the user to manually enter the code.
                # The success condition is the appearance of the main chat search box.
                page.wait_for_selector(self.selectors['search_box'], timeout=timeout)

                # If we reach here, it means the user has successfully logged in.
                storage = context.storage_state()
                with open(self.session_file, 'w') as f:
                    json.dump(storage, f)

                browser.close()
                return "login_successful"

            except PlaywrightTimeoutError:
                browser.close()
                return "timed_out"
            except Exception as e:
                browser.close()
                return f"error: {str(e)}"

    # Placeholder for other functions that will use the saved session
    def is_logged_in(self):
        return os.path.exists(self.session_file)

    def send_messages(self, usernames, message):
        if not self.is_logged_in():
            return "error: not_logged_in"

        # This part can be re-implemented similarly, using the saved session file
        # For now, we focus on the login process
        pass
