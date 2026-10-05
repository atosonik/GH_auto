from __future__ import annotations

import re
import time
from typing import Any

FILL_SCRIPT = r"""
async function fillGreenhouse(profile) {
  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
  function clean(text) {
    return (text || "").replace(/\*/g, "").replace(/\s+/g, " ").trim();
  }
  function normalize(text) {
    return clean(text).toLowerCase();
  }
  function hasForm() {
    return !!(
      document.getElementById("first_name") ||
      document.querySelector("input.select__input") ||
      document.querySelector(".application--container") ||
      document.querySelector("form")
    );
  }
  function labelFor(input) {
    if (!input) return "";
    if (input.id) {
      const byFor = document.querySelector('label[for="' + CSS.escape(input.id) + '"]');
      if (byFor) return clean(byFor.textContent);
      const byLabelId = document.getElementById(input.id + "-label");
      if (byLabelId) return clean(byLabelId.textContent);
    }
    const wrap = input.closest(".field-wrapper, .select__container, .input-wrapper, .field, label");
    const label = wrap && wrap.querySelector("label");
    return label ? clean(label.textContent) : clean(input.getAttribute("aria-label"));
  }
  function matchRule(label, rules) {
    const hay = normalize(label);
    if (!hay) return null;
    for (const rule of rules || []) {
      if (hay.includes(normalize(rule.includes))) return rule;
    }
    return null;
  }
  function setNativeValue(el, value) {
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }
  function reactProps(el) {
    if (!el) return null;
    const keys = Object.keys(el);
    for (const key of keys) {
      if (key.startsWith("__reactProps$")) return el[key];
    }
    let fiber = null;
    for (const key of keys) {
      if (key.startsWith("__reactFiber$") || key.startsWith("__reactInternalInstance$")) {
        fiber = el[key];
        break;
      }
    }
    let depth = 0;
    while (fiber && depth < 6) {
      if (fiber.memoizedProps && (fiber.memoizedProps.onMouseDown || fiber.memoizedProps.onChange)) {
        return fiber.memoizedProps;
      }
      fiber = fiber.return;
      depth += 1;
    }
    return null;
  }
  function invokeMouseDown(el) {
    let node = el;
    for (let hop = 0; hop < 4 && node; hop += 1) {
      const props = reactProps(node);
      if (props && typeof props.onMouseDown === "function") {
        props.onMouseDown({
          button: 0, target: node, currentTarget: node,
          preventDefault() {}, stopPropagation() {}, persist() {},
        });
        return true;
      }
      node = node.parentElement;
    }
    el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, view: window }));
    el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, view: window }));
    el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
    return false;
  }
  function openOptions() {
    const menus = Array.from(document.querySelectorAll(".select__menu"));
    let visibleMenu = null;
    for (const menu of menus) {
      if (menu.getClientRects().length > 0) visibleMenu = menu;
    }
    const root = visibleMenu || document;
    return Array.from(root.querySelectorAll(".select__option"));
  }
  function findOption(value) {
    const target = normalize(value);
    let options = openOptions().filter((option) => option.offsetParent !== null || option.getClientRects().length > 0);
    if (!options.length) options = openOptions();
    return (
      options.find((option) => normalize(option.textContent) === target) ||
      options.find((option) => normalize(option.textContent).startsWith(target)) ||
      options.find((option) => normalize(option.textContent).includes(target)) ||
      null
    );
  }
  function selectedValue(shell) {
    const current = shell && shell.querySelector(".select__single-value");
    return current ? normalize(current.textContent) : "";
  }
  function clickOption(option) {
    if (!option) return;
    option.scrollIntoView({ block: "nearest", inline: "nearest" });
    const opts = { bubbles: true, cancelable: true, view: window, button: 0 };
    option.dispatchEvent(new MouseEvent("mouseover", opts));
    option.dispatchEvent(new MouseEvent("mousemove", opts));
    try { option.dispatchEvent(new PointerEvent("pointerdown", opts)); } catch (e) {}
    option.dispatchEvent(new MouseEvent("mousedown", opts));
    try { option.dispatchEvent(new PointerEvent("pointerup", opts)); } catch (e) {}
    option.dispatchEvent(new MouseEvent("mouseup", opts));
    option.dispatchEvent(new MouseEvent("click", opts));
    try { option.click(); } catch (e) {}
    invokeMouseDown(option);
  }
  async function fillSelect(input, value, waitMs) {
    // Fast path aligned with the Chrome extension autofill timings.
    waitMs = waitMs || 1600;
    const wanted = String(value || "").trim();
    if (!wanted) throw new Error("empty select value");
    const shell = input.closest(".select-shell") || input.closest(".select") || input.closest(".select__container");
    if (!shell) throw new Error("select shell not found");
    const control = shell.querySelector(".select__control");
    if (!control) throw new Error("select control not found");
    if (selectedValue(shell) === normalize(wanted)) return;

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
    await sleep(40);
    control.scrollIntoView({ behavior: "auto", block: "nearest" });
    invokeMouseDown(control);
    await sleep(140);
    // Typing helps long lists; for Yes/No the option is already visible.
    if (wanted.length > 3) {
      setNativeValue(input, wanted);
      await sleep(120);
    }
    let option = null;
    const started = Date.now();
    while (Date.now() - started < waitMs) {
      option = findOption(wanted);
      if (option) break;
      await sleep(40);
    }
    if (!option) {
      // One short retry: reopen + type.
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
      await sleep(40);
      invokeMouseDown(control);
      await sleep(140);
      setNativeValue(input, wanted);
      await sleep(140);
      const retryStarted = Date.now();
      while (Date.now() - retryStarted < 1200) {
        option = findOption(wanted);
        if (option) break;
        await sleep(40);
      }
    }
    if (!option) throw new Error('option "' + wanted + '" not in the menu');
    clickOption(option);
    await sleep(100);
    if (selectedValue(shell) !== normalize(wanted)) {
      input.dispatchEvent(new KeyboardEvent("keydown", {
        key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true,
      }));
      await sleep(100);
    }
    if (selectedValue(shell) !== normalize(wanted) && selectedValue(shell).indexOf(normalize(wanted)) === -1) {
      throw new Error('option "' + wanted + '" not selected (still: ' + (selectedValue(shell) || "Select...") + ")");
    }
  }
  function cityOnly(value) {
    return String(value || "").split(",")[0].trim();
  }
  function isLocationLabel(label) {
    const hay = normalize(label);
    // City autocomplete only — NOT "located in one of the following countries".
    if (/email|phone|company|country|countries|sponsorship|authorized|citizen/.test(hay)) return false;
    if (/location\s*\(city\)|currently located|current location|city,\s*state|city\/state|where are you located|what city/.test(hay)) return true;
    if (/^(city|location)\b/.test(hay)) return true;
    return false;
  }
  function locationSuggestionOptions() {
    const selectors = [
      '[role="listbox"] [role="option"]',
      ".select__menu .select__option",
      ".select__option",
      ".pac-item",
      '[class*="autocomplete"] [role="option"]',
      '[class*="typeahead"] [role="option"]',
      'ul[role="listbox"] li',
    ];
    const out = [];
    const seen = new Set();
    for (const sel of selectors) {
      for (const el of Array.from(document.querySelectorAll(sel))) {
        if (seen.has(el)) continue;
        const rects = el.getClientRects();
        // Greenhouse geocode rows can be "hidden" in a11y trees but still selectable.
        if (!rects.length && el.offsetParent === null && !el.getAttribute("aria-selected")) continue;
        const text = clean(el.textContent);
        if (!text || text.length < 2) continue;
        if (/locate me|no options|loading/i.test(text)) continue;
        seen.add(el);
        out.push(el);
      }
    }
    return out;
  }
  async function typeIntoLocation(input, text) {
    input.focus();
    setNativeValue(input, "");
    await sleep(40);
    // Character-by-character so geocode/typeahead debounce fires like a real user.
    let built = "";
    for (const ch of String(text || "")) {
      built += ch;
      setNativeValue(input, built);
      try {
        input.dispatchEvent(new InputEvent("input", { bubbles: true, data: ch, inputType: "insertText" }));
      } catch (e) {
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
      await sleep(45);
    }
  }
  async function fillLocationField(value) {
    if (!value) return false;
    const city = cityOnly(value);
    const typed = city || String(value).trim();
    if (!typed) return false;
    const inputs = Array.from(document.querySelectorAll(
      "input.select__input, input#location, input[name='location'], input[type='text'], input:not([type]), textarea"
    ));
    let filled = false;
    for (const input of inputs) {
      if (input.type === "hidden" || input.type === "file") continue;
      if (input.closest(".iti, .intl-tel-input, .PhoneInput")) continue;
      const label = labelFor(input);
      const idName = String(input.id || "") + " " + String(input.name || "");
      if (!isLocationLabel(label) && !/^(location|job_application_location)/i.test(idName.trim()) && !/location|city/i.test(idName)) {
        continue;
      }
      const shell = input.closest(".select-shell") || input.closest(".select") || input.closest(".select__container");
      const control = shell && shell.querySelector(".select__control");
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
      await sleep(40);
      if (control) {
        control.scrollIntoView({ behavior: "auto", block: "nearest" });
        invokeMouseDown(control);
        await sleep(120);
      } else {
        input.scrollIntoView({ behavior: "auto", block: "center" });
        input.click();
        await sleep(80);
      }
      await typeIntoLocation(input, typed);
      let option = null;
      const started = Date.now();
      while (Date.now() - started < 3200) {
        const opts = locationSuggestionOptions();
        // Always take the TOP suggestion after typing — that row is the correct city.
        option = opts[0] || null;
        if (option) break;
        await sleep(70);
      }
      if (!option) {
        // Keyboard commit: highlight first row then Enter.
        input.dispatchEvent(new KeyboardEvent("keydown", {
          key: "ArrowDown", code: "ArrowDown", keyCode: 40, which: 40, bubbles: true,
        }));
        await sleep(80);
        input.dispatchEvent(new KeyboardEvent("keydown", {
          key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true,
        }));
        await sleep(120);
        if ((input.value || "").trim() || (shell && selectedValue(shell))) {
          filled = true;
          log.push("Location committed via keyboard: " + typed);
          continue;
        }
        continue;
      }
      clickOption(option);
      await sleep(120);
      filled = true;
      log.push("Location selected (top): " + clean(option.textContent));
    }
    return filled;
  }
  function fillText(input, value) {
    if (!input || value == null || value === "") return false;
    if (input.classList.contains("select__input")) return false;
    input.scrollIntoView({ behavior: "auto", block: "center" });
    input.focus();
    setNativeValue(input, value);
    return true;
  }
  if (!hasForm()) return { skipped: true, log: [], gaps: [] };
  const personal = profile.personal || {};
  const log = [];
  // Never leave the phone dial-code list open — it steals focus from real selects.
  try {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
    const itiList = document.querySelector(".iti__country-list");
    if (itiList) itiList.classList.add("iti__hide");
    const itiDrop = document.querySelector(".iti__dropdown-content");
    if (itiDrop) itiDrop.style.display = "none";
  } catch (e) {}
  const byId = {
    first_name: personal.firstName,
    last_name: personal.lastName,
    preferred_name: personal.preferredName || personal.firstName,
    email: personal.email,
  };
  for (const [id, value] of Object.entries(byId)) {
    const el = document.getElementById(id);
    if (fillText(el, value)) log.push("Filled " + id);
  }
  function countryToIso2(country, phone) {
    const c = normalize(country || "");
    if (/united states|^usa$|^us$|america/.test(c)) return "us";
    if (/canada|^ca$/.test(c)) return "ca";
    if (/united kingdom|^uk$|great britain|england/.test(c)) return "gb";
    const digits = String(phone || "").replace(/[^\d+]/g, "");
    if (digits.startsWith("+1") || (!digits.startsWith("+") && digits.length >= 10)) return "us";
    return "us";
  }
  function getItiInstance(input) {
    if (!input) return null;
    try {
      if (window.intlTelInput && typeof window.intlTelInput.getInstance === "function") {
        const inst = window.intlTelInput.getInstance(input);
        if (inst) return inst;
      }
    } catch (e) {}
    try {
      if (window.intlTelInputGlobals && typeof window.intlTelInputGlobals.getInstance === "function") {
        const inst = window.intlTelInputGlobals.getInstance(input);
        if (inst) return inst;
      }
    } catch (e) {}
    return input.iti || input._iti || null;
  }
  async function selectPhoneCountry(iso2) {
    const code = String(iso2 || "us").toLowerCase();
    const phone = document.getElementById("phone");
    const wrap = (phone && phone.closest(".iti, .intl-tel-input")) || document.querySelector(".iti, .intl-tel-input");
    if (!wrap) return false;

    // Preferred: official iti API (commits countrychange so Greenhouse clears the error).
    const iti = getItiInstance(phone);
    if (iti) {
      try {
        if (typeof iti.setSelectedCountry === "function") iti.setSelectedCountry(code);
        else if (typeof iti.setCountry === "function") iti.setCountry(code);
        await sleep(80);
        return true;
      } catch (e) {}
    }

    // UI path: open dialer → search → click the country row.
    const btn = wrap.querySelector("button.iti__selected-country, .iti__selected-country");
    if (!btn) return false;
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
    await sleep(40);
    btn.scrollIntoView({ behavior: "auto", block: "nearest" });
    btn.click();
    await sleep(160);
    const drop = document.querySelector(".iti__dropdown-content:not(.iti__hide), #iti-0__dropdown-content");
    if (drop) drop.classList.remove("iti__hide");
    const search = document.querySelector(".iti__search-input, input.iti__search-input");
    const names = { us: "United States", ca: "Canada", gb: "United Kingdom" };
    if (search) {
      setNativeValue(search, names[code] || code);
      await sleep(180);
    }
    let option =
      document.querySelector('li.iti__country[data-country-code="' + code + '"]') ||
      document.querySelector('#iti-0__item-' + code);
    if (!option) {
      const rows = Array.from(document.querySelectorAll("li.iti__country[data-country-code]"));
      option = rows.find((r) => (r.getAttribute("data-country-code") || "").toLowerCase() === code) || null;
    }
    if (!option) {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
      return false;
    }
    option.scrollIntoView({ block: "nearest" });
    option.click();
    try { option.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window })); } catch (e) {}
    await sleep(120);
    // Ensure list is closed so it can't steal later select focus.
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
    const list = document.querySelector(".iti__country-list");
    if (list) list.classList.add("iti__hide");
    const dd = document.querySelector(".iti__dropdown-content");
    if (dd) dd.classList.add("iti__hide");
    return true;
  }
  async function fillPhoneField(raw, countryName) {
    const input = document.getElementById("phone");
    if (!input || !raw) return false;
    const iso2 = countryToIso2(countryName, raw);
    await selectPhoneCountry(iso2);

    let digits = String(raw).replace(/[^\d+]/g, "");
    const iti = getItiInstance(input);
    if (iti && typeof iti.setNumber === "function") {
      try {
        const e164 = digits.startsWith("+") ? digits : (iso2 === "us" || iso2 === "ca" ? "+1" + digits.replace(/^1/, "") : digits);
        iti.setNumber(e164);
        await sleep(100);
        input.dispatchEvent(new Event("blur", { bubbles: true }));
        return !!(input.value || "").trim();
      } catch (e) {}
    }
    // National digits after country is selected.
    if (digits.startsWith("+1")) digits = digits.slice(2);
    else if (digits.startsWith("1") && digits.length === 11) digits = digits.slice(1);
    else digits = digits.replace(/^\+\d{1,3}/, "");
    input.scrollIntoView({ behavior: "auto", block: "center" });
    input.focus();
    setNativeValue(input, "");
    await sleep(30);
    setNativeValue(input, digits);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    input.dispatchEvent(new Event("blur", { bubbles: true }));
    await sleep(80);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
    return !!(input.value || "").trim();
  }
  if (personal.phone || personal.country) {
    try {
      const iso2 = countryToIso2(personal.country, personal.phone);
      if (await selectPhoneCountry(iso2)) log.push("Selected phone country: " + iso2);
      else log.push("Phone country select failed");
    } catch (error) {
      log.push("Phone country failed: " + error.message);
    }
  }
  if (personal.phone) {
    try {
      if (await fillPhoneField(personal.phone, personal.country)) log.push("Filled phone");
    } catch (error) {
      log.push("Phone failed: " + error.message);
    }
  }
  const textInputs = Array.from(
    document.querySelectorAll("input[type='text'], input[type='email'], input[type='tel'], input:not([type]), textarea")
  );
  for (const input of textInputs) {
    if (input.classList.contains("select__input")) continue;
    if (input.closest(".iti, .iti__dropdown-content, .iti__country-list, .intl-tel-input")) continue;
    if (byId[input.id] || input.id === "phone") continue;
    const label = labelFor(input);
    // Location text fields are handled by fillLocationField below.
    if (isLocationLabel(label)) continue;
    const rule = matchRule(label, profile.textRules || []);
    if (!rule) continue;
    // Only fill the mapped profile field — never dump free-form profile context.
    if (!rule.field || rule.field === "location") continue;
    const value = personal[rule.field];
    if (fillText(input, value)) log.push("Filled " + label);
  }
  if (personal.location) {
    try {
      await fillLocationField(personal.location);
    } catch (error) {
      log.push("Location failed: " + error.message);
    }
  }
  if (personal.country) {
    const country = document.getElementById("country");
    if (country && country.classList.contains("select__input")) {
      try {
        await fillSelect(country, personal.country);
        log.push("Selected country: " + personal.country);
      } catch (error) {
        log.push("Country failed: " + error.message);
      }
    }
  }
  const selects = Array.from(document.querySelectorAll("input.select__input"));
  for (const select of selects) {
    if (select.id === "country") continue;
    const label = labelFor(select);
    if (isLocationLabel(label)) continue; // already handled
    const eeocValue = profile.eeoc && profile.eeoc[select.id];
    const isEeoc = ["gender", "hispanic_ethnicity", "veteran_status", "disability_status"].includes(select.id);
    let value = "";
    if (isEeoc) {
      if (!profile.fillEeoc || !eeocValue) continue;
      value = eeocValue;
    } else {
      const rule = matchRule(label, profile.dropdownRules || []);
      if (!rule || !rule.value) continue;
      value = rule.value;
    }
    try {
      await fillSelect(select, value, 4000);
      log.push("Selected " + (label || select.id) + ": " + value);
    } catch (error) {
      log.push("Failed " + (label || select.id) + ": " + error.message);
    }
  }
  function fieldIsRequired(input) {
    if (input.required || input.getAttribute("aria-required") === "true") return true;
    const wrap = input.closest(
      ".field-wrapper, .input-wrapper, .field, .select__container, .select-shell, .select, .file-upload, [role='group']"
    );
    if (wrap && wrap.querySelector(".required, .asterisk, span.required")) return true;
    if (wrap && /\*/.test(wrap.textContent || "")) return true;
    if (input.id) {
      const lab = document.querySelector('label[for="' + CSS.escape(input.id) + '"]');
      if (lab && (lab.querySelector(".required") || /\*/.test(lab.textContent || ""))) return true;
    }
    return false;
  }
  const gaps = [];
  for (const input of textInputs) {
    if (input.classList.contains("select__input")) continue;
    if (input.value) continue;
    if (input.type === "hidden") continue;
    if (input.closest(".iti, .intl-tel-input")) continue;
    const label = labelFor(input);
    if (isLocationLabel(label)) continue; // location must be committed via typeahead, not DeepSeek
    if (fieldIsRequired(input) && label) {
      gaps.push({ label, name: input.name || input.id || label, kind: "text", required: true });
    }
  }
  return { ok: true, log, gaps };
}
function submitGreenhouse() {
  function labelOf(el) {
    return String((el && el.textContent) || "").replace(/\s+/g, " ").trim();
  }
  const selectors = [
    ".application--submit button[type='submit']",
    ".application--submit button",
    ".application--container button[type='submit']",
    "form button[type='submit']",
    "button[type='submit']",
  ];
  let button = null;
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && el.getClientRects().length) { button = el; break; }
  }
  if (!button) {
    const buttons = Array.from(document.querySelectorAll("button"));
    button = buttons.find((b) => /submit application/i.test(labelOf(b)))
      || buttons.find((b) => /^submit$/i.test(labelOf(b)));
  }
  if (!button) return { skipped: true, ok: false, reason: "Submit application button not found" };
  const label = labelOf(button);
  if (button.getAttribute("aria-disabled") === "true" || button.disabled) {
    return { skipped: true, ok: false, reason: "Submit application button is disabled", clicked: label };
  }
  button.scrollIntoView({ behavior: "auto", block: "center" });
  button.focus();
  button.click();
  // Also dispatch a real click event in case React ignored .click().
  button.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
  return { ok: true, clicked: label || "Submit application" };
}
function submissionConfirmed() {
  const href = String(window.location.href || "").toLowerCase();
  const text = String(document.body && document.body.innerText || "").toLowerCase();
  if (href.includes("confirmation") || href.includes("thank")) return true;
  if (text.includes("thank you for applying")) return true;
  if (text.includes("application has been received")) return true;
  if (text.includes("thanks for applying")) return true;
  return false;
}
function findSecurityCodeField() {
  // Greenhouse 8-box OTP: #security-input-0 .. #security-input-7
  const boxes = Array.from(document.querySelectorAll(
    ".email-verification input[id^='security-input-'], #email-verification input[id^='security-input-'], input[id^='security-input-']"
  )).filter((el) => el.getClientRects().length > 0);
  if (boxes.length >= 4) {
    return {
      found: true,
      kind: "boxes",
      count: boxes.length,
      id: boxes[0].id || "security-input-0",
    };
  }
  if (document.querySelector(".email-verification, #email-verification, fieldset#email-verification")) {
    return { found: true, kind: "section", id: "email-verification" };
  }
  const inputs = Array.from(document.querySelectorAll("input[type='text'], input[type='tel'], input[type='number'], input:not([type])"));
  for (const input of inputs) {
    const label = (
      (input.id && document.querySelector('label[for="' + CSS.escape(input.id) + '"]')?.textContent) ||
      input.getAttribute("aria-label") ||
      input.placeholder ||
      ""
    ).toLowerCase();
    const wrapText = (input.closest(".email-verification, fieldset, .field")?.innerText || "").toLowerCase();
    if (/security|verif|code|otp|one[- ]time/.test(label) || /verification code was sent|security code/.test(wrapText)) {
      return { found: true, kind: "single", id: input.id || null, name: input.name || null };
    }
  }
  return { found: false };
}
"""

