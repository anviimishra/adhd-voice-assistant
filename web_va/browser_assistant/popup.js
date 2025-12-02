const API_BASE = 'http://localhost:5050';

const statusEl = document.getElementById('status');
const dropZoneWrapper = document.getElementById('dropZoneWrapper');
const micBtn = document.getElementById('micBtn');
const voiceControls = document.getElementById('voiceControls');
const syllabusControls = document.getElementById('syllabusControls');
const syllabusDropZone = document.getElementById('syllabusDropZone');
const browseSyllabusBtn = document.getElementById('browseSyllabusBtn');
const syllabusFileInput = document.getElementById('syllabusFileInput');
const uploadSyllabusBtn = document.getElementById('uploadSyllabusBtn');
const syllabusStatus = document.getElementById('syllabusStatus');
const syllabusFileName = document.getElementById('syllabusFileName');
const downloadPlanBtn = document.getElementById('downloadPlanBtn');
const studyControls = document.getElementById("studyControls");
const studyToggleBtn = document.getElementById("studyToggleBtn");
const studyStateLabel = document.getElementById("studyStateLabel");
const studyConfidence = document.getElementById("studyConfidence");
browseSyllabusBtn.addEventListener('click', () => syllabusFileInput.click());

let studyStream = null;
let studyInterval = null;
let monitorActive = false;


const captureCanvas = document.createElement("canvas");
const captureCtx = captureCanvas.getContext("2d");

const transcript = document.getElementById('transcript');
const response = document.getElementById('response');

// BUTTON HANDLERS
document.getElementById('voiceBtn').onclick = () => activateMode("voice");
document.getElementById('syllabusBtn').onclick = () => activateMode("syllabus");
document.getElementById('studyModeBtn').onclick = () => activateMode("study");

let currentMode = null;
let selectedSyllabusFile = null;
let currentPlanObjectUrl = null;

// Toggle button
studyToggleBtn?.addEventListener("click", () => {
  if (!monitorActive) startFocusWatch();
  else stopFocusWatch();
});


// Load tabs when popup opens (optional)
document.addEventListener("DOMContentLoaded", loadTabs);


// When user enters study mode
function activateMode(mode) {
  currentMode = mode;

  voiceControls.classList.add("hidden");
  syllabusControls.classList.add("hidden");
  studyControls.classList.add("hidden");

  statusEl.textContent = "Mode: " + mode;

  if (mode === "voice") {
    voiceControls.classList.remove("hidden");
  }

  if (mode === "syllabus") {
    syllabusControls.classList.remove("hidden");
    resetSyllabusUI();
  }

  if (mode === "study") {
    studyControls.classList.remove("hidden");
    statusEl.textContent = "Study Mode enabled. Click Start Focus Watch.";
  }
}

async function startFocusWatch() {
  try {
    studyStream = await navigator.mediaDevices.getUserMedia({ video: true });

    monitorActive = true;
    studyToggleBtn.textContent = "Stop Focus Watch";
    studyStateLabel.textContent = "Calibrating…";
    statusEl.textContent = "Focus Watch running.";

    // capture every 5 seconds
    studyInterval = setInterval(captureAndAnalyze, 5000);

  } catch (err) {
    statusEl.textContent = "Camera access denied.";
  }
}

function stopFocusWatch() {
  monitorActive = false;

  if (studyInterval) clearInterval(studyInterval);
  studyInterval = null;

  if (studyStream) {
    studyStream.getTracks().forEach(t => t.stop());
    studyStream = null;
  }

  studyToggleBtn.textContent = "Start Focus Watch";
  studyStateLabel.textContent = "Camera idle.";
  studyConfidence.textContent = "";
  statusEl.textContent = "Study Mode stopped.";
}

async function captureAndAnalyze() {
  if (!monitorActive || !studyStream) return;

  const track = studyStream.getVideoTracks()[0];
  const imageCapture = new ImageCapture(track);

  try {
    const bitmap = await imageCapture.grabFrame();

    captureCanvas.width = bitmap.width;
    captureCanvas.height = bitmap.height;
    captureCtx.drawImage(bitmap, 0, 0);

    const dataUrl = captureCanvas.toDataURL("image/jpeg", 0.85);
    const base64 = dataUrl.split(",")[1];

    analyzeFocus(base64);

  } catch (err) {
    console.error("Frame error:", err);
  }
}

async function analyzeFocus(imageB64) {
  studyStateLabel.textContent = "Checking…";
  studyConfidence.textContent = "";

  try {
    const res = await fetch(`${API_BASE}/focus-check`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: imageB64 })
    });

    const data = await res.json();
    const state = (data.state || "").toLowerCase();
    const confidence = Math.round((data.confidence || 0) * 100);

    if (state === "distracted") {
      studyStateLabel.textContent = "Distracted!";
      studyStateLabel.classList.add("distracted");
      studyStateLabel.classList.remove("focused");

      studyConfidence.textContent = `Confidence: ${confidence}%`;
      statusEl.textContent = "⚠️ Heads up — Stay focused!";

      chrome.runtime.sendMessage({
        action: "nudge",
        message: "You're getting distracted — come back to focus! 💡"
      });
    } else {
      studyStateLabel.textContent = "Focused";
      studyStateLabel.classList.add("focused");
      studyStateLabel.classList.remove("distracted");

      studyConfidence.textContent = `Confidence: ${confidence}%`;
      statusEl.textContent = "You're doing great!";
    }

  } catch (err) {
    studyStateLabel.textContent = "Error analyzing focus.";
    studyConfidence.textContent = err.message;
  }
}


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


