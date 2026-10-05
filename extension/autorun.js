(async function () {
  if (globalThis.__ghAutoRan) return;
  var stored = await chrome.storage.local.get(["autoFill", "personal", "fillEeoc"]);
  if (!stored.autoFill) return;

  var started = Date.now();
  var ready = false;
  while (Date.now() - started < 15000) {
    if (document.getElementById("first_name") || document.querySelector("input.select__input")) {
      ready = true;
      break;
    }
    await new Promise(function (resolve) {
      setTimeout(resolve, 300);
    });
  }
  if (!ready || typeof globalThis.fillGreenhouse !== "function") return;

  globalThis.__ghAutoRan = true;
  var profile = buildGreenhouseProfile(stored.personal || {}, { fillEeoc: !!stored.fillEeoc });
  await globalThis.fillGreenhouse(profile);
})();
