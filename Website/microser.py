# microser.py
# Requirements: pip install flask requests
import os, time, threading, logging, json
from typing import Dict, Any
from flask import Flask, request, jsonify, send_file
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("microser")

CORAL_URL = os.getenv("CORAL_URL", "http://127.0.0.1:5555")
TIMEOUT_SECONDS = int(os.getenv("SEARCH_TIMEOUT", "25"))
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "session-template.json")

app = Flask(__name__, static_folder=".", static_url_path="")

def load_template() -> Dict[str, Any]:
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def create_session_on_coral(template: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{CORAL_URL}/api/v1/sessions"
    headers = {"Content-Type": "application/json"}
    r = requests.post(url, json=template, headers=headers, timeout=15)
    logger.info("Coral returned: %s %s", r.status_code, r.text[:500])
    r.raise_for_status()
    return r.json()

@app.route("/", methods=["GET"])
def index():
    return send_file("index.html")

@app.route("/search", methods=["POST"])
def search():
    try:
        template = load_template()
        resp = create_session_on_coral(template)
        return jsonify({"ok": True, "result": resp})
    except Exception as e:
        logger.exception("Session create failed")
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    logger.info("Starting microser on http://127.0.0.1:5000 (CORAL_URL=%s)", CORAL_URL)
    app.run(host="127.0.0.1", port=5000, debug=True)