from __future__ import annotations

import json
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from app.automation.json_repair import looks_like_resume, parse_resume_json

COMPOSER_SELECTORS = [
    "#prompt-textarea",
    'div[contenteditable="true"].ProseMirror',
    'form div[contenteditable="true"]',
    'div[contenteditable="true"]',
    'textarea[placeholder*="Ask" i]',
    'textarea[placeholder*="Message" i]',
    "form textarea",
    "textarea",
]

SEND_SELECTORS = [
    ".ds-button--primary.ds-button--filled.ds-button--circle",
    '.ds-button--primary.ds-button--filled',
    '[data-testid="send-button"]',
    'button[aria-label*="Send" i]',
    'form button[type="submit"]',
]

VISIBLE_JS = """(el) => {
                  const rect = el.getBoundingClientRect();
                  const style = window.getComputedStyle(el);
                  return rect.width > 20 && rect.height > 10 &&
                    style.visibility !== 'hidden' && style.display !== 'none';
                }"""

SET_COMPOSER_JS = """([el, value]) => {
          el.focus();
          el.click();
          if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
            const proto = el.tagName === 'TEXTAREA'
              ? window.HTMLTextAreaElement.prototype
              : window.HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
            setter.call(el, value);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
          }
          // ProseMirror: paste first, then insertText fallback.
          try {
            document.execCommand('selectAll', false, null);
            document.execCommand('delete', false, null);
          } catch (e) {}
          const dt = new DataTransfer();
          dt.setData('text/plain', value);
          el.dispatchEvent(new ClipboardEvent('paste', {
            bubbles: true, cancelable: true, clipboardData: dt
          }));
          const landed = (el.textContent || '').includes(value.slice(-Math.min(40, value.length)));
          if (!landed) {
            try {
              document.execCommand('insertText', false, value);
            } catch (e) {
              el.textContent = value;
              el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText' }));
            }
          }
          return true;
        }"""

SENDABLE_JS = """(el) => {
              if (!el) return false;
              const disabled = el.disabled ||
                el.getAttribute('aria-disabled') === 'true' ||
                (el.className || '').includes('ds-button--disabled') ||
                el.classList.contains('ds-button--disabled');
              const rect = el.getBoundingClientRect();
              return !disabled && rect.width > 0 && rect.height > 0;
            }"""

FIND_SEND_JS = """(composer) => {
          const selectors = [
            '.ds-button--primary.ds-button--filled.ds-button--circle',
            '.ds-button--primary.ds-button--filled',
            '[data-testid="send-button"]',
            'button[aria-label*="Send" i]'
          ];
          for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (!el) continue;
            const disabled = el.disabled ||
              el.getAttribute('aria-disabled') === 'true' ||
              (el.className || '').includes('ds-button--disabled');
            const rect = el.getBoundingClientRect();
            if (!disabled && rect.width > 0 && rect.height > 0) return true;
          }
          if (!composer) return false;
          const top = composer.getBoundingClientRect().top - 4;
          let node = composer.parentElement;
          for (let up = 0; node && up < 8; up += 1) {
            const found = Array.from(node.querySelectorAll('[role="button"], button')).filter((b) => {
              const rect = b.getBoundingClientRect();
              const text = (b.textContent || '').replace(/\\s+/g, ' ').trim();
              const disabled = b.disabled ||
                b.getAttribute('aria-disabled') === 'true' ||
                (b.className || '').includes('ds-button--disabled');
              return !disabled && rect.width > 0 && rect.height > 0 &&
                rect.top >= top && text.length === 0;
            });
            if (found.length) {
              const rightmost = found.reduce((best, b) =>
                b.getBoundingClientRect().left > best.getBoundingClientRect().left ? b : best
              );
              rightmost.click();
              return 'clicked';
            }
            node = node.parentElement;
          }
          return false;
        }"""

CLICK_NAMED_SEND_JS = """() => {
          const selectors = [
            '.ds-button--primary.ds-button--filled.ds-button--circle',
            '.ds-button--primary.ds-button--filled',
            '[data-testid="send-button"]',
            'button[aria-label*="Send" i]'
          ];
          for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (!el) continue;
            const disabled = el.disabled ||
              el.getAttribute('aria-disabled') === 'true' ||
              (el.className || '').includes('ds-button--disabled');
            const rect = el.getBoundingClientRect();
            if (!disabled && rect.width > 0 && rect.height > 0) {
              el.click();
              return sel;
            }
          }
          return null;
        }"""

