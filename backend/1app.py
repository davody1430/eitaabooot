# backend/app.py - نسخه کامل با پشتیبانی از ربات‌های مختلف
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import os
import json
import threading
import time
import random
from datetime import datetime
from bot_core import EitaaBot
import sqlite3
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder='../frontend', static_folder='../frontend')
CORS(app)

# تنظیمات
app.config['SECRET_KEY'] = 'eitaa-bot-secret-key-2024'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
app.config['SESSION_FOLDER'] = 'sessions'
app.config['BOT_INSTANCES'] = {}

# ایجاد پوشه‌ها
for folder in [app.config['UPLOAD_FOLDER'], app.config['SESSION_FOLDER']]:
    os.makedirs(folder, exist_ok=True)

# دیتابیس ساده
def init_db():
    conn = sqlite3.connect('eitaa_bot.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            source TEXT,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sent_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            status TEXT,
            message TEXT,
            sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # تنظیمات پیش‌فرض
    default_settings = [
        ('min_delay', '2.0'),
        ('max_delay', '5.0'),
        ('message_text', 'سلام [نام] عزیز،\nاین پیام از طرف [سازمان] است.\nبا تشکر'),
        ('max_per_hour', '100'),
        ('auto_break', '50'),
        ('session_saved', 'false')
    ]

    for key, value in default_settings:
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))

    conn.commit()
    conn.close()

# تابع کمکی برای تبدیل شماره تلفن
def convert_phone_number_format(phone_number_str):
    from bot_core import convert_phone_number_format
    return convert_phone_number_format(phone_number_str)

# API Endpoints
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/settings', methods=['GET'])
def get_settings():
    conn = sqlite3.connect('eitaa_bot.db')
    cursor = conn.cursor()

    cursor.execute('SELECT key, value FROM settings')
    settings = {row[0]: row[1] for row in cursor.fetchall()}

    conn.close()
    return jsonify(settings)

