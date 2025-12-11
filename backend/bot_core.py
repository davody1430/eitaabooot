# backend/bot_core.py - نسخه کامل با المنت‌های واقعی ایتا
import pickle
import os
import time
import random
import re
import pandas as pd
import unicodedata
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# توابع کمکی از کد فعلی
def normalize_persian_text(text):
    if text is None:
        return None
    # تبدیل کاراکترهای رایج عربی به معادل فارسی قبل از نرمال‌سازی کلی
    text = text.replace('\u064A', '\u06CC').replace('\u0649', '\u06CC')  # ی عربی (ي, ى) به ی فارسی (ی)
    text = text.replace('\u0643', '\u06A9')  # ک عربی (ك) به ک فارسی (ک)
    text = text.replace('\u0629', '\u0647')  # ة عربی به ه فارسی
    # نرمال‌سازی با NFKC برای یکسان‌سازی سایر کاراکترهای سازگار و ترکیبی
    return unicodedata.normalize('NFKC', text)

def extract_usernames_from_text(text):
    if not text: return []
    return re.findall(r'@[\w\d_]+', text)

def convert_phone_number_format(phone_number_str):
    if phone_number_str and phone_number_str.startswith('09') and len(phone_number_str) == 11 and phone_number_str.isdigit():
        return '98' + phone_number_str[1:]
    return phone_number_str