EXTRACT_JD_JS = """() => {
          const clean = (t) => (t || "").replace(/\\s+/g, " ").trim();
          const title =
            clean(document.querySelector(".job__title h1, h1.section-header, h1")?.textContent) ||
            clean(document.querySelector('[data-testid="job-title"]')?.textContent) ||
            clean(document.title);
          let company = clean(
            document.querySelector('[data-testid="company-name"], .company-name, .app-title, .header-company')?.textContent
          ) || "";
          // Greenhouse board slug: ?for=array
          if (!company) {
            try {
              const forSlug = new URL(window.location.href).searchParams.get("for") || "";
              if (forSlug) {
                company = forSlug
                  .replace(/[-_]+/g, " ")
                  .replace(/\\b\\w/g, (c) => c.toUpperCase());
              }
            } catch (e) {}
          }
          const locationText = clean(
            document.querySelector(".job__location div:last-child, .job__location, [data-testid='job-location'], .location")?.textContent
          );
          // Prefer the real JD block — avoid entire body / job-alert chrome.
          const preferred = [
            ".job__description.body",
            ".job__description",
            "#content",
            "#app_body",
            ".content",
            "main",
            "article",
          ];
          let description = "";
          for (const sel of preferred) {
            const el = document.querySelector(sel);
            if (!el) continue;
            // Clone and strip job-alert / apply chrome if present inside.
            const clone = el.cloneNode(true);
            clone.querySelectorAll(".job-alert, .job__header, a.link").forEach((n) => n.remove());
            const text = (clone.innerText || el.innerText || "").trim();
            if (text.length > 80) {
              description = text;
              break;
            }
            if (text.length > description.length) description = text;
          }
          if (description.length > 12000) description = description.slice(0, 12000);
          return { title, company, location: locationText, description, url: window.location.href };
        }"""