@app.route('/api/settings', methods=['POST'])
def save_settings():
    data = request.json
    conn = sqlite3.connect('eitaa_bot.db')
    cursor = conn.cursor()

    for key, value in data.items():
        cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value)
            VALUES (?, ?)
        ''', (key, str(value)))

    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/api/bot/create', methods=['POST'])
def create_bot():
    """ایجاد یک نمونه ربات جدید"""
    try:
        bot_id = request.json.get('bot_id', str(int(time.time())))
        min_delay = float(request.json.get('min_delay', 2.0))
        max_delay = float(request.json.get('max_delay', 5.0))
        headless = request.json.get('headless', False)

        bot = EitaaBot(
            min_delay=min_delay,
            max_delay=max_delay,
            session_file=f"{app.config['SESSION_FOLDER']}/session_{bot_id}.pkl",
            headless=headless
        )

        app.config['BOT_INSTANCES'][bot_id] = bot

        return jsonify({
            'status': 'success',
            'bot_id': bot_id,
            'message': 'ربات ایجاد شد'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/<bot_id>/login', methods=['POST'])
def bot_login(bot_id):
    """لاگین ربات"""
    if bot_id not in app.config['BOT_INSTANCES']:
        return jsonify({'error': 'ربات پیدا نشد'}), 404

    bot = app.config['BOT_INSTANCES'][bot_id]
    phone_number = request.json.get('phone_number')

    if not phone_number:
        return jsonify({'error': 'شماره تلفن الزامی است'}), 400

    try:
        # تبدیل شماره تلفن
        converted_phone = convert_phone_number_format(phone_number)

        result = bot.login(phone_number=converted_phone)

        if result == "waiting_for_user":
            return jsonify({
                'status': 'waiting',
                'message': 'لطفاً در مرورگر کد تأیید را وارد کنید'
            })
        elif result:
            return jsonify({
                'status': 'success',
                'message': 'لاگین موفقیت‌آمیز بود'
            })
        else:
            return jsonify({'error': 'لاگین ناموفق'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/<bot_id>/confirm-login', methods=['POST'])
def confirm_login(bot_id):
    """تأیید لاگین دستی"""
    if bot_id not in app.config['BOT_INSTANCES']:
        return jsonify({'error': 'ربات پیدا نشد'}), 404

    bot = app.config['BOT_INSTANCES'][bot_id]

    try:
        success = bot.confirm_login()

        if success:
            return jsonify({
                'status': 'success',
                'message': 'لاگین تأیید شد'
            })
        else:
            return jsonify({'error': 'لاگین تأیید نشد'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/<bot_id>/send', methods=['POST'])
def send_messages(bot_id):
    """ارسال پیام‌ها"""
    if bot_id not in app.config['BOT_INSTANCES']:
        return jsonify({'error': 'ربات پیدا نشد'}), 404

    bot = app.config['BOT_INSTANCES'][bot_id]
    data = request.json

    send_type = data.get('type', 'excel')  # excel, group_message, combined
    message = data.get('message', '')
    excel_path = data.get('excel_path', '')
    group_name = data.get('group_name', '')
    message_prefix = data.get('message_prefix', '')

    # جمع‌آوری مخاطبان بر اساس نوع
    usernames = []

    if send_type in ['excel', 'combined'] and excel_path:
        usernames.extend(bot.read_usernames_from_excel(excel_path))

    if send_type in ['group_message', 'combined'] and group_name and message_prefix:
        group_usernames = bot.extract_usernames_from_group_message(group_name, message_prefix)
        usernames.extend(group_usernames)

    if not usernames:
        return jsonify({'error': 'هیچ مخاطبی یافت نشد'}), 400

    # حذف تکراری‌ها
    usernames = list(set(usernames))

    # شروع ارسال در تابع جداگانه
    def send_thread():
        success_count = 0
        fail_count = 0

        for i, username in enumerate(usernames):
            try:
                success = bot.send_direct_message(username, message)
                if success:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                fail_count += 1
                print(f"خطا در ارسال به {username}: {e}")

        print(f"ارسال کامل شد: {success_count} موفق، {fail_count} ناموفق")

    thread = threading.Thread(target=send_thread, daemon=True)
    thread.start()

    return jsonify({
        'status': 'started',
        'total': len(usernames),
        'message': f'ارسال به {len(usernames)} مخاطب شروع شد'
    })

@app.route('/api/bot/<bot_id>/status', methods=['GET'])
def bot_status(bot_id):
    """وضعیت ربات"""
    if bot_id not in app.config['BOT_INSTANCES']:
        return jsonify({'error': 'ربات پیدا نشد'}), 404

    bot = app.config['BOT_INSTANCES'][bot_id]

    return jsonify({
        'is_logged_in': bot.is_logged_in,
        'min_delay': bot.min_delay,
        'max_delay': bot.max_delay
    })

@app.route('/api/bot/<bot_id>/close', methods=['POST'])
def close_bot(bot_id):
    """بستن ربات"""
    if bot_id not in app.config['BOT_INSTANCES']:
        return jsonify({'error': 'ربات پیدا نشد'}), 404

    bot = app.config['BOT_INSTANCES'][bot_id]
    bot.close()

    if bot_id in app.config['BOT_INSTANCES']:
        del app.config['BOT_INSTANCES'][bot_id]

    return jsonify({'status': 'success', 'message': 'ربات بسته شد'})

# سایر endpointها مانند قبل باقی می‌مانند
@app.route('/api/contacts', methods=['GET'])
def get_contacts():
    # ... (کد قبلی)
    pass

@app.route('/api/contacts/upload', methods=['POST'])
def upload_contacts():
    # ... (کد قبلی)
    pass

@app.route('/api/bot/start', methods=['POST'])
def start_bot():
    # این endpoint قدیمی، برای سازگاری نگه داشته شده
    return create_bot()

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)