COMPOSER_LEN_JS = """() => {
          const el =
            document.querySelector('#prompt-textarea') ||
            document.querySelector('div[contenteditable="true"].ProseMirror') ||
            document.querySelector('div[contenteditable="true"]') ||
            document.querySelector('textarea');
          if (!el) return 0;
          const text = (el.value !== undefined ? el.value : (el.textContent || ''));
          return text.replace(/\\s+/g, '').length;
        }"""

CONTINUE_REPLY_JS = """() => {
          // ONLY the truncated-generation "Continue" control.
          // Never click "Reply" — that is a normal chat affordance and will
          // loop forever, blocking resume JSON detection.
          const buttons = Array.from(document.querySelectorAll('.ds-button, button, [role="button"]'));
          for (const btn of buttons) {
            const label = (
              btn.querySelector('.ds-button__content')?.textContent ||
              btn.textContent || ''
            ).replace(/\\s+/g, ' ').trim().toLowerCase();
            if (label !== 'continue') continue;
            const rect = btn.getBoundingClientRect();
            const style = window.getComputedStyle(btn);
            if (rect.width > 0 && rect.height > 0 &&
                style.visibility !== 'hidden' && style.display !== 'none') {
              btn.click();
              return label;
            }
          }
          return null;
        }"""

PAGE_STATE_JS = """() => {
              // Only treat a visible Stop/Abort control as "still generating".
              // Broad [class*=stop] matches false-positives and can hang waiters.
              const stopCandidates = Array.from(document.querySelectorAll(
                'button[aria-label*="Stop" i], button[aria-label*="Abort" i], [role="button"][aria-label*="Stop" i]'
              ));
              const stop = stopCandidates.find((el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                const label = (
                  (el.getAttribute('aria-label') || '') + ' ' + (el.textContent || '')
                ).toLowerCase();
                return rect.width > 0 && rect.height > 0 &&
                  style.visibility !== 'hidden' && style.display !== 'none' &&
                  /stop|abort/.test(label);
              });
              const stopping = Boolean(stop);

              // Prefer top-level assistant bubbles so nested .ds-markdown nodes
              // do not inflate answerCount or make "last reply" flicker.
              const roots = Array.from(document.querySelectorAll(
                '.ds-assistant-message-main-content, [data-message-author-role="assistant"]'
              ));
              const answers = roots.filter((el) =>
                !roots.some((other) => other !== el && other.contains(el))
              );
              const markdownOnly = answers.length
                ? answers
                : Array.from(document.querySelectorAll('.ds-markdown')).filter((el) =>
                    !el.parentElement?.closest('.ds-markdown')
                  );
              const nodes = answers.length ? answers : markdownOnly;
              const last = nodes.length ? nodes[nodes.length - 1] : null;
              const reply = last ? (last.innerText || last.textContent || '') : '';
              const text = document.body?.innerText || '';
              return {
                text,
                size: text.length,
                reply,
                replySize: reply.length,
                answerCount: nodes.length,
                stopping,
                composerLen: (function () {
                  const el =
                    document.querySelector('#prompt-textarea') ||
                    document.querySelector('div[contenteditable="true"].ProseMirror') ||
                    document.querySelector('div[contenteditable="true"]');
                  if (!el) return 0;
                  const t = el.value !== undefined ? el.value : (el.textContent || '');
                  return t.replace(/\\s+/g, '').length;
                })()
              };
            }"""

REPLY_PAYLOAD_JS = """() => {
          const blocks = Array.from(document.querySelectorAll(
            '.md-code-block pre, .ds-markdown pre, pre, code, .ds-assistant-message-main-content'
          ));
          const texts = [];
          for (const block of blocks.reverse()) {
            const t = (block.textContent || block.innerText || '').trim();
            if (!t.includes('"name"')) continue;
            if (t.includes('"experience"') || t.includes('"skills"') || t.includes('"summary"')) {
              texts.push(t);
            }
          }
          const answers = Array.from(document.querySelectorAll(
            '.ds-assistant-message-main-content, .ds-markdown'
          ));
          if (answers.length) {
            const last = answers[answers.length - 1];
            texts.push((last.innerText || last.textContent || '').trim());
          }
          texts.push((document.body?.innerText || '').trim());
          return texts;
        }"""


def _sleep(ms: float) -> None:
    time.sleep(ms / 1000.0)


def load_prompt(prompts_dir: str, profile_name: str) -> str:
    path = Path(prompts_dir) / f"{profile_name}.txt"
    return path.read_text(encoding="utf-8").strip()


def load_profile_context(context_dir: str, profile_name: str) -> str:
    path = Path(context_dir) / f"{profile_name}.txt"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def load_profiles_json(profiles_json_path: str) -> dict[str, Any]:
    path = Path(profiles_json_path)
    return json.loads(path.read_text(encoding="utf-8"))


