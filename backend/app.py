# backend/app.py
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import os
import threading
import time
import random
from bot_core import EitaaBot, convert_phone_number_format
import sqlite3
from werkzeug.utils import secure_filename
from queue import Queue
from datetime import datetime
import pandas as pd

app = Flask(__name__, template_folder='../frontend', static_folder='../frontend')
CORS(app)

app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SESSION_FOLDER'] = 'sessions'
app.config['BOT_INSTANCES'] = {}
app.config['SEND_STATS'] = {}
app.config['CONTACTS'] = []
app.config['REPORTS'] = []
app.config['SETTINGS'] = {
    'default_message': 'سلام [نام] عزیز،\nاین پیام از طرف [سازمان] است.\nبا تشکر',
    'default_min_delay': 2.0,
    'default_max_delay': 5.0,
    'max_per_hour': 100
}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['SESSION_FOLDER'], exist_ok=True)

def init_db():
    conn = sqlite3.connect('eitaa_bot.db')
    cursor = conn.cursor()
    
    # ایجاد جداول
    cursor.execute('''CREATE TABLE IF NOT EXISTS logs 
                     (id INTEGER PRIMARY KEY, bot_id TEXT, message TEXT, timestamp DATETIME)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS contacts 
                     (id INTEGER PRIMARY KEY, user_id TEXT, source TEXT, added_date DATETIME)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS reports 
                     (id INTEGER PRIMARY KEY, date TEXT, total INTEGER, success INTEGER, errors INTEGER, duration TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings 
                     (id INTEGER PRIMARY KEY, key TEXT UNIQUE, value TEXT)''')
    
    # افزودن تنظیمات پیش‌فرض
    default_settings = [
        ('default_message', 'سلام [نام] عزیز،\nاین پیام از طرف [سازمان] است.\nبا تشکر'),
        ('default_min_delay', '2.0'),
        ('default_max_delay', '5.0'),
        ('max_per_hour', '100')
    ]
    
    for key, value in default_settings:
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
    
    conn.commit()
    conn.close()

# ==================== ROUTES ====================

@app.route('/')
def index():
    return render_template('index.html')

# ==================== BOT MANAGEMENT ====================

