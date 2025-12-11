# backend/app.py
import threading
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import os
from bot_core import EitaaBot, convert_phone_number_format
import time

app = Flask(__name__, template_folder='../frontend', static_folder='../frontend')
CORS(app)

app.config.update(
    SECRET_KEY='eitaa-bot-secret-key-2024',
    SESSION_FOLDER='sessions',
    BOT_INSTANCES={}
)
os.makedirs(app.config['SESSION_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/bot/create', methods=['POST'])
def create_bot():
    bot_id = f"bot_{int(time.time() * 1000)}"
    session_file = os.path.join(app.config['SESSION_FOLDER'], f"session_{bot_id}.json")

    bot = EitaaBot(session_file=session_file)
    app.config['BOT_INSTANCES'][bot_id] = bot

    return jsonify({'status': 'success', 'bot_id': bot_id})

@app.route('/api/bot/<bot_id>/login', methods=['POST'])
def bot_login(bot_id):
    bot = app.config['BOT_INSTANCES'].get(bot_id)
    if not bot:
        return jsonify({'error': 'Bot not found'}), 404

    phone_number = request.json.get('phone_number')
    if not phone_number:
        return jsonify({'error': 'Phone number is required'}), 400

    converted_phone = convert_phone_number_format(phone_number)

    # This will be a long-running request.
    # It's better to run it in a thread to not block other potential server activities.
    result = {}
    def login_task():
        res = bot.launch_and_wait_for_login(converted_phone)
        result['status'] = res

    thread = threading.Thread(target=login_task)
    thread.start()

    # We don't wait for the thread to finish here.
    # The frontend will just assume it started.
    # A more advanced implementation would use websockets or status polling.
    return jsonify({'status': 'login_process_started'})

# All other routes can be re-implemented later
# For now, focus is on solving the login issue definitively

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