def assemble_prompt(prompt_text: str, job: dict[str, Any], mode: str = "attach") -> tuple[str, str]:
    """Return (composer_text, attachable_prompt)."""
    lines: list[str] = []
    attachable = ""

    if mode == "full":
        lines.extend(
            [
                prompt_text.rstrip(),
                "",
                "========================",
                "JOB DESCRIPTION",
                "========================",
                "",
            ]
        )
    elif mode == "attach":
        attachable = prompt_text
        lines.extend(
            [
                "The attached file contains your instructions. Follow them exactly.",
                "",
                "Using the job description below, return ONLY the resume JSON that the "
                "attached instructions define - no prose, no explanation, no questions.",
                "",
            ]
        )

    lines.append(f"Company: {job.get('company') or '(unknown)'}")
    lines.append(f"Role: {job.get('title') or '(unknown)'}")
    if job.get("location"):
        lines.append(f"Location: {job['location']}")
    if job.get("url"):
        lines.append(f"Original posting: {job['url']}")
    lines.append("")
    if mode != "jd":
        lines.append(
            "Use the text below verbatim as the `jd` field, escaping it correctly for JSON."
        )
        lines.append("")
    lines.append(job.get("description") or "(no description could be extracted)")
    return "\n".join(lines), attachable


def _is_nav_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(
        token in text
        for token in (
            "execution context was destroyed",
            "most likely because of a navigation",
            "target closed",
            "frame was detached",
            "navigating",
        )
    )


def find_composer(page, timeout_ms: int = 45000):
    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=2500)
        except Exception:
            pass

        try:
            for sel in COMPOSER_SELECTORS:
                handle = page.query_selector(sel)
                if not handle:
                    continue
                try:
                    visible = handle.evaluate(VISIBLE_JS)
                except Exception as error:
                    if _is_nav_error(error):
                        break
                    continue
                if visible:
                    return handle
        except Exception as error:
            if not _is_nav_error(error):
                raise
            # DeepSeek often redirects after open; wait and retry.
            try:
                page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass

        _sleep(350)
    return None


def set_composer_value(page, el, value: str) -> None:
    try:
        el.click(timeout=5000)
    except Exception:
        pass
    page.evaluate(SET_COMPOSER_JS, [el, value])
    _sleep(400)


def attach_prompt_file(page, prompt_text: str, profile_name: str) -> bool:
    safe_name = re.sub(r"\s+", "-", profile_name.strip()) or "profile"
    path = Path(tempfile.gettempdir()) / f"gh-prompt-{safe_name}.txt"
    path.write_text(prompt_text, encoding="utf-8")
    try:
        file_input = page.query_selector('input[type="file"]')
        if not file_input:
            return False
        file_input.set_input_files(str(path))
        # Wait until send becomes usable / attachment chip appears.
        deadline = time.time() + 20
        stem = path.stem[:10]
        while time.time() < deadline:
            enabled = False
            for sel in SEND_SELECTORS:
                btn = page.query_selector(sel)
                if btn and btn.evaluate(SENDABLE_JS):
                    enabled = True
                    break
            body = page.evaluate("() => document.body?.innerText || ''") or ""
            if enabled or stem in body or ".txt" in body.lower():
                _sleep(600)
                return True
            _sleep(300)
        return True
    except Exception:
        return False
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def _composer_len(page) -> int:
    try:
        return int(page.evaluate(COMPOSER_LEN_JS) or 0)
    except Exception:
        return 0


def _try_click_send(page, composer) -> str | None:
    try:
        named = page.evaluate(CLICK_NAMED_SEND_JS)
        if named:
            return f"button:{named}"
    except Exception:
        pass
    try:
        result = page.evaluate(FIND_SEND_JS, composer)
        if result == "clicked" or result is True:
            return "button:heuristic"
    except Exception:
        pass
    return None


def _send_succeeded(page, before_len: int, before_answers: int) -> bool:
    try:
        state = page.evaluate(PAGE_STATE_JS)
    except Exception:
        return False
    composer_len = int(state.get("composerLen") or 0)
    stopping = bool(state.get("stopping"))
    answers = int(state.get("answerCount") or 0)
    if stopping:
        return True
    if before_len > 20 and composer_len < max(10, before_len * 0.35):
        return True
    if answers > before_answers:
        return True
    return False