@app.route('/api/bot/create', methods=['POST'])
def create_bot():
    """ایجاد ربات جدید"""
    try:
        data = request.json or {}
        bot_id = f"bot_{int(time.time())}"
        session_file = f"{app.config['SESSION_FOLDER']}/session_{bot_id}.json"
        
        # تنظیمات تاخیر
        min_delay = float(data.get('min_delay', 2.0))
        max_delay = float(data.get('max_delay', 5.0))
        
        bot = EitaaBot(
            min_delay=min_delay,
            max_delay=max_delay,
            session_file=session_file,
            headless=False,
            log_queue=Queue()
        )
        
        app.config['BOT_INSTANCES'][bot_id] = {
            'bot': bot,
            'log_queue': bot.log_queue,
            'created_at': datetime.now()
        }
        
        # لاگ
        log_to_db(bot_id, f"ربات {bot_id} ایجاد شد")
        
        return jsonify({
            'status': 'success', 
            'bot_id': bot_id,
            'message': 'ربات با موفقیت ایجاد شد'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/<bot_id>/login', methods=['POST'])
def bot_login(bot_id):
    """ورود به ایتا"""
    if bot_id not in app.config['BOT_INSTANCES']:
        return jsonify({'error': 'ربات پیدا نشد'}), 404
    
    bot_data = app.config['BOT_INSTANCES'][bot_id]
    bot = bot_data['bot']
    
    data = request.json or {}
    phone = data.get('phone_number')
    
    if not phone:
        return jsonify({'error': 'شماره تلفن لازم است'}), 400
    
    try:
        phone_converted = convert_phone_number_format(phone)
        result = bot.login(phone_number=phone_converted)
        
        if "waiting_for_code" in result:
            log_to_db(bot_id, f"منتظر کد تأیید برای شماره {phone}")
            return jsonify({
                'status': 'waiting_for_code',
                'message': 'کد تأیید ارسال شد'
            })
        elif "already_logged_in" in result:
            log_to_db(bot_id, "کاربر از قبل لاگین است")
            return jsonify({
                'status': 'success', 
                'message': 'قبلاً لاگین شده‌اید'
            })
        else:
            log_to_db(bot_id, f"خطا در لاگین: {result}")
            return jsonify({'error': result}), 500
    except Exception as e:
        log_to_db(bot_id, f"خطا در لاگین: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/<bot_id>/submit-code', methods=['POST'])
def submit_code(bot_id):
    """ثبت کد تأیید"""
    if bot_id not in app.config['BOT_INSTANCES']:
        return jsonify({'error': 'ربات پیدا نشد'}), 404
    
    bot_data = app.config['BOT_INSTANCES'][bot_id]
    bot = bot_data['bot']
    
    data = request.json or {}
    code = data.get('code')
    
    if not code:
        return jsonify({'error': 'کد تایید لازم است'}), 400
    
    try:
        result = bot.submit_code(code)
        if "login_successful" in result:
            log_to_db(bot_id, "لاگین موفقیت‌آمیز")
            return jsonify({
                'status': 'success',
                'message': 'لاگین موفقیت‌آمیز'
            })
        else:
            log_to_db(bot_id, f"خطا در تأیید کد: {result}")
            return jsonify({'error': result}), 500
    except Exception as e:
        log_to_db(bot_id, f"خطا در تأیید کد: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/<bot_id>/send-test', methods=['POST'])
def send_test_message(bot_id):
    """تست ارسال پیام"""
    if bot_id not in app.config['BOT_INSTANCES']:
        return jsonify({'error': 'ربات پیدا نشد'}), 404
    
    bot_data = app.config['BOT_INSTANCES'][bot_id]
    bot = bot_data['bot']
    
    if not bot.is_logged_in:
        return jsonify({'error': 'ابتدا لاگین کنید'}), 403
    
    data = request.json or {}
    username = data.get('username', '@test')
    message = data.get('message', 'تست ربات ایتا')
    
    try:
        success = bot.send_direct_message(username, message)
        if success:
            log_to_db(bot_id, f"تست ارسال به {username} موفق بود")
            return jsonify({
                'status': 'success', 
                'message': 'پیام تست ارسال شد'
            })
        else:
            log_to_db(bot_id, f"تست ارسال به {username} ناموفق بود")
            return jsonify({'error': 'ارسال ناموفق'}), 500
    except Exception as e:
        log_to_db(bot_id, f"خطا در تست ارسال: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/<bot_id>/status', methods=['GET'])
def bot_status(bot_id):
    """دریافت وضعیت ربات"""
    if bot_id not in app.config['BOT_INSTANCES']:
        return jsonify({'error': 'ربات پیدا نشد'}), 404
    
    bot_data = app.config['BOT_INSTANCES'][bot_id]
    bot = bot_data['bot']
    
    # جمع‌آوری لاگ‌ها
    logs = []
    while not bot_data['log_queue'].empty():
        logs.append(bot_data['log_queue'].get())
    
    # لاگ‌های اخیر از دیتابیس
    recent_logs = get_recent_logs(bot_id, 10)
    
    return jsonify({
        'is_logged_in': bot.is_logged_in,
        'session_age': (datetime.now() - bot_data['created_at']).total_seconds(),
        'logs': logs[-5:] + recent_logs[-5:]  # 5 لاگ از هر دو منبع
    })

@app.route('/api/bot/<bot_id>/close', methods=['POST'])
def close_bot(bot_id):
    """بستن ربات"""
    if bot_id not in app.config['BOT_INSTANCES']:
        return jsonify({'error': 'ربات پیدا نشد'}), 404
    
    bot_data = app.config['BOT_INSTANCES'][bot_id]
    bot = bot_data['bot']
    bot.close()
    
    # حذف از حافظه
    del app.config['BOT_INSTANCES'][bot_id]
    
    # حذف آمار ارسال
    if bot_id in app.config['SEND_STATS']:
        del app.config['SEND_STATS'][bot_id]
    
    log_to_db(bot_id, "ربات بسته شد")
    
    return jsonify({'status': 'success', 'message': 'ربات بسته شد'})

# ==================== CONTACTS MANAGEMENT ====================

@app.route('/api/contacts/upload', methods=['POST'])
def upload_contacts():
    """آپلود فایل مخاطبین"""
    if 'file' not in request.files:
        return jsonify({'error': 'فایل انتخاب نشده'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'نام فایل خالی است'}), 400
    
    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        return jsonify({'error': 'فقط فایل‌های اکسل و CSV مجاز هستند'}), 400
    
    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # خواندن فایل
        if file.filename.endswith('.csv'):
            df = pd.read_csv(filepath, header=None)
        else:
            df = pd.read_excel(filepath, header=None)
        
        # استخراج یوزرنیم‌ها
        contacts = []
        usernames = []
        
        for col in df.columns:
            for value in df[col].dropna():
                val_str = str(value).strip()
                
                # استخراج یوزرنیم از متن
                if '@' in val_str:
                    # پیدا کردن همه یوزرنیم‌ها
                    import re
                    found_usernames = re.findall(r'@[\w\d_]+', val_str)
                    for username in found_usernames:
                        if username not in usernames:
                            usernames.append(username)
                            contacts.append({
                                'id': len(contacts) + 1,
                                'user_id': username,
                                'source': 'Excel',
                                'added_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            })
        
        # ذخیره در حافظه
        app.config['CONTACTS'] = contacts
        
        # ذخیره در دیتابیس
        conn = sqlite3.connect('eitaa_bot.db')
        cursor = conn.cursor()
        
        # حذف مخاطبین قبلی
        cursor.execute("DELETE FROM contacts WHERE source = 'Excel'")
        
        # ذخیره مخاطبین جدید
        for contact in contacts:
            cursor.execute(
                "INSERT INTO contacts (user_id, source, added_date) VALUES (?, ?, ?)",
                (contact['user_id'], contact['source'], contact['added_date'])
            )
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'filepath': filepath,
            'count': len(contacts),
            'contacts': contacts[:10],  # 10 مورد اول
            'message': f'{len(contacts)} مخاطب با موفقیت اضافه شدند'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/contacts', methods=['GET'])
def get_contacts():
    """دریافت لیست مخاطبین"""
    try:
        conn = sqlite3.connect('eitaa_bot.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM contacts ORDER BY added_date DESC LIMIT 100")
        rows = cursor.fetchall()
        
        contacts = []
        for row in rows:
            contacts.append({
                'id': row[0],
                'user_id': row[1],
                'source': row[2],
                'added_date': row[3]
            })
        
        conn.close()
        
        return jsonify({
            'status': 'success',
            'count': len(contacts),
            'contacts': contacts
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/contacts', methods=['DELETE'])
def delete_contacts():
    """حذف مخاطبین"""
    data = request.json or {}
    ids = data.get('ids', [])
    
    if not ids:
        return jsonify({'error': 'شناسه‌ای انتخاب نشده'}), 400
    
    try:
        conn = sqlite3.connect('eitaa_bot.db')
        cursor = conn.cursor()
        
        placeholders = ','.join('?' for _ in ids)
        cursor.execute(f"DELETE FROM contacts WHERE id IN ({placeholders})", ids)
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'message': f'{len(ids)} مخاطب حذف شدند',
            'deleted_ids': ids
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== MESSAGE SENDING ====================

@app.route('/api/bot/<bot_id>/send', methods=['POST'])
def send_messages(bot_id):
    """شروع ارسال پیام‌ها"""
    if bot_id not in app.config['BOT_INSTANCES']:
        return jsonify({'error': 'ربات پیدا نشد'}), 404
    
    bot_data = app.config['BOT_INSTANCES'][bot_id]
    bot = bot_data['bot']
    
    if not bot.is_logged_in:
        return jsonify({'error': 'ربات لاگین نیست'}), 403
    
    data = request.json or {}
    message = data.get('message', '')
    send_type = data.get('type', 'excel')
    
    if not message:
        return jsonify({'error': 'متن پیام ضروری است'}), 400
    
    # ساخت لیست کاربران
    usernames = []
    
    if send_type == 'excel':
        excel_path = data.get('excel_path', '')
        if excel_path and os.path.exists(excel_path):
            usernames = bot.read_usernames_from_excel(excel_path)
        else:
            # خواندن از دیتابیس
            conn = sqlite3.connect('eitaa_bot.db')
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM contacts")
            rows = cursor.fetchall()
            usernames = [row[0] for row in rows if row[0].startswith('@')]
            conn.close()
            
            if not usernames:
                # نمونه‌های تست
                usernames = ['@user1', '@user2', '@user3', '@user4', '@user5']
    
    elif send_type == 'group_message':
        group_name = data.get('group_name', '')
        message_prefix = data.get('message_prefix', '')
        
        if group_name and message_prefix:
            usernames = bot.extract_usernames_from_group_message(group_name, message_prefix)
        else:
            usernames = ['@group_user1', '@group_user2', '@group_user3']
    
    else:
        usernames = ['@test_user']
    
    if not usernames:
        return jsonify({'error': 'هیچ کاربری پیدا نشد'}), 400
    
    # تنظیمات ارسال
    min_delay = float(data.get('min_delay', bot.min_delay))
    max_delay = float(data.get('max_delay', bot.max_delay))
    bot.min_delay = min_delay
    bot.max_delay = max_delay
    
    # ذخیره آمار
    app.config['SEND_STATS'][bot_id] = {
        'total': len(usernames),
        'sent': 0,
        'success': 0,
        'error': 0,
        'is_running': True,
        'logs': [],
        'usernames': usernames,
        'current_index': 0
    }
    
    def send_thread():
        stats = app.config['SEND_STATS'][bot_id]
        stats['logs'].append(f"شروع ارسال به {stats['total']} کاربر")
        
        for i, username in enumerate(stats['usernames']):
            if not stats['is_running']:
                stats['logs'].append("ارسال توسط کاربر متوقف شد")
                break
            
            # ارسال پیام
            try:
                success = bot.send_direct_message(username, message)
                stats['sent'] = i + 1
                stats['current_index'] = i
                
                if success:
                    stats['success'] += 1
                    stats['logs'].append(f"✅ پیام به {username} ارسال شد")
                else:
                    stats['error'] += 1
                    stats['logs'].append(f"❌ خطا در ارسال به {username}")
                
                # وقفه بین ارسال‌ها
                if i < len(stats['usernames']) - 1:
                    time.sleep(random.uniform(min_delay, max_delay))
                    
            except Exception as e:
                stats['error'] += 1
                stats['logs'].append(f"❌ خطای سیستمی: {str(e)}")
        
        stats['is_running'] = False
        stats['logs'].append("ارسال کامل شد")
        
        # ذخیره گزارش
        save_report(bot_id, stats)
    
    # اجرا در ترد جداگانه
    thread = threading.Thread(target=send_thread)
    thread.daemon = True
    thread.start()
    
    log_to_db(bot_id, f"شروع ارسال {len(usernames)} پیام")
    
    return jsonify({
        'status': 'started',
        'total': len(usernames),
        'bot_id': bot_id,
        'message': f'ارسال به {len(usernames)} کاربر شروع شد'
    })

@app.route('/api/bot/<bot_id>/send/status', methods=['GET'])
def send_status(bot_id):
    """دریافت وضعیت ارسال جاری"""
    if bot_id not in app.config['SEND_STATS']:
        return jsonify({
            'is_running': False,
            'total': 0,
            'sent': 0,
            'success': 0,
            'error': 0,
            'message': 'هیچ فرآیند ارسالی فعال نیست'
        })
    
    stats = app.config['SEND_STATS'][bot_id]
    return jsonify(stats)

@app.route('/api/bot/<bot_id>/send/stop', methods=['POST'])
def stop_sending(bot_id):
    """توقف ارسال جاری"""
    if bot_id not in app.config['SEND_STATS']:
        return jsonify({'error': 'هیچ فرآیند ارسالی فعال نیست'}), 404
    
    stats = app.config['SEND_STATS'][bot_id]
    stats['is_running'] = False
    
    log_to_db(bot_id, f"ارسال متوقف شد. {stats['sent']} از {stats['total']} ارسال شد.")
    
    return jsonify({
        'status': 'stopped',
        'message': f'ارسال متوقف شد. {stats["sent"]} از {stats["total"]} ارسال شد.',
        'stats': {
            'sent': stats['sent'],
            'success': stats['success'],
            'error': stats['error'],
            'remaining': stats['total'] - stats['sent']
        }
    })

# ==================== REPORTS ====================

@app.route('/api/reports', methods=['GET'])
def get_reports():
    """دریافت گزارش‌ها"""
    try:
        conn = sqlite3.connect('eitaa_bot.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM reports ORDER BY date DESC LIMIT 50")
        rows = cursor.fetchall()
        
        reports = []
        for row in rows:
            reports.append({
                'id': row[0],
                'date': row[1],
                'total': row[2],
                'success': row[3],
                'errors': row[4],
                'duration': row[5]
            })
        
        conn.close()
        
        # محاسبه آمار کلی
        total_messages = sum(r['total'] for r in reports)
        success_messages = sum(r['success'] for r in reports)
        error_messages = sum(r['errors'] for r in reports)
        
        return jsonify({
            'status': 'success',
            'reports': reports,
            'summary': {
                'total_messages': total_messages,
                'success_messages': success_messages,
                'error_messages': error_messages,
                'success_rate': (success_messages / total_messages * 100) if total_messages > 0 else 0
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== SETTINGS ====================

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """دریافت تنظیمات"""
    try:
        conn = sqlite3.connect('eitaa_bot.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT key, value FROM settings")
        rows = cursor.fetchall()
        
        settings = {}
        for row in rows:
            settings[row[0]] = row[1]
        
        conn.close()
        
        # تنظیمات پیش‌فرض اگر وجود نداشت
        defaults = app.config['SETTINGS']
        for key, value in defaults.items():
            if key not in settings:
                settings[key] = value
        
        return jsonify({
            'status': 'success',
            'settings': settings
        })
    except Exception as e:
        # برگرداندن تنظیمات پیش‌فرض در صورت خطا
        return jsonify({
            'status': 'success',
            'settings': app.config['SETTINGS']
        })

@app.route('/api/settings', methods=['POST'])
def save_settings():
    """ذخیره تنظیمات"""
    data = request.json or {}
    
    if not data:
        return jsonify({'error': 'داده تنظیمات ارسال نشده'}), 400
    
    try:
        conn = sqlite3.connect('eitaa_bot.db')
        cursor = conn.cursor()
        
        for key, value in data.items():
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value))
            )
        
        conn.commit()
        conn.close()
        
        # آپدیت حافظه
        for key, value in data.items():
            app.config['SETTINGS'][key] = value
        
        return jsonify({
            'status': 'success',
            'message': 'تنظیمات ذخیره شد',
            'settings': data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== SYSTEM STATUS ====================

@app.route('/api/system/status', methods=['GET'])
def system_status():
    """وضعیت سیستم"""
    try:
        # وضعیت سرور
        server_status = {
            'running': True,
            'port': 5000,
            'uptime': time.time() - app_start_time,
            'memory_usage': get_memory_usage()
        }
        
        # وضعیت ربات‌ها
        bots_status = []
        for bot_id, bot_data in app.config['BOT_INSTANCES'].items():
            bot = bot_data['bot']
            bots_status.append({
                'bot_id': bot_id,
                'is_logged_in': bot.is_logged_in,
                'session_age': (datetime.now() - bot_data['created_at']).total_seconds(),
                'has_active_send': bot_id in app.config['SEND_STATS'] and 
                                   app.config['SEND_STATS'][bot_id]['is_running']
            })
        
        # وضعیت ذخیره‌سازی
        import shutil
        total, used, free = shutil.disk_usage(".")
        
        return jsonify({
            'status': 'success',
            'server': server_status,
            'bots': bots_status,
            'storage': {
                'total_gb': total // (2**30),
                'used_gb': used // (2**30),
                'free_gb': free // (2**30),
                'used_percent': (used / total) * 100
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== HELPER FUNCTIONS ====================

def log_to_db(bot_id, message):
    """ذخیره لاگ در دیتابیس"""
    try:
        conn = sqlite3.connect('eitaa_bot.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO logs (bot_id, message, timestamp) VALUES (?, ?, ?)",
            (bot_id, message, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        conn.commit()
        conn.close()
    except:
        pass

def get_recent_logs(bot_id, limit=10):
    """دریافت لاگ‌های اخیر"""
    try:
        conn = sqlite3.connect('eitaa_bot.db')
        cursor = conn.cursor()
        cursor.execute(
            "SELECT message, timestamp FROM logs WHERE bot_id = ? ORDER BY timestamp DESC LIMIT ?",
            (bot_id, limit)
        )
        rows = cursor.fetchall()
        conn.close()
        
        return [f"[{row[1]}] {row[0]}" for row in rows]
    except:
        return []

def save_report(bot_id, stats):
    """ذخیره گزارش در دیتابیس"""
    try:
        conn = sqlite3.connect('eitaa_bot.db')
        cursor = conn.cursor()
        
        duration = "نامشخص"
        if stats['total'] > 0:
            estimated = stats['total'] * 3.5 / 60  # میانگین 3.5 ثانیه برای هر پیام
            duration = f"{estimated:.1f} دقیقه"
        
        cursor.execute(
            """INSERT INTO reports (date, total, success, errors, duration) 
               VALUES (?, ?, ?, ?, ?)""",
            (datetime.now().strftime('%Y-%m-%d'), 
             stats['total'], 
             stats['success'], 
             stats['error'], 
             duration)
        )
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"خطا در ذخیره گزارش: {e}")

def get_memory_usage():
    """دریافت میزان مصرف حافظه"""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024  # MB
    except:
        return 0

# ==================== MAIN ====================

if __name__ == '__main__':
    init_db()
    app_start_time = time.time()
    print("🚀 سرور ربات ایتا در حال راه‌اندازی...")
    print("🌐 آدرس دسترسی: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
