# backend/app.py - Updated for Playwright and new login flow
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import os
import threading
import time
from bot_core import EitaaBot
import sqlite3
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder='../frontend', static_folder='../frontend')
CORS(app)

# Settings
app.config['SECRET_KEY'] = 'eitaa-bot-secret-key-2024'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SESSION_FOLDER'] = 'sessions'
app.config['BOT_INSTANCES'] = {}
app.config['SEND_STATS'] = {}

for folder in [app.config['UPLOAD_FOLDER'], app.config['SESSION_FOLDER']]:
    os.makedirs(folder, exist_ok=True)

# Database Initialization
def init_db():
    conn = sqlite3.connect('eitaa_bot.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS contacts (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, source TEXT, added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS sent_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, status TEXT, message TEXT, sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    default_settings = [('min_delay', '2.0'), ('max_delay', '5.0'), ('message_text', 'سلام [نام] عزیز'), ('session_saved', 'false')]
    for key, value in default_settings:
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def convert_phone_number_format(phone_number_str):
    from bot_core import convert_phone_number_format
    return convert_phone_number_format(phone_number_str)

# API Endpoints
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    conn = sqlite3.connect('eitaa_bot.db')
    cursor = conn.cursor()
    if request.method == 'GET':
        cursor.execute('SELECT key, value FROM settings')
        settings = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        return jsonify(settings)
    else: # POST
        data = request.json
        for key, value in data.items():
            cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})

@app.route('/api/bot/create', methods=['POST'])
def create_bot():
    bot_id = request.json.get('bot_id', str(int(time.time())))
    session_file = f"{app.config['SESSION_FOLDER']}/session_{bot_id}.json"
    from queue import Queue
    log_queue = Queue()
    bot = EitaaBot(session_file=session_file, headless=True, log_queue=log_queue)
    app.config['BOT_INSTANCES'][bot_id] = bot
    return jsonify({'status': 'success', 'bot_id': bot_id})

@app.route('/api/bot/<bot_id>/login', methods=['POST'])
def bot_login(bot_id):
    if bot_id not in app.config['BOT_INSTANCES']:
        return jsonify({'error': 'Bot not found'}), 404

    bot = app.config['BOT_INSTANCES'][bot_id]
    phone_number = request.json.get('phone_number')
    if not phone_number:
        return jsonify({'error': 'Phone number is required'}), 400

    try:
        converted_phone = convert_phone_number_format(phone_number)
        result = bot.login(phone_number=converted_phone)

        if result == "waiting_for_code":
            return jsonify({'status': 'waiting_for_code', 'message': 'Please enter the verification code.'})
        elif result == "already_logged_in":
            return jsonify({'status': 'success', 'message': 'Already logged in.'})
        else:
            return jsonify({'error': 'Login failed', 'details': result}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/<bot_id>/submit-code', methods=['POST'])
def submit_code(bot_id):
    if bot_id not in app.config['BOT_INSTANCES']:
        return jsonify({'error': 'Bot not found'}), 404

    bot = app.config['BOT_INSTANCES'][bot_id]
    code = request.json.get('code')
    if not code:
        return jsonify({'error': 'Verification code is required'}), 400

    try:
        result = bot.submit_code(code)
        if result == "login_successful":
            return jsonify({'status': 'success', 'message': 'Login successful.'})
        else:
            return jsonify({'error': 'Failed to submit code', 'details': result}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/<bot_id>/send', methods=['POST'])
def send_messages(bot_id):
    if bot_id not in app.config['BOT_INSTANCES']:
        return jsonify({'error': 'Bot not found'}), 404

    bot = app.config['BOT_INSTANCES'][bot_id]
    if not bot.is_logged_in:
        return jsonify({'error': 'Bot is not logged in'}), 403

    data = request.json
    message = data.get('message', '')
    send_type = data.get('type')
    usernames = []

    if send_type == 'excel':
        excel_path = data.get('excel_path', '')
        if not excel_path or not os.path.exists(excel_path):
            return jsonify({'error': 'Excel file path is missing or invalid'}), 400
        usernames = bot.read_usernames_from_excel(excel_path)
        if not usernames:
            return jsonify({'error': 'No usernames found in the Excel file'}), 400
    elif send_type == 'group_message':
        group_name = data.get('group_name')
        message_prefix = data.get('message_prefix')
        if not group_name or not message_prefix:
            return jsonify({'error': 'Group name and message prefix are required'}), 400
        usernames = bot.extract_usernames_from_group_message(group_name, message_prefix)
        if not usernames:
            return jsonify({'error': 'No usernames found for the given group and prefix'}), 400
    else:
        return jsonify({'error': 'Invalid send type specified'}), 400

    # Initialize stats for this bot
    app.config['SEND_STATS'][bot_id] = {
        'total': len(usernames),
        'sent': 0,
        'success': 0,
        'error': 0,
        'is_running': True,
        'logs': []
    }

    def send_thread():
        stats = app.config['SEND_STATS'][bot_id]
        while not bot.log_queue.empty():
            stats['logs'].append(bot.log_queue.get())

        for username in usernames:
            if not stats['is_running']:
                stats['logs'].append("Sending stopped by user.")
                break
            success = bot.send_direct_message(username, message)
            stats['sent'] += 1
            if success:
                stats['success'] += 1
            else:
                stats['error'] += 1

            while not bot.log_queue.empty():
                stats['logs'].append(bot.log_queue.get())

        stats['is_running'] = False
        stats['logs'].append("Sending process finished.")

    thread = threading.Thread(target=send_thread, daemon=True)
    thread.start()

    return jsonify({'status': 'started', 'total': len(usernames)})

@app.route('/api/bot/<bot_id>/send/status', methods=['GET'])
def send_status(bot_id):
    stats = app.config['SEND_STATS'].get(bot_id)
    if not stats:
        return jsonify({'error': 'No sending process found for this bot'}), 404
    return jsonify(stats)

@app.route('/api/bot/<bot_id>/send/stop', methods=['POST'])
def stop_sending(bot_id):
    stats = app.config['SEND_STATS'].get(bot_id)
    if stats:
        stats['is_running'] = False
        return jsonify({'status': 'stopping'})
    return jsonify({'error': 'No sending process to stop'}), 404

@app.route('/api/bot/<bot_id>/status', methods=['GET'])
def bot_status(bot_id):
    if bot_id not in app.config['BOT_INSTANCES']:
        return jsonify({'error': 'Bot not found'}), 404
    bot = app.config['BOT_INSTANCES'][bot_id]
    return jsonify({'is_logged_in': bot.is_logged_in})

@app.route('/api/bot/<bot_id>/close', methods=['POST'])
def close_bot(bot_id):
    if bot_id not in app.config['BOT_INSTANCES']:
        return jsonify({'error': 'Bot not found'}), 404
    bot = app.config['BOT_INSTANCES'][bot_id]
    bot.close()
    del app.config['BOT_INSTANCES'][bot_id]
    return jsonify({'status': 'success'})

@app.route('/api/contacts/upload', methods=['POST'])
def upload_contacts():
    if 'file' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'File name is empty'}), 400
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        return jsonify({'status': 'success', 'filepath': filepath})
    return jsonify({'error': 'Unknown error during file upload'}), 500

if __name__ == '__main__':
    init_db()
    # **اصلاح حیاتی: اجرای تک رشته‌ای برای Playwright**
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=False)
