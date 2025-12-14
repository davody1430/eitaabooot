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
        """
        نسخه جدید: استفاده از منطق ساده‌تر و سلکتورهای مطمئن‌تر
        """
        if not self.is_logged_in:
            self._log("❌ امکان استخراج نام‌های کاربری وجود ندارد، لطفاً ابتدا وارد شوید.")
            return []

        try:
            self._log(f"🔍 شروع عملیات برای گروه: {group_name}")
            
            # --- مرحله ۱: باز کردن جستجو و جستجوی گروه ---
            self._log("۱. باز کردن جستجو...")
            
            # روش ۱: کلیک روی دکمه جستجو
            try:
                search_button = self.page.locator(".tgico-search, .icon-search, button[aria-label='جستجو']").first
                if search_button.is_visible():
                    search_button.click()
                    self.page.wait_for_timeout(1000)
            except:
                pass
            
            # پیدا کردن فیلد جستجو
            search_selector = "input.input-search-input, input[placeholder*='جستجو'], input[type='search']"
            search_input = self.page.locator(search_selector).first
            
            if not search_input.is_visible():
                self._log("❌ فیلد جستجو پیدا نشد")
                return []
            
            # پاک کردن و وارد کردن نام گروه
            self._log(f"۲. جستجوی گروه: {group_name}")
            search_input.click()
            search_input.fill("")
            self.page.wait_for_timeout(500)
            search_input.fill(group_name)
            self.page.wait_for_timeout(3000)
            
            # --- مرحله ۲: پیدا کردن و کلیک روی گروه ---
            self._log("۳. پیدا کردن گروه در نتایج...")
            
            # روش ۱: استفاده از سلکتور عمومی‌تر
            group_selectors = [
                f"li.chatlist-chat:has-text('{group_name}')",
                f"li.rp:has-text('{group_name}')",
                f"li:has-text('{group_name}')"
            ]
            
            group_element = None
            for selector in group_selectors:
                try:
                    element = self.page.locator(selector).first
                    if element.is_visible(timeout=2000):
                        group_element = element
                        break
                except:
                    continue
            
            if not group_element:
                self._log(f"❌ گروه '{group_name}' در نتایج جستجو پیدا نشد")
                # عکس بگیریم برای دیباگ
                self.page.screenshot(path="debug_group_not_found.png")
                return []
            
            self._log("۴. کلیک روی گروه...")
            group_element.click()
            self.page.wait_for_timeout(2000)
            
            # --- مرحله ۳: انتظار برای بارگذاری صفحه گروه ---
            self._log("۵. منتظر بارگذاری صفحه گروه...")
            
            # چندین نشانگر برای اطمینان از بارگذاری گروه
            group_indicators = [
                "div.chat-info",
                "div.bubbles-scroller",
                "div.chat-input",
                "div.input-message-input"
            ]
            
            for indicator in group_indicators:
                try:
                    self.page.wait_for_selector(indicator, timeout=5000)
                    break
                except:
                    continue
            
            self._log(f"✅ گروه '{group_name}' با موفقیت باز شد")
            
            # --- مرحله ۴: جستجوی پیام با پیشوند مشخص ---
            self._log(f"۶. جستجوی پیام با پیشوند: {message_prefix}")
            
            # اسکرول به بالا
            self._log("۷. اسکرول به بالا برای دیدن پیام‌های بیشتر...")
            try:
                # تلاش برای اسکرول
                self.page.evaluate("window.scrollTo(0, 0)")
                self.page.wait_for_timeout(2000)
                
                # اسکرول مجدد برای اطمینان
                self.page.evaluate("""
                    const scrollContainer = document.querySelector('.bubbles-scroller, .scrollable-y, .bubbles');
                    if (scrollContainer) scrollContainer.scrollTop = 0;
                """)
                self.page.wait_for_timeout(2000)
            except:
                pass
            
            # جستجوی پیام‌ها
            target_message_text = None
            
            # چندین سلکتور ممکن برای پیام‌ها
            message_selectors = [
                "div.bubble",
                "div.message",
                "div.bubble-content",
                "div.text-content"
            ]
            
            for msg_selector in message_selectors:
                try:
                    messages = self.page.locator(msg_selector)
                    count = messages.count()
                    
                    if count > 0:
                        self._log(f"   پیدا شد {count} پیام با سلکتور {msg_selector}")
                        
                        # بررسی از آخرین پیام
                        for i in range(count - 1, -1, -1):
                            try:
                                msg = messages.nth(i)
                                text = msg.inner_text(timeout=1000)
                                
                                if text:
                                    clean_text = normalize_persian_text(text.strip())
                                    clean_prefix = normalize_persian_text(message_prefix.strip())
                                    
                                    if clean_text and clean_prefix and clean_text.startswith(clean_prefix):
                                        target_message_text = text.strip()
                                        self._log(f"🎯 پیام هدف پیدا شد: '{target_message_text[:50]}...'")
                                        break
                            except:
                                continue
                        
                        if target_message_text:
                            break
                except:
                    continue
            
            if not target_message_text:
                self._log(f"⚠️ پیام با پیشوند '{message_prefix}' پیدا نشد")
                # عکس برای دیباگ
                self.page.screenshot(path="debug_message_not_found.png")
                return []
            
            # --- مرحله ۵: استخراج نام‌های کاربری ---
            self._log("۸. استخراج نام‌های کاربری از پیام...")
            usernames = extract_usernames_from_text(target_message_text)
            
            if not usernames:
                self._log("⚠️ هیچ نام کاربری (@username) در پیام پیدا نشد")
                return []
            
            self._log(f"✅ {len(usernames)} نام کاربری استخراج شد: {', '.join(usernames[:5])}...")
            
            # --- مرحله ۶: بازگشت به صفحه اصلی ---
            self._log("۹. بازگشت به صفحه اصلی...")
            try:
                # بستن صفحه گروه با کلیک روی جستجو
                search_input.click()
                search_input.fill("")
                self.page.wait_for_timeout(1000)
            except:
                pass
            
            return usernames
            
        except Exception as e:
            self._log(f"❌ خطا در استخراج از گروه: {str(e)}")
            import traceback
            self._log(f"جزئیات خطا: {traceback.format_exc()}")
            
            # عکس بگیریم برای دیباگ
            try:
                self.page.screenshot(path="debug_extract_error.png")
            except:
                pass
            
            return []
            