APPLY_GAPS_JS = """async (items) => {
          function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
          function clean(text) {
            return (text || "").replace(/\\*/g, "").replace(/\\s+/g, " ").trim();
          }
          function normalize(text) { return clean(text).toLowerCase(); }
          function labelFor(input) {
            if (!input) return "";
            if (input.id) {
              const byFor = document.querySelector('label[for="' + CSS.escape(input.id) + '"]');
              if (byFor) return clean(byFor.textContent);
              const byLabelId = document.getElementById(input.id + "-label");
              if (byLabelId) return clean(byLabelId.textContent);
            }
            const wrap = input.closest(
              ".field-wrapper, .input-wrapper, .field, label, .select__container, .select-shell, .select, [role='group']"
            );
            const label = wrap && wrap.querySelector("label, .label");
            return label ? clean(label.textContent) : clean(input.getAttribute("aria-label") || input.placeholder || "");
          }
          function setNativeValue(el, value) {
            const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
            setter.call(el, value);
            el.dispatchEvent(new Event("input", { bubbles: true }));
            el.dispatchEvent(new Event("change", { bubbles: true }));
            el.dispatchEvent(new Event("blur", { bubbles: true }));
          }
          function reactProps(el) {
            if (!el) return null;
            const keys = Object.keys(el);
            for (const key of keys) {
              if (key.startsWith("__reactProps$")) return el[key];
            }
            return null;
          }
          function invokeMouseDown(el) {
            let node = el;
            for (let hop = 0; hop < 4 && node; hop += 1) {
              const props = reactProps(node);
              if (props && typeof props.onMouseDown === "function") {
                props.onMouseDown({
                  button: 0, target: node, currentTarget: node,
                  preventDefault() {}, stopPropagation() {}, persist() {},
                });
                return true;
              }
              node = node.parentElement;
            }
            el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, view: window }));
            el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, view: window }));
            el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
            return false;
          }
          function openOptions() {
            const menus = Array.from(document.querySelectorAll(".select__menu"));
            const menu = menus.find((m) => m.getClientRects().length > 0) || menus[menus.length - 1];
            return Array.from((menu || document).querySelectorAll(".select__option"));
          }
          function findInputForItem(item) {
            const name = String(item.name || "").trim();
            if (name) {
              const byId = document.getElementById(name);
              if (byId) return byId;
              try {
                const byName = document.querySelector('[name="' + CSS.escape(name) + '"]');
                if (byName) return byName;
              } catch (e) {}
            }
            const want = normalize(item.label || "");
            if (!want) return null;
            const nodes = Array.from(document.querySelectorAll(
              "textarea, input.select__input, input[type='text'], input:not([type]), input[type='email'], input[type='tel']"
            ));
            let best = null;
            let bestScore = 0;
            for (const input of nodes) {
              if (input.type === "hidden" || input.type === "file") continue;
              const lab = normalize(labelFor(input));
              if (!lab) continue;
              let score = 0;
              if (lab === want) score = 100;
              else if (lab.includes(want) || want.includes(lab)) score = Math.min(lab.length, want.length);
              if (score > bestScore) {
                bestScore = score;
                best = input;
              }
            }
            return bestScore >= 8 ? best : null;
          }
          function selectedValue(shell) {
            const current = shell && shell.querySelector(".select__single-value");
            return current ? normalize(current.textContent) : "";
          }
          function clickOption(option) {
            if (!option) return;
            option.scrollIntoView({ block: "nearest", inline: "nearest" });
            const opts = { bubbles: true, cancelable: true, view: window, button: 0 };
            option.dispatchEvent(new MouseEvent("pointerover", opts));
            option.dispatchEvent(new MouseEvent("mouseover", opts));
            option.dispatchEvent(new MouseEvent("mousemove", opts));
            try { option.dispatchEvent(new PointerEvent("pointerdown", opts)); } catch (e) {}
            option.dispatchEvent(new MouseEvent("mousedown", opts));
            try { option.dispatchEvent(new PointerEvent("pointerup", opts)); } catch (e) {}
            option.dispatchEvent(new MouseEvent("mouseup", opts));
            option.dispatchEvent(new MouseEvent("click", opts));
            try { option.click(); } catch (e) {}
            invokeMouseDown(option);
          }
          async function fillSelect(input, value) {
            const wanted = String(value || "").trim();
            if (!wanted || /^select\\.\\.\\.?$/i.test(wanted)) return false;
            const shell = input.closest(".select-shell") || input.closest(".select") || input.closest(".select__container");
            if (!shell) return false;
            const control = shell.querySelector(".select__control") || shell;
            const target = normalize(wanted);
            if (selectedValue(shell) === target) return true;

            document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
            await sleep(40);
            control.scrollIntoView({ behavior: "auto", block: "nearest" });
            invokeMouseDown(control);
            await sleep(140);
            if (wanted.length > 3) {
              setNativeValue(input, wanted);
              await sleep(120);
            }
            let option = null;
            const started = Date.now();
            while (Date.now() - started < 1600) {
              const options = openOptions();
              option =
                options.find((o) => normalize(o.textContent) === target) ||
                options.find((o) => normalize(o.textContent).startsWith(target)) ||
                options.find((o) => normalize(o.textContent).includes(target)) ||
                null;
              if (option) break;
              await sleep(40);
            }
            if (!option) return false;
            clickOption(option);
            await sleep(100);
            if (selectedValue(shell) !== target) {
              input.dispatchEvent(new KeyboardEvent("keydown", {
                key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true,
              }));
              await sleep(80);
            }
            const got = selectedValue(shell);
            return got === target || got.indexOf(target) !== -1;
          }
          async function fillLocation(input, value) {
            const city = String(value || "").split(",")[0].trim();
            if (!city) return false;
            const shell = input.closest(".select-shell") || input.closest(".select") || input.closest(".select__container");
            const control = shell && shell.querySelector(".select__control");
            document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
            await sleep(40);
            if (control) {
              control.scrollIntoView({ behavior: "auto", block: "nearest" });
              invokeMouseDown(control);
              await sleep(120);
            } else {
              input.scrollIntoView({ behavior: "auto", block: "center" });
              input.focus();
              await sleep(60);
            }
            setNativeValue(input, "");
            await sleep(30);
            let built = "";
            for (const ch of city) {
              built += ch;
              setNativeValue(input, built);
              try {
                input.dispatchEvent(new InputEvent("input", { bubbles: true, data: ch, inputType: "insertText" }));
              } catch (e) {
                input.dispatchEvent(new Event("input", { bubbles: true }));
              }
              await sleep(45);
            }
            let option = null;
            const started = Date.now();
            while (Date.now() - started < 3200) {
              const opts = Array.from(document.querySelectorAll(
                '[role="listbox"] [role="option"], .select__menu .select__option, .select__option, .pac-item, ul[role="listbox"] li'
              )).filter((o) => clean(o.textContent).length > 1);
              option = opts[0] || null;
              if (option) break;
              await sleep(70);
            }
            if (!option) {
              input.dispatchEvent(new KeyboardEvent("keydown", {
                key: "ArrowDown", code: "ArrowDown", keyCode: 40, which: 40, bubbles: true,
              }));
              await sleep(80);
              input.dispatchEvent(new KeyboardEvent("keydown", {
                key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true,
              }));
              await sleep(100);
              return !!(input.value || "").trim();
            }
            clickOption(option);
            await sleep(100);
            return true;
          }
          async function fillCheckboxGroup(item, value) {
            const wantRaw = String(value || "");
            const wanted = wantRaw.split(/\\n|;|\\|/g).map((s) => normalize(s)).filter(Boolean);
            if (!wanted.length) return false;
            const wantLabel = normalize(item.label || "");
            let fieldset = null;
            const name = String(item.name || item.id || "").trim();
            if (name) {
              try {
                fieldset = document.getElementById(name)
                  || document.querySelector('fieldset[id="' + CSS.escape(name) + '"]')
                  || document.querySelector('fieldset.checkbox[name="' + CSS.escape(name) + '"]');
              } catch (e) {}
              if (!fieldset) {
                const byName = document.querySelector('input[type="checkbox"][name="' + CSS.escape(name) + '"]');
                if (byName) fieldset = byName.closest("fieldset");
              }
            }
            if (!fieldset && wantLabel) {
              for (const fs of Array.from(document.querySelectorAll("fieldset.checkbox, fieldset"))) {
                const leg = clean((fs.querySelector("legend") || {}).textContent || "");
                if (normalize(leg) === wantLabel || normalize(leg).includes(wantLabel) || wantLabel.includes(normalize(leg))) {
                  fieldset = fs;
                  break;
                }
              }
            }
            if (!fieldset) return false;
            const wrappers = Array.from(fieldset.querySelectorAll(".checkbox__wrapper, input[type='checkbox']"));
            let matched = 0;
            // Prefer exclusive "None/Not applicable" style answers: uncheck others first.
            const exclusive = wanted.some((w) => /none|not applicable|n\\/a/.test(w));
            if (exclusive) {
              for (const box of Array.from(fieldset.querySelectorAll('input[type="checkbox"]'))) {
                if (box.checked) {
                  box.click();
                  await sleep(40);
                }
              }
            }
            for (const wrap of wrappers) {
              const box = wrap.matches && wrap.matches('input[type="checkbox"]')
                ? wrap
                : wrap.querySelector('input[type="checkbox"]');
              if (!box) continue;
              let t = "";
              if (box.id) {
                const lab = document.querySelector('label[for="' + CSS.escape(box.id) + '"]');
                if (lab) t = clean(lab.textContent);
              }
              if (!t) {
                const lab = (wrap.closest ? wrap : box.closest(".checkbox__wrapper") || box.parentElement);
                const labEl = lab && lab.querySelector && lab.querySelector("label");
                if (labEl) t = clean(labEl.textContent);
              }
              const nt = normalize(t);
              const hit = wanted.some((w) => nt === w || nt.includes(w) || w.includes(nt));
              if (!hit) continue;
              if (!box.checked) {
                box.click();
                await sleep(60);
              }
              matched += 1;
            }
            return matched > 0;
          }

          const list = Array.isArray(items) ? items : [];
          const log = [];
          const missed = [];
          for (const item of list) {
            const value = String((item && item.answer) || "").trim();
            if (!value || /^select\\.\\.\\.?$/i.test(value)) {
              missed.push((item && item.label) || "?");
              continue;
            }
            const kind = String((item && item.kind) || "").toLowerCase();
            if (kind === "checkbox") {
              const okCb = await fillCheckboxGroup(item || {}, value);
              if (okCb) log.push("Checked: " + ((item && item.label) || "?") + " = " + value);
              else missed.push((item && item.label) || "?");
              continue;
            }
            const input = findInputForItem(item || {});
            if (!input) {
              missed.push((item && item.label) || "?");
              continue;
            }
            const label = labelFor(input) || item.label || input.id || "";
            const lab = normalize(label);
            const isLoc =
              !/country|countries|sponsorship|authorized|citizen/.test(lab) &&
              (/location\\s*\\(city\\)|currently located|current location|city,\\s*state|city\\/state|where are you located|what city/.test(lab) ||
                /^(city|location)\\b/.test(lab));
            const isEdu =
              /school name|^school\\b|university|college|degree|discipline|major|field of study/.test(lab);
            let ok = false;
            if (isLoc || isEdu) ok = await fillLocation(input, value);
            else if (kind === "select" || input.classList.contains("select__input")) ok = await fillSelect(input, value);
            else {
              setNativeValue(input, value);
              ok = true;
            }
            if (ok) log.push("Filled: " + label + " = " + value);
            else missed.push(label);
          }
          return { ok: true, filled: log.length, log, missed };
        }"""

