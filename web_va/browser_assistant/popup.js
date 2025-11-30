const API_BASE = 'http://localhost:5050';

const micBtn = document.getElementById('micBtn');
const status = document.getElementById('status');
const transcript = document.getElementById('transcript');
const response = document.getElementById('response');

let mediaRecorder;
let chunks = [];
let isRecording = false;

checkBackend();

async function checkBackend() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (res.ok) status.textContent = "✅ Ready! Click mic to speak";
    else status.textContent = "⚠️ Backend error";
  } catch {
    status.textContent = "❌ Backend offline";
  }
}

micBtn.onclick = () => {
  if (!isRecording) startRecording();
  else stopRecording();
};

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
    chunks = [];

    mediaRecorder.ondataavailable = e => chunks.push(e.data);

    mediaRecorder.onstop = async () => {
      const blob = new Blob(chunks, { type: 'audio/webm' });
      await processAudio(blob);
      stream.getTracks().forEach(t => t.stop());
    };

    mediaRecorder.start();
    isRecording = true;
    micBtn.classList.add('recording');
    status.textContent = "🔴 Recording… Click again to stop";

  } catch (e) {
    status.textContent = "❌ Mic access denied";
  }
}

function stopRecording() {
  mediaRecorder.stop();
  isRecording = false;
  micBtn.classList.remove('recording');
  status.textContent = "⏳ Processing…";
}

async function processAudio(blob) {
  try {
    // 1. Transcribe
    const fd = new FormData();
    fd.append("audio", blob, "recording.webm");

    const trRes = await fetch(`${API_BASE}/transcribe`, {
      method: "POST",
      body: fd
    });

    const tr = await trRes.json();
    transcript.textContent = tr.text || "(no text)";
    
    // 2. Chat
    const chatRes = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: tr.text })
    });

    const chat = await chatRes.json();
    response.textContent = chat.response;

    // 3. Speak
    const speakRes = await fetch(`${API_BASE}/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: chat.response })
    });

    const audioBlob = await speakRes.blob();
    const audio = new Audio(URL.createObjectURL(audioBlob));
    audio.play();

    audio.onended = () => {
      status.textContent = "✅ Ready! Click to speak again";
    };

  } catch (err) {
    status.textContent = "❌ Error: " + err.message;
    console.error(err);
  }
}
