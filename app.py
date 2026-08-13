import os
import base64
import time
import threading
import requests
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from io import BytesIO
from PIL import Image

app = Flask(__name__)

# Secret Key - Inasoma kutoka Environment Variables
app.secret_key = os.environ.get("SECRET_KEY", "SSMS_TANZANIA_2026_FLASK_KEY")

# Title Mpya - SSMS Tanzania AI
APP_NAME = "SSMS Tanzania AI - Smart Education Assistant"

# Inasoma API Keys kutoka Environment Variables
GEMINI_KEYS = [
    key for key in [
        os.environ.get("GEMINI_API_KEY"),
        os.environ.get("GEMINI_API_KEY_2"),
        os.environ.get("GEMINI_API_KEY_3")
    ] if key
]

# =============================================
# KEEP-ALIVE SELF-PING MECHANISM
# =============================================
def start_keep_alive():
    """Inagonga server kila baada ya dakika 10 ili kuzuia Render Free Tier isilale."""
    def ping_self():
        server_url = os.environ.get("RENDER_EXTERNAL_URL", "http://127.0.0.1:5000")
        ping_endpoint = f"{server_url.rstrip('/')}/ping"
        
        time.sleep(15)
        
        while True:
            try:
                response = requests.get(ping_endpoint, timeout=10)
                print(f"[Keep-Alive] Ping sent to {ping_endpoint} | Status: {response.status_code}")
            except Exception as e:
                print(f"[Keep-Alive] Ping failed: {e}")
            
            time.sleep(600)

    thread = threading.Thread(target=ping_self, daemon=True)
    thread.start()

# Anzisha Keep-Alive Thread
start_keep_alive()

@app.route("/ping", methods=["GET"])
def ping():
    """Endpoint nyepesi inayopokea pings ili kuweka server alive"""
    return jsonify({"status": "alive", "timestamp": time.time()}), 200

# =============================================
# PROMPT MPYA - SSMS TANZANIA AI
# =============================================
def get_expert_instruction():
    """Prompt mpya ya SSMS Tanzania AI - Msaidizi wa Walimu na Wanafunzi"""
    return (
        "You are SSMS Tanzania AI, an expert AI teaching assistant designed specifically for Tanzanian students, teachers, and schools.\n\n"
        "YOUR ROLE:\n"
        "1. TEACHING ASSISTANT: Help teachers prepare lesson notes, lesson plans, teaching materials, and assessment questions.\n"
        "2. STUDENT TUTOR: Help students understand difficult concepts, answer homework questions, explain topics clearly, and provide study tips.\n"
        "3. CURRICULUM SUPPORT: Provide guidance on Tanzanian curriculum (Primary and Secondary) subjects including Mathematics, English, Kiswahili, Science, Social Studies, History, Geography, Biology, Chemistry, Physics, and Civics.\n"
        "4. EXAM PREPARATION: Help students prepare for national exams (PSLE, CSEE, ACSEE) by providing practice questions, revision tips, and exam strategies.\n"
        "5. LESSON PLANNING: Help teachers create structured lesson plans with objectives, activities, teaching aids, and assessment methods.\n\n"
        "RESPONSE STYLE:\n"
        "- Use clear, simple language that is easy for students to understand.\n"
        "- Use examples and real-world contexts that are relevant to Tanzania.\n"
        "- When appropriate, break down complex topics into simple steps.\n"
        "- Encourage critical thinking and active learning.\n"
        "- Be supportive, encouraging, and patient.\n\n"
        "When a teacher asks for lesson notes, provide:\n"
        "- Topic title and grade level\n"
        "- Learning objectives\n"
        "- Key concepts and vocabulary\n"
        "- Main content with clear explanations\n"
        "- Activities for students\n"
        "- Assessment questions (short answer, multiple choice)\n\n"
        "When a student asks for help with a subject:\n"
        "- Explain concepts simply and clearly\n"
        "- Provide step-by-step solutions for problems\n"
        "- Give examples and analogies\n"
        "- Offer additional practice questions\n"
        "- Encourage them with positive feedback\n\n"
        "If an image/diagram is provided, analyze it and explain it in detail.\n\n"
        "Always respond in natural, conversational language. If the user asks in Swahili, respond in Swahili. If in English, respond in English."
    )