function resetSyllabusUI() {
  selectedSyllabusFile = null;
  uploadSyllabusBtn.disabled = true;
  uploadSyllabusBtn.textContent = "Generate Study Plan";
  syllabusFileName.textContent = "No file selected.";
  syllabusStatus.textContent = "Upload a PDF syllabus to create a personalized plan.";
  syllabusStatus.classList.remove("error");
  dropZoneWrapper.classList.add("hidden");
  downloadPlanBtn.classList.add("hidden");
  if (currentPlanObjectUrl) {
    URL.revokeObjectURL(currentPlanObjectUrl);
    currentPlanObjectUrl = null;
  }
}

function handleSyllabusFile(file) {
  if (!file) return;

  if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
    syllabusStatus.textContent = "Please upload a PDF file.";
    syllabusStatus.classList.add("error");
    return;
  }

  selectedSyllabusFile = file;
  syllabusFileName.textContent = file.name;
  syllabusStatus.textContent = "Ready to generate your study plan.";
  syllabusStatus.classList.remove("error");
  uploadSyllabusBtn.disabled = false;
  downloadPlanBtn.classList.add("hidden");
  dropZoneWrapper.classList.remove("hidden");
  if (currentPlanObjectUrl) {
    URL.revokeObjectURL(currentPlanObjectUrl);
    currentPlanObjectUrl = null;
  }
}

function bindDropEvents() {
  if (!syllabusDropZone) return;

  ['dragenter', 'dragover'].forEach(evt => {
    syllabusDropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      syllabusDropZone.classList.add('dragging');
    });
  });

  ['dragleave', 'drop'].forEach(evt => {
    syllabusDropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (evt === 'drop') {
        const file = e.dataTransfer?.files?.[0];
        handleSyllabusFile(file);
      }
      syllabusDropZone.classList.remove('dragging');
    });
  });

  syllabusDropZone.addEventListener('click', () => syllabusFileInput.click());
}

async function uploadSyllabus() {
  if (!selectedSyllabusFile) {
    syllabusStatus.textContent = "Select a PDF before generating.";
    syllabusStatus.classList.add("error");
    return;
  }

  uploadSyllabusBtn.disabled = true;
  uploadSyllabusBtn.textContent = "Generating…";
  syllabusStatus.textContent = "Reading your syllabus and building a plan…";
  syllabusStatus.classList.remove("error");

  try {
    const fd = new FormData();
    fd.append("syllabus", selectedSyllabusFile);

    const res = await fetch(`${API_BASE}/study-plan`, {
      method: "POST",
      body: fd
    });

    if (!res.ok) {
      let errText = "Failed to generate study plan.";
      try {
        const data = await res.json();
        errText = data.error || errText;
      } catch (_) {
        // Ignore JSON parse errors for non-JSON responses.
      }
      throw new Error(errText);
    }

    const blob = await res.blob();
    if (currentPlanObjectUrl) {
      URL.revokeObjectURL(currentPlanObjectUrl);
    }
    currentPlanObjectUrl = URL.createObjectURL(blob);

    downloadPlanBtn.href = currentPlanObjectUrl;
    downloadPlanBtn.download = `study-plan-${Date.now()}.pdf`;
    downloadPlanBtn.classList.remove("hidden");

    syllabusStatus.textContent = "Study plan ready! Download below.";

  } catch (err) {
    console.error("Study plan error", err);
    syllabusStatus.textContent = err.message || "Failed to generate study plan.";
    syllabusStatus.classList.add("error");
  } finally {
    uploadSyllabusBtn.disabled = !selectedSyllabusFile;
    uploadSyllabusBtn.textContent = "Generate Study Plan";
  }
}

browseSyllabusBtn?.addEventListener('click', () => syllabusFileInput.click());
syllabusFileInput?.addEventListener('change', (e) => handleSyllabusFile(e.target.files[0]));
uploadSyllabusBtn?.addEventListener('click', uploadSyllabus);
bindDropEvents();

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
    if (chat.response.startsWith("Here are the tabs")) {
    // Ask backend directly for the flat tab list
    fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: transcript.textContent })
    })
        .then(res => res.json())
        .then(data => {
        if (data.tabs && data.tabs.length > 0) {
            chrome.runtime.sendMessage({
            action: "groupTabs",
            task: data.task,
            tabs: data.tabs
            });
        }
        });
    }

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
