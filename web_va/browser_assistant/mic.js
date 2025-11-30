document.getElementById("ask").onclick = async () => {
  try {
    await navigator.mediaDevices.getUserMedia({ audio: true });
    alert("🎉 Microphone permission granted!");
  } catch (err) {
    alert("❌ Error: " + err.message);
  }
};