def click_send(page, composer) -> bool:
    """
    Actually send the DeepSeek message.

    Previous logic treated "page has any text" as success, so Enter looked like
    it worked when nothing was submitted.
    """
    try:
        composer.click(timeout=5000)
    except Exception:
        try:
            composer.focus()
        except Exception:
            pass

    before_len = _composer_len(page)
    try:
        before_answers = int(page.evaluate(PAGE_STATE_JS).get("answerCount") or 0)
    except Exception:
        before_answers = 0

    deadline = time.time() + 60
    pressed_enter = False

    while time.time() < deadline:
        # Wait for send control to enable (attachments upload slowly).
        clicked = _try_click_send(page, composer)
        if not clicked:
            try:
                composer.click(timeout=2000)
            except Exception:
                pass
            # DeepSeek: Enter sends. Also try Ctrl+Enter as fallback once.
            page.keyboard.press("Enter")
            pressed_enter = True
            _sleep(350)
            if not _send_succeeded(page, before_len, before_answers):
                page.keyboard.press("Control+Enter")

        for _ in range(12):
            if _send_succeeded(page, before_len, before_answers):
                return True
            _sleep(250)

        # Re-find composer if the node went stale after a partial navigation.
        fresh = find_composer(page, timeout_ms=4000)
        if fresh:
            composer = fresh

        _sleep(300)

    return pressed_enter and _send_succeeded(page, before_len, before_answers)


def click_continue_or_reply(page) -> str | None:
    return page.evaluate(CONTINUE_REPLY_JS)


def extract_json_candidate(text: str) -> dict[str, Any] | None:
    return parse_resume_json(text or "")


