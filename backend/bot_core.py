# backend/bot_core.py
import os
import json
import pandas as pd
import unicodedata
import re
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Helper functions (remains the same)
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
        self.selectors = {
            'login_page': 'https://web.eitaa.com/',
            'phone_input': 'div.input-field-phone div.input-field-input[contenteditable="true"]',
            'code_input': 'input[type="tel"]',
            'search_box': 'input.input-search-input[placeholder="جستجو"]',
            'message_input': 'div.input-message-input[contenteditable="true"]',
        }
        self.is_logged_in = self.check_initial_login()

    def _get_browser_context(self, playwright_instance, use_session=True):
        storage_state = self.session_file if use_session and os.path.exists(self.session_file) else None
        return playwright_instance.chromium.launch(headless=self.headless), storage_state

    def check_initial_login(self):
        try:
            with sync_playwright() as p:
                browser, storage = self._get_browser_context(p)
                if not storage: return False
                context = browser.new_context(storage_state=storage)
                page = context.new_page()
                page.goto(self.selectors['login_page'], timeout=15000)
                page.wait_for_selector(self.selectors['search_box'], timeout=5000)
                browser.close()
                return True
        except Exception:
            return False

    def login(self, phone_number):
        try:
            with sync_playwright() as p:
                browser, _ = self._get_browser_context(p, use_session=False)
                context = browser.new_context()
                page = context.new_page()

                page.goto(self.selectors['login_page'], timeout=60000)
                page.screenshot(path='screenshots/login_01_page_loaded.png')

                phone_input = page.locator(self.selectors['phone_input'])
                phone_input.wait_for(timeout=30000)
                phone_input.fill(phone_number)
                page.screenshot(path='screenshots/login_02_phone_entered.png')

                phone_input.press('Enter')
                page.locator(self.selectors['code_input']).wait_for(timeout=30000)
                page.screenshot(path='screenshots/login_03_code_prompt.png')

                storage = context.storage_state()
                with open(self.session_file, 'w') as f:
                    json.dump(storage, f)

                browser.close()
            return "waiting_for_code", None
        except Exception as e:
            return "error", str(e)

    def submit_code(self, code):
        try:
            with sync_playwright() as p:
                browser, storage = self._get_browser_context(p)
                if not storage: return "error", "Session file not found."

                context = browser.new_context(storage_state=storage)
                page = context.new_page()

                page.goto(self.selectors['login_page'], timeout=60000)
                page.screenshot(path='screenshots/submit_01_reloaded_page.png')

                code_input = page.locator(self.selectors['code_input'])
                code_input.fill(code)
                page.screenshot(path='screenshots/submit_02_code_entered.png')

                # This is the critical moment. We wait for the search box to appear.
                page.wait_for_selector(self.selectors['search_box'], timeout=60000)
                page.screenshot(path='screenshots/submit_03_login_successful.png')

                self.is_logged_in = True
                storage = context.storage_state()
                with open(self.session_file, 'w') as f:
                    json.dump(storage, f)

                browser.close()
            return "login_successful", None
        except Exception as e:
            # Take a screenshot right when the error happens
            error_screenshot = f'screenshots/submit_error_{int(time.time())}.png'
            try:
                # Need a new browser instance to take the screenshot if the old one crashed
                 with sync_playwright() as p_err:
                    browser_err, storage_err = self._get_browser_context(p_err)
                    if storage_err:
                        context_err = browser_err.new_context(storage_state=storage_err)
                        page_err = context_err.new_page()
                        page_err.goto(self.selectors['login_page'], timeout=30000)
                        page_err.screenshot(path=error_screenshot)
                        browser_err.close()
            except:
                pass # If screenshot fails, we still return the error
            return "error", str(e)

    # Other methods remain unchanged for now
    def read_usernames_from_excel(self, excel_path):
        # ... (implementation)
        pass

    def send_bulk_direct_messages(self, usernames, message):
        # ... (implementation)
        pass
