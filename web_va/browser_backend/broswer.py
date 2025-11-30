from flask import Flask, request, jsonify, send_file, session, redirect
from flask_cors import CORS
import speech_recognition as sr
import tempfile
import subprocess
import os
import io
from gtts import gTTS
from dotenv import load_dotenv
from agent import ADHDWiz_respond
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials


load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True)

app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

GOOGLE_CLIENT_SECRETS_FILE = "credentials.json"
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar"]
GOOGLE_REDIRECT_URI = "http://localhost:5050/calendar/oauth2callback"

def convert_webm_to_wav(webm_path, wav_path):
    """Convert WebM → WAV using ffmpeg"""
    subprocess.run([
        "ffmpeg", "-y",
        "-i", webm_path,
        "-ac", "1",             # mono
        "-ar", "16000",         # 16 kHz
        wav_path
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"})

@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    """Convert speech to text"""
    try:
        if 'audio' not in request.files:
            return jsonify({"error": "No audio file"}), 400
        
        # Save WebM temp file
        audio_file = request.files['audio']
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_webm:
            audio_file.save(temp_webm.name)
            webm_path = temp_webm.name

        # Convert to WAV
        wav_path = webm_path.replace('.webm', '.wav')
        convert_webm_to_wav(webm_path, wav_path)

        # Transcribe WAV
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)

        # Cleanup
        os.unlink(webm_path)
        os.unlink(wav_path)

        return jsonify({"text": text})
    
    except sr.UnknownValueError:
        return jsonify({"error": "Could not understand audio"}), 400
    except Exception as e:
        print("Transcription error:", e)
        return jsonify({"error": str(e)}), 500

@app.route('/chat', methods=['POST'])
def chat():
    """Use ADHDWiz agent to respond to user"""
    try:
        msg = request.json.get("message", "")

        if not msg:
            return jsonify({"response": "No message received."})

        ai = ADHDWiz_respond(msg)
        return jsonify({"response": ai})

    except Exception as e:
        print("AI Error:", e)
        return jsonify({"response": "Oops—ADHDWiz lost the thread 😅 try again?"})

@app.route('/speak', methods=['POST'])
def text_to_speech():
    """Convert text to speech"""
    try:
        data = request.json
        text = data.get('text', '')

        if not text:
            return jsonify({"error": "No text provided"}), 400

        tts = gTTS(text=text, lang='en')
        buffer = io.BytesIO()
        tts.write_to_fp(buffer)
        buffer.seek(0)

        return send_file(buffer, mimetype='audio/mpeg')
    
    except Exception as e:
        print("TTS Error:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/calendar/auth")
def calendar_auth():
    """
    Start Google OAuth flow for Calendar.
    User visits this once to connect their Google account.
    """
    try:
        flow = Flow.from_client_secrets_file(
            GOOGLE_CLIENT_SECRETS_FILE,
            scopes=GOOGLE_SCOPES,
            redirect_uri=GOOGLE_REDIRECT_URI,
        )

        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )

        session["oauth_state"] = state
        return redirect(authorization_url)
    
    except Exception as e:
        print(f"OAuth auth error: {e}")
        return f"<h2>OAuth Error</h2><p>{str(e)}</p><p>Make sure credentials.json exists and is valid.</p>", 500


@app.route("/calendar/oauth2callback")
def calendar_oauth2callback():
    """
    Google redirects here after the user approves access.
    We exchange the code for tokens and save them to token.json.
    """
    try:
        state = session.get("oauth_state")
        if not state:
            return "<h2>Error</h2><p>Missing OAuth state. Please start again at <a href='/calendar/auth'>/calendar/auth</a></p>", 400

        flow = Flow.from_client_secrets_file(
            GOOGLE_CLIENT_SECRETS_FILE,
            scopes=GOOGLE_SCOPES,
            redirect_uri=GOOGLE_REDIRECT_URI,
            state=state,
        )

        flow.fetch_token(authorization_response=request.url)
        creds = flow.credentials

        # Save credentials to token.json so calendar_tool.py can use them
        with open("token.json", "w") as token_file:
            token_file.write(creds.to_json())

        return (
            "<h2>Google Calendar connected ✅</h2>"
            "<p>You can close this tab and go back to ADHDWiz.</p>"
        )
    
    except Exception as e:
        print(f"OAuth callback error: {e}")
        return f"<h2>OAuth Error</h2><p>{str(e)}</p><p>Please try again at <a href='/calendar/auth'>/calendar/auth</a></p>", 500


if __name__ == '__main__':
    app.run(debug=True, port=5050)