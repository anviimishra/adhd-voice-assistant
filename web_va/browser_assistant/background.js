console.log("ADHD Study Assistant: Background loaded");

// Utility: Extract readable content from a tab
async function extractTabContent(tabId) {
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        // Safely get readable text
        return document.body ? document.body.innerText.slice(0, 100000) : "";
      }
    });

    return result.result || "";
  } catch (err) {
    console.warn("Could not extract content from tab:", tabId, err);
    return "(content restricted or unreadable)";
  }
}

// Main function: capture all tabs
async function saveAllTabs() {
  chrome.tabs.query({}, async (tabs) => {
    let output = [];

    for (let tab of tabs) {
      // Ignore chrome://, extensions, edge cases
      if (!tab.url || tab.url.startsWith("chrome://") || tab.url.startsWith("chrome-extension://")) {
        output.push({
          id: tab.id,
          title: tab.title || "",
          url: tab.url || "",
          content: "(system tab - no content)"
        });
        continue;
      }

      const text = await extractTabContent(tab.id);

      output.push({
        id: tab.id,
        title: tab.title || "",
        url: tab.url || "",
        content: text
      });
    }

    // Save
    chrome.storage.local.set({ openTabs: output }, () => {
      console.log("✨ Stored all tabs:", output);
    });
  });
}

// EVENT HOOKS — keep everything up to date
chrome.runtime.onStartup.addListener(() => {
  console.log("🚀 Chrome started — capturing tabs");
  saveAllTabs();
});

chrome.runtime.onInstalled.addListener(() => {
  console.log("📦 Extension installed — capturing tabs");
  saveAllTabs();
});

chrome.tabs.onCreated.addListener(() => {
  console.log("➕ Tab created — updating");
  saveAllTabs();
});

chrome.tabs.onRemoved.addListener(() => {
  console.log("❌ Tab removed — updating");
  saveAllTabs();
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete") {
    console.log("🔄 Tab updated — rescanning");
    saveAllTabs();
  }
});

// Manual trigger from popup (optional)
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "storeTabs") {
    saveAllTabs();
  }
});
