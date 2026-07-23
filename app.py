import os
import base64
import requests
from flask import Flask, render_template, request, jsonify, session
from io import BytesIO
from PIL import Image

app = Flask(__name__)
# Inasoma Secret Key kutoka Render Environment Variables, au inatumia default ikiwa haipo
app.secret_key = os.environ.get("SECRET_KEY", "MUST_SUPER_PREFS_2026_FLASK_KEY")

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

@app.route("/")
def index():
    if "chat_history" not in session:
        session["chat_history"] = []
    return render_template("index.html", app_name=APP_NAME)

@app.route("/set_name", methods=["POST"])
def set_name():
    data = request.json or {}
    name = data.get("name", "").strip()
    if not name:
        name = "Mbunifu"
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
def clear_history():
    session["chat_history"] = []
    session.modified = True
    return jsonify({"status": "success", "message": "History imefutwa!"})

if __name__ == "__main__":
    app.run(debug=True, port=5000)