def _unwrap_resume_parse(result: Any) -> tuple[dict[str, Any] | None, str]:
    """
    parse_resume_json returns {"raw","parsed","source"}.
    Older callers sometimes treat that wrapper as the resume itself — unwrap it.
    """
    if not isinstance(result, dict) or not result:
        return None, ""
    # Already a resume payload.
    if result.get("name") and (
        isinstance(result.get("experience"), dict) or result.get("summary")
    ):
        try:
            return result, json.dumps(result, indent=2, ensure_ascii=False)
        except Exception:
            return result, str(result)
    # Wrapper from parse_resume_json.
    parsed = result.get("parsed")
    raw = result.get("raw") or ""
    if isinstance(parsed, dict) and parsed.get("name"):
        return parsed, raw if isinstance(raw, str) else str(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and parsed.get("name"):
                return parsed, raw
        except Exception:
            pass
    return None, raw if isinstance(raw, str) else ""


_PLACEHOLDER_SNIPPETS = (
    "target company",
    "normalized target role",
    "complete job description",
    "tailored one-paragraph",
    "tailored resume headline",
    "dynamic category",
    "skill 1",
    "skill 2",
    "skill 3",
)


def _looks_like_placeholder_resume(payload: dict[str, Any]) -> bool:
    """Catch schema/example JSON DeepSeek sometimes emits instead of a real resume."""
    blob = json.dumps(payload, ensure_ascii=False).lower()
    hits = sum(1 for snippet in _PLACEHOLDER_SNIPPETS if snippet in blob)
    if hits >= 2:
        return True
    experience = payload.get("experience")
    if isinstance(experience, dict) and experience:
        bullets = []
        for entry in experience.values():
            if isinstance(entry, dict):
                bullets.extend(entry.get("bullets") or [])
            elif isinstance(entry, list):
                bullets.extend(entry)
        if bullets and all(str(b).strip() in {"", "...", "…", "-", "bullet"} for b in bullets):
            return True
    return False


def _resume_ready(payload: dict[str, Any] | None) -> bool:
    """Require a complete-enough resume before leaving DeepSeek / calling Word."""
    if not isinstance(payload, dict):
        return False
    if not str(payload.get("name") or "").strip():
        return False
    if _looks_like_placeholder_resume(payload):
        return False
    experience = payload.get("experience")
    if isinstance(experience, dict) and len(experience) > 0:
        return True
    if isinstance(experience, list) and len(experience) > 0:
        return True
    summary = str(payload.get("summary") or "").strip()
    skills = payload.get("skills")
    if summary and isinstance(skills, (dict, list)) and len(skills) > 0:
        return True
    # Skills-heavy replies still count if name + skills + some experience/summary signal.
    if isinstance(skills, dict) and len(skills) >= 2 and (
        summary or (isinstance(experience, dict) and experience)
    ):
        return True
    return False


def _extract_from_page(page) -> dict[str, Any] | None:
    try:
        blobs = page.evaluate(REPLY_PAYLOAD_JS) or []
    except Exception:
        blobs = []
    for blob in blobs:
        found = parse_resume_json(blob)
        parsed, _raw = _unwrap_resume_parse(found)
        if parsed and _resume_ready(parsed):
            return {"parsed": parsed, "raw": _raw or json.dumps(parsed, ensure_ascii=False)}
    try:
        text = page.evaluate("() => document.body?.innerText || ''")
    except Exception:
        text = ""
    found = parse_resume_json(text or "")
    parsed, _raw = _unwrap_resume_parse(found)
    if parsed and _resume_ready(parsed):
        return {"parsed": parsed, "raw": _raw or json.dumps(parsed, ensure_ascii=False)}
    return None


def run_deepseek_chat(
    page,
    composer_text: str,
    attach_text: str = "",
    profile_name: str = "profile",
    timeout_ms: int = 600000,
) -> dict[str, Any]:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=30000)
    except Exception:
        pass

    composer = find_composer(page)
    if not composer:
        raise RuntimeError("DeepSeek composer not found")

    # Prefer one full message (prompt + JD). Attachment is optional enhancement.
    message = composer_text
    if attach_text:
        # If caller still passes a short composer + attach file, put both inline
        # when the file path fails — DeepSeek automation is more reliable that way.
        attached = attach_prompt_file(page, attach_text, profile_name)
        composer = find_composer(page) or composer
        if not attached:
            message = f"{attach_text.rstrip()}\n\n{composer_text}"

    set_composer_value(page, composer, message)
    _sleep(600)
    composer = find_composer(page) or composer

    if _composer_len(page) < 20:
        # Paste via Playwright keyboard as a last resort.
        try:
            composer.click()
            page.keyboard.press("Control+A")
            page.keyboard.insert_text(message)
            _sleep(400)
        except Exception:
            pass

    if not click_send(page, composer):
        raise RuntimeError(
            "Could not send DeepSeek message (Enter/send button did not submit). "
            "Check that the composer has text and the send control is enabled."
        )

    try:
        baseline_state = page.evaluate(PAGE_STATE_JS)
    except Exception as error:
        if not _is_nav_error(error):
            raise
        _sleep(1000)
        baseline_state = page.evaluate(PAGE_STATE_JS)

    baseline_reply = int(baseline_state.get("replySize") or 0)
    baseline_answers = int(baseline_state.get("answerCount") or 0)
    deadline = time.time() + (timeout_ms / 1000.0)
    last_reply = baseline_reply
    quiet_since = time.time()
    found = None
    ready_since: float | None = None
    last_ready_fingerprint = ""

    while time.time() < deadline:
        try:
            state = page.evaluate(PAGE_STATE_JS)
        except Exception as error:
            if _is_nav_error(error):
                _sleep(700)
                continue
            raise

        reply = state.get("reply") or ""
        reply_size = int(state.get("replySize") or 0)
        stopping = bool(state.get("stopping"))
        answers = int(state.get("answerCount") or 0)
        composer_len = int(state.get("composerLen") or 0)

        # Only poke Continue while DeepSeek is still generating / truncated.
        if stopping:
            click_continue_or_reply(page)

        # Prefer assistant reply text, then whole-page / code-block extraction.
        candidate = None
        if reply:
            parsed, raw = _unwrap_resume_parse(parse_resume_json(reply))
            if parsed and _resume_ready(parsed):
                candidate = {
                    "parsed": parsed,
                    "raw": raw or json.dumps(parsed, ensure_ascii=False),
                }
        if not candidate:
            candidate = _extract_from_page(page)

        # Only treat meaningful growth as "still streaming". Tiny DOM jitter
        # after completion used to reset quiet forever and block PDF generation.
        grew = reply_size > last_reply + 80
        if grew or (answers > baseline_answers and not candidate):
            last_reply = max(last_reply, reply_size)
            quiet_since = time.time()
            if grew:
                ready_since = None
        else:
            last_reply = reply_size

        if candidate:
            fingerprint = str(len(candidate.get("raw") or "")) + ":" + str(
                (candidate.get("parsed") or {}).get("name") or ""
            )
            if fingerprint != last_ready_fingerprint:
                last_ready_fingerprint = fingerprint
                ready_since = time.time()
            elif ready_since is None:
                ready_since = time.time()

            ready_for = time.time() - (ready_since or time.time())
            quiet_for = time.time() - quiet_since
            # Generation finished: no Stop button, composer idle, JSON ready.
            # Keep this snappy — users were waiting 10s+ after JSON appeared.
            if not stopping and ready_for >= 0.25 and quiet_for >= 0.25:
                found = candidate
                break
            if not stopping and composer_len == 0 and ready_for >= 0.2:
                found = candidate
                break
            # Some DeepSeek builds leave a Stop-like control stuck visible.
            if ready_for >= 1.2 and quiet_for >= 0.6:
                found = candidate
                break
            # Valid complete JSON + not growing: take it even if Stop flickers.
            if ready_for >= 0.8 and not grew:
                found = candidate
                break

        _sleep(220)

    if not found:
        found = _extract_from_page(page)
    if not found:
        raise TimeoutError("Timed out waiting for DeepSeek resume JSON")
    if found.get("parsed") and found.get("raw"):
        return {"parsed": found["parsed"], "raw": found["raw"]}
    parsed, raw = _unwrap_resume_parse(found)
    if not parsed or not _resume_ready(parsed):
        raise TimeoutError("DeepSeek reply was not a complete resume JSON yet")
    return {
        "parsed": parsed,
        "raw": raw or json.dumps(parsed, indent=2, ensure_ascii=False),
    }