# =============================================
# IMAGE COMPRESSION FUNCTION
# =============================================
def compress_image(image_bytes):
    """Resizes and compresses image to max 1024x1024"""
    try:
        img = Image.open(BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        
        img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        
        output = BytesIO()
        img.save(output, format="JPEG", quality=80)
        return output.getvalue()
    except Exception as e:
        print("Compression error:", e)
        return None

# =============================================
# GEMINI API CALL FUNCTION
# =============================================
def call_gemini_api(history, key_index=0):
    if not GEMINI_KEYS:
        return {"error": "SSMS Tanzania AI inaandaliwa kwa sasa. Tafadhali jaribu tena baada ya muda mfupi."}

    if key_index >= len(GEMINI_KEYS):
        return {"error": "SSMS Tanzania AI inaombwa kwa wingi kwa sasa. Tafadhali subiri sekunde chache kisha jaribu tena."}

    api_key = GEMINI_KEYS[key_index]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": history}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        
        if response.status_code == 429:
            return call_gemini_api(history, key_index + 1)
            
        if response.status_code == 200:
            data = response.json()
            try:
                ai_response = data["candidates"][0]["content"]["parts"][0]["text"]
                return {"success": True, "text": ai_response}
            except Exception:
                return {"error": "SSMS AI haikuweza kuchanganua jibu. Tafadhali jaribu tena."}
        else:
            return {"error": f"Hitilafu: {response.status_code}. Tafadhali jaribu tena."}
            
    except requests.exceptions.RequestException:
        return {"error": "Tatizo la mtandao. Hakikisha mtandao wako uko sawa."}

# =============================================
# APPLICATION ROUTES
# =============================================

@app.route("/")
def index():
    if "chat_history" not in session:
        session["chat_history"] = []

    user_info = {
        "name": session.get("user_name", "Mwalimu")
    }

    return render_template("index.html", app_name=APP_NAME, user=user_info)

@app.route("/set_name", methods=["POST"])
def set_name():
    data = request.json or {}
    name = data.get("name", "").strip()
    if not name:
        name = session.get("user_name", "Mwalimu")
    session["user_name"] = name
    
    session["chat_history"] = [
        {
            "role": "user",
            "parts": [{"text": f"SYSTEM INSTRUCTION: {get_expert_instruction()}"}]
        }
    ]
    
    welcome_msg = (
        f"Karibu {name}! 🎓\n\n"
        "Mimi ni SSMS Tanzania AI - Msaidizi wako wa elimu!\n\n"
        "Ninaweza kukusaidia na:\n"
        "📚 Kuandaa mipango ya masomo (Lesson Plans)\n"
        "📝 Kuunda maswali na majaribio\n"
        "🧠 Kueleza dhana ngumu kwa wanafunzi\n"
        "📖 Kusaidia wanafunzi kwenye masomo yao\n"
        "✅ Kuandaa maelezo ya somo (Lesson Notes)\n"
        "📊 Kukusaidia na tathmini na madaraja\n\n"
        "Niambie ni somo gani au mada gani unahitaji msaada nayo!"
    )
    
    return jsonify({
        "status": "success", 
        "user_name": name, 
        "welcome_message": welcome_msg
    })

@app.route("/process", methods=["POST"])
def process():
    user_prompt = request.form.get("prompt", "").strip()
    image_file = request.files.get("image")
    
    history = session.get("chat_history", [])
    
    if not history:
        history.append({
            "role": "user",
            "parts": [{"text": f"SYSTEM INSTRUCTION: {get_expert_instruction()}"}]
        })

    # Case 1: Image Upload
    if image_file and image_file.filename != '':
        mime_type = image_file.content_type or "image/jpeg"
        raw_bytes = image_file.read()
        compressed_bytes = compress_image(raw_bytes)
        
        if not compressed_bytes:
            return jsonify({"error": "Imeshindwa kusoma picha hii. Jaribu picha nyingine."}), 400
            
        base64_data = base64.b64encode(compressed_bytes).decode("utf-8")
        
        parts = [
            {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": base64_data
                }
            },
            {
                "text": user_prompt if user_prompt else "Tafadhali chambua picha hii na unisaidie kuelewa vizuri."
            }
        ]
        
        history.append({
            "role": "user",
            "parts": parts
        })
        
    # Case 2: Only Text Prompt
    elif user_prompt:
        history.append({
            "role": "user",
            "parts": [{"text": user_prompt}]
        })
    else:
        return jsonify({"error": "Tafadhali ingiza swali lako au weka picha."}), 400

    # Prune history to max 20 turns
    if len(history) > 20:
        history = history[-20:]

    result = call_gemini_api(history)
    
    if "error" in result:
        return jsonify({"error": result["error"]}), 500
        
    ai_response = result["text"]
    
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
def clear_history():
    session["chat_history"] = []
    session.modified = True
    return jsonify({"status": "success", "message": "Mazungumzo yamefutwa!"})

# =============================================
# RUN THE APP
# =============================================
if __name__ == "__main__":
    app.run(debug=True, port=5000)
