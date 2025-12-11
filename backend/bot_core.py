# backend/bot_core.py
import os
import asyncio
import json
import pandas as pd
import unicodedata
import re
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

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
        }

    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        storage_state = self.session_file if os.path.exists(self.session_file) else None
        self.context = await self.browser.new_context(storage_state=storage_state)
        self.page = await self.context.new_page()

    async def login(self, phone_number):
        if not self.page:
            await self.start()

        await self.page.goto(self.selectors['login_page'], timeout=60000)

        try:
            await self.page.wait_for_selector(self.selectors['search_box'], timeout=10000)
            self.is_logged_in = True
            return "already_logged_in"
        except PlaywrightTimeoutError:
            pass

        phone_input = self.page.locator(self.selectors['phone_input'])
        await phone_input.wait_for(timeout=30000)
        await phone_input.fill(phone_number)
        await phone_input.press('Enter')

        code_input = self.page.locator(self.selectors['code_input'])
        await code_input.wait_for(timeout=30000)

        return "waiting_for_code"

    async def submit_code(self, code):
        if not self.page:
            return "error: page_not_initialized"

        code_input = self.page.locator(self.selectors['code_input'])
        await code_input.fill(code)

        await self.page.wait_for_selector(self.selectors['search_box'], timeout=60000)
        
        self.is_logged_in = True

        storage = await self.context.storage_state()
        with open(self.session_file, 'w') as f:
            json.dump(storage, f)

        return "login_successful"

    async def send_direct_message(self, username, message):
        if not self.is_logged_in:
            return False
        
        try:
            search_box = self.page.locator(self.selectors['search_box'])
            await search_box.fill(username)
            await self.page.wait_for_timeout(2000)

            user_in_list = self.page.locator(f"li.chatlist-chat:has-text('{username.lstrip('@')}')")
            await user_in_list.first.click()

            message_input = self.page.locator(self.selectors['message_input'])
            await message_input.fill(message)
            await message_input.press('Enter')

            return True
        except Exception:
            return False

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
            return []

    async def extract_usernames_from_group_message(self, group_name, message_prefix):
        if not self.is_logged_in:
            return []

        try:
            search_box = self.page.locator(self.selectors['search_box'])
            await search_box.fill(group_name)
            await self.page.wait_for_timeout(2000)

            group_in_list = self.page.locator(f"li.chatlist-chat:has-text('{group_name}')")
            await group_in_list.first.click()
            await self.page.wait_for_load_state('networkidle')

            message_bubbles = self.page.locator('div.bubble')
            count = await message_bubbles.count()
            for i in range(count - 1, -1, -1):
                bubble = message_bubbles.nth(i)
                message_text_element = bubble.locator('div.message')
                if await message_text_element.count() > 0:
                    text_content = await message_text_element.inner_text()
                    if text_content.startswith(message_prefix):
                        return re.findall(r'@[\w\d_]+', text_content)
            return []
        except Exception as e:
            return []

    async def close(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