QUESTION_SYSTEM_PROMPT = (
    "These are required questions for applying for this role "
    "(each is marked required with * on the form).\n"
    "To get hired faster, answer in a short but impactful way.\n"
    "When you give a free-text answer, remove dashes in sentences.\n"
    "\n"
    "CRITICAL for dropdown / multiple-choice / checkbox questions:\n"
    "- I will list every Choice for that question under Choices.\n"
    "- Your JSON value MUST be EXACTLY one of those Choice strings "
    "(for checkboxes, one choice — prefer None/Not applicable when that option exists "
    "unless the candidate context clearly requires another).\n"
    "- Pick the single most appropriate option. Do NOT write a sentence.\n"
    "- Do NOT invent, paraphrase, or combine choices. CHOOSE from the list.\n"
    "\n"
    "CRITICAL for free-text / typing questions (no Choices list):\n"
    "- Answer briefly. Prefer a number, short phrase, or 1-3 sentences.\n"
    "- Salary / compensation / expectation questions: reply with ONLY a number or a tight "
    "USD range for the candidate's current metro and the role seniority "
    "(example: 145000 or 140000-160000). No currency essay. No currency symbol required.\n"
    "- Use candidate context location when judging local market rates.\n"
    "\n"
    "Return ONLY a JSON object. Prefer numbered keys matching the list "
    '(example: {"1":"Yes","2":"..."}). You may also use the exact question '
    "labels as keys. No markdown fences, no commentary, no resume JSON."
)

_RESUME_SHAPE_KEYS = {
    "name",
    "experience",
    "summary",
    "skills",
    "education",
    "projects",
    "target",
    "posting",
}


def _parse_answers_object(text: str) -> dict[str, Any]:
    if not text:
        return {}
    from app.automation.json_repair import repair_json

    chunks: list[str] = []
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        chunks.append(fenced.group(1).strip())
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        chunks.append(match.group(0))
    chunks.append(text)

    for chunk in chunks:
        try:
            try:
                parsed = json.loads(chunk)
            except Exception:
                repaired, _ = repair_json(chunk)
                parsed = json.loads(repaired)
            if isinstance(parsed, dict) and parsed:
                out: dict[str, Any] = {}
                for key, value in parsed.items():
                    if isinstance(value, (dict, list)):
                        out[str(key)] = json.dumps(value, ensure_ascii=False)
                    else:
                        # Prefer short impactful prose without leading dashes.
                        cleaned = str(value).replace("\n- ", "\n").replace("- ", "")
                        out[str(key)] = cleaned.strip()
                return out
        except Exception:
            continue
    return {}


def _looks_like_resume_payload(parsed: dict[str, Any] | None) -> bool:
    if not parsed:
        return False
    keys = {str(k).strip().lower() for k in parsed}
    if "name" in keys and "experience" in keys:
        return True
    return len(keys & _RESUME_SHAPE_KEYS) >= 3


