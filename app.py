import os
import base64
import time
import threading
import requests
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from io import BytesIO
from PIL import Image
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

app = Flask(__name__)

# Inasoma Secret Key kutoka Render Environment Variables
app.secret_key = os.environ.get("SECRET_KEY", "MUST_SUPER_PREFS_2026_FLASK_KEY")

# Google OAuth Credentials kutoka Render Environment Variables
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

# Title Mpya
APP_NAME = "Elixa Smart Diagram & Architecture AI"

# Inasoma API Keys kutoka Render Environment Variables (inaweza kusoma key zaidi ya moja)
GEMINI_KEYS = [
    key for key in [
        os.environ.get("GEMINI_API_KEY"),
        os.environ.get("GEMINI_API_KEY_2"),
        os.environ.get("GEMINI_API_KEY_3")
    ] if key
]

# Decorator ya kuzuia mtumiaji asitumie mfumo bila kulogin na Google
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Unauthorized. Tafadhali ingia na Google kwanza ili kutumia huduma hii."}), 401
        return f(*args, **kwargs)
    return decorated_function

# Keep-Alive Self-Ping Mechanism (Kuzuia Server Isilale)
def start_keep_alive():
    """Inagonga server kila baada ya dakika 10 ili kuzuia Render Free Tier isilale."""
    def ping_self():
        # Render inatoa URL kwenye env variable ya RENDER_EXTERNAL_URL otomatiki
        server_url = os.environ.get("RENDER_EXTERNAL_URL", "http://127.0.0.1:5000")
        ping_endpoint = f"{server_url.rstrip('/')}/ping"
        
        # Subiri sekunde 15 server iwe tayari kabla ya ping ya kwanza
        time.sleep(15)
        
        while True:
            try:
                response = requests.get(ping_endpoint, timeout=10)
                print(f"[Keep-Alive] Ping sent to {ping_endpoint} | Status: {response.status_code}")
            except Exception as e:
                print(f"[Keep-Alive] Ping failed: {e}")
            
            # Subiri dakika 10 (sekunde 600) kabla ya kugonga tena
            time.sleep(600)

    thread = threading.Thread(target=ping_self, daemon=True)
    thread.start()

# Anzisha Keep-Alive Thread
start_keep_alive()

@app.route("/ping", methods=["GET"])
def ping():
    """Endpoint nyepesi inayopokea pings ili kuweka server alive"""
    return jsonify({"status": "alive", "timestamp": time.time()}), 200

def get_expert_instruction():
    """Prompt Mpya ya Expert Systems Architect & Diagram Generator"""
    return (
        "You are an expert Systems Architect, Software Engineer, and Technical Visualizer AI.\n\n"
        "Your task is to analyze user requests or diagrams/images, provide clear technical explanations, "
        "and generate clean, perfectly valid Mermaid.js diagrams whenever applicable.\n\n"
        "STRICT MERMAID GENERATION RULES:\n"
        "1. Whenever you generate a diagram, ALWAYS wrap it strictly inside standard Markdown code blocks: ```mermaid <code here> ```.\n"
        "2. Keep the Mermaid code clean, robust, and free of syntax errors. Avoid special characters inside node labels unless properly quoted.\n"
        "3. Supported diagram types include: flowchart, sequenceDiagram, classDiagram, erDiagram, stateDiagram, or gantt as appropriate.\n"
        "4. Along with the diagram code, provide concise, professional natural language explanations detailing the architecture, process flow, or component interaction.\n"
        "5. If an image is provided, analyze its technical workflow, flowchart, or wireframe and explain or reconstruct it using valid Mermaid code.\n\n"
        "Keep responses clean, structured, clear, and easy to render on modern web UIs."
    )

def compress_image(image_bytes):
    """Resizes and compresses image to max 1024x1024, similar to Android's inSampleSize logic"""
    try:
        img = Image.open(BytesIO(image_bytes))
        # Keep transparency support if converting to JPEG
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        
        # Max dimensions matching reqWidth and reqHeight (1024)
        img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        
        output = BytesIO()
        img.save(output, format="JPEG", quality=80)
        return output.getvalue()
    except Exception as e:
        print("Compression error:", e)
        return None

def call_gemini_api(history, key_index=0):
    if not GEMINI_KEYS:
        return {"error": "API Key haijawekwa kwenye Render Environment Variables."}

    if key_index >= len(GEMINI_KEYS):
        return {"error": "Mfumo umezidiwa au keys zote hazina salio. Jaribu tena."}

    api_key = GEMINI_KEYS[key_index]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": history}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        
        if response.status_code == 429:
            # Fallback to the next key recursively if ratelimited
            return call_gemini_api(history, key_index + 1)
            
        if response.status_code == 200:
            data = response.json()
            try:
                ai_response = data["candidates"][0]["content"]["parts"][0]["text"]
                return {"success": True, "text": ai_response}
            except Exception as e:
                return {"error": "Imeshindwa kusoma matokeo kutoka kwa AI."}
        else:
            return {"error": f"Hitilafu kutoka Gemini API: {response.status_code}"}
            
    except requests.exceptions.RequestException:
        return {"error": "Hitilafu ya mtandao imetokea."}

