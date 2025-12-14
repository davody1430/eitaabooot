# backend/bot_core.py - نسخه کارکرده استخراج
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
            self._log("❌ امکان استخراج نام‌های کاربری وجود ندارد، لطفاً ابتدا وارد شوید.")
            return []

        try:
            self._log(f"🔍 شروع عملیات برای گروه: {group_name}")

            # --- مرحله ۱: جستجو و باز کردن گروه ---
            self._log("۱.۱: در حال پیدا کردن و پاک کردن کادر جستجو...")
            search_input = self.page.locator(self.selectors['search_box'])
            search_input.wait_for(timeout=10000)
            search_input.click(timeout=5000)
            search_input.fill("")
            self.page.wait_for_timeout(500)

            self._log(f"۱.۲: در حال جستجوی گروه '{group_name}'...")
            search_input.fill(group_name)
            self.page.wait_for_timeout(3000)  # Wait for search results

            self._log("۱.۳: در حال پیدا کردن گروه در نتایج...")
            group_item_selector = f'li.rp.chatlist-chat:has(span.peer-title:has-text("{group_name}"))'
            group_chat_element = self.page.locator(group_item_selector).first
            group_chat_element.wait_for(state='visible', timeout=15000)
            group_chat_element.click(timeout=10000)
            self._log(f"✅ گروه '{group_name}' با موفقیت باز شد.")
            self.page.wait_for_timeout(3000) # Wait for group messages to load

            # --- مرحله ۲: پیدا کردن پیام هدف در گروه ---
            self._log("\n--- شروع مرحله ۲: پیدا کردن پیام هدف در گروه ---")
            target_message_text = None
            try:
                message_bubble_selector = "div.bubble"
                message_text_in_bubble_selector = "div.message"

                # اسکرول به بالا برای بارگذاری پیام‌های قدیمی‌تر
                self._log("۲.۱: در حال اسکرول به بالای صفحه برای بارگذاری پیام‌ها...")
                chat_scrollable_area_locator = self.page.locator('//div[contains(@class, "bubbles-scroller")]/div[contains(@class, "scrollable-y")]').first
                if chat_scrollable_area_locator.count() > 0:
                    for i in range(3):  # اسکرول چندباره برای اطمینان
                        self._log(f"   اسکرول به بالا (تلاش {i+1}/3)...")
                        chat_scrollable_area_locator.evaluate("el => el.scrollTop = 0")
                        self.page.wait_for_timeout(2000)

                # پیدا کردن همه حباب‌های پیام
                all_message_bubbles = self.page.locator(message_bubble_selector)
                count = all_message_bubbles.count()
                self._log(f"۲.۲: تعداد {count} حباب پیام در گروه یافت شد. در حال بررسی از آخر...")

                if count == 0:
                     self._log("   هیچ پیامی در گروه یافت نشد. ممکن است گروه خالی باشد یا هنوز بارگذاری نشده باشد.")
                     self.page.screenshot(path='debug_no_messages_found.png')


                # حلقه برای پیدا کردن پیام
                for i in range(count - 1, -1, -1):
                    single_bubble_locator = all_message_bubbles.nth(i)
                    # اسکرول به پیام برای اینکه قابل مشاهده باشد
                    try:
                        single_bubble_locator.scroll_into_view_if_needed(timeout=1000)
                    except:
                        pass

                    message_text_locator = single_bubble_locator.locator(message_text_in_bubble_selector)
                    if message_text_locator.count() > 0:
                        try:
                            text_content = message_text_locator.inner_text(timeout=3000)
                            text_to_check = normalize_persian_text(text_content.strip() if text_content else "")
                            prefix_to_check = normalize_persian_text(message_prefix)

                            if text_to_check and prefix_to_check and text_to_check.startswith(prefix_to_check):
                                target_message_text = text_content.strip()
                                self._log(f"🎯 پیام هدف پیدا شد: '{target_message_text[:50]}...'")
                                break # از حلقه خارج شو
                        except Exception as e_inner:
                            self._log(f"   (خطای جزئی در خواندن متن پیام شماره {i}: {e_inner})")
                            pass

                if not target_message_text:
                    self._log(f"⚠️ پیام با پیشوند '{message_prefix}' در گروه '{group_name}' پیدا نشد.")
                    self.page.screenshot(path='debug_message_not_found.png')
                    return [] # بازگشت لیست خالی چون پیام پیدا نشد

            except Exception as e_find_msg:
                self._log(f"❌ خطایی در هنگام جستجوی پیام هدف در گروه '{group_name}' رخ داد: {e_find_msg}")
                self.page.screenshot(path='debug_find_message_error.png')
                return []

            # --- مرحله ۳: استخراج منشن‌ها و بازگشت ---
            self._log("\n--- شروع مرحله ۳: استخراج منشن‌ها ---")
            if target_message_text:
                usernames = extract_usernames_from_text(target_message_text)
                if not usernames:
                    self._log("⚠️ هیچ نام کاربری (@username) در پیام پیدا نشد.")
                    return []
                else:
                    self._log(f"✅ {len(usernames)} نام کاربری استخراج شد: {', '.join(usernames[:5])}...")
                    # پاک کردن فیلد جستجو برای آماده‌سازی مراحل بعدی
                    try:
                        search_input.click(timeout=3000)
                        search_input.fill("")
                        self.page.wait_for_timeout(500)
                    except:
                        pass
                    return usernames
            else:
                 # این حالت نباید اتفاق بیفتد چون قبلا کنترل شده
                self._log("ℹ️ پیام هدف یافت نشد، بنابراین هیچ نام کاربری برای استخراج وجود ندارد.")
                return []

        except Exception as e:
            self._log(f"❌ خطای کلی و غیرمنتظره در تابع extract_mentions_from_group: {e}")
            import traceback
            self._log(f"جزئیات خطا: {traceback.format_exc()}")
            if self.page:
                self.page.screenshot(path='debug_extract_general_error.png')
            return []
            