def _question_labels(questions: list[dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    for question in questions:
        if isinstance(question, dict):
            labels.append(str(question.get("label") or question.get("name") or "").strip())
        else:
            labels.append(str(question).strip())
    return [label for label in labels if label]


def _snap_to_choice(answer: str, choices: list[str]) -> str:
    """Force model output onto an exact dropdown choice when choices exist."""
    text = (answer or "").strip()
    if not choices:
        return text
    if not text:
        return choices[0]

    def norm(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "").strip().lower())

    text_n = norm(text)
    # Exact match first.
    for choice in choices:
        if norm(choice) == text_n:
            return choice

    # Numbered Greenhouse options: model answers "1" / "2 - Hands-on" / "Hands-on".
    num = re.match(r"^(\d+)\b", text_n)
    if num:
        prefix = num.group(1) + " -"
        for choice in choices:
            if norm(choice).startswith(prefix) or norm(choice).startswith(num.group(1) + "."):
                return choice
            if norm(choice).startswith(num.group(1) + " "):
                return choice

    # Short choices (Yes/No/etc): only match as whole words — never let
    # "no" hitch a ride inside "not" / "now" / "another".
    short = [c for c in choices if len(norm(c)) <= 4]
    long = [c for c in choices if len(norm(c)) > 4]

    for choice in short:
        cn = norm(choice)
        if re.search(rf"\b{re.escape(cn)}\b", text_n):
            return choice

    for choice in long:
        cn = norm(choice)
        # Compare on the distinctive head of long options (before ':' if present).
        head = cn.split(":", 1)[0].strip()
        text_head = text_n.split(":", 1)[0].strip()
        if text_n.startswith(cn[:48]) or cn.startswith(text_n[:48]):
            return choice
        if head and (text_head in head or head in text_head or text_n in cn or cn in text_n):
            return choice
    for choice in long:
        cn = norm(choice)
        if cn in text_n or text_n in cn:
            return choice

    # Polarity for Yes/No-style lists when the model wrote a sentence.
    choice_norms = {norm(c): c for c in choices}
    yes_choice = next((choice_norms[k] for k in ("yes", "y", "true") if k in choice_norms), None)
    no_choice = next((choice_norms[k] for k in ("no", "n", "false") if k in choice_norms), None)
    if yes_choice or no_choice:
        neg = bool(
            re.search(
                r"\b(no|not|never|none|neither|don't|dont|do not|won't|wont|"
                r"cannot|can't|cant|unable|without|decline|refuse)\b",
                text_n,
            )
        )
        pos = bool(
            re.search(r"\b(yes|yeah|yep|true|correct|affirmative|already|have)\b", text_n)
        )
        if neg and no_choice:
            return no_choice
        if pos and not neg and yes_choice:
            return yes_choice
        if text_n in {"y", "yes", "true"} and yes_choice:
            return yes_choice
        if text_n in {"n", "no", "false"} and no_choice:
            return no_choice

    # Fall back to first listed choice — never return free-form invented text.
    return choices[0]


def _normalize_gap_answers(
    parsed: dict[str, Any],
    questions: list[dict[str, Any]],
) -> dict[str, str]:
    """Map model keys (1/2/... or labels) onto exact Greenhouse question labels."""
    labels = _question_labels(questions)
    if not parsed or not labels:
        return {}

    def norm(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    out: dict[str, str] = {}
    used_keys: set[str] = set()

    for idx, question in enumerate(questions, start=1):
        label = (
            str(question.get("label") or question.get("name") or "").strip()
            if isinstance(question, dict)
            else str(question).strip()
        )
        if not label:
            continue
        candidates = [
            str(idx),
            f"Q{idx}",
            f"q{idx}",
            f"question {idx}",
            label,
        ]
        chosen = None
        for key in candidates:
            if key in parsed and str(parsed[key]).strip():
                chosen = key
                break
        if chosen is None:
            label_n = norm(label)
            for key, value in parsed.items():
                if key in used_keys or not str(value).strip():
                    continue
                key_n = norm(str(key))
                if not key_n:
                    continue
                if key_n == label_n or label_n in key_n or key_n in label_n:
                    chosen = str(key)
                    break
        if chosen is None:
            continue
        used_keys.add(chosen)
        value = str(parsed[chosen]).strip()
        choices = []
        if isinstance(question, dict):
            choices = [str(c).strip() for c in (question.get("choices") or []) if str(c).strip()]
        if choices:
            value = _snap_to_choice(value, choices)
        out[label] = value

    return out


def _extract_gap_reply_blobs(page) -> list[str]:
    try:
        blobs = page.evaluate(
            """() => {
              const out = [];
              const roots = Array.from(document.querySelectorAll(
                '.ds-assistant-message-main-content, [data-message-author-role="assistant"]'
              ));
              const top = roots.filter((el) =>
                !roots.some((other) => other !== el && other.contains(el))
              );
              const nodes = top.length
                ? top
                : Array.from(document.querySelectorAll('.ds-markdown, pre, code'));
              if (nodes.length) {
                const last = nodes[nodes.length - 1];
                out.push((last.innerText || last.textContent || '').trim());
              }
              // Also grab any trailing {...} from the page text as a fallback.
              const body = (document.body?.innerText || '').trim();
              const brace = body.match(/\\{[\\s\\S]*\\}\\s*$/);
              if (brace) out.push(brace[0].trim());
              return out;
            }"""
        ) or []
        return [b for b in blobs if isinstance(b, str) and b.strip()]
    except Exception:
        return []


def ask_deepseek_gaps(
    page,
    questions: list[dict[str, Any]],
    profile_context: str = "",
) -> dict[str, Any]:
    composer = find_composer(page)
    if not composer:
        raise RuntimeError("DeepSeek composer not found for gap answers")

    labels = _question_labels(questions)
    if not labels:
        return {}

    # Snapshot the prior assistant turn (resume JSON) BEFORE sending questions.
    try:
        before_state = page.evaluate(PAGE_STATE_JS)
        before_answers = int(before_state.get("answerCount") or 0)
        before_reply = (before_state.get("reply") or "").strip()
    except Exception:
        before_answers = 0
        before_reply = ""

    lines = [QUESTION_SYSTEM_PROMPT, ""]
    if profile_context:
        lines.extend(["Candidate context:", profile_context.strip(), ""])
    lines.append("Questions:")
    for idx, question in enumerate(questions, start=1):
        if isinstance(question, dict):
            label = str(question.get("label") or question.get("name") or "").strip()
            choices = [
                str(c).strip()
                for c in (question.get("choices") or [])
                if str(c).strip()
            ]
            kind = str(question.get("kind") or "text")
            field_text = str(
                question.get("fieldText") or question.get("description") or ""
            ).strip()
        else:
            label = str(question).strip()
            choices = []
            kind = "text"
            field_text = ""
        if not label:
            continue
        if re.match(r"^select\.?\.?\.?$", label, re.I):
            continue
        lines.append(f"{idx}. {label}")
        if kind in {"text", "textarea"}:
            lines.append("   Type: free-text (type into the edit box)")
            if re.search(r"salary|compensation|pay|expect", label, re.I):
                lines.append(
                    "   Hint: answer with a local-market USD number or tight range only"
                )
        # Send the full required .field-wrapper text so DeepSeek sees helper/
        # description lines (e.g. United States of America / Canada under a Yes/No).
        if field_text and field_text.lower() != label.lower():
            # Keep prompt lean — drop the bare label prefix if present.
            ctx = field_text
            if ctx.lower().startswith(label.lower()):
                ctx = ctx[len(label) :].strip(" \n:*")
            ctx = re.sub(r"\bThis field is required\.?\b", "", ctx, flags=re.I).strip()
            ctx = re.sub(r"\bSelect\.\.\.\b", "", ctx, flags=re.I).strip()
            if ctx:
                lines.append(f"   Field text: {ctx}")
        if kind in {"select", "checkbox"} or choices:
            # Drop accidental phone dial-code lists (Afghanistan+93, ...).
            clean_choices = [
                c
                for c in choices
                if c and not re.search(r"\+\d{1,4}$", c)
            ]
            if len(clean_choices) >= 20:
                dial_hits = sum(1 for c in clean_choices if re.search(r"\+\d{1,4}$", c))
                if dial_hits >= 10:
                    clean_choices = []
            if len(choices) >= 30 and sum(
                1 for c in choices if re.search(r"\+\d{1,4}$", c)
            ) >= 15:
                clean_choices = []
            if clean_choices:
                if kind == "checkbox":
                    lines.append(
                        "   Choices (checkbox — pick EXACTLY one of these verbatim):"
                    )
                else:
                    lines.append("   Choices (pick EXACTLY one of these verbatim):")
                for choice in clean_choices:
                    lines.append(f"   - {choice}")
            else:
                lines.append(
                    "   Choices: (dropdown options failed to load — answer with "
                    "the single best short option text you would click, not a sentence)"
                )

    set_composer_value(page, composer, "\n".join(lines))
    _sleep(400)
    composer = find_composer(page) or composer
    if not click_send(page, composer):
        raise RuntimeError("Could not send application questions to DeepSeek")

    deadline = time.time() + 180
    last_reply = ""
    quiet_since = time.time()
    best: dict[str, str] = {}
    needed = max(1, (len(labels) + 1) // 2)

    while time.time() < deadline:
        # Only poke Continue while generation is active.
        try:
            state = page.evaluate(PAGE_STATE_JS)
        except Exception:
            _sleep(500)
            continue

        stopping = bool(state.get("stopping"))
        if stopping:
            click_continue_or_reply(page)

        reply = (state.get("reply") or "").strip()
        answer_count = int(state.get("answerCount") or 0)

        # Ignore the previous resume message until a newer assistant bubble exists.
        if answer_count <= before_answers and reply == before_reply:
            _sleep(500)
            continue

        if reply != last_reply:
            last_reply = reply
            quiet_since = time.time()

        candidates = [reply]
        candidates.extend(_extract_gap_reply_blobs(page))

        for blob in candidates:
            parsed = _parse_answers_object(blob)
            if _looks_like_resume_payload(parsed):
                continue
            mapped = _normalize_gap_answers(parsed, questions)
            if len(mapped) > len(best):
                best = mapped

        complete = bool(best) and (
            len(best) >= len(labels) or len(best) >= needed
        )
        if complete and not stopping:
            # Short answer JSON often finishes in one shot — don't wait forever.
            if len(best) >= len(labels) or (time.time() - quiet_since) >= 1.0:
                return best

        _sleep(400)

    return best

