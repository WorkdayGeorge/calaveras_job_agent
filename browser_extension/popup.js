const SERVICE_URL = "https://calaveras-job-agent-596810600756.us-west2.run.app";

const setup = document.getElementById("setup");
const assistant = document.getElementById("assistant");
const tokenInput = document.getElementById("token");
const resumeSelect = document.getElementById("resume");
const identity = document.getElementById("identity");
const status = document.getElementById("status");
const fillButton = document.getElementById("fill");

let cachedProfile = null;

function showStatus(message, kind = "") {
  status.textContent = message;
  status.className = kind;
}

async function storedToken() {
  const result = await chrome.storage.local.get("applicationAssistantToken");
  return result.applicationAssistantToken || "";
}

async function apiFetch(path, token) {
  const response = await fetch(`${SERVICE_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store"
  });
  if (!response.ok) {
    let message = `Connection failed (${response.status})`;
    try {
      const body = await response.json();
      message = body.error || message;
    } catch (_) {}
    throw new Error(message);
  }
  return response;
}

function showProfile(profile) {
  cachedProfile = profile;
  identity.textContent = `${profile.identity.full_name} — ${profile.identity.email}`;
  resumeSelect.replaceChildren(new Option("Do not upload a resume", ""));
  for (const resume of profile.resumes || []) {
    const label = resume.type === "focused"
      ? `Focused — ${resume.filename}`
      : `All work experience — ${resume.filename}`;
    resumeSelect.add(new Option(label, resume.id));
  }
  setup.hidden = true;
  assistant.hidden = false;
  showStatus("Connected.", "success");
}

async function connect(token) {
  const response = await apiFetch("/api/application-assistant/profile", token);
  const profile = await response.json();
  showProfile(profile);
}

async function resumePayload(token, resumeId) {
  if (!resumeId || !cachedProfile) return null;
  const metadata = cachedProfile.resumes.find(item => item.id === resumeId);
  if (!metadata) return null;
  const response = await apiFetch(metadata.download_path, token);
  const buffer = new Uint8Array(await response.arrayBuffer());
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < buffer.length; index += chunkSize) {
    binary += String.fromCharCode(...buffer.subarray(index, index + chunkSize));
  }
  return {
    filename: metadata.filename,
    mimeType: response.headers.get("content-type") || "application/octet-stream",
    base64: btoa(binary)
  };
}

document.getElementById("saveToken").addEventListener("click", async () => {
  const token = tokenInput.value.trim();
  if (!token) return showStatus("Paste an access token first.", "error");
  showStatus("Connecting…");
  try {
    await connect(token);
    await chrome.storage.local.set({ applicationAssistantToken: token });
    tokenInput.value = "";
  } catch (error) {
    showStatus(error.message, "error");
  }
});

document.getElementById("disconnect").addEventListener("click", async () => {
  await chrome.storage.local.remove("applicationAssistantToken");
  cachedProfile = null;
  assistant.hidden = true;
  setup.hidden = false;
  showStatus("Token removed from this browser.");
});

fillButton.addEventListener("click", async () => {
  fillButton.disabled = true;
  showStatus("Preparing application data…");
  try {
    const token = await storedToken();
    const response = await apiFetch("/api/application-assistant/profile", token);
    const profile = await response.json();
    cachedProfile = profile;
    const resume = await resumePayload(token, resumeSelect.value);
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !/^https?:/.test(tab.url || "")) {
      throw new Error("Open a job application webpage first.");
    }
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
    const result = await chrome.tabs.sendMessage(tab.id, {
      type: "CALAVERAS_FILL_APPLICATION",
      profile,
      resume
    });
    if (result?.error) throw new Error(result.error);
    showStatus(
      `Filled ${result.filled} field${result.filled === 1 ? "" : "s"}; ` +
      `skipped ${result.skipped}. Review the page before continuing.`,
      "success"
    );
  } catch (error) {
    showStatus(error.message || "The application could not be filled.", "error");
  } finally {
    fillButton.disabled = false;
  }
});

(async () => {
  const token = await storedToken();
  if (!token) return;
  try {
    await connect(token);
  } catch (error) {
    await chrome.storage.local.remove("applicationAssistantToken");
    showStatus(`${error.message}. Create or paste a new token.`, "error");
  }
})();
