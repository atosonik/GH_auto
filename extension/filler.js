// Ports fill_select() from Greenhouse-AI webfiller.py:
// scroll to the combobox, click .select__control, then click .select__option.
// Events go through React props because extension clicks are not trusted events.

globalThis.fillGreenhouse = async function fillGreenhouse(profile) {
  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
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
      document.querySelector(".application--container")
    );
  }

  function labelFor(input) {
    if (!input) return "";
    if (input.id) {
      var byFor = document.querySelector('label[for="' + CSS.escape(input.id) + '"]');
      if (byFor) return clean(byFor.textContent);
      var byLabelId = document.getElementById(input.id + "-label");
      if (byLabelId) return clean(byLabelId.textContent);
    }
    var wrap = input.closest(".field-wrapper, .select__container, .input-wrapper");
    var label = wrap && wrap.querySelector("label");
    return label ? clean(label.textContent) : "";
  }

  function matchRule(label, rules) {
    var hay = normalize(label);
    if (!hay) return null;
    for (var i = 0; i < rules.length; i++) {
      if (hay.indexOf(normalize(rules[i].includes)) !== -1) return rules[i];
    }
    return null;
  }

  function setNativeValue(el, value) {
    var proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    var setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function reactProps(el) {
    if (!el) return null;
    var keys = Object.keys(el);
    for (var i = 0; i < keys.length; i++) {
      if (keys[i].indexOf("__reactProps$") === 0) return el[keys[i]];
    }
    var fiber = null;
    for (var j = 0; j < keys.length; j++) {
      if (keys[j].indexOf("__reactFiber$") === 0 || keys[j].indexOf("__reactInternalInstance$") === 0) {
        fiber = el[keys[j]];
        break;
      }
    }
    var depth = 0;
    while (fiber && depth < 6) {
      if (fiber.memoizedProps && (fiber.memoizedProps.onMouseDown || fiber.memoizedProps.onChange)) {
        return fiber.memoizedProps;
      }
      fiber = fiber.return;
      depth++;
    }
    return null;
  }

  function invokeMouseDown(el) {
    var node = el;
    for (var hop = 0; hop < 4 && node; hop++) {
      var props = reactProps(node);
      if (props && typeof props.onMouseDown === "function") {
        props.onMouseDown({
          button: 0,
          target: node,
          currentTarget: node,
          preventDefault: function () {},
          stopPropagation: function () {},
          persist: function () {},
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
    var menus = Array.prototype.slice.call(document.querySelectorAll(".select__menu"));
    var visibleMenu = null;
    for (var i = 0; i < menus.length; i++) {
      if (menus[i].getClientRects().length > 0) visibleMenu = menus[i];
    }
    var root = visibleMenu || document;
    return Array.prototype.slice.call(root.querySelectorAll(".select__option"));
  }

  function findOption(value) {
    var target = normalize(value);
    var options = openOptions().filter(function (option) {
      return option.offsetParent !== null || option.getClientRects().length > 0;
    });
    if (!options.length) options = openOptions();
    var exact = options.find(function (option) {
      return normalize(option.textContent) === target;
    });
    if (exact) return exact;
    var starts = options.find(function (option) {
      return normalize(option.textContent).indexOf(target) === 0;
    });
    if (starts) return starts;
    return options.find(function (option) {
      return normalize(option.textContent).indexOf(target) !== -1;
    }) || null;
  }

  async function fillSelect(input, value) {
    var shell = input.closest(".select-shell") || input.closest(".select");
    if (!shell) throw new Error("select shell not found");
    var control = shell.querySelector(".select__control");
    if (!control) throw new Error("select control not found");

    var current = shell.querySelector(".select__single-value");
    if (current && normalize(current.textContent) === normalize(value)) return;

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
    await sleep(100);
    control.scrollIntoView({ behavior: "auto", block: "center" });
    await sleep(200);
    invokeMouseDown(control);
    await sleep(250);

    setNativeValue(input, value);
    await sleep(250);

    var option = null;
    var started = Date.now();
    while (Date.now() - started < 1500) {
      option = findOption(value);
      if (option) break;
      await sleep(50);
    }
    if (!option) throw new Error('option "' + value + '" not in the menu');

    invokeMouseDown(option);
    await sleep(200);

    var chosen = shell.querySelector(".select__single-value");
    if (!chosen || normalize(chosen.textContent).indexOf(normalize(value)) === -1) {
      throw new Error('menu closed without selecting "' + value + '"');
    }
  }

  function fillText(input, value) {
    if (!input || value == null || value === "") return false;
    if (input.classList.contains("select__input")) return false;
    input.scrollIntoView({ behavior: "auto", block: "center" });
    input.focus();
    setNativeValue(input, value);
    return true;
  }

  async function attachResume(file) {
    if (!file || !file.buffer) return false;
    var input = document.querySelector("#resume, input[type='file'][name='resume'], input[type='file']");
    if (!input) return false;
    var bytes = new Uint8Array(file.buffer);
    var blob = new Blob([bytes], { type: file.type || "application/pdf" });
    var transfer = new DataTransfer();
    transfer.items.add(new File([blob], file.name || "resume.pdf", { type: blob.type }));
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  if (!hasForm()) return { skipped: true, log: [] };

  var personal = profile.personal || {};
  var log = [];

  var byId = {
    first_name: personal.firstName,
    last_name: personal.lastName,
    preferred_name: personal.preferredName,
    email: personal.email,
    phone: personal.phone,
  };

  Object.keys(byId).forEach(function (id) {
    var el = document.getElementById(id);
    if (fillText(el, byId[id])) log.push("Filled " + id);
  });

  var textInputs = Array.prototype.slice.call(
    document.querySelectorAll("input[type='text'], input[type='email'], input[type='tel'], input:not([type]), textarea")
  );
  textInputs.forEach(function (input) {
    if (input.classList.contains("select__input")) return;
    if (input.closest(".iti__dropdown-content, .iti__country-list")) return;
    if (byId[input.id]) return;
    var rule = matchRule(labelFor(input), profile.textRules || []);
    if (!rule) return;
    var value = personal[rule.field];
    if (fillText(input, value)) log.push("Filled " + labelFor(input));
  });

  if (personal.country) {
    var country = document.getElementById("country");
    if (country && country.classList.contains("select__input")) {
      try {
        await fillSelect(country, personal.country);
        log.push("Selected country: " + personal.country);
      } catch (error) {
        log.push("Country failed: " + error.message);
      }
    }
  }

  var selects = Array.prototype.slice.call(document.querySelectorAll("input.select__input"));
  for (var s = 0; s < selects.length; s++) {
    var select = selects[s];
    if (select.id === "country") continue;
    var label = labelFor(select);
    var eeocValue = profile.eeoc && profile.eeoc[select.id];
    var isEeoc = select.id === "gender" || select.id === "hispanic_ethnicity" || select.id === "veteran_status" || select.id === "disability_status";
    var value = "";
    if (isEeoc) {
      if (!profile.fillEeoc || !eeocValue) continue;
      value = eeocValue;
    } else {
      var rule = matchRule(label, profile.dropdownRules || []);
      if (!rule || !rule.value) continue;
      value = rule.value;
    }
    try {
      await fillSelect(select, value);
      log.push("Selected " + (label || select.id) + ": " + value);
    } catch (error) {
      log.push("Failed " + (label || select.id) + ": " + error.message);
    }
  }

  try {
    if (await attachResume(profile.resume)) log.push("Attached resume");
  } catch (error) {
    log.push("Resume failed: " + error.message);
  }

  return { ok: true, log: log };
};

globalThis.submitGreenhouse = function submitGreenhouse() {
  var button = document.querySelector(".application--container button[type='submit'], form button[type='submit']");
  if (!button) return { skipped: true };
  button.scrollIntoView({ behavior: "auto", block: "center" });
  button.click();
  return { ok: true };
};