class EitaaBot:
    def __init__(self, min_delay=2.0, max_delay=5.0, session_file='session.pkl', headless=False):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.session_file = session_file
        self.headless = headless
        self.driver = None
        self.is_logged_in = False
        
        # المنت‌های اصلی ایتا (از کد فعلی استخراج شده)
        self.selectors = {
            # لاگین
            'login_page': 'https://web.eitaa.com/',
            'phone_input': 'div.input-field-phone div.input-field-input[contenteditable="true"]',
            'code_input': 'input[placeholder="کد تأیید"]',  # نیاز به تأیید
            
            # جستجو
            'search_box': 'input.input-search-input[placeholder="جستجو"]',
            
            # گروه
            'group_item': 'li.rp.chatlist-chat',
            'group_title': 'span.peer-title > i',
            
            # پیام‌ها
            'chat_container': '#chatlist-container',
            'message_bubble': 'div.bubble',
            'message_text': 'div.message',
            'bubbles_container': 'div.bubbles div.scrollable-y',
            
            # ارسال پیام
            'message_input': 'div.input-message-input[contenteditable="true"]:not(.input-field-input-fake)',
            'send_button': 'button.btn-send',  # نیاز به تأیید
            
            # کاربران
            'user_item': 'li.rp.chatlist-chat',
            'user_last_message': 'p.dialog-subtitle > span.user-last-message > i',
            
            # عمومی
            'loading': 'div.loading',
            'error': 'div.error-message'
        }
        
        # استراتژی‌های جایگزین برای تطبیق‌پذیری
        self.alternative_selectors = {
            'phone_input': [
                '//div[contains(@class, "input-field-phone")]//div[@contenteditable="true"]',
                '//div[@contenteditable="true" and contains(@class, "input-field-input")]'
            ],
            'search_box': [
                '//input[@placeholder="جستجو" and contains(@class, "input-search-input")]',
                '//input[contains(@class, "search") and @placeholder="جستجو"]'
            ],
            'message_input': [
                '//div[@contenteditable="true" and contains(@class, "input-message-input")]',
                '//div[contains(@class, "input-message") and @contenteditable="true"]'
            ]
        }
    
    def _find_element(self, selector_name, timeout=10):
        """پیدا کردن المان با استراتژی‌های مختلف"""
        # ابتدا با CSS اصلی
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, self.selectors[selector_name]))
            )
        except TimeoutException:
            # اگر پیدا نشد، با استراتژی‌های جایگزین
            if selector_name in self.alternative_selectors:
                for xpath in self.alternative_selectors[selector_name]:
                    try:
                        return WebDriverWait(self.driver, 3).until(
                            EC.presence_of_element_located((By.XPATH, xpath))
                        )
                    except TimeoutException:
                        continue
            
            # اگر هیچ کدام کار نکرد
            raise NoSuchElementException(f"Element {selector_name} not found with any selector")
    
    def _find_elements(self, selector_name):
        """پیدا کردن چندین المان"""
        try:
            return self.driver.find_elements(By.CSS_SELECTOR, self.selectors[selector_name])
        except:
            return []
    
    def _wait_random_delay(self):
        """انتظار رندوم بین حداقل و حداکثر"""
        delay = random.uniform(self.min_delay, self.max_delay)
        time.sleep(delay)
        return delay
    
    def load_session(self):
        """بارگذاری نشست ذخیره شده"""
        if os.path.exists(self.session_file):
            try:
                self.driver.get("https://web.eitaa.com/")
                time.sleep(2)
                
                # بررسی آیا کاربر وارد شده است
                if self._is_logged_in():
                    self.is_logged_in = True
                    return True
            except:
                pass
        return False
    
    def _is_logged_in(self):
        """بررسی آیا کاربر وارد شده است"""
        try:
            # بررسی وجود عناصر پس از لاگین
            elements_to_check = [
                self.selectors['chat_container'],
                self.selectors['search_box']
            ]
            
            for selector in elements_to_check:
                try:
                    self.driver.find_element(By.CSS_SELECTOR, selector)
                    return True
                except:
                    continue
            return False
        except:
            return False
    
    def save_session(self):
        """ذخیره کوکی‌های نشست فعلی"""
        if self.driver:
            try:
                cookies = self.driver.get_cookies()
                session_data = {
                    'cookies': cookies,
                    'url': self.driver.current_url,
                    'saved_at': datetime.now().isoformat()
                }
                with open(self.session_file, 'wb') as f:
                    pickle.dump(session_data, f)
                return True
            except Exception as e:
                print(f"خطا در ذخیره نشست: {e}")
                return False
        return False
    
    def login(self, phone_number=None):
        """لاگین به ایتا"""
        try:
            # تنظیمات Chrome
            options = webdriver.ChromeOptions()
            if self.headless:
                options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1200,800')
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            self.driver = webdriver.Chrome(options=options)
            
            # رفتن به صفحه ایتا
            self.driver.get(self.selectors['login_page'])
            time.sleep(3)
            
            # بررسی آیا قبلاً لاگین شده‌اید
            if self._is_logged_in():
                self.is_logged_in = True
                print("✅ قبلاً وارد شده‌اید")
                return True
            
            # وارد کردن شماره تلفن
            if phone_number:
                try:
                    phone_input = self._find_element('phone_input', 20)
                    phone_input.clear()
                    phone_input.send_keys(phone_number)
                    phone_input.send_keys(Keys.RETURN)
                    print(f"شماره {phone_number} وارد شد")
                    
                    # منتظر ماندن برای ورود دستی کاربر
                    print("⏳ لطفاً در مرورگر باز شده:")
                    print("1. کد تأیید را وارد کنید")
                    print("2. پس از ورود به صفحه اصلی، برگردید")
                    print("3. دکمه 'تأیید لاگین' را در برنامه بزنید")
                    
                    return "waiting_for_user"
                except Exception as e:
                    print(f"خطا در وارد کردن شماره: {e}")
                    return False
            
            return False
                
        except Exception as e:
            print(f"خطا در لاگین: {e}")
            if self.driver:
                self.driver.save_screenshot('login_error.png')
            return False
    
    def confirm_login(self):
        """تأیید اینکه کاربر دستی لاگین کرده است"""
        try:
            # منتظر بارگذاری صفحه اصلی
            time.sleep(5)
            
            if self._is_logged_in():
                self.is_logged_in = True
                self.save_session()
                print("✅ لاگین تأیید شد و نشست ذخیره گردید")
                return True
            else:
                print("❌ لاگین تایید نشد. لطفاً دوباره تلاش کنید")
                return False
        except Exception as e:
            print(f"خطا در تأیید لاگین: {e}")
            return False
    
    def send_direct_message(self, username, message):
        """ارسال پیام مستقیم به یک کاربر"""
        if not self.is_logged_in:
            raise Exception("ابتدا باید لاگین کنید")
        
        try:
            # پیدا کردن فیلد جستجو
            search_box = self._find_element('search_box', 10)
            search_box.clear()
            time.sleep(0.5)
            
            # جستجوی کاربر
            search_box.send_keys(username)
            time.sleep(2)  # منتظر نتایج
            
            # پیدا کردن کاربر در نتایج
            try:
                # جستجوی کاربر با نام کاربری
                user_elements = self._find_elements('user_item')
                user_found = False
                
                for user_element in user_elements:
                    try:
                        user_text = user_element.text
                        if username.lower() in user_text.lower():
                            user_element.click()
                            user_found = True
                            break
                    except:
                        continue
                
                if not user_found:
                    raise NoSuchElementException(f"User {username} not found in search results")
                
                # منتظر باز شدن چت
                time.sleep(2)
                
                # پیدا کردن فیلد پیام
                message_input = self._find_element('message_input', 10)
                message_input.clear()
                
                # ارسال پیام کاراکتر به کاراکتر (شبیه تایپ انسان)
                normalized_message = normalize_persian_text(message)
                for char in normalized_message:
                    message_input.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.15))  # تایپ طبیعی
                
                # ارسال پیام
                message_input.send_keys(Keys.RETURN)
                
                # تأخیر رندوم
                delay = self._wait_random_delay()
                
                print(f"✅ پیام به {username} ارسال شد (تأخیر: {delay:.1f}ثانیه)")
                return True
                
            except Exception as e:
                print(f"خطا در یافتن کاربر {username}: {e}")
                return False
                
        except Exception as e:
            print(f"خطا در ارسال پیام به {username}: {e}")
            if self.driver:
                self.driver.save_screenshot(f'send_error_{username}.png')
            return False
    
    def extract_group_members(self, group_name):
        """استخراج اعضای گروه"""
        if not self.is_logged_in:
            raise Exception("ابتدا باید لاگین کنید")
        
        members = []
        try:
            # جستجوی گروه
            search_box = self._find_element('search_box', 10)
            search_box.clear()
            time.sleep(0.5)
            
            normalized_group_name = normalize_persian_text(group_name)
            search_box.send_keys(normalized_group_name)
            time.sleep(2)
            
            # پیدا کردن گروه
            group_elements = self._find_elements('group_item')
            group_found = False
            
            for group_element in group_elements:
                try:
                    group_text = group_element.text
                    if normalized_group_name in normalize_persian_text(group_text):
                        group_element.click()
                        group_found = True
                        break
                except:
                    continue
            
            if not group_found:
                raise NoSuchElementException(f"Group {group_name} not found")
            
            # منتظر بارگذاری گروه
            time.sleep(3)
            
            # اینجا منطق استخراج اعضا نیاز به بررسی دقیق‌تر UI ایتا دارد
            # در نسخه فعلی، این بخش نیاز به توسعه دارد
            print(f"⚠️ استخراج اعضای گروه نیاز به توسعه بیشتر دارد")
            
            return members
            
        except Exception as e:
            print(f"خطا در استخراج اعضای گروه: {e}")
            return members
    
    def extract_usernames_from_group_message(self, group_name, message_prefix):
        """استخراج نام کاربری‌ها از پیام گروه با پیشوند خاص"""
        if not self.is_logged_in:
            raise Exception("ابتدا باید لاگین کنید")
        
        usernames = []
        try:
            # ورود به گروه
            search_box = self._find_element('search_box', 10)
            search_box.clear()
            time.sleep(0.5)
            
            normalized_group_name = normalize_persian_text(group_name)
            search_box.send_keys(normalized_group_name)
            time.sleep(2)
            
            # پیدا کردن گروه
            group_elements = self._find_elements('group_item')
            group_found = False
            
            for group_element in group_elements:
                try:
                    group_text = group_element.text
                    if normalized_group_name in normalize_persian_text(group_text):
                        group_element.click()
                        group_found = True
                        break
                except:
                    continue
            
            if not group_found:
                raise NoSuchElementException(f"Group {group_name} not found")
            
            # منتظر بارگذاری پیام‌ها
            time.sleep(3)
            
            # اسکرول و پیدا کردن پیام‌ها
            normalized_prefix = normalize_persian_text(message_prefix)
            
            # پیدا کردن حباب‌های پیام
            message_bubbles = self._find_elements('message_bubble')
            
            for bubble in message_bubbles[-20:]:  # بررسی 20 پیام آخر
                try:
                    message_element = bubble.find_element(By.CSS_SELECTOR, self.selectors['message_text'])
                    message_text = message_element.text
                    
                    if normalized_prefix in normalize_persian_text(message_text):
                        # استخراج نام کاربری‌ها
                        found_usernames = extract_usernames_from_text(message_text)
                        usernames.extend(found_usernames)
                        break
                except:
                    continue
            
            return list(set(usernames))  # حذف تکراری‌ها
            
        except Exception as e:
            print(f"خطا در استخراج نام کاربری‌ها از گروه: {e}")
            return usernames
    
    def read_usernames_from_excel(self, excel_path):
        """خواندن نام کاربری‌ها از فایل اکسل"""
        try:
            df = pd.read_excel(excel_path, header=None)
            usernames = []
            
            for col in df.columns:
                for value in df[col].dropna():
                    if isinstance(value, str) and value.startswith('@'):
                        usernames.append(value.strip())
            
            return list(set(usernames))  # حذف تکراری‌ها
        except Exception as e:
            print(f"خطا در خواندن فایل اکسل: {e}")
            return []
    
    def close(self):
        """بستن مرورگر و ذخیره نشست"""
        if self.driver:
            try:
                self.save_session()
                self.driver.quit()
                print("مرورگر بسته شد و نشست ذخیره گردید")
            except:
                pass
        self.is_logged_in = False