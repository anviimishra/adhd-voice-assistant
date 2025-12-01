const API_BASE = 'http://localhost:5050';

const statusEl = document.getElementById('status');
const micBtn = document.getElementById('micBtn');
const voiceControls = document.getElementById('voiceControls');

const transcript = document.getElementById('transcript');
const response = document.getElementById('response');

// BUTTON HANDLERS
document.getElementById('voiceBtn').onclick = () => activateMode("voice");
document.getElementById('syllabusBtn').onclick = () => activateMode("syllabus");
document.getElementById('studyModeBtn').onclick = () => activateMode("study");

let currentMode = null;

// Load tabs when popup opens (optional)
document.addEventListener("DOMContentLoaded", loadTabs);

function activateMode(mode) {
  currentMode = mode;

  // Reset UI
  voiceControls.classList.add("hidden");
  statusEl.textContent = "Mode: " + mode;

  if (mode === "voice") {
    voiceControls.classList.remove("hidden");
  }

  if (mode === "syllabus") {
    statusEl.textContent = "Open your syllabus tab. Extracting…";
    chrome.runtime.sendMessage({ action: "openSyllabusPlanner" });

    // Grab stored tabs
    loadTabs();
  }

  if (mode === "study") {
    statusEl.textContent = "Study Mode enabled (focus + distraction monitoring)";
    chrome.runtime.sendMessage({ action: "startStudyMode" });
  }
}

//
// AUTO-LOAD ALL STORED TABS
//
function loadTabs() {
  chrome.storage.local.get("openTabs", (data) => {
    if (!data.openTabs) {
      console.log("No stored tabs yet.");
      return;
    }

    console.log("Loaded tabs:", data.openTabs);

    // Optional: Preview in popup
    const list = data.openTabs
      .map(t => `• ${t.title} (${t.url})`)
      .join("\n");

    console.log("Tab list:\n" + list);
  });
}

//
// VOICE MODE LOGIC
//
let mediaRecorder;
let chunks = [];
let isRecording = false;

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
    statusEl.textContent = "Listening…";

  } catch (err) {
    statusEl.textContent = "Mic access denied.";
  }
}

function stopRecording() {
  mediaRecorder.stop();
  isRecording = false;
  micBtn.classList.remove('recording');
  statusEl.textContent = "Processing…";
}

async function processAudio(blob) {
  try {
    const fd = new FormData();
    fd.append("audio", blob, "speech.webm");

    // STEP 1: Transcribe
    const trRes = await fetch(`${API_BASE}/transcribe`, { method: "POST", body: fd });
    const tr = await trRes.json();
    transcript.textContent = tr.text ?? "(no speech detected)";

    // STEP 2: Chat
    const chatRes = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: tr.text })
    });

    const chat = await chatRes.json();
    response.textContent = chat.response;

    // STEP 3: Speak result
    const speakRes = await fetch(`${API_BASE}/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: chat.response })
    });

    const audioBlob = await speakRes.blob();
    new Audio(URL.createObjectURL(audioBlob)).play();

    statusEl.textContent = "Ready";

  } catch (err) {
    statusEl.textContent = "Error: " + err.message;
  }
}
