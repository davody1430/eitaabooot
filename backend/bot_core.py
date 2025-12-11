# backend/bot_core.py - نسخه نهایی با Playwright و Pandas
import os
import random
import re
import time
import json
import unicodedata
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# توابع کمکی
def normalize_persian_text(text):
    if text is None: return None
    text = text.replace('\u064A', '\u06CC').replace('\u0649', '\u06CC')
    text = text.replace('\u0643', '\u06A9')
    text = text.replace('\u0629', '\u0647')
    return unicodedata.normalize('NFKC', text)

def extract_usernames_from_text(text):
    if not text: return []
    return re.findall(r'@[\w\d_]+', text)

def convert_phone_number_format(phone_number_str):
    if phone_number_str and phone_number_str.startswith('09') and len(phone_number_str) == 11 and phone_number_str.isdigit():
        return '98' + phone_number_str[1:]
    return phone_number_str

class EitaaBot:
    def __init__(self, min_delay=2.0, max_delay=5.0, session_file='session.json', headless=True):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.session_file = session_file
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.is_logged_in = False
        
        self.selectors = {
            'login_page': 'https://web.eitaa.com/',
            'phone_input': 'div.input-field-phone div.input-field-input[contenteditable="true"]',
            'code_input': 'input[type="tel"]',
            'search_box': 'input.input-search-input[placeholder="جستجو"]',
            'message_input': 'div.input-message-input[contenteditable="true"]',
            'send_button': 'button.btn-send',
            'chat_list_item': 'li.chatlist-chat',
            'message_bubble': 'div.bubble',
            'message_text': 'div.message',
        }

    def _wait_random_delay(self):
        time.sleep(random.uniform(self.min_delay, self.max_delay))

    def login(self, phone_number=None):
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=self.headless)
            
            storage_state = self.session_file if os.path.exists(self.session_file) else None
            self.context = self.browser.new_context(storage_state=storage_state)
            self.page = self.context.new_page()

            self.page.goto(self.selectors['login_page'], timeout=60000)

            try:
                self.page.wait_for_selector(self.selectors['search_box'], timeout=10000)
                self.is_logged_in = True
                return "already_logged_in"
            except PlaywrightTimeoutError:
                pass

            if not phone_number:
                return "phone_number_required"

            phone_input = self.page.locator(self.selectors['phone_input'])
            phone_input.wait_for(timeout=30000)
            phone_input.fill(phone_number)
            phone_input.press('Enter')
            
            code_input = self.page.locator(self.selectors['code_input'])
            code_input.wait_for(timeout=30000)
            
            return "waiting_for_code"

        except Exception as e:
            if self.page:
                self.page.screenshot(path='login_error.png')
            return f"error: {e}"

    def submit_code(self, code):
        try:
            if not self.page:
                return "error: page_not_initialized"

            code_input = self.page.locator(self.selectors['code_input'])
            code_input.fill(code)

            # Take a screenshot right after entering the code to see the result
            self.page.screenshot(path='login_attempt.png')

            self.page.wait_for_selector(self.selectors['search_box'], timeout=60000)
            
            self.is_logged_in = True
            
            storage = self.context.storage_state()
            with open(self.session_file, 'w') as f:
                json.dump(storage, f)
            
            return "login_successful"
        
        except Exception as e:
            if self.page:
                self.page.screenshot(path='submit_code_error.png')
            return f"error: {e}"

    def send_direct_message(self, username, message):
        if not self.is_logged_in:
            return False
        
        try:
            search_box = self.page.locator(self.selectors['search_box'])
            search_box.fill(username)
            self._wait_random_delay()

            user_in_list = self.page.locator(f"{self.selectors['chat_list_item']}:has-text('{username.lstrip('@')}')")
            user_in_list.first.click()

            message_input = self.page.locator(self.selectors['message_input'])
            message_input.fill(message)
            message_input.press('Enter')

            self._wait_random_delay()
            return True
        except Exception:
            if self.page:
                self.page.screenshot(path=f'send_message_error_{username}.png')
            return False
            
    def close(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def read_usernames_from_excel(self, excel_path):
        try:
            df = pd.read_excel(excel_path, header=None)
            usernames = []
            
            for col in df.columns:
                for value in df[col].dropna():
                    if isinstance(value, str) and value.startswith('@'):
                        usernames.append(value.strip())
            
            return list(set(usernames))
        except Exception as e:
            print(f"خطا در خواندن فایل اکسل: {e}")
            return []
    
    def extract_usernames_from_group_message(self, group_name, message_prefix):
        if not self.is_logged_in:
            return []

        try:
            # 1. Search for the group
            search_box = self.page.locator(self.selectors['search_box'])
            search_box.fill(group_name)
            self._wait_random_delay()

            # 2. Click on the group in the chat list
            group_in_list = self.page.locator(f"{self.selectors['chat_list_item']}:has-text('{group_name}')")
            group_in_list.first.click()
            self.page.wait_for_load_state('networkidle')

            # 3. Find the message with the prefix
            normalized_prefix = normalize_persian_text(message_prefix)
            message_bubbles = self.page.locator(self.selectors['message_bubble'])

            # Iterate through recent messages to find the one with the prefix
            # This might need adjustment based on how many messages are loaded at once
            for i in range(message_bubbles.count() - 1, -1, -1):
                bubble = message_bubbles.nth(i)
                message_text_element = bubble.locator(self.selectors['message_text'])
                if message_text_element.count() > 0:
                    text_content = message_text_element.inner_text()
                    if normalize_persian_text(text_content).startswith(normalized_prefix):
                        # Found the message, extract usernames
                        return extract_usernames_from_text(text_content)

            # If the loop finishes without finding the message
            return []

        except Exception as e:
            print(f"Error extracting usernames from group: {e}")
            if self.page:
                self.page.screenshot(path='extract_usernames_error.png')
            return []

    def confirm_login(self):
        return self.is_logged_in
