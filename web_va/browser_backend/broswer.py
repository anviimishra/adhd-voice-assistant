from flask import Flask, request, jsonify, send_file, session, redirect
from flask_cors import CORS
import speech_recognition as sr
import tempfile
import subprocess
import os
import io
import textwrap
from gtts import gTTS
from dotenv import load_dotenv
from agent import ADHDWiz_respond, generate_study_plan_from_syllabus
from tabs_retriever import sync_tabs_snapshot
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None


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
        "-ac", "1",
        "-ar", "16000",
        wav_path
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)


# ---------------------------------------------------------------
# FIX 1: Helper to remove emojis / non-latin1 safely
# ---------------------------------------------------------------
def _to_latin1_safe(value: str) -> str:
    """
    Ensure value can be encoded in latin-1 by replacing unsupported characters
    (e.g., emoji) with '?'.
    """
    return value.encode("latin-1", "replace").decode("latin-1")


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Attempt to extract raw text from a PDF using PyPDF2 if available.
    """
    if not file_bytes or PdfReader is None:
        if PdfReader is None:
            print("PyPDF2 not installed; returning empty syllabus text.")
        return ""

    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        pages_text = []
        for page in reader.pages:
            try:
                pages_text.append(page.extract_text() or "")
            except Exception as page_err:
                print(f"Failed to read PDF page: {page_err}")
        return "\n".join(pages_text)
    except Exception as err:
        print(f"PDF extraction error: {err}")
        return ""


def _escape_pdf_text(value: str) -> str:
    """
    Escape characters for PDF text drawing AND ensure latin1 safe.
    """
    value = _to_latin1_safe(value)
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def render_plan_pdf(plan_text: str) -> bytes:
    """
    Build a very small PDF document containing the study plan text.
    """
    cleaned_text = plan_text.strip() or "Study plan could not be generated."

    # Ensure whole content is latin1-encodable
    cleaned_text = _to_latin1_safe(cleaned_text)

    wrapped_lines = []
    for paragraph in cleaned_text.splitlines():
        if paragraph.strip() == "":
            wrapped_lines.append("")
            continue
        wrapped_lines.extend(textwrap.wrap(paragraph, width=90) or [""])

    if not wrapped_lines:
        wrapped_lines = ["Study plan could not be generated."]

    lines_per_page = 40
    pages = [
        wrapped_lines[i:i + lines_per_page]
        for i in range(0, len(wrapped_lines), lines_per_page)
    ]

    next_obj_id = 1

    def reserve_obj_id():
        nonlocal next_obj_id
        obj_id = next_obj_id
        next_obj_id += 1
        return obj_id

    catalog_id = reserve_obj_id()
    pages_id = reserve_obj_id()
    font_id = reserve_obj_id()

    page_entries = []
    for page_lines in pages:
        content_id = reserve_obj_id()
        page_id = reserve_obj_id()
        page_entries.append((page_id, content_id, page_lines))

    objects = {}

    def set_object(obj_id, data):
        if isinstance(data, bytes):
            objects[obj_id] = data
        else:
            # encode safely into latin-1
            safe = _to_latin1_safe(data)
            objects[obj_id] = safe.encode("latin-1")

    # font
    set_object(font_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    left_margin = 72
    start_height = 760
    line_height = 16

    for page_id, content_id, lines in page_entries:
        buffer_lines = [
            "BT",
            "/F1 12 Tf",
            f"{left_margin} {start_height} Td",
        ]
        first_line = True
        for line in lines:
            if not first_line:
                buffer_lines.append(f"0 -{line_height} Td")
            else:
                first_line = False
            safe_line = _escape_pdf_text(line)
            buffer_lines.append(f"({safe_line}) Tj")
        buffer_lines.append("ET")

        stream_text = "\n".join(buffer_lines)
        stream_data = stream_text.encode("latin-1", "replace")

        content_stream = (
            f"<< /Length {len(stream_data)} >>\nstream\n".encode("latin-1") +
            stream_data +
            b"\nendstream"
        )
        set_object(content_id, content_stream)

        page_obj = (
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        )
        set_object(page_id, page_obj)

    kids_refs = " ".join(f"{page_id} 0 R" for page_id, _, _ in page_entries)
    set_object(pages_id, f"<< /Type /Pages /Kids [{kids_refs}] /Count {len(page_entries)} >>")
    set_object(catalog_id, f"<< /Type /Catalog /Pages {pages_id} 0 R >>")

    pdf_buffer = io.BytesIO()
    pdf_buffer.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    offsets = [0] * next_obj_id

    for obj_id in range(1, next_obj_id):
        offsets[obj_id] = pdf_buffer.tell()
        pdf_buffer.write(f"{obj_id} 0 obj\n".encode("ascii"))
        pdf_buffer.write(objects[obj_id])
        pdf_buffer.write(b"\nendobj\n")

    xref_position = pdf_buffer.tell()
    pdf_buffer.write(f"xref\n0 {next_obj_id}\n".encode("ascii"))
    pdf_buffer.write(b"0000000000 65535 f \n")
    for obj_id in range(1, next_obj_id):
        pdf_buffer.write(f"{offsets[obj_id]:010} 00000 n \n".encode("ascii"))

    pdf_buffer.write(
        f"trailer\n<< /Size {next_obj_id} /Root {catalog_id} 0 R >>\n".encode("ascii")
    )
    pdf_buffer.write(f"startxref\n{xref_position}\n%%EOF".encode("ascii"))

    return pdf_buffer.getvalue()


# --------------------------------------------------------------------------------
# ROUTES
# --------------------------------------------------------------------------------

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"})


@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    try:
        if 'audio' not in request.files:
            return jsonify({"error": "No audio file"}), 400

        audio_file = request.files['audio']
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_webm:
            audio_file.save(temp_webm.name)
            webm_path = temp_webm.name

        wav_path = webm_path.replace('.webm', '.wav')
        convert_webm_to_wav(webm_path, wav_path)

        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)

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
    try:
        msg = request.json.get("message", "")
        if not msg:
            return jsonify({"response": "No message received."})
        ai = ADHDWiz_respond(msg)
        return jsonify({"response": ai})
    except Exception as e:
        print("AI Error:", e)
        return jsonify({"response": "Oops—ADHDWiz lost the thread 😅 try again?"})


@app.route('/tabs/sync', methods=['POST'])
def sync_tabs():
    """Store the latest snapshot of open tabs for retrieval."""
    try:
        payload = request.get_json(silent=True) or {}
        tabs = payload.get("tabs", [])
        if not isinstance(tabs, list):
            return jsonify({"error": "tabs must be a list"}), 400

        sync_tabs_snapshot(tabs)
        return jsonify({"success": True, "count": len(tabs)})
    except Exception as e:
        print(f"Tab sync error: {e}")
        return jsonify({"error": "Failed to sync tabs"}), 500


@app.route('/study-plan', methods=['POST'])
def study_plan():
    try:
        upload = request.files.get("syllabus")
        if not upload:
            return jsonify({"error": "Missing syllabus PDF."}), 400

        pdf_bytes = upload.read()
        syllabus_text = extract_text_from_pdf(pdf_bytes)
        plan_text = generate_study_plan_from_syllabus(
            syllabus_text or upload.filename or ""
        )

        plan_pdf = render_plan_pdf(plan_text)

        buffer = io.BytesIO(plan_pdf)
        buffer.seek(0)
        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="study-plan.pdf"
        )

    except Exception as e:
        print(f"Study plan generation error: {e}")
        return jsonify({"error": "Could not generate study plan."}), 500


@app.route('/speak', methods=['POST'])
def text_to_speech():
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
    try:
        flow = Flow.from_client_secrets_file(
            GOOGLE_CLIENT_SECRETS_FILE,
            scopes=GOOGLE_SCOPES,
            redirect_uri=GOOGLE_REDIRECT_URI,
        )

        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="false",
            prompt="consent",
        )

        session["oauth_state"] = state
        return redirect(authorization_url)

    except Exception as e:
        print(f"OAuth auth error: {e}")
        return f"<h2>OAuth Error</h2><p>{str(e)}</p>", 500


@app.route("/calendar/oauth2callback")
def calendar_oauth2callback():
    try:
        state = session.get("oauth_state")
        if not state:
            return (
                "<h2>Error</h2><p>Missing OAuth state. Start again at "
                "<a href='/calendar/auth'>/calendar/auth</a></p>"
            ), 400

        flow = Flow.from_client_secrets_file(
            GOOGLE_CLIENT_SECRETS_FILE,
            scopes=GOOGLE_SCOPES,
            redirect_uri=GOOGLE_REDIRECT_URI,
            state=state,
        )

        flow.fetch_token(authorization_response=request.url)
        creds = flow.credentials

        with open("token.json", "w") as token_file:
            token_file.write(creds.to_json())

        return (
            "<h2>Google Calendar connected ✅</h2>"
            "<p>You can close this tab.</p>"
        )

    except Exception as e:
        print(f"OAuth callback error: {e}")
        return (
            f"<h2>OAuth Error</h2><p>{str(e)}</p>"
            "<p>Please try again.</p>"
        ), 500


@app.route('/calendar/add-event', methods=['POST'])
def add_calendar_event():
    try:
        from calendar_tool import add_event

        data = request.json
        summary = data.get('summary')
        start = data.get('start')
        end = data.get('end')
        description = data.get('description', '')

        if not summary or not start or not end:
            return jsonify({"error": "Missing required fields"}), 400

        result = add_event(summary, start, end, description)
        return jsonify({"success": True, "event": result})

    except Exception as e:
        print(f"Add event error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5050)
