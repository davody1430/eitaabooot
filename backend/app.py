# backend/app.py
import asyncio
import threading
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import os
from bot_core import EitaaBot, convert_phone_number_format
import time
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder='../frontend', static_folder='../frontend')
CORS(app)

app.config.update(
    SECRET_KEY='eitaa-bot-secret-key-2024',
    UPLOAD_FOLDER='uploads',
    SESSION_FOLDER='sessions',
    BOT_INSTANCES={}
)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['SESSION_FOLDER'], exist_ok=True)

# --- asyncio event loop management ---
def run_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

loop = asyncio.new_event_loop()
t = threading.Thread(target=run_async_loop, args=(loop,), daemon=True)
t.start()
# ------------------------------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/bot/create', methods=['POST'])
def create_bot():
    bot_id = request.json.get('bot_id', f"bot_{int(time.time() * 1000)}")
    session_file = os.path.join(app.config['SESSION_FOLDER'], f"session_{bot_id}.json")
    headless = request.json.get('headless', True)

    if bot_id in app.config['BOT_INSTANCES']:
        old_bot = app.config['BOT_INSTANCES'][bot_id]
        asyncio.run_coroutine_threadsafe(old_bot.close(), loop)

    bot = EitaaBot(session_file=session_file, headless=headless)
    app.config['BOT_INSTANCES'][bot_id] = bot

    asyncio.run_coroutine_threadsafe(bot.start(), loop)

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

        future = asyncio.run_coroutine_threadsafe(bot.login(phone_number=converted_phone), loop)
        result = future.result()

        if result == "waiting_for_code":
            return jsonify({'status': 'waiting_for_code'})
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
        future = asyncio.run_coroutine_threadsafe(bot.submit_code(code), loop)
        result = future.result()

        if result == "login_successful":
            return jsonify({'status': 'success'})
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
    send_type = data.get('type')
    message = data.get('message')

    usernames = []
    if send_type == 'excel':
        excel_path = data.get('excel_path')
        if not excel_path or not os.path.exists(excel_path):
            return jsonify({'error': 'Excel file path is missing or invalid'}), 400
        usernames = bot.read_usernames_from_excel(excel_path)
    elif send_type == 'group_message':
        group_name = data.get('group_name')
        message_prefix = data.get('message_prefix')
        if not group_name or not message_prefix:
            return jsonify({'error': 'Group name and message prefix are required'}), 400

        future = asyncio.run_coroutine_threadsafe(bot.extract_usernames_from_group_message(group_name, message_prefix), loop)
        usernames = future.result()

    if not usernames:
        return jsonify({'error': 'No usernames found to send messages to'}), 400

    async def send_task(users, msg):
        for user in users:
            await bot.send_direct_message(user, msg)

    asyncio.run_coroutine_threadsafe(send_task(usernames, message), loop)

    return jsonify({'status': 'started', 'total': len(usernames)})

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
    app.run(host='0.0.0.0', port=5000, debug=True)
