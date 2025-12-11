# backend/app.py
import os
import time
import threading
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from bot_core import EitaaBot, convert_phone_number_format

app = Flask(__name__, template_folder='../frontend', static_folder='../frontend')
CORS(app)

# --- Configuration ---
app.config.update(
    SECRET_KEY='eitaa-bot-secret-key-2024',
    UPLOAD_FOLDER='uploads',
    SESSION_FOLDER='sessions',
    BOT_INSTANCES={}
)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['SESSION_FOLDER'], exist_ok=True)
os.makedirs('screenshots', exist_ok=True) # Ensure screenshots folder exists

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/bot/create', methods=['POST'])
def create_bot():
    bot_id = f"bot_{int(time.time() * 1000)}"
    session_file = os.path.join(app.config['SESSION_FOLDER'], f"session_{bot_id}.json")
    headless = request.json.get('headless', True)

    bot = EitaaBot(session_file=session_file, headless=headless)
    app.config['BOT_INSTANCES'][bot_id] = bot

    return jsonify({
        'status': 'success',
        'bot_id': bot_id,
        'is_logged_in': bot.is_logged_in
    })

@app.route('/api/bot/<bot_id>/login', methods=['POST'])
def bot_login(bot_id):
    bot = app.config['BOT_INSTANCES'].get(bot_id)
    if not bot: return jsonify({'error': 'Bot not found'}), 404

    phone_number = request.json.get('phone_number')
    if not phone_number: return jsonify({'error': 'Phone number is required'}), 400

    converted_phone = convert_phone_number_format(phone_number)
    status, detail = bot.login(phone_number=converted_phone)

    if status == "error":
        return jsonify({'error': 'Login failed', 'details': detail}), 500

    return jsonify({'status': status})

@app.route('/api/bot/<bot_id>/submit-code', methods=['POST'])
def submit_code(bot_id):
    bot = app.config['BOT_INSTANCES'].get(bot_id)
    if not bot: return jsonify({'error': 'Bot not found'}), 404

    code = request.json.get('code')
    if not code: return jsonify({'error': 'Verification code is required'}), 400

    status, detail = bot.submit_code(code)

    if status == "login_successful":
        return jsonify({'status': 'success'})
    else:
        return jsonify({
            'error': 'Failed to submit code',
            'details': detail,
        }), 500

# --- Placeholder for other routes ---
@app.route('/api/bot/<bot_id>/send', methods=['POST'])
def send_messages(bot_id):
    # This can be re-implemented later once login is stable
    return jsonify({'status': 'not_implemented'})

@app.route('/api/contacts/upload', methods=['POST'])
def upload_contacts():
    # This can be re-implemented later
    return jsonify({'status': 'not_implemented'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