FILL_CODE_JS = """(value) => {
          function setNativeValue(el, next) {
            const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
            setter.call(el, String(next == null ? "" : next));
            el.dispatchEvent(new Event("input", { bubbles: true }));
            el.dispatchEvent(new Event("change", { bubbles: true }));
            el.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true }));
          }
          const code = String(value || "").trim();
          if (!code) return { ok: false, reason: "empty code" };

          // Preferred: Greenhouse 8 single-char boxes.
          let boxes = Array.from(document.querySelectorAll(
            ".email-verification input[id^='security-input-'], #email-verification input[id^='security-input-'], input[id^='security-input-']"
          )).filter((el) => el.getClientRects().length > 0);
          if (!boxes.length) {
            // Numeric sort security-input-0..7 if query order is odd.
            boxes = Array.from(document.querySelectorAll("input[id^='security-input-']"))
              .sort((a, b) => String(a.id).localeCompare(String(b.id), undefined, { numeric: true }));
          }
          if (boxes.length >= 4) {
            boxes.sort((a, b) => String(a.id).localeCompare(String(b.id), undefined, { numeric: true }));
            const chars = code.replace(/\\s+/g, "").split("");
            for (let i = 0; i < boxes.length; i += 1) {
              setNativeValue(boxes[i], chars[i] || "");
            }
            try { boxes[Math.min(chars.length, boxes.length) - 1]?.focus(); } catch (e) {}
            return { ok: true, kind: "boxes", filled: Math.min(chars.length, boxes.length), codeLength: chars.length };
          }

          // Fallback: one security/code text field.
          const inputs = Array.from(document.querySelectorAll(
            "input[type='text'], input[type='tel'], input[type='number'], input:not([type])"
          ));
          for (const input of inputs) {
            const label = (
              (input.id && document.querySelector('label[for="' + CSS.escape(input.id) + '"]')?.textContent) ||
              input.getAttribute("aria-label") ||
              input.placeholder ||
              ""
            ).toLowerCase();
            if (/security|verif|code|otp|one[- ]time/.test(label)) {
              setNativeValue(input, code);
              return { ok: true, kind: "single" };
            }
          }
          return { ok: false, reason: "security inputs not found" };
        }"""


def _sleep(ms: float) -> None:
    time.sleep(ms / 1000.0)


def extract_job_description(page) -> dict[str, Any]:
    page.bring_to_front()
    # Fast path: Greenhouse boards often already show JD on the posting page.
    try:
        quick = page.evaluate(EXTRACT_JD_JS) or {}
        if len(str(quick.get("description") or "")) > 200 and quick.get("title"):
            # Still click Apply if present so the form is ready for fill later.
            apply_btn = page.locator(
                'button[aria-label="Apply"], button.btn--pill:has-text("Apply"), '
                'a:has-text("Apply for this job"), a:has-text("Apply")'
            )
            if apply_btn.count() > 0:
                try:
                    apply_btn.first.click(timeout=3000)
                    _sleep(400)
                except Exception:
                    pass
            return quick
    except Exception:
        pass

    apply_selectors = [
        'button[aria-label="Apply"]',
        'button.btn--pill:has-text("Apply")',
        'a[href*="apply"]',
        'button:has-text("Apply")',
        'a:has-text("Apply")',
        'a:has-text("Apply for this job")',
    ]
    for sel in apply_selectors:
        try:
            handles = page.query_selector_all(sel)
        except Exception:
            continue
        for link in handles:
            try:
                text = (link.inner_text() or "").strip().lower()
                aria = (link.get_attribute("aria-label") or "").strip().lower()
                if "apply" not in text and "apply" not in aria:
                    continue
                try:
                    with page.expect_navigation(wait_until="domcontentloaded", timeout=8000):
                        link.click()
                except Exception:
                    link.click()
                break
            except Exception:
                try:
                    link.click()
                except Exception:
                    pass
        else:
            continue
        break

    _sleep(350)
    return page.evaluate(EXTRACT_JD_JS)


