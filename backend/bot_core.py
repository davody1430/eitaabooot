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
            code_input = self.page.locator(self.selectors['code_input'])
            code_input.wait_for(timeout=30000)
            
            self._log("Ready to receive verification code.")
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
            self._log(f"❌ عدم امکان ارسال پیام به {username}: کاربر وارد نشده است.")
            return False
        
        clean_username = username.lstrip('@')

        try:
            self._log(f"--- شروع ارسال پیام به {username} ---")

            # --- مرحله ۱: پاکسازی جستجو و جستجوی کاربر ---
            try:
                self._log(f"۱.۱: در حال پیدا کردن و پاک کردن کادر جستجو...")
                search_box = self.page.locator(self.selectors['search_box'])
                search_box.wait_for(timeout=10000)
                search_box.click(timeout=5000)
                search_box.fill("")
                self.page.wait_for_timeout(500)

                self._log(f"۱.۲: در حال وارد کردن نام کاربری '{username}'...")
                search_box.fill(username)
                self.page.wait_for_timeout(1500) # زمان انتظار برای ظاهر شدن نتایج
                self._log("۱.۳: نام کاربری با موفقیت وارد شد.")

            except Exception as e:
                self._log(f"❌ خطا در مرحله جستجوی کاربر '{username}': {e}")
                self.page.screenshot(path=f'error_search_{clean_username}.png')
                return False

            # --- مرحله ۲: انتخاب دقیق کاربر از لیست نتایج ---
            try:
                self._log(f"۲.۱: در حال جستجوی '{clean_username}' در لیست نتایج...")
                # انتخابگر دقیق‌تر برای پیدا کردن آیتم چت کاربر
                user_item_selector = f'li.rp.chatlist-chat:has(span.peer-title:has-text("{clean_username}"))'
                user_chat_element = self.page.locator(user_item_selector).first
                user_chat_element.wait_for(state='attached', timeout=15000)

                self._log(f"۲.۲: '{clean_username}' در لیست پیدا شد. در حال اسکرول و کلیک...")
                try:
                    user_chat_element.scroll_into_view_if_needed(timeout=5000)
                except Exception as scroll_err:
                    self._log(f"   (هشدار جزئی) اسکرول به کاربر با خطا مواجه شد: {scroll_err}")

                user_chat_element.wait_for(state='visible', timeout=20000)
                user_chat_element.click(timeout=10000)
                self._log(f"۲.۳: با موفقیت روی '{clean_username}' کلیک شد.")

            except PlaywrightTimeoutError:
                self._log(f"❌ خطا: کاربر '{username}' پس از جستجو در لیست نتایج پیدا نشد (Timeout).")
                self.page.screenshot(path=f'error_user_not_found_{clean_username}.png')
                return False
            except Exception as e:
                self._log(f"❌ خطا در مرحله انتخاب کاربر '{username}' از لیست: {e}")
                self.page.screenshot(path=f'error_clicking_user_{clean_username}.png')
                return False

            # --- مرحله ۳: ارسال پیام ---
            try:
                self._log("۳.۱: در حال پیدا کردن کادر ورودی پیام...")
                # انتخابگر دقیق‌تر برای کادر پیام که ویرایش‌پذیر است و fake نیست
                dm_message_input_selector = 'div.input-message-input[contenteditable="true"]:not(.input-field-input-fake)'
                message_input = self.page.locator(dm_message_input_selector)
                message_input.wait_for(state='visible', timeout=15000)

                self._log("۳.۲: در حال نوشتن پیام...")
                message_input.fill(message)
                self.page.wait_for_timeout(500)

                self._log("۳.۳: در حال فشردن کلید Enter برای ارسال...")
                message_input.press('Enter')
                self._log(f"✅ پیام با موفقیت برای {username} ارسال شد.")
                self._wait_random_delay()

            except Exception as e:
                self._log(f"❌ خطا در مرحله ارسال پیام به '{username}': {e}")
                self.page.screenshot(path=f'error_sending_message_{clean_username}.png')
                return False

            self._log(f"--- پایان عملیات ارسال برای {username} ---")
            return True

        except Exception as e:
            self._log(f"❌ خطای کلی و غیرمنتظره در تابع send_direct_message برای '{username}': {e}")
            if self.page:
                self.page.screenshot(path=f'error_general_send_{clean_username}.png')
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
            self.page.wait_for_timeout(2000)

            self._log("در حال کلیک روی دکمه جستجو در گروه...")
            search_button_selector = "#column-center > div > div > div.sidebar-header.topbar > div.chat-utils > button.btn-icon.tgico-search.rp"
            self.page.locator(search_button_selector).click()
            self.page.wait_for_timeout(1000)

            self._log(f"در حال وارد کردن پیشوند پیام: '{message_prefix}'")
            search_input_selector = "#search-private-container .input-search-input"
            self.page.locator(search_input_selector).fill(message_prefix)
            self.page.wait_for_timeout(3000)

            self._log("در حال کلیک روی اولین نتیجه جستجو...")
            search_result_selector = "#search-private-container > div.sidebar-content > div > div > div > ul > li"
            self.page.locator(search_result_selector).first.click()
            self.page.wait_for_timeout(3000)

            self._log("در حال استخراج منشن‌ها از پیام یافت شده...")
            message_selector = "div.bubble-content div.message"
            message_elements = self.page.locator(message_selector).all()

            # Log all message bubble HTMLs
            for i, el in enumerate(message_elements):
                self._log(f"--- HTML پیام شماره {i} ---")
                self._log(el.inner_html())
                self._log("--------------------------")

            for el in reversed(message_elements):
                text_content = el.inner_text()
                if normalize_persian_text(text_content).startswith(normalize_persian_text(message_prefix)):
                    mentions = el.locator('a.mention').all()
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