# ================= AUTHENTICATION ROUTES =================

@app.route("/")
def index():
    if "chat_history" not in session:
        session["chat_history"] = []

    user_info = {
        "is_logged_in": "user_id" in session,
        "name": session.get("user_name", ""),
        "email": session.get("user_email", ""),
        "picture": session.get("user_picture", "")
    }

    return render_template(
        "index.html", 
        app_name=APP_NAME, 
        user=user_info, 
        google_client_id=GOOGLE_CLIENT_ID
    )

@app.route("/login/google", methods=["POST"])
def google_login():
    """Verify Google ID Token from Google Sign-In Client"""
    data = request.json or {}
    token = data.get("credential")
    if not token:
        return jsonify({"error": "Credential token haijapatikana."}), 400

    try:
        id_info = id_token.verify_oauth2_token(
            token, 
            google_requests.Request(), 
            GOOGLE_CLIENT_ID
        )

        session["user_id"] = id_info.get("sub")
        session["user_name"] = id_info.get("name", "Mbunifu")
        session["user_email"] = id_info.get("email", "")
        session["user_picture"] = id_info.get("picture", "")
        
        # Initialize user-bound chat history
        session["chat_history"] = [
            {
                "role": "user",
                "parts": [{"text": f"SYSTEM INSTRUCTION: {get_expert_instruction()}"}]
            }
        ]

        return jsonify({
            "status": "success",
            "user_name": session["user_name"],
            "user_email": session["user_email"],
            "user_picture": session["user_picture"]
        })

    except ValueError:
        return jsonify({"error": "Google Token si sahihi au imekwisha muda wake."}), 400

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "success", "message": "Umetoka kwenye akaunti kikamilifu."})

# ================= PROTECTED APPLICATION ROUTES =================

@app.route("/set_name", methods=["POST"])
@login_required
def set_name():
    data = request.json or {}
    name = data.get("name", "").strip()
    if not name:
        name = session.get("user_name", "Mbunifu")
    session["user_name"] = name
    
    # Initialize system session history
    session["chat_history"] = [
        {
            "role": "user",
            "parts": [{"text": f"SYSTEM INSTRUCTION: {get_expert_instruction()}"}]
        }
    ]
    
    welcome_msg = f"Habari {name}! Mimi ni msaidizi wako wa kuchora na kuchanganua michoro ya mfumo (System Architecture & Diagrams). Niambie ungependa kuchora mfumo gani leo au pakia picha ya mchoro ulio nao."
    
    return jsonify({
        "status": "success", 
        "user_name": name, 
        "welcome_message": welcome_msg
    })

@app.route("/process", methods=["POST"])
@login_required
def process():
    user_prompt = request.form.get("prompt", "").strip()
    image_file = request.files.get("image")
    
    history = session.get("chat_history", [])
    
    # Ensure system instruction is first if history was somehow empty
    if not history:
        history.append({
            "role": "user",
            "parts": [{"text": f"SYSTEM INSTRUCTION: {get_expert_instruction()}"}]
        })

    # Case 1: Image Upload (with optional text prompt)
    if image_file and image_file.filename != '':
        mime_type = image_file.content_type or "image/jpeg"
        raw_bytes = image_file.read()
        compressed_bytes = compress_image(raw_bytes)
        
        if not compressed_bytes:
            return jsonify({"error": "Imeshindwa kusoma na kubana picha hii."}), 400
            
        base64_data = base64.b64encode(compressed_bytes).decode("utf-8")
        
        parts = [
            {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": base64_data
                }
            },
            {
                "text": user_prompt if user_prompt else "Analyze this architectural/flow diagram image, explain it clearly, and generate equivalent Mermaid code."
            }
        ]
        
        history.append({
            "role": "user",
            "parts": parts
        })
        
    # Case 2: Only Text Prompt Input
    elif user_prompt:
        history.append({
            "role": "user",
            "parts": [{"text": user_prompt}]
        })
    else:
        return jsonify({"error": "Tafadhali ingiza ujumbe au weka picha."}), 400

    # Prune history to max 20 turns
    if len(history) > 20:
        history = history[-20:]

    # Request Gemini execution
    result = call_gemini_api(history)
    
    if "error" in result:
        return jsonify({"error": result["error"]}), 500
        
    ai_response = result["text"]
    
    # Commit AI response to dynamic chat session
    history.append({
        "role": "model",
        "parts": [{"text": ai_response}]
    })
    session["chat_history"] = history
    session.modified = True
    
    return jsonify({
        "success": True, 
        "response": ai_response
    })

@app.route("/clear", methods=["POST"])
@login_required
def clear_history():
    session["chat_history"] = []
    session.modified = True
    return jsonify({"status": "success", "message": "History imefutwa!"})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
