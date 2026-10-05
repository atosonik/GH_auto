var fields = ["firstName", "lastName", "email", "phone", "linkedin", "location", "company", "website", "address", "country"];
var statusEl = document.getElementById("status");
var submitButton = document.getElementById("submit");
var filledFrameId = null;

function personalFromForm() {
  var personal = {};
  fields.forEach(function (id) {
    personal[id] = document.getElementById(id).value.trim();
  });
  personal.preferredName = personal.firstName;
  personal.github = "";
  return personal;
}

function saveSettings() {
  return chrome.storage.local.set({
    personal: personalFromForm(),
    autoFill: document.getElementById("autoFill").checked,
    fillEeoc: document.getElementById("fillEeoc").checked,
  });
}

async function resumePayload() {
  var file = document.getElementById("resume").files[0];
  if (!file) return null;
  var bytes = new Uint8Array(await file.arrayBuffer());
  return {
    name: file.name,
    type: file.type,
    buffer: Array.from(bytes),
  };
}

async function greenhouseFrames(tabId) {
  var frames = await chrome.webNavigation.getAllFrames({ tabId: tabId });
  var ids = frames
    .filter(function (frame) {
      return /greenhouse\.io/i.test(frame.url || "");
    })
    .map(function (frame) {
      return frame.frameId;
    });
  if (!ids.length) ids = frames.map(function (frame) { return frame.frameId; });
  return ids;
}

async function runInFrame(tabId, frameId, file, func, args) {
  if (file) {
    await chrome.scripting.executeScript({
      target: { tabId: tabId, frameIds: [frameId] },
      files: [file],
    });
  }
  var injected = await chrome.scripting.executeScript({
    target: { tabId: tabId, frameIds: [frameId] },
    func: func,
    args: args || [],
  });
  return injected[0] ? injected[0].result : null;
}

document.getElementById("fill").addEventListener("click", async function () {
  statusEl.textContent = "Filling…";
  submitButton.disabled = true;
  filledFrameId = null;
  await saveSettings();

  var profile = buildGreenhouseProfile(personalFromForm(), {
    fillEeoc: document.getElementById("fillEeoc").checked,
    resume: await resumePayload(),
  });

  try {
    var [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    var frameIds = await greenhouseFrames(tab.id);
    var logs = [];
    var errors = [];
    for (var i = 0; i < frameIds.length; i++) {
      try {
        var result = await runInFrame(tab.id, frameIds[i], "filler.js", function (nextProfile) {
          return globalThis.fillGreenhouse(nextProfile);
        }, [profile]);
        if (result && result.ok) {
          filledFrameId = frameIds[i];
          logs = logs.concat(result.log || []);
        }
      } catch (error) {
        errors.push(String(error));
      }
    }
    if (filledFrameId == null) {
      statusEl.textContent = errors[0] || "No Greenhouse application form was found in this tab.";
      return;
    }
    statusEl.textContent = logs.length ? logs.join("\n") : "Form found, but no fields matched the profile.";
    submitButton.disabled = !document.getElementById("confirmSubmit").checked;
  } catch (error) {
    statusEl.textContent = String(error);
  }
});

document.getElementById("confirmSubmit").addEventListener("change", function (event) {
  submitButton.disabled = !event.target.checked || filledFrameId == null;
});

document.getElementById("submit").addEventListener("click", async function () {
  if (filledFrameId == null || !document.getElementById("confirmSubmit").checked) return;
  var [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  var result = await runInFrame(tab.id, filledFrameId, null, function () {
    return globalThis.submitGreenhouse();
  });
  statusEl.textContent = result && result.ok ? "Submit clicked." : "Submit button was not found.";
});

["autoFill", "fillEeoc"].concat(fields).forEach(function (id) {
  document.getElementById(id).addEventListener("change", saveSettings);
});

chrome.storage.local.get(["personal", "autoFill", "fillEeoc"], function (stored) {
  var personal = stored.personal || {};
  fields.forEach(function (id) {
    if (personal[id]) document.getElementById(id).value = personal[id];
  });
  document.getElementById("autoFill").checked = !!stored.autoFill;
  document.getElementById("fillEeoc").checked = !!stored.fillEeoc;
});
