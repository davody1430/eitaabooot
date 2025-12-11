# backend/bot_core.py
import os
import json
import pandas as pd
import unicodedata
import re
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

def normalize_persian_text(text):
    if text is None: return None
    text = text.replace('\u064A', '\u06CC').replace('\u0649', '\u06CC')
    text = text.replace('\u0643', '\u06A9')
    text = text.replace('\u0629', '\u0647')
    return unicodedata.normalize('NFKC', text)

def convert_phone_number_format(phone_number_str):
    if phone_number_str and phone_number_str.startswith('09') and len(phone_number_str) == 11 and phone_number_str.isdigit():
        return '98' + phone_number_str[1:]
    return phone_number_str

class EitaaBot:
    def __init__(self, session_file='session.json', headless=True):
        self.session_file = session_file
        self.headless = headless
        self.is_logged_in = self.check_initial_login()
        self.selectors = {
            'login_page': 'https://web.eitaa.com/',
            'phone_input': 'div.input-field-phone div.input-field-input[contenteditable="true"]',
            'code_input': 'input[type="tel"]',
            'search_box': 'input.input-search-input[placeholder="جستجو"]',
            'message_input': 'div.input-message-input[contenteditable="true"]',
            'chat_list_item': 'li.chatlist-chat',
        }

    def check_initial_login(self):
        if not os.path.exists(self.session_file):
            return False
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(storage_state=self.session_file)
                page = context.new_page()
                page.goto(self.selectors['login_page'], timeout=30000)
                page.wait_for_selector(self.selectors['search_box'], timeout=5000)
                browser.close()
                return True
        except PlaywrightTimeoutError:
            return False
        except Exception:
            return False

    def login(self, phone_number):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context()
            page = context.new_page()

            page.goto(self.selectors['login_page'], timeout=60000)

            phone_input = page.locator(self.selectors['phone_input'])
            phone_input.wait_for(timeout=30000)
            phone_input.fill(phone_number)
            phone_input.press('Enter')

            page.locator(self.selectors['code_input']).wait_for(timeout=30000)

            storage = context.storage_state()
            with open(self.session_file, 'w') as f:
                json.dump(storage, f)

            browser.close()
        return "waiting_for_code"

    def submit_code(self, code):
        if not os.path.exists(self.session_file):
            return "error: session_file_not_found"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(storage_state=self.session_file)
            page = context.new_page()

            page.goto(self.selectors['login_page'], timeout=60000)

            code_input = page.locator(self.selectors['code_input'])
            code_input.fill(code)

            page.wait_for_selector(self.selectors['search_box'], timeout=60000)
            self.is_logged_in = True

            storage = context.storage_state()
            with open(self.session_file, 'w') as f:
                json.dump(storage, f)

            browser.close()
        return "login_successful"

    def send_direct_message(self, username, message):
        if not self.is_logged_in: return False
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(storage_state=self.session_file)
            page = context.new_page()
            page.goto(self.selectors['login_page'], timeout=60000)

            try:
                search_box = page.locator(self.selectors['search_box'])
                search_box.fill(username)
                page.wait_for_timeout(2000)

                user_in_list = page.locator(f"li.chatlist-chat:has-text('{username.lstrip('@')}')")
                user_in_list.first.click()

                message_input = page.locator(self.selectors['message_input'])
                message_input.fill(message)
                message_input.press('Enter')

                browser.close()
                return True
            except Exception:
                browser.close()
                return False

    def send_bulk_direct_messages(self, usernames, message):
        if not self.is_logged_in: return False
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(storage_state=self.session_file)
            page = context.new_page()
            page.goto(self.selectors['login_page'], timeout=60000)

            success_count = 0
            for username in usernames:
                try:
                    search_box = page.locator(self.selectors['search_box'])
                    search_box.fill(username)
                    page.wait_for_timeout(2000)

                    user_in_list = page.locator(f"li.chatlist-chat:has-text('{username.lstrip('@')}')")
                    user_in_list.first.click()

                    message_input = page.locator(self.selectors['message_input'])
                    message_input.fill(message)
                    message_input.press('Enter')
                    success_count += 1
                except Exception:
                    continue # Continue with the next user if one fails

            browser.close()
            return success_count

    def read_usernames_from_excel(self, excel_path):
        try:
            df = pd.read_excel(excel_path, header=None)
            return [str(u).strip() for u in df[0] if str(u).strip().startswith('@')]
        except Exception:
            return []

    def extract_usernames_from_group_message(self, group_name, message_prefix):
        if not self.is_logged_in: return []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(storage_state=self.session_file)
            page = context.new_page()
            page.goto(self.selectors['login_page'], timeout=60000)

            try:
                search_box = page.locator(self.selectors['search_box'])
                search_box.fill(group_name)
                page.wait_for_timeout(2000)

                group_in_list = page.locator(f"li.chatlist-chat:has-text('{group_name}')")
                group_in_list.first.click()
                page.wait_for_load_state('networkidle')

                message_bubbles = page.locator('div.bubble')
                count = message_bubbles.count()
                for i in range(count - 1, -1, -1):
                    bubble = message_bubbles.nth(i)
                    message_text_element = bubble.locator('div.message')
                    if message_text_element.count() > 0:
                        text_content = message_text_element.inner_text()
                        if text_content.startswith(message_prefix):
                            browser.close()
                            return re.findall(r'@[\w\d_]+', text_content)

                browser.close()
                return []
            except Exception:
                browser.close()
                return []
