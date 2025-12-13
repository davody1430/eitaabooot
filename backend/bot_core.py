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
    text = text.replace('ي', 'ی').replace('ك', 'ک')
    return unicodedata.normalize('NFKC', text)

def extract_usernames_from_text(text):
    if not text: return []
    return re.findall(r'@[\w\d_]+', text)

def convert_phone_number_format(phone_number_str):
    if phone_number_str and phone_number_str.startswith('09') and len(phone_number_str) == 11 and phone_number_str.isdigit():
        return '98' + phone_number_str[1:]
    return phone_number_str

class EitaaBot:
    def __init__(self, min_delay=2.0, max_delay=5.0, session_file='session.json', headless=True, log_queue=None):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.session_file = session_file
        self.headless = headless
        self.log_queue = log_queue
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

    def _log(self, message):
        if self.log_queue:
            self.log_queue.put(message)
        else:
            print(message)

    def _wait_random_delay(self):
        delay = random.uniform(self.min_delay, self.max_delay)
        self._log(f"Waiting for {delay:.2f} seconds...")
        time.sleep(delay)

    def login(self, phone_number=None):
        try:
            self._log("Initializing Playwright...")
            if not self.playwright:
                self.playwright = sync_playwright().start()
                self.browser = self.playwright.chromium.launch(headless=self.headless)
                
                storage_state = self.session_file if os.path.exists(self.session_file) else None
                self._log(f"Loading session from: {self.session_file if storage_state else 'None'}")
                self.context = self.browser.new_context(storage_state=storage_state)
                self.page = self.context.new_page()

                self._log(f"Navigating to {self.selectors['login_page']}...")
                self.page.goto(self.selectors['login_page'], timeout=60000)

            self._log("Checking login status...")
            try:
                self.page.wait_for_selector(self.selectors['search_box'], timeout=10000)
                self.is_logged_in = True
                self._log("Already logged in.")
                return "already_logged_in"
            except PlaywrightTimeoutError:
                self._log("Not logged in. Proceeding with login flow.")
                pass

            if not phone_number:
                self._log("Phone number is required but not provided.")
                return "phone_number_required"

            self._log(f"Entering phone number: {phone_number}")
            phone_input = self.page.locator(self.selectors['phone_input'])
            phone_input.wait_for(timeout=30000)
            phone_input.fill(phone_number)
            phone_input.press('Enter')
            
            self._log("Waiting for verification code input field...")
            # ما منتظر فیلد کد می‌مانیم تا مطمئن شویم صفحه بارگذاری شده
            # اما کاربر خودش کد را وارد می‌کند
            code_input_visible = self.page.locator(self.selectors['code_input'])
            code_input_visible.wait_for(timeout=30000)
            
            self._log("Ready for manual code entry.")
            return "waiting_for_code"

        except Exception as e:
            self._log(f"ERROR during login: {e}")
            if self.page:
                self.page.screenshot(path='login_error.png')
            return f"error: {e}"

    def submit_code(self, code):
        try:
            if not self.page:
                self._log("خطا: صفحه مرورگر مقداردهی اولیه نشده است.")
                return "error: page_not_initialized"

            self._log("در حال تأیید وضعیت ورود...")
            self._log("این تابع پس از آن فراخوانی شده که شما کد را دستی وارد کرده و دکمه تأیید را در برنامه زده‌اید.")

            # با یک زمان کوتاه، بررسی می‌کنیم که آیا ورود موفقیت‌آمیز بوده یا خیر
            # چون کاربر باید قبلاً به صورت دستی وارد شده باشد
            self.page.wait_for_selector(self.selectors['search_box'], timeout=15000) # زمان انتظار را کمی بیشتر کردم

            self.is_logged_in = True
            self._log("✅ ورود موفقیت‌آمیز تأیید شد. در حال ذخیره نشست...")

            storage = self.context.storage_state()
            with open(self.session_file, 'w') as f:
                json.dump(storage, f)

            return "login_successful"

        except PlaywrightTimeoutError:
            self._log("❌ خطا: ورود موفقیت‌آمیز تأیید نشد. لطفاً ابتدا در پنجره مرورگر باز شده وارد شوید و سپس دکمه تأیید را بزنید.")
            if self.page:
                self.page.screenshot(path='submit_code_verification_error.png')
            return "error: login_not_verified"
        except Exception as e:
            self._log(f"❌ خطا در هنگام تأیید ورود: {e}")
            if self.page:
                self.page.screenshot(path='submit_code_error.png')
            return f"error: {e}"

    def send_direct_message(self, username, message):
        if not self.is_logged_in:
            self._log("Cannot send message, not logged in.")
            return False
        
        try:
            self._log(f"Searching for user: {username}")
            search_box = self.page.locator(self.selectors['search_box'])
            search_box.fill(username)
            self._wait_random_delay()

            self._log(f"Clicking on user '{username}' in chat list.")
            user_in_list = self.page.locator(f"{self.selectors['chat_list_item']}:has-text('{username.lstrip('@')}')")
            user_in_list.first.click()

            self._log("Typing message...")
            message_input = self.page.locator(self.selectors['message_input'])
            message_input.fill(message)
            message_input.press('Enter')

            self._log(f"Message sent successfully to {username}.")
            self._wait_random_delay()
            return True
        except Exception as e:
            self._log(f"ERROR sending message to {username}: {e}")
            if self.page:
                self.page.screenshot(path=f'send_message_error_{username}.png')
            return False
            
    def close(self):
        self._log("Closing browser.")
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def read_usernames_from_excel(self, excel_path):
        try:
            self._log(f"Reading usernames from Excel file: {excel_path}")
            df = pd.read_excel(excel_path, header=None)
            usernames = []
            
            for col in df.columns:
                for value in df[col].dropna():
                    if isinstance(value, str) and value.startswith('@'):
                        usernames.append(value.strip())
            
            self._log(f"Found {len(usernames)} unique usernames.")
            return list(set(usernames))
        except Exception as e:
            self._log(f"ERROR reading Excel file: {e}")
            return []
    
    def extract_mentions_from_group(self, group_name, message_prefix):
        if not self.is_logged_in:
            self._log("امکان استخراج نام‌های کاربری وجود ندارد، لطفاً ابتدا وارد شوید.")
            return []

        try:
            self._log(f"در حال جستجو برای گروه: {group_name}")
            search_box = self.page.locator(self.selectors['search_box'])
            search_box.fill(group_name)
            self._wait_random_delay()

            self._log(f"در حال کلیک روی گروه '{group_name}' در لیست گفتگوها.")
            group_in_list = self.page.locator(f"li.chatlist-chat:has-text('{group_name}')")
            group_in_list.first.click()

            self._log("در حال انتظار برای بارگذاری کامل صفحه گروه...")
            self.page.wait_for_timeout(5000)
            self.page.wait_for_load_state('networkidle')
            self.page.screenshot(path='group_page_after_load.png')

            self._log(f"در حال جستجو برای پیام با پیشوند: '{message_prefix}'")
            normalized_prefix = normalize_persian_text(message_prefix)

            # حلقه اسکرول برای بارگذاری تاریخچه
            for _ in range(5): # 5 بار اسکرول به بالا
                self.page.evaluate("document.querySelector('.scrollable-y').scrollTop = 0")
                self.page.wait_for_timeout(2000)

            # از انتخابگر جدید برای حباب‌های پیام استفاده می‌کنیم
            message_bubbles = self.page.locator('div.bubble .message')

            count = message_bubbles.count()
            self._log(f"تعداد {count} حباب پیام پیدا شد. در حال بررسی برای یافتن پیام مورد نظر...")
            for i in range(count - 1, -1, -1):
                bubble = message_bubbles.nth(i)
                text_content = bubble.inner_text()

                if normalize_persian_text(text_content).startswith(normalized_prefix):
                    self._log("پیام مورد نظر پیدا شد. در حال استخراج منشن‌ها...")
                    # به جای استخراج از متن، مستقیماً تگ‌های a.mention را پیدا می‌کنیم
                    mentions = bubble.locator('a.mention').all()
                    usernames = [mention.inner_text() for mention in mentions]

                    self._log(f"تعداد {len(usernames)} نام کاربری استخراج شد: {', '.join(usernames)}")
                    return usernames

            self._log("پیامی با پیشوند مشخص شده پیدا نشد.")
            return []

        except Exception as e:
            self._log(f"خطا در استخراج نام‌های کاربری از گروه: {e}")
            if self.page:
                self.page.screenshot(path='extract_mentions_error.png')
            return []

    def confirm_login(self):
        return self.is_logged_in