def _location_query(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.split(",")[0].strip() or text


def fill_typeahead_playwright(page, label_pattern: str, value: str) -> bool:
    """Type into a labeled Greenhouse field, then commit the top suggestion/option."""
    query = str(value or "").strip()
    if not query or not label_pattern:
        return False
    page.bring_to_front()
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    _sleep(40)

    import re as _re

    target = None
    try:
        target = page.get_by_label(_re.compile(label_pattern, _re.I)).first
        if not target.is_visible(timeout=500):
            target = None
    except Exception:
        target = None
    if target is None:
        try:
            lab = page.get_by_text(_re.compile(label_pattern, _re.I)).first
            wrap = lab.locator(
                "xpath=ancestor::div[contains(@class,'field') or contains(@class,'select') or contains(@class,'input')][1]"
            )
            inp = wrap.locator(
                "input.select__input, input[type='text'], input:not([type]), textarea"
            ).first
            if inp.is_visible(timeout=500):
                target = inp
        except Exception:
            target = None
    if target is None:
        return False

    try:
        target.click(timeout=1500)
    except Exception:
        return False
    try:
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
    except Exception:
        pass
    _sleep(60)
    typed = query.split(",")[0].strip() or query
    try:
        target.press_sequentially(typed, delay=45)
    except Exception:
        try:
            page.keyboard.type(typed, delay=45)
        except Exception:
            return False

    option_selectors = [
        ".select__menu .select__option",
        '[role="listbox"] [role="option"]',
        ".select__option",
        ".pac-item",
        'ul[role="listbox"] li',
    ]
    for sel in option_selectors:
        opt = page.locator(sel).first
        try:
            opt.wait_for(state="attached", timeout=2800)
            # Prefer option that includes the typed text; else top row.
            matched = page.locator(sel).filter(has_text=_re.compile(_re.escape(typed[:40]), _re.I))
            if matched.count() > 0:
                matched.first.click(timeout=1500, force=True)
            else:
                opt.click(timeout=1500, force=True)
            _sleep(120)
            return True
        except Exception:
            continue
    try:
        page.keyboard.press("ArrowDown")
        _sleep(80)
        page.keyboard.press("Enter")
        _sleep(120)
        return True
    except Exception:
        return False


def fill_education_playwright(page, education: dict[str, str] | None) -> dict[str, bool]:
    """Fill School / Degree / Discipline via typeahead (same pattern as Location)."""
    edu = education or {}
    results = {}
    mapping = [
        ("school", r"school name|^school$|university|college"),
        ("degree", r"^degree$|degree level"),
        ("discipline", r"discipline|major|field of study"),
    ]
    for key, pattern in mapping:
        value = str(edu.get(key) or "").strip()
        if not value:
            results[key] = False
            continue
        results[key] = fill_typeahead_playwright(page, pattern, value)
        _sleep(120)
    return results


def fill_checkbox_playwright(page, label: str, answer: str) -> bool:
    """Check the option whose label matches answer inside a checkbox fieldset."""
    wanted = [a.strip() for a in re.split(r"[\n;|]", str(answer or "")) if a.strip()]
    if not wanted:
        return False
    page.bring_to_front()
    try:
        return bool(
            page.evaluate(
                """({ label, wanted }) => {
                  function clean(t) { return (t || '').replace(/\\*/g, '').replace(/\\s+/g, ' ').trim(); }
                  function norm(t) { return clean(t).toLowerCase(); }
                  const wantLabel = norm(label);
                  const wants = (wanted || []).map(norm).filter(Boolean);
                  let fieldset = null;
                  for (const fs of Array.from(document.querySelectorAll('fieldset.checkbox, fieldset'))) {
                    const leg = clean((fs.querySelector('legend') || {}).textContent || '');
                    const n = norm(leg);
                    if (!wantLabel || n === wantLabel || n.includes(wantLabel) || wantLabel.includes(n)) {
                      fieldset = fs;
                      if (n === wantLabel) break;
                    }
                  }
                  if (!fieldset) return false;
                  const exclusive = wants.some((w) => /none|not applicable|n\\/a/.test(w));
                  if (exclusive) {
                    for (const box of Array.from(fieldset.querySelectorAll('input[type="checkbox"]'))) {
                      if (box.checked) box.click();
                    }
                  }
                  let matched = 0;
                  for (const wrap of Array.from(fieldset.querySelectorAll('.checkbox__wrapper'))) {
                    const box = wrap.querySelector('input[type="checkbox"]');
                    if (!box) continue;
                    const lab = wrap.querySelector('label');
                    const t = norm(lab ? lab.textContent : '');
                    if (!wants.some((w) => t === w || t.includes(w) || w.includes(t))) continue;
                    if (!box.checked) box.click();
                    matched += 1;
                  }
                  return matched > 0;
                }""",
                {"label": label, "wanted": wanted},
            )
        )
    except Exception:
        return False


def fill_location_playwright(page, location: str) -> bool:
    """Type location, then commit the top geocode/typeahead suggestion.

    Greenhouse Location (City) only validates after a listbox option is chosen
    (lat/lon hidden fields). Plain setValue leaves "Please enter your location".
    """
    query = _location_query(location)
    if not query:
        return False
    page.bring_to_front()
    # Close phone dialer / stray menus first.
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    _sleep(60)

    candidates = []
    try:
        candidates.append(page.get_by_label(re.compile(r"location\s*\(?city\)?", re.I)))
    except Exception:
        pass
    for sel in (
        "#location",
        'input[name="location"]',
        'input[id*="location" i]',
        'input[aria-label*="Location" i]',
    ):
        try:
            candidates.append(page.locator(sel).first)
        except Exception:
            pass

    target = None
    for loc in candidates:
        try:
            handle = loc.first if hasattr(loc, "first") else loc
            if handle.is_visible(timeout=400):
                target = handle
                break
        except Exception:
            continue
    if target is None:
        # Last resort: label text near Locate me.
        try:
            target = page.locator(
                "xpath=//label[contains(translate(., 'LOCATIONCITY', 'locationcity'), 'location')]"
                "/following::input[not(@type='hidden')][1]"
            ).first
            if not target.is_visible(timeout=400):
                target = None
        except Exception:
            target = None
    if target is None:
        return False

    try:
        target.click(timeout=1500)
    except Exception:
        return False
    try:
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
    except Exception:
        pass
    _sleep(80)
    # Real keystrokes so api-geocode-earth-proxy debounce runs.
    try:
        target.press_sequentially(query, delay=50)
    except Exception:
        try:
            page.keyboard.type(query, delay=50)
        except Exception:
            return False

    option_selectors = [
        '[role="listbox"] [role="option"]',
        ".select__menu .select__option",
        ".select__option",
        ".pac-item",
        'ul[role="listbox"] li',
    ]
    for sel in option_selectors:
        opt = page.locator(sel).first
        try:
            opt.wait_for(state="attached", timeout=2800)
            # Top row — even if aria-hidden / low opacity.
            opt.click(timeout=1500, force=True)
            _sleep(150)
            return True
        except Exception:
            continue

    # Keyboard: focus first suggestion then Enter.
    try:
        page.keyboard.press("ArrowDown")
        _sleep(100)
        page.keyboard.press("Enter")
        _sleep(150)
        return True
    except Exception:
        return False


def _country_to_iso2(country: str, phone: str = "") -> str:
    c = re.sub(r"\s+", " ", str(country or "").strip().lower())
    if re.search(r"united states|^usa$|^us$|america", c):
        return "us"
    if re.search(r"canada|^ca$", c):
        return "ca"
    if re.search(r"united kingdom|^uk$|great britain|england", c):
        return "gb"
    digits = re.sub(r"[^\d+]", "", str(phone or ""))
    if digits.startswith("+1") or (digits and not digits.startswith("+")):
        return "us"
    return "us"


def fill_phone_country_playwright(page, country: str = "", phone: str = "") -> bool:
    """Commit the intl-tel-input Country control (clears 'Select a country')."""
    iso2 = _country_to_iso2(country, phone)
    name = {"us": "United States", "ca": "Canada", "gb": "United Kingdom"}.get(iso2, "United States")
    page.bring_to_front()
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    _sleep(40)

    # Fast path: iti instance API inside the page.
    try:
        ok = page.evaluate(
            """(code) => {
              const input = document.getElementById('phone');
              if (!input) return false;
              let iti = null;
              try {
                if (window.intlTelInput && intlTelInput.getInstance)
                  iti = intlTelInput.getInstance(input);
              } catch (e) {}
              try {
                if (!iti && window.intlTelInputGlobals && intlTelInputGlobals.getInstance)
                  iti = intlTelInputGlobals.getInstance(input);
              } catch (e) {}
              iti = iti || input.iti || input._iti;
              if (!iti) return false;
              if (typeof iti.setSelectedCountry === 'function') iti.setSelectedCountry(code);
              else if (typeof iti.setCountry === 'function') iti.setCountry(code);
              else return false;
              return true;
            }""",
            iso2,
        )
        if ok:
            _sleep(80)
            return True
    except Exception:
        pass

    btn = page.locator("button.iti__selected-country, .iti__selected-country").first
    try:
        if not btn.is_visible(timeout=800):
            return False
        btn.click(timeout=1500)
    except Exception:
        return False
    _sleep(150)
    search = page.locator(".iti__search-input").first
    try:
        if search.is_visible(timeout=600):
            search.click()
            search.fill("")
            try:
                search.press_sequentially(name, delay=35)
            except Exception:
                search.fill(name)
            _sleep(200)
    except Exception:
        pass

    option = page.locator(f'li.iti__country[data-country-code="{iso2}"]').first
    try:
        option.wait_for(state="attached", timeout=2000)
        option.click(timeout=1500, force=True)
        _sleep(120)
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return True
    except Exception:
        try:
            page.keyboard.press("Enter")
            _sleep(100)
            page.keyboard.press("Escape")
            return True
        except Exception:
            return False


def fill_greenhouse_form(page, profile: dict[str, Any]) -> dict[str, Any]:
    page.bring_to_front()
    result = page.evaluate(
        """async ([profileData, script]) => {
          const fn = new Function(script + '; return fillGreenhouse;')();
          return await fn(profileData);
        }""",
        [profile, FILL_SCRIPT],
    ) or {}
    personal = profile.get("personal") or {}
    log = list(result.get("log") or [])

    # Phone Country (intl-tel-input dialer) — must be explicitly committed.
    if personal.get("phone") or personal.get("country"):
        ok_phone_country = fill_phone_country_playwright(
            page,
            str(personal.get("country") or ""),
            str(personal.get("phone") or ""),
        )
        log.append("Phone country commit: " + ("ok" if ok_phone_country else "failed"))
        result["phoneCountryOk"] = ok_phone_country

    # Application Country react-select (#country), separate from the phone dialer.
    app_country = str(personal.get("country") or "United States").strip()
    if app_country:
        try:
            sel = fill_selects_playwright(
                page,
                [
                    {
                        "label": "Country",
                        "name": "country",
                        "id": "country",
                        "kind": "select",
                        "answer": app_country,
                        "choices": [app_country],
                    }
                ],
            )
            ok_app = bool(sel.get("filled"))
            log.append(
                "App country select: "
                + ("ok" if ok_app else "failed")
                + f" ({app_country})"
            )
            result["appCountryOk"] = ok_app
        except Exception as error:
            log.append(f"App country select failed: {error}")

    location = str(personal.get("location") or "").strip()
    if location:
        ok = fill_location_playwright(page, location)
        log.append(
            "Location top-suggestion: " + ("ok" if ok else "failed") + f" ({_location_query(location)})"
        )
        result["locationOk"] = ok

    education = profile.get("education") or {}
    if any(str(education.get(k) or "").strip() for k in ("school", "degree", "discipline")):
        edu_ok = fill_education_playwright(page, education)
        for key, ok in edu_ok.items():
            val = str(education.get(key) or "")
            if val:
                log.append(f"Education {key}: " + ("ok" if ok else "failed") + f" ({val})")
        result["educationOk"] = edu_ok

    result["log"] = log
    return result


def upload_resume(page, resume_path: str) -> bool:
    """
    Greenhouse uses <input id="resume" type="file" accept=".pdf,.doc,...">
    (visually hidden under Resume/CV). Prefer that exact control.
    """
    page.bring_to_front()
    path = str(resume_path or "")
    if not path:
        raise RuntimeError("Resume path is empty")

    selectors = [
        "#resume",
        'input[type="file"]#resume',
        'input[type="file"][accept*=".pdf"]',
        'input[type="file"][accept*="pdf"]',
        'input[type="file"][name="resume"]',
        'input[type="file"]',
    ]
    file_input = None
    for sel in selectors:
        try:
            handle = page.query_selector(sel)
        except Exception:
            handle = None
        if not handle:
            continue
        # Prefer the resume control over cover_letter if a bare file input matched.
        try:
            el_id = (handle.get_attribute("id") or "").lower()
            if el_id == "cover_letter":
                continue
        except Exception:
            pass
        file_input = handle
        break

    if not file_input:
        raise RuntimeError('Resume file input (#resume) not found on the application form')

    file_input.set_input_files(path)
    _sleep(350)
    # Best-effort confirmation the filename landed in the UI.
    try:
        page.wait_for_selector(
            ".file-upload [class*='filename'], .file-upload__filename, "
            "#resume + *, [data-testid*='resume']",
            timeout=2000,
        )
    except Exception:
        pass
    return True


COLLECT_QUESTIONS_JS = """() => {
  function clean(text) {
    return (text || "").replace(/\\*/g, "").replace(/\\s+/g, " ").trim();
  }
  function isJunkLabel(label) {
    const t = clean(label).toLowerCase();
    if (!t || t.length < 3) return true;
    if (/^select\\.?\\.?\\.?$/.test(t)) return true;
    if (t === "required" || t === "optional") return true;
    return false;
  }
  function descChoices(wrap) {
    // Greenhouse often lists options under .question-description (e.g. USA / Canada).
    const nodes = Array.from((wrap || document).querySelectorAll(
      ".question-description, [id$='-description'], .body__secondary .question-description"
    ));
    const out = [];
    const seen = new Set();
    for (const node of nodes) {
      // Prefer <br>-split lines / <p> / <li>
      const html = node.innerHTML || "";
      const chunks = html
        .replace(/<br\\s*\\/?>/gi, "\\n")
        .replace(/<\\/p>/gi, "\\n")
        .replace(/<\\/li>/gi, "\\n")
        .replace(/<[^>]+>/g, " ")
        .split(/\\n|\\u2022|•|;/);
      const texts = chunks.length > 1
        ? chunks
        : String(node.innerText || node.textContent || "").split(/\\n|\\u2022|•/);
      for (const raw of texts) {
        const t = clean(raw);
        if (!t || t.length < 2 || t.length > 200) continue;
        if (/^select\\.?\\.?\\.?$/i.test(t)) continue;
        if (/this field is required/i.test(t)) continue;
        if (/\\+\\d{1,4}$/.test(t)) continue; // dial codes
        const key = t.toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        out.push(t);
      }
    }
    return out;
  }
  function isRequiredWrap(wrap, input) {
    if (input && (input.required || input.getAttribute("aria-required") === "true")) return true;
    if (!wrap) return false;
    if (wrap.getAttribute("aria-required") === "true") return true;
    if (wrap.querySelector(".required, .asterisk, span.required, [aria-hidden='true']")) {
      const lab = wrap.querySelector("label, .label");
      if (lab && /\\*/.test(lab.textContent || "")) return true;
    }
    const lab = wrap.querySelector("label, .label");
    return !!(lab && /\\*/.test(lab.textContent || ""));
  }
  const skipIds = new Set([
    "first_name", "last_name", "email", "phone", "preferred_name", "country",
    "gender", "hispanic_ethnicity", "veteran_status", "disability_status",
    "resume", "cover_letter"
  ]);
  // Profile / typeahead-filled fields — keep off DeepSeek.
  const skipLabel = /(first name|last name|email|phone|linkedin|github|resume|cover letter|password|security code|verification|gender|veteran|disability|hispanic|race|ethnicity|^location\\b|location \\(city\\)|city, state|currently located|school name|^school\\b|university|college|degree|discipline|major|field of study)/i;
  const out = [];
  const seen = new Set();
  let auto = 0;

  // Primary: every required .field-wrapper (custom Greenhouse questions).
  const wrappers = Array.from(document.querySelectorAll(".field-wrapper"));
  for (const wrap of wrappers) {
    if (wrap.closest(".iti, .intl-tel-input, .PhoneInput")) continue;

    // Checkbox groups (multi-select).
    const fieldset = wrap.querySelector("fieldset.checkbox, fieldset[class*='checkbox']");
    if (fieldset) {
      if (!(fieldset.getAttribute("aria-required") === "true"
        || fieldset.querySelector("input[type='checkbox'][required]")
        || /\\*/.test((fieldset.querySelector("legend") || {}).textContent || ""))) {
        // still allow if any checkbox is required
        const anyReq = Array.from(fieldset.querySelectorAll("input[type='checkbox']")).some(
          (b) => b.required || b.getAttribute("aria-required") === "true"
        );
        if (!anyReq) continue;
      }
      const legend = fieldset.querySelector("legend, .checkbox__description, .label");
      const label = clean(legend ? legend.textContent : "");
      if (isJunkLabel(label) || skipLabel.test(label)) continue;
      const boxes = Array.from(fieldset.querySelectorAll('input[type="checkbox"]'));
      if (!boxes.length) continue;
      if (boxes.some((b) => b.checked)) continue;
      const choices = [];
      const seenChoice = new Set();
      for (const box of boxes) {
        let t = "";
        if (box.id) {
          const lab = document.querySelector('label[for="' + CSS.escape(box.id) + '"]');
          if (lab) t = clean(lab.textContent);
        }
        if (!t) {
          const wrapLab = box.closest(".checkbox__wrapper");
          const lab = wrapLab && wrapLab.querySelector("label");
          if (lab) t = clean(lab.textContent);
        }
        if (!t || seenChoice.has(t.toLowerCase())) continue;
        seenChoice.add(t.toLowerCase());
        choices.push(t);
      }
      const key = label.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      auto += 1;
      const finder = fieldset.id || (boxes[0] && boxes[0].name) || ("cb" + auto);
      const descNode = wrap.querySelector(".question-description, [id$='-description']");
      out.push({
        label,
        name: finder,
        id: finder,
        kind: "checkbox",
        required: true,
        value: "",
        choices,
        description: clean(descNode ? (descNode.innerText || descNode.textContent || "") : ""),
        fieldText: clean(wrap.innerText || wrap.textContent || "")
      });
      continue;
    }

    const selectInput = wrap.querySelector("input.select__input");
    const textInput = wrap.querySelector(
      "textarea, input.input, input.input__single-line, input[type='text'], input:not([type]), input[type='email'], input[type='tel'], input[type='number']"
    );
    const input = selectInput || textInput;
    if (!input) continue;
    if (input.type === "hidden" || input.type === "file" || input.type === "checkbox") continue;
    if (skipIds.has(input.id)) continue;
    if (!isRequiredWrap(wrap, input)) continue;

    const labelEl = wrap.querySelector("legend, label.label, .select__label, label, .label");
    let label = clean(labelEl ? labelEl.textContent : "");
    if (!label && input.id) {
      const byFor = document.querySelector('label[for="' + CSS.escape(input.id) + '"]');
      if (byFor) label = clean(byFor.textContent);
    }
    if (!label) label = clean(input.getAttribute("aria-label") || "");
    if (isJunkLabel(label) || skipLabel.test(label)) continue;

    const isSelect = !!selectInput || !!wrap.querySelector(".select__control, .select-shell");
    if (isSelect) {
      const selected = wrap.querySelector(".select__single-value");
      const selectedText = selected ? clean(selected.textContent) : "";
      if (selectedText && !/^select/i.test(selectedText)) continue;
    } else if ((input.value || "").trim()) {
      continue;
    }

    const key = label.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    auto += 1;
    if (isSelect && !input.getAttribute("data-gh-q")) {
      input.setAttribute("data-gh-q", "q" + auto);
    }
    const finder = input.id || input.name || input.getAttribute("data-gh-q") || ("q" + auto);
    const desc = descChoices(wrap);
    const descNode = wrap.querySelector(".question-description, [id$='-description']");
    // Full required field text (label + description + helpers) for DeepSeek context.
    const fieldText = clean(wrap.innerText || wrap.textContent || "");
    out.push({
      label,
      name: finder,
      id: finder,
      kind: isSelect ? "select" : (input.tagName === "TEXTAREA" ? "textarea" : "text"),
      required: true,
      value: isSelect ? "" : (input.value || ""),
      choices: isSelect ? desc : [],
      description: clean(descNode ? (descNode.innerText || descNode.textContent || "") : ""),
      fieldText
    });
  }
  return out;
}"""


READ_SELECT_CHOICES_JS = """async (payload) => {
  function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
  function clean(text) {
    return (text || "").replace(/\\*/g, "").replace(/\\s+/g, " ").trim();
  }
  function isDialCodeChoice(text) {
    // Phone country picker: "United States+1", "Afghanistan+93"
    return /\\+\\d{1,4}$/.test(text) || /^\\+\\d{1,4}\\b/.test(text);
  }
  function looksLikeCountryDialList(list) {
    if (!list || list.length < 20) return false;
    const hits = list.filter(isDialCodeChoice).length;
    return hits >= Math.max(10, list.length * 0.5);
  }
  function reactProps(el) {
    if (!el) return null;
    for (const key of Object.keys(el)) {
      if (key.startsWith("__reactProps$")) return el[key];
    }
    return null;
  }
  function invokeMouseDown(el) {
    let node = el;
    for (let hop = 0; hop < 4 && node; hop += 1) {
      const props = reactProps(node);
      if (props && typeof props.onMouseDown === "function") {
        props.onMouseDown({
          button: 0, target: node, currentTarget: node,
          preventDefault() {}, stopPropagation() {}, persist() {},
        });
        return true;
      }
      node = node.parentElement;
    }
    el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, view: window }));
    el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, view: window }));
    el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
    return false;
  }
  function findInput(fieldId, label) {
    if (fieldId) {
      let input = document.getElementById(fieldId);
      if (input && input.classList.contains("select__input")) return input;
      input = document.querySelector('input.select__input[data-gh-q="' + CSS.escape(fieldId) + '"]');
      if (input) return input;
      try {
        input = document.querySelector('input.select__input#' + CSS.escape(fieldId));
        if (input) return input;
      } catch (e) {}
    }
    const want = clean(label).toLowerCase();
    if (!want) return null;
    let best = null;
    let bestScore = 0;
    for (const input of Array.from(document.querySelectorAll("input.select__input"))) {
      // Never use the phone dial-code widget.
      if (input.closest(".iti, .intl-tel-input, .PhoneInput")) continue;
      const wrap = input.closest(".field-wrapper, .select__container, .select-shell, .select, [role='group']");
      const lab = wrap && wrap.querySelector("label, .label");
      const text = clean(lab && lab.textContent).toLowerCase();
      if (!text) continue;
      let score = 0;
      if (text === want) score = 100;
      else if (text.includes(want) || want.includes(text)) score = Math.min(text.length, want.length);
      if (score > bestScore) {
        bestScore = score;
        best = input;
      }
    }
    return bestScore >= 8 ? best : null;
  }
  function readMenuOptions(control) {
    // Prefer the react-select menu tied to this control / currently open.
    const menus = Array.from(document.querySelectorAll(".select__menu"))
      .filter((m) => m.getClientRects().length > 0)
      .filter((m) => !m.closest(".iti, .iti__country-list, .intl-tel-input"));
    let menu = null;
    if (menus.length === 1) menu = menus[0];
    else if (menus.length > 1 && control) {
      const cr = control.getBoundingClientRect();
      menu = menus
        .map((m) => {
          const r = m.getBoundingClientRect();
          const dx = Math.abs(r.left - cr.left);
          const dy = Math.abs(r.top - cr.bottom);
          return { m, dist: dx + dy };
        })
        .sort((a, b) => a.dist - b.dist)[0].m;
    } else {
      menu = menus[menus.length - 1] || null;
    }
    if (!menu) return [];
    return Array.from(menu.querySelectorAll(".select__option"))
      .map((o) => clean(o.textContent))
      .filter((t) => t && !/^select\\.?\\.?\\.?$/i.test(t) && !isDialCodeChoice(t));
  }

  const fieldId = typeof payload === "string" ? payload : (payload && payload.id) || "";
  const label = typeof payload === "string" ? "" : (payload && payload.label) || "";
  const input = findInput(fieldId, label);
  if (!input) return [];
  if (input.closest(".iti, .intl-tel-input, .PhoneInput")) return [];
  const shell = input.closest(".select-shell") || input.closest(".select") || input.closest(".select__container");
  const control = shell && shell.querySelector(".select__control");
  if (!control) return [];

  // Close any open phone country list first.
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
  await sleep(80);
  const itiList = document.querySelector(".iti__country-list");
  if (itiList) itiList.classList.add("iti__hide");

  control.scrollIntoView({ behavior: "auto", block: "nearest" });
  invokeMouseDown(control);
  await sleep(250);

  let options = [];
  const started = Date.now();
  while (Date.now() - started < 2500) {
    options = readMenuOptions(control);
    if (options.length) break;
    await sleep(80);
  }
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
  await sleep(60);

  if (looksLikeCountryDialList(options)) return [];

  const seen = new Set();
  const out = [];
  for (const opt of options) {
    const key = opt.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(opt);
  }
  return out;
}"""


def _desc_choices_usable(label: str, choices: list[str]) -> list[str]:
    """Use .question-description lines as select choices only when they look like options.

    Yes/No questions often list countries (or other context) under the description —
    those lines are context, not the dropdown values.
    """
    cleaned = [str(c).strip() for c in choices if str(c).strip()]
    if not cleaned:
        return []
    lab = (label or "").lower()
    if re.search(
        r"\b(are you|do you|have you|will you|can you|did you|would you)\b",
        lab,
    ):
        return []
    # Too many long lines → prose, not a choice list.
    if len(cleaned) > 12:
        return []
    return cleaned


def _rule_value_for_label(label: str, rules: list[dict[str, Any]] | None) -> str | None:
    hay = re.sub(r"\s+", " ", str(label or "").strip().lower())
    if not hay or not rules:
        return None
    for rule in rules:
        needle = re.sub(r"\s+", " ", str(rule.get("includes") or "").strip().lower())
        if needle and needle in hay:
            value = rule.get("value")
            if value is None:
                continue
            return str(value)
    return None


def _education_from_payload(payload: Any) -> dict[str, str]:
    """Normalize resume/profile education into school/degree/discipline strings."""
    out = {"school": "", "degree": "", "discipline": ""}
    if not isinstance(payload, dict):
        return out
    edu = payload.get("education")
    if isinstance(edu, list) and edu:
        edu = edu[0] if isinstance(edu[0], dict) else {}
    if not isinstance(edu, dict):
        return out
    out["school"] = str(
        edu.get("institution")
        or edu.get("school")
        or edu.get("school_name")
        or edu.get("university")
        or ""
    ).strip()
    out["degree"] = str(edu.get("degree") or edu.get("degree_name") or "").strip()
    out["discipline"] = str(
        edu.get("discipline") or edu.get("major") or edu.get("field") or ""
    ).strip()
    # "Bachelor's Degree, Computer Science" → split if discipline empty
    if out["degree"] and not out["discipline"] and "," in out["degree"]:
        left, right = out["degree"].split(",", 1)
        if left.strip() and right.strip():
            out["degree"] = left.strip()
            out["discipline"] = right.strip()
    return out


def collect_questions(
    page,
    *,
    read_choices: bool = True,
    dropdown_rules: list[dict[str, Any]] | None = None,
    checkbox_rules: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Collect only required (*) Greenhouse questions that still need answers."""
    page.bring_to_front()
    _sleep(80)
    questions = page.evaluate(COLLECT_QUESTIONS_JS) or []
    questions = [
        q
        for q in questions
        if q.get("required") is not False
        and str(q.get("label") or "").strip()
        and not re.match(r"^select\.?\.?\.?$", str(q.get("label") or "").strip(), re.I)
    ]
    # Opening every dropdown is slow — only do it when DeepSeek must pick,
    # and skip selects already covered by dropdownRules (Yes/No etc.).
    # Prefer choices already scraped from .question-description when usable.
    for question in questions:
        kind = str(question.get("kind") or "")
        label = str(question.get("label") or "").strip()
        if kind == "checkbox":
            ruled = _rule_value_for_label(label, checkbox_rules)
            if ruled is not None:
                question["ruleValue"] = ruled
            question.setdefault("choices", list(question.get("choices") or []))
            continue
        if kind != "select":
            question.setdefault("choices", [])
            continue
        ruled = _rule_value_for_label(label, dropdown_rules)
        if ruled is not None:
            question["choices"] = []
            question["ruleValue"] = ruled
            continue
        if not read_choices:
            question["choices"] = []
            continue
        desc_choices = _desc_choices_usable(label, list(question.get("choices") or []))
        if desc_choices:
            question["choices"] = desc_choices
            continue
        field_id = str(question.get("id") or question.get("name") or "").strip()
        choices: list[str] = []
        try:
            choices = page.evaluate(
                READ_SELECT_CHOICES_JS, {"id": field_id, "label": label}
            ) or []
        except Exception:
            choices = []
        choices = [str(c).strip() for c in choices if str(c).strip()]
        if not choices:
            choices = _read_choices_playwright(page, field_id, label)
        question["choices"] = choices
        _sleep(40)
    return questions


def _read_choices_playwright(page, field_id: str, label: str) -> list[str]:
    """Trusted-click fallback when JS menu scrape returns nothing."""
    import re as _re

    def is_dial(text: str) -> bool:
        return bool(re.search(r"\+\d{1,4}$", text or ""))

    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    _sleep(60)
    control = None
    if field_id:
        safe = field_id.replace("\\", "\\\\").replace('"', '\\"')
        for cand in (
            page.locator(f"input.select__input#{safe}").locator(
                "xpath=ancestor::div[contains(@class,'select__control')][1]"
            ),
            page.locator(f'input.select__input[data-gh-q="{safe}"]').locator(
                "xpath=ancestor::div[contains(@class,'select__control')][1]"
            ),
        ):
            try:
                if cand.count() > 0 and cand.first.is_visible():
                    control = cand.first
                    break
            except Exception:
                continue
    if control is None and label:
        labs = page.get_by_text(_re.compile(_re.escape(label[:70]), _re.I))
        if labs.count() > 0:
            ctrl = labs.first.locator(
                "xpath=ancestor::div[contains(@class,'select') or contains(@class,'field')][1]"
                "//div[contains(@class,'select__control')]"
            )
            if ctrl.count() > 0:
                control = ctrl.first
    if control is None:
        return []
    try:
        control.scroll_into_view_if_needed(timeout=2000)
        control.click(timeout=2500)
        _sleep(220)
        # Only Greenhouse react-select menus — never phone dial-code listbox.
        opts = page.locator(".select__menu:visible .select__option")
        if opts.count() == 0:
            opts = page.locator(".select__menu .select__option")
        texts: list[str] = []
        for i in range(min(opts.count(), 40)):
            t = re.sub(r"\s+", " ", (opts.nth(i).inner_text() or "")).strip()
            if not t or re.match(r"^select\.?\.?\.?$", t, re.I) or is_dial(t):
                continue
            texts.append(t)
        page.keyboard.press("Escape")
        seen: set[str] = set()
        out: list[str] = []
        for t in texts:
            k = t.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(t)
        # Reject accidental phone country dumps.
        if len(out) >= 20 and sum(1 for t in out if is_dial(t)) >= 10:
            return []
        if len(out) >= 30 and all(len(t) < 40 for t in out[:10]):
            # Huge short-option lists that aren't management/challenge questions.
            dialish = sum(1 for t in out if "+" in t)
            if dialish >= 10:
                return []
        return out
    except Exception:
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return []


def apply_gap_answers(
    page,
    answers: dict[str, Any] | list[dict[str, Any]],
    questions: list[dict[str, Any]] | None = None,
    *,
    use_playwright_fallback: bool = True,
) -> dict[str, Any]:
    """
    Fill answers into the exact Greenhouse fields collected earlier.
    Prefer a list of {label, name, kind, answer}; dict label->answer is also accepted.
    """
    page.bring_to_front()
    _sleep(80)

    items: list[dict[str, Any]] = []
    if isinstance(answers, list):
        items = [a for a in answers if isinstance(a, dict)]
    elif isinstance(answers, dict):
        if questions:
            for question in questions:
                label = str(question.get("label") or "").strip()
                value = answers.get(label)
                if value is None:
                    # numbered fallback
                    continue
                items.append(
                    {
                        "label": label,
                        "name": question.get("name") or question.get("id") or label,
                        "kind": question.get("kind") or "text",
                        "answer": value,
                    }
                )
            # Include any leftover answer keys that weren't in questions.
            used = {str(i.get("label") or "") for i in items}
            for key, value in answers.items():
                if str(key) in used:
                    continue
                items.append({"label": str(key), "name": str(key), "kind": "text", "answer": value})
        else:
            items = [
                {"label": str(k), "name": str(k), "kind": "text", "answer": v}
                for k, v in answers.items()
            ]

    # Text fields via JS first (fast).
    js_result = page.evaluate(APPLY_GAPS_JS, items) or {}
    missed = list(js_result.get("missed") or [])
    pw: dict[str, Any] = {"filled": 0, "log": [], "labels": []}
    log = list(js_result.get("log") or [])
    filled = int(js_result.get("filled") or 0)

    # Checkbox groups: Playwright/DOM click commit.
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("kind") or "").lower() != "checkbox":
            continue
        label = str(item.get("label") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if not answer:
            continue
        if fill_checkbox_playwright(page, label, answer):
            filled += 1
            log.append(f"Checked PW: {label} = {answer}")
            missed = [m for m in missed if str(m).strip().lower() != label.lower()]
        elif label not in missed:
            missed.append(label)

    # Education typeaheads among gap answers.
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if not answer:
            continue
        if not re.search(
            r"school name|^school\b|university|college|degree|discipline|major|field of study",
            label,
            re.I,
        ):
            continue
        if fill_typeahead_playwright(page, re.escape(label[:40]), answer):
            filled += 1
            log.append(f"Education PW: {label} = {answer}")
            missed = [m for m in missed if str(m).strip().lower() != label.lower()]

    # ALWAYS re-commit dropdowns with Playwright trusted clicks.
    # Greenhouse react-select often opens/highlights but never sticks via JS-only clicks.
    if use_playwright_fallback:
        select_items = [
            item
            for item in items
            if isinstance(item, dict)
            and str(item.get("kind") or "").lower() not in {"text", "textarea", "checkbox"}
            and (
                str(item.get("kind") or "") == "select"
                or bool(item.get("choices"))
                or str(item.get("answer") or "").strip().lower() in {"yes", "no"}
                or (
                    len(str(item.get("answer") or "")) <= 80
                    and not str(item.get("answer") or "").startswith("http")
                )
            )
        ]
        # Also retry anything JS reported missed that looks like a select answer.
        if missed:
            missed_l = {str(m).strip().lower() for m in missed}
            for item in items:
                if not isinstance(item, dict):
                    continue
                if str(item.get("kind") or "").lower() in {"text", "textarea", "checkbox"}:
                    continue
                if str(item.get("label") or "").strip().lower() in missed_l and item not in select_items:
                    select_items.append(item)
        if select_items:
            pw = fill_selects_playwright(page, select_items)
            filled += int(pw.get("filled") or 0)
            log.extend(list(pw.get("log") or []))

    pw_labels = {str(x).strip().lower() for x in (pw.get("labels") or [])}
    missed = [m for m in missed if str(m).strip().lower() not in pw_labels]
    return {
        "ok": True,
        "filled": filled,
        "log": log,
        "missed": missed,
        "playwright": pw,
    }


def fill_selects_playwright(page, items: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Commit react-select choices with real Playwright clicks.
    Fixes menus that open/highlight but stay on Select...
    """
    import re as _re

    page.bring_to_front()
    log: list[str] = []
    labels: list[str] = []
    filled = 0

    def selected_text(field_id: str) -> str:
        if not field_id:
            return ""
        try:
            return str(
                page.evaluate(
                    """(id) => {
                      const input = document.getElementById(id);
                      if (!input) return "";
                      const shell = input.closest(".select-shell, .select, .select__container");
                      const cur = shell && shell.querySelector(".select__single-value");
                      return (cur && cur.textContent || "").replace(/\\s+/g, " ").trim();
                    }""",
                    field_id,
                )
                or ""
            )
        except Exception:
            return ""

    def already_selected(field_id: str, value: str) -> bool:
        cur = selected_text(field_id).lower()
        want = (value or "").strip().lower()
        if not cur or not want or cur.startswith("select"):
            return False
        return cur == want or want[:40] in cur or cur[:40] in want

    def find_option_locator(value: str, choices: list[str]):
        # Snap to known choice first.
        from app.automation.deepseek import _snap_to_choice

        target = _snap_to_choice(value, choices) if choices else value
        needles = [target]
        # Also try distinctive head ("1 - Hands-on...") and leading number.
        head = target.split(":", 1)[0].strip()
        if head and head not in needles:
            needles.append(head)
        m = _re.match(r"^(\d+)\s*[-.)]", target.strip())
        if m:
            needles.append(m.group(1))

        for needle in needles:
            if not needle:
                continue
            # Exact full option
            loc = page.locator(
                ".select__menu .select__option",
                has_text=_re.compile(rf"^{_re.escape(needle)}$", _re.I),
            )
            if loc.count() > 0:
                return loc.first, target
            # Starts with
            loc = page.locator(
                ".select__menu .select__option",
                has_text=_re.compile(rf"^{_re.escape(needle[:80])}", _re.I),
            )
            if loc.count() > 0:
                return loc.first, target
            # Contains (last resort for long options)
            if len(needle) >= 4:
                loc = page.locator(
                    ".select__option",
                    has_text=_re.compile(_re.escape(needle[:60]), _re.I),
                )
                if loc.count() > 0:
                    return loc.first, target
        return None, target

    for item in items:
        if not isinstance(item, dict):
            continue
        value = str(item.get("answer") or "").strip()
        kind = str(item.get("kind") or "").strip().lower()
        choices = [str(c).strip() for c in (item.get("choices") or []) if str(c).strip()]
        label = str(item.get("label") or "").strip()
        field_id = str(item.get("name") or item.get("id") or "").strip()
        if not value or value.startswith("http"):
            continue
        if kind == "text" and not choices and value.lower() not in {"yes", "no"}:
            # Free-text answers are not dropdowns.
            if len(value) > 80:
                continue
        if field_id and already_selected(field_id, value):
            continue

        try:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            _sleep(80)

            control = None
            if field_id:
                safe_id = field_id.replace("\\", "\\\\").replace('"', '\\"')
                candidates = [
                    page.locator(f"#{safe_id}").locator(
                        "xpath=ancestor::div[contains(@class,'select__control')][1]"
                    ),
                    page.locator(f"#{safe_id}").locator(
                        "xpath=ancestor::div[contains(@class,'select-shell') or contains(@class,'select__container')][1]"
                        "//div[contains(@class,'select__control')]"
                    ),
                ]
                for cand in candidates:
                    try:
                        if cand.count() > 0 and cand.first.is_visible():
                            control = cand.first
                            break
                    except Exception:
                        continue

            if control is None and label:
                lab_matches = page.get_by_text(
                    _re.compile(_re.escape(label[:70]), _re.I)
                )
                if lab_matches.count() > 0:
                    wrap = lab_matches.first.locator(
                        "xpath=ancestor::div[contains(@class,'select') or contains(@class,'field') or contains(@class,'application')][1]"
                    )
                    ctrl = wrap.locator(".select__control")
                    if ctrl.count() > 0:
                        control = ctrl.first

            if control is None:
                log.append(f"PW select control missing: {label or field_id}")
                continue

            control.scroll_into_view_if_needed(timeout=2500)
            control.click(timeout=2500)
            _sleep(160)

            opt, target = find_option_locator(value, choices)
            if opt is None:
                # Type a short filter then retry.
                try:
                    page.keyboard.type(target[:24], delay=15)
                    _sleep(180)
                    opt, target = find_option_locator(value, choices)
                except Exception:
                    pass
            if opt is None:
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
                log.append(f"PW select option missing: {label or field_id} -> {value[:60]}")
                continue

            try:
                opt.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                pass
            try:
                opt.click(timeout=2500)
            except Exception:
                opt.click(timeout=2500, force=True)
            _sleep(150)
            # Enter commits if click only highlighted.
            if field_id and not already_selected(field_id, target):
                try:
                    page.keyboard.press("Enter")
                except Exception:
                    pass
                _sleep(120)

            if not field_id or already_selected(field_id, target) or already_selected(field_id, value):
                filled += 1
                labels.append(label or field_id)
                log.append(f"PW select: {label or field_id} = {target[:80]}")
            else:
                log.append(
                    f"PW select stuck Select...: {label or field_id} "
                    f"(got {selected_text(field_id)!r})"
                )
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
        except Exception as error:
            log.append(f"PW select failed {label or field_id}: {error}")

    return {"filled": filled, "log": log, "labels": labels}


def submit_application(page) -> dict[str, Any]:
    """
    Click Greenhouse's real "Submit application" button.
    Prefer Playwright locator clicks (trusted events); fall back to in-page JS.
    Raises if the button cannot be clicked.
    """
    page.bring_to_front()
    _sleep(120)

    # Try role/text first (most reliable on Greenhouse), then CSS.
    attempts: list[tuple[str, Any]] = [
        ("role=button Submit application", lambda: page.get_by_role("button", name="Submit application")),
        ("role=button Submit Application", lambda: page.get_by_role("button", name="Submit Application")),
        ("css .application--submit button[type='submit']", lambda: page.locator(".application--submit button[type='submit']")),
        ("css .application--submit button.btn", lambda: page.locator(".application--submit button.btn")),
        ("css form button[type='submit']", lambda: page.locator("form button[type='submit']")),
        ("css button[type='submit']", lambda: page.locator("button[type='submit']")),
        ("text Submit application", lambda: page.locator("button:has-text('Submit application')")),
    ]

    last_error: Exception | None = None
    for label, factory in attempts:
        try:
            matches = factory()
            if matches.count() == 0:
                continue
            loc = matches.first
            try:
                loc.wait_for(state="visible", timeout=4000)
            except Exception as error:
                last_error = error
                continue
            aria = (loc.get_attribute("aria-disabled") or "").lower()
            try:
                disabled = bool(loc.is_disabled())
            except Exception:
                disabled = False
            if aria == "true" or disabled:
                last_error = RuntimeError(
                    f"Submit button found via {label!r} but it is disabled"
                )
                continue
            loc.scroll_into_view_if_needed(timeout=3000)
            _sleep(80)
            try:
                loc.click(timeout=5000)
            except Exception:
                loc.click(timeout=5000, force=True)
            _sleep(400)
            return {"ok": True, "clicked": "Submit application", "via": label}
        except Exception as error:
            last_error = error
            continue

    # Last resort: in-page JS helper from FILL_SCRIPT.
    try:
        result = page.evaluate(
            """(script) => {
              const fn = new Function(script + '; return submitGreenhouse;')();
              return fn();
            }""",
            FILL_SCRIPT,
        ) or {}
    except Exception as error:
        result = {"ok": False, "skipped": True, "reason": str(error)}

    if result.get("ok"):
        _sleep(800)
        return result

    reason = (
        (result or {}).get("reason")
        or (str(last_error) if last_error else "Submit application button not found")
    )
    raise RuntimeError(f"Could not submit Greenhouse application: {reason}")


def detect_submission_success(page) -> bool:
    """True when Greenhouse shows the confirmation page / thank-you copy."""
    try:
        return bool(
            page.evaluate(
                """(script) => {
                  const fn = new Function(script + '; return submissionConfirmed;')();
                  return fn();
                }""",
                FILL_SCRIPT,
            )
        )
    except Exception:
        try:
            href = (page.url or "").lower()
            if "confirmation" in href:
                return True
        except Exception:
            pass
        return False


def detect_security_code_field(page) -> dict[str, Any]:
    return page.evaluate(
        """(script) => {
          const fn = new Function(script + '; return findSecurityCodeField;')();
          return fn();
        }""",
        FILL_SCRIPT,
    )


def fill_security_code(page, code: str) -> dict[str, Any]:
    """
    Fill Greenhouse email verification — usually 8 single-char inputs
    (#security-input-0 .. #security-input-7), else one text field.
    """
    page.bring_to_front()
    cleaned = re.sub(r"\s+", "", str(code or "").strip())
    if not cleaned:
        return {"ok": False, "reason": "empty code"}

    result = page.evaluate(FILL_CODE_JS, cleaned) or {}
    if result.get("ok"):
        return result

    # Playwright fallback: type one char per box.
    try:
        boxes = page.locator("input[id^='security-input-']")
        count = boxes.count()
        if count >= 4:
            for i, ch in enumerate(cleaned[:count]):
                box = boxes.nth(i)
                box.click(timeout=3000)
                box.fill("")
                box.type(ch, delay=40)
            return {"ok": True, "kind": "boxes-playwright", "filled": min(len(cleaned), count)}
        single = page.locator("#security-input-0, input[aria-required='true']").first
        if single.count() > 0:
            single.click(timeout=3000)
            single.fill(cleaned)
            return {"ok": True, "kind": "single-playwright"}
    except Exception as error:
        result = {"ok": False, "reason": str(error)}
    return result if result.get("ok") else (result or {"ok": False})


def build_greenhouse_profile(personal: dict[str, Any], options: dict[str, Any] | None = None) -> dict[str, Any]:
    options = options or {}
    employment = personal.get("employment") or []
    company = ""
    if employment:
        company = (employment[0] or {}).get("company") or ""

    return {
        "personal": {
            "firstName": personal.get("first") or personal.get("firstName") or "",
            "lastName": personal.get("last") or personal.get("lastName") or "",
            "preferredName": personal.get("preferredName")
            or personal.get("first")
            or personal.get("firstName")
            or "",
            "email": personal.get("email") or "",
            "phone": personal.get("phone") or "",
            "linkedin": personal.get("linkedin") or "",
            "website": personal.get("website") or personal.get("github") or "",
            "github": personal.get("github") or "",
            "location": personal.get("location") or "",
            "company": company,
            "address": personal.get("address") or "",
            "country": personal.get("country") or "United States",
        },
        "eeoc": {
            "gender": (options.get("eeoc") or {}).get("gender") or "Male",
            "hispanic_ethnicity": (options.get("eeoc") or {}).get("hispanic_ethnicity") or "No",
            "veteran_status": (options.get("eeoc") or {}).get("veteran_status")
            or "I am not a protected veteran",
            "disability_status": (options.get("eeoc") or {}).get("disability_status")
            or "No, I do not have a disability",
        },
        "fillEeoc": bool(options.get("fillEeoc", True)),
        "dropdownRules": [
            {"includes": "comfortable interviewing for the salary", "value": "Yes"},
            {"includes": "right to work", "value": "Yes"},
            {"includes": "legally authorized to work", "value": "Yes"},
            {"includes": "eligible to work", "value": "Yes"},
            {"includes": "sponsorship to work in the united states", "value": "No"},
            {"includes": "sponsorship to work in the country", "value": "No"},
            {"includes": "sponsorship to work on this role", "value": "No"},
            {"includes": "need visa sponsorship", "value": "No"},
            {"includes": "require sponsorship", "value": "No"},
            {"includes": "visa sponsorship", "value": "No"},
            {"includes": "require visa", "value": "No"},
            {"includes": "employer sponsorship", "value": "No"},
            {"includes": "work legally in the united states", "value": "No"},
            # Description lists USA/Canada; the control itself is Yes/No.
            {"includes": "located in one of the following countries", "value": "Yes"},
            {"includes": "following countries", "value": "Yes"},
            {"includes": "work authorization", "value": "Yes"},
            {"includes": "open to working 3 days", "value": "Yes"},
            {"includes": "former coreweave employee", "value": "No"},
            {"includes": "ever been employed", "value": "No"},
            {"includes": "u.s. person", "value": "Yes"},
            {"includes": "previously employed", "value": "No"},
        ],
        "checkboxRules": [
            {
                "includes": "immigration and residency",
                "value": "None/Not applicable",
            },
            {
                "includes": "none / not applicable",
                "value": "None/Not applicable",
            },
            {
                "includes": "u.s. citizen or legal permanent resident",
                "value": "None/Not applicable",
            },
        ],
        "education": (
            _education_from_payload({"education": options.get("education")})
            if options.get("education") is not None
            else _education_from_payload(personal)
        ),
        "textRules": [
            {"includes": "preferred first name", "field": "preferredName"},
            {"includes": "linkedin", "field": "linkedin"},
            {"includes": "website", "field": "website"},
            {"includes": "portfolio", "field": "website"},
            {"includes": "currently located", "field": "location"},
            {"includes": "city, state", "field": "location"},
            {"includes": "current company", "field": "company"},
            {"includes": "legal address", "field": "address"},
            {"includes": "github", "field": "github"},
        ],
        "resume": options.get("resume"),
    }
