# backend/app.py
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/bot/create', methods=['POST'])
def create_bot():
    bot_id = request.json.get('bot_id', f"bot_{int(time.time() * 1000)}")
    session_file = os.path.join(app.config['SESSION_FOLDER'], f"session_{bot_id}.json")
    headless = request.json.get('headless', True)

    bot = EitaaBot(session_file=session_file, headless=headless)
    app.config['BOT_INSTANCES'][bot_id] = bot

    return jsonify({'status': 'success', 'bot_id': bot_id, 'is_logged_in': bot.is_logged_in})

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
        return jsonify({'status': result})
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
        usernames = bot.extract_usernames_from_group_message(group_name, message_prefix)

    if not usernames:
        return jsonify({'error': 'No usernames found to send messages to'}), 400

    def send_task(users, msg):
        bot.send_bulk_direct_messages(users, msg)

    # Running in a separate thread to avoid blocking the request
    import threading
    thread = threading.Thread(target=send_task, args=(usernames, message), daemon=True)
    thread.start()

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
    app.run(host='0.0.0.0', port=5000)
