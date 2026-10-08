from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import sync_playwright

from app.automation.chrome import (
    DEFAULT_CDP_PORT,
    ensure_live_debugging,
    ensure_profile_clone,
    find_chrome_executable,
    focus_page,
    launch_live_profile_browser,
    launch_profile_browser,
    open_deepseek_tab,
    open_job_page,
    tile_bounds,
)
from app.automation.deepseek import (
    _resume_ready,
    _snap_to_choice,
    _unwrap_resume_parse,
    ask_deepseek_cover_letter,
    ask_deepseek_gaps,
    assemble_prompt,
    load_profile_context,
    load_profiles_json,
    load_prompt,
    run_deepseek_chat,
)
from app.automation.greenhouse import (
    apply_gap_answers,
    build_greenhouse_profile,
    collect_questions,
    cover_letter_state,
    detect_security_code_field,
    detect_submission_success,
    detect_validation_errors,
    extract_job_description,
    fill_cover_letter_text,
    fill_security_code,
    prefill_contact_fields,
    submit_application,
    upload_resume,
)
from app.automation.outlook_web_otp import wait_for_security_code_with_fallback
from app.automation.resume import ResumeBridge


def resolve_imap_config(
    profile: dict[str, Any], personal: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    IMAP config for OTP. If the UI left mailbox blank, fall back to
    profiles.json email (common when adding a profile via outlook_login only).
    """
    imap = dict((profile or {}).get("imap") or {})
    user = str(imap.get("user") or "").strip()
    if not user:
        user = str((personal or {}).get("email") or "").strip()
        if user:
            imap["user"] = user
    host = str(imap.get("host") or "").strip().lower()
    preset = str(imap.get("preset") or "").strip().lower()
    auth = str(imap.get("auth") or "").strip().lower()
    if not auth:
        if (
            preset == "outlook"
            or "outlook" in host
            or "office365" in host
            or user.lower().endswith("@outlook.com")
            or user.lower().endswith("@hotmail.com")
            or user.lower().endswith("@live.com")
        ):
            imap["auth"] = "oauth"
            if not host:
                imap["host"] = "outlook.office365.com"
                imap["port"] = int(imap.get("port") or 993)
            if not preset:
                imap["preset"] = "outlook"
    return imap


def _profile_facts(gh_profile: dict[str, Any]) -> list[tuple[str, str]]:
    personal = gh_profile.get("personal") or {}
    edu = gh_profile.get("education") or {}
    pairs = [
        ("First name", personal.get("firstName")),
        ("Last name", personal.get("lastName")),
        ("Preferred name", personal.get("preferredName")),
        ("Location", personal.get("location")),
        ("Country", personal.get("country")),
        ("School", edu.get("school")),
        ("Degree", edu.get("degree")),
        ("Discipline", edu.get("discipline")),
    ]
    return [(k, str(v).strip()) for k, v in pairs if str(v or "").strip()]


def _with_candidate_facts(profile_context: str, gh_profile: dict[str, Any]) -> str:
    facts = _profile_facts(gh_profile)
    if not facts:
        return profile_context
    block = "Candidate facts:\n" + "\n".join(f"{k}: {v}" for k, v in facts)
    return f"{profile_context.strip()}\n\n{block}" if profile_context.strip() else block


def _fact_for_label(label: str, gh_profile: dict[str, Any]) -> str | None:
    """Last-resort value from profiles.json / resume education for a label."""
    facts = dict(_profile_facts(gh_profile))
    lab = label.lower()
    checks = [
        (r"preferred", "Preferred name"),
        (r"first name|given name", "First name"),
        (r"last name|family name|surname", "Last name"),
        (r"locat|city", "Location"),
        (r"school|university|college", "School"),
        (r"degree", "Degree"),
        (r"discipline|major|field of study", "Discipline"),
    ]
    for pattern, key in checks:
        if re.search(pattern, lab):
            return facts.get(key)
    return None


def _eeoc_rules(gh_profile: dict[str, Any]) -> list[dict[str, Any]]:
    if not gh_profile.get("fillEeoc"):
        return []
    eeoc = gh_profile.get("eeoc") or {}
    pairs = [
        ("gender", eeoc.get("gender")),
        ("hispanic", eeoc.get("hispanic_ethnicity")),
        ("veteran", eeoc.get("veteran_status")),
        ("disability", eeoc.get("disability_status")),
    ]
    return [{"includes": k, "value": v} for k, v in pairs if v]


def _answer_for(answers: dict[str, Any], question: dict[str, Any], index: int | None) -> Any:
    label = str(question.get("label") or "").strip()
    keys = [label]
    if index is not None:
        keys += [str(index), f"Q{index}", f"q{index}"]
    for key in keys:
        if key in answers and str(answers[key]).strip():
            return answers[key]
    label_l = label.lower()
    for key, candidate in answers.items():
        key_l = str(key).lower()
        if key_l == label_l or label_l in key_l or key_l in label_l:
            return candidate
    return None


def _bind_answer(question: dict[str, Any], value: Any) -> dict[str, Any]:
    label = str(question.get("label") or "").strip()
    kind = str(question.get("kind") or "text")
    choices = [str(c).strip() for c in (question.get("choices") or []) if str(c).strip()]
    answer = str(value).strip()
    if choices and kind in {"select", "checkbox"}:
        answer = _snap_to_choice(answer, choices)
    return {
        "label": label,
        "name": question.get("name") or question.get("id") or label,
        "kind": kind,
        "choices": choices,
        "answer": answer,
    }


class Runner:
    def __init__(
        self,
        settings: dict[str, Any],
        work_area: dict[str, int],
        on_status: Callable[[dict[str, Any]], None] | None = None,
        on_run_state: Callable[[dict[str, Any]], None] | None = None,
        user_data_root: str | Path | None = None,
    ):
        self.settings = settings
        self.work_area = work_area
        self.on_status = on_status
        self.on_run_state = on_run_state
        self.user_data_root = Path(user_data_root or Path.cwd() / ".app-data")
        self.stop_requested = False
        self.running = False
        self._contexts: list[Any] = []
        self._browsers: list[Any] = []
        self._contexts_lock = threading.Lock()
        self.resume_bridge = ResumeBridge(settings)
        self.profiles_json = load_profiles_json(settings["profilesJsonPath"])

    def is_running(self) -> bool:
        return self.running

    def stop(self) -> None:
        self.stop_requested = True

    def emit_profile_status(self, profile_id: str, payload: dict[str, Any]) -> None:
        if self.on_status:
            message = {"profileId": profile_id, **payload}
            self.on_status(message)

    def set_job_state(self, profile_id: str, jobs: list[dict[str, Any]], message: str = "") -> None:
        done = sum(1 for job in jobs if job.get("state") in {"submitted", "skipped", "failed"})
        total = max(len(jobs), 1)
        self.emit_profile_status(
            profile_id,
            {
                "message": message,
                "progress": int((done / total) * 100),
                "jobs": jobs,
            },
        )

    def _fill_required(
        self,
        greenhouse_page,
        deepseek_page,
        gh_profile: dict[str, Any],
        context_text: str,
        profile_id: str,
        jobs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Collect every required field → one DeepSeek request → fill from its JSON.
        Single-option fields are clicked without asking. Rules / profile facts
        are only used afterwards for anything that is still empty.
        """
        rules = list(gh_profile.get("dropdownRules") or []) + _eeoc_rules(gh_profile)
        checkbox_rules = list(gh_profile.get("checkboxRules") or [])

        self.set_job_state(profile_id, jobs, "collecting required fields")
        questions = collect_questions(
            greenhouse_page,
            read_choices=True,
            dropdown_rules=rules,
            checkbox_rules=checkbox_rules,
        ) or []

        auto = [_bind_answer(q, q["autoValue"]) for q in questions if q.get("autoValue")]
        if auto:
            apply_gap_answers(greenhouse_page, auto)
        questions = [q for q in questions if not q.get("autoValue")]

        answers: dict[str, Any] = {}
        if questions:
            self.set_job_state(
                profile_id, jobs, f"asking DeepSeek ({len(questions)} fields)"
            )
            focus_page(deepseek_page)
            answers = ask_deepseek_gaps(
                deepseek_page, questions, profile_context=context_text
            ) or {}
            focus_page(greenhouse_page, retries=4)
            self.set_job_state(profile_id, jobs, "filling answers")
            bound = []
            for idx, question in enumerate(questions, start=1):
                value = _answer_for(answers, question, idx)
                if value is not None:
                    bound.append(_bind_answer(question, value))
            if not bound:
                self.set_job_state(
                    profile_id, jobs, "warning: no question answers parsed from DeepSeek"
                )
            else:
                applied = apply_gap_answers(greenhouse_page, bound) or {}
                if int(applied.get("filled") or 0) <= 0:
                    self.set_job_state(
                        profile_id, jobs, "warning: answers parsed but no fields matched"
                    )

        remaining = collect_questions(
            greenhouse_page,
            read_choices=False,
            dropdown_rules=rules,
            checkbox_rules=checkbox_rules,
        ) or []
        fixup: list[dict[str, Any]] = []
        for question in remaining:
            label = str(question.get("label") or "").strip()
            label_l = label.lower()
            kind = str(question.get("kind") or "")
            value = _answer_for(answers, question, None)
            if value is None:
                value = question.get("autoValue") or question.get("ruleValue")
            if value is None:
                value = _fact_for_label(label, gh_profile)
            if value is None and kind == "select":
                if any(x in label_l for x in ("visa", "sponsorship")):
                    value = "No"
                elif any(
                    x in label_l
                    for x in (
                        "authorized to work",
                        "legally authorized",
                        "right to work",
                        "eligible to work",
                    )
                ):
                    value = "Yes"
            if value is None:
                continue
            fixup.append(_bind_answer(question, value))
        if fixup:
            self.set_job_state(profile_id, jobs, "filling leftover required fields")
            apply_gap_answers(greenhouse_page, fixup)
        return answers

    def start(self, urls: list[dict[str, Any]], profiles: list[dict[str, Any]]) -> None:
        if not urls:
            raise ValueError("Select at least one URL")
        if not profiles:
            raise ValueError("Select at least one profile")

        self.stop_requested = False
        self.running = True
        prepared: list[dict[str, Any]] = []
        if self.on_run_state:
            self.on_run_state({"running": True, "message": "Starting…"})

        try:
            executable_path = find_chrome_executable()
            browser_mode = str(self.settings.get("browserMode") or "isolated").lower()
            if browser_mode not in {"isolated", "live"}:
                browser_mode = "isolated"
            debug_port = int(self.settings.get("chromeDebugPort") or DEFAULT_CDP_PORT)
            clone_root = self.user_data_root / ".chrome-profiles"

            if browser_mode == "live":
                ensure_live_debugging(
                    executable_path,
                    self.settings["chromeUserDataDir"],
                    debug_port,
                )

            for i, profile in enumerate(profiles):
                bounds = tile_bounds(self.work_area, i, len(profiles))
                item: dict[str, Any] = {
                    "profile": profile,
                    "bounds": bounds,
                    "executable_path": executable_path,
                    "browser_mode": browser_mode,
                    "debug_port": debug_port,
                    "chrome_user_data_dir": self.settings["chromeUserDataDir"],
                }
                if browser_mode == "isolated":
                    item["user_data_dir"] = ensure_profile_clone(
                        self.settings["chromeUserDataDir"],
                        int(profile.get("chromeProfileNumber") or 0),
                        clone_root,
                    )
                prepared.append(item)

            # Isolated: one Playwright + Chrome per profile thread (true parallel).
            # Live CDP: sequential window attach to avoid grabbing the wrong page.
            workers = 1 if browser_mode == "live" else max(len(prepared), 1)
            failures = 0
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(self.run_profile, item, urls)
                    for item in prepared
                ]
                for future in as_completed(futures):
                    error = future.exception()
                    if error and not self.stop_requested:
                        failures += 1

            if self.on_run_state:
                if self.stop_requested:
                    message = "Stopped"
                elif failures:
                    message = f"Finished with {failures} failed profile(s)"
                else:
                    message = "Finished"
                self.on_run_state({"running": False, "message": message})
        finally:
            self.running = False
            with self._contexts_lock:
                for context in list(self._contexts):
                    try:
                        if getattr(context, "_gh_keep_open", False):
                            continue
                        context.close()
                    except Exception:
                        pass
                self._contexts.clear()
                self._browsers.clear()

    def run_profile(self, prepared: dict[str, Any], urls: list[dict[str, Any]]) -> None:
        profile = prepared["profile"]
        profile_id = profile.get("id") or profile.get("name")
        name = (profile.get("name") or "").strip()
        personal = self.profiles_json.get(name)
        if not personal:
            raise RuntimeError(
                f'No profiles.json entry for "{name}". Name must match exactly.'
            )

        prompt_text = load_prompt(self.settings["promptsDir"], name)
        profile_context = load_profile_context(self.settings["profileContextDir"], name)

        jobs = [
            {"urlId": u.get("id"), "url": u.get("url"), "state": "queued"}
            for u in urls
        ]
        self.set_job_state(profile_id, jobs, "queued")

        # Each profile thread owns its Playwright instance (required for Sync API).
        with sync_playwright() as playwright:
            browser = None
            if prepared.get("browser_mode") == "live":
                context, _page, browser = launch_live_profile_browser(
                    playwright,
                    prepared["executable_path"],
                    prepared["chrome_user_data_dir"],
                    int(prepared["profile"].get("chromeProfileNumber") or 0),
                    prepared["bounds"],
                    int(prepared.get("debug_port") or DEFAULT_CDP_PORT),
                )
                context._gh_keep_open = True  # type: ignore[attr-defined]
            else:
                context, _page, browser = launch_profile_browser(
                    playwright,
                    prepared["executable_path"],
                    prepared["user_data_dir"],
                    prepared["bounds"],
                )

            with self._contexts_lock:
                self._contexts.append(context)
                if browser is not None:
                    self._browsers.append(browser)

            pages = None
            try:
                for url_item in jobs:
                    if self.stop_requested:
                        url_item["state"] = "skipped"
                        self.set_job_state(profile_id, jobs, "Stopped")
                        continue

                    try:
                        job_url = url_item["url"]
                        self.set_job_state(profile_id, jobs, "reading job")
                        url_item["state"] = "reading job"
                        greenhouse_page = open_job_page(context, job_url, pages)
                        job = extract_job_description(greenhouse_page)
                        posting_text, _attach_text = assemble_prompt(
                            prompt_text, job, mode="full"
                        )

                        if self.stop_requested:
                            url_item["state"] = "skipped"
                            break

                        url_item["state"] = "chatting"
                        self.set_job_state(profile_id, jobs, "chatting")
                        deepseek_page = open_deepseek_tab(context, pages)
                        pages = {
                            "greenhouse_page": greenhouse_page,
                            "deepseek_page": deepseek_page,
                        }
                        resume = run_deepseek_chat(
                            deepseek_page,
                            posting_text,
                            attach_text="",
                            profile_name=name,
                        )

                        payload = None
                        raw = ""
                        if isinstance(resume, dict):
                            # Preferred shape from run_deepseek_chat.
                            if isinstance(resume.get("parsed"), dict) and resume["parsed"].get("name"):
                                payload = resume["parsed"]
                                raw = resume.get("raw") or ""
                            else:
                                payload, raw = _unwrap_resume_parse(resume)
                        if payload is None and isinstance(resume, dict) and resume.get("raw"):
                            try:
                                payload = json.loads(resume["raw"])
                                raw = resume["raw"]
                            except Exception:
                                pass
                        if not raw and isinstance(payload, dict):
                            raw = json.dumps(payload, indent=2, ensure_ascii=False)

                        if not _resume_ready(payload):
                            raise RuntimeError(
                                "DeepSeek returned incomplete resume JSON "
                                "(need name + experience, or summary + skills). "
                                "Stay on the DeepSeek tab until the full object finishes."
                            )

                        if isinstance(payload, dict):
                            payload["auto"] = True
                            payload["name"] = name
                            target = payload.setdefault("target", {})
                            # Always prefer real JD metadata over model placeholders
                            # like "Target Company" / "Normalized Target Role".
                            placeholder_company = {
                                "",
                                "target company",
                                "unknown",
                                "company",
                                "normalized target company",
                            }
                            placeholder_role = {
                                "",
                                "normalized target role",
                                "target role",
                                "role",
                                "tailored resume headline",
                            }
                            current_company = str(target.get("company") or "").strip()
                            current_role = str(target.get("role") or "").strip()
                            if job.get("company") and (
                                not current_company
                                or current_company.lower() in placeholder_company
                            ):
                                target["company"] = job.get("company")
                            if job.get("title") and (
                                not current_role or current_role.lower() in placeholder_role
                            ):
                                target["role"] = job.get("title")
                            if job.get("url"):
                                payload["posting"] = job.get("url")
                            # Prefer real JD text over placeholder "Complete Job Description".
                            jd_text = str(job.get("description") or "").strip()
                            if jd_text and str(payload.get("jd") or "").strip().lower() in {
                                "",
                                "complete job description",
                                "job description",
                            }:
                                payload["jd"] = jd_text[:20000]
                            raw = json.dumps(payload, indent=2, ensure_ascii=False)
                        elif raw:
                            raw = re.sub(
                                r'"name"\s*:\s*"[^"]*"',
                                f'"name": {json.dumps(name)}',
                                raw,
                                count=1,
                            )

                        company = (
                            job.get("company")
                            or ((payload or {}).get("target") or {}).get("company")
                            or ""
                        )

                        # Stay on DeepSeek while Word builds the PDF.
                        url_item["state"] = "waiting for resume"
                        self.set_job_state(profile_id, jobs, "waiting for resume")
                        focus_page(deepseek_page)

                        resume_started = time.time()
                        pdf_path = self.resume_bridge.generate(
                            name,
                            payload=payload,
                            raw_text=raw,
                            company=company,
                            on_status=lambda msg: self.set_job_state(profile_id, jobs, msg),
                        )
                        matched = self.resume_bridge.find_resume_pdf(
                            name, company=company, after_ts=resume_started
                        )
                        if matched:
                            pdf_path = matched
                        if not pdf_path or not Path(pdf_path).exists():
                            raise RuntimeError(
                                f'Resume PDF was not created for "{name}". '
                                "Check Paths → Resume main.py / Python for main.py, "
                                "and that templates/<name>.docx exists."
                            )

                        resume_folder = str(Path(pdf_path).resolve().parent)
                        url_item["pdfPath"] = pdf_path
                        url_item["resumeFolder"] = resume_folder

                        # Hard switch back to the Greenhouse job/application tab.
                        url_item["state"] = "filling"
                        self.set_job_state(profile_id, jobs, "filling")
                        focus_page(greenhouse_page, retries=4)
                        try:
                            greenhouse_page.bring_to_front()
                        except Exception:
                            pass
                        time.sleep(0.15)

                        gh_profile = build_greenhouse_profile(
                            personal,
                            {
                                "fillEeoc": True,
                                "education": (payload or {}).get("education")
                                if isinstance(payload, dict)
                                else None,
                            },
                        )
                        context_text = _with_candidate_facts(profile_context, gh_profile)

                        # Only email / phone / phone country / LinkedIn are prefilled.
                        prefill_contact_fields(greenhouse_page, gh_profile["personal"])

                        url_item["state"] = "uploading resume"
                        self.set_job_state(profile_id, jobs, "uploading resume")
                        upload_resume(greenhouse_page, pdf_path)

                        self._fill_required(
                            greenhouse_page,
                            deepseek_page,
                            gh_profile,
                            context_text,
                            profile_id,
                            jobs,
                        )

                        letter = cover_letter_state(greenhouse_page)
                        if letter.get("required") and not letter.get("filled"):
                            url_item["state"] = "writing cover letter"
                            self.set_job_state(profile_id, jobs, "writing cover letter")
                            focus_page(deepseek_page)
                            cover_text = ask_deepseek_cover_letter(deepseek_page)
                            focus_page(greenhouse_page, retries=4)
                            if not fill_cover_letter_text(greenhouse_page, cover_text):
                                raise RuntimeError(
                                    "Cover letter is required but could not be pasted "
                                    "via Enter manually"
                                )
                            url_item["coverLetter"] = True

                        focus_page(greenhouse_page, retries=3)
                        try:
                            greenhouse_page.bring_to_front()
                        except Exception:
                            pass
                        imap_cfg = resolve_imap_config(profile, personal)
                        url_item["state"] = "submitting"
                        self.set_job_state(profile_id, jobs, "submitting")
                        submit_result = submit_application(greenhouse_page) or {}
                        if not submit_result.get("ok"):
                            raise RuntimeError(
                                "Submit application click failed: "
                                f"{submit_result.get('reason') or submit_result}"
                            )
                        url_item["submit"] = submit_result.get("via") or submit_result.get(
                            "clicked"
                        ) or "clicked"

                        # Confirmation page is mandatory — wait for thank-you /
                        # confirmation URL. Handle security-code interstitial if it appears.
                        # If validation errors block submit, refill + resubmit once.
                        confirmed = False
                        resubmit_used = False
                        validation_fix_used = False
                        confirm_started = time.time()
                        confirm_deadline = confirm_started + 120
                        while time.time() < confirm_deadline:
                            if detect_submission_success(greenhouse_page):
                                confirmed = True
                                break
                            code_field = detect_security_code_field(greenhouse_page)
                            if code_field.get("found"):
                                url_item["state"] = "security code"
                                self.set_job_state(profile_id, jobs, "security code")
                                if not str(imap_cfg.get("user") or "").strip():
                                    raise RuntimeError(
                                        "Greenhouse asked for an email security code, but "
                                        "this profile has no IMAP mailbox. Set imap.user "
                                        f"or add email to profiles.json for {name!r}."
                                    )
                                code = wait_for_security_code_with_fallback(
                                    imap_cfg,
                                    browser_context=context,
                                    timeout_ms=180000,
                                )
                                filled = fill_security_code(greenhouse_page, code) or {}
                                if not filled.get("ok"):
                                    raise RuntimeError(
                                        f"Got security code {code!r} but could not fill "
                                        f"the 8-box verification inputs: {filled}"
                                    )
                                url_item["securityCode"] = code
                                submit_application(greenhouse_page)
                                time.sleep(1.5)
                                continue

                            errors = detect_validation_errors(greenhouse_page)
                            if errors and not validation_fix_used:
                                validation_fix_used = True
                                self.set_job_state(
                                    profile_id,
                                    jobs,
                                    "fixing validation errors",
                                )
                                # Contact prefill again, then the same
                                # collect → DeepSeek → fill pass for leftovers.
                                try:
                                    prefill_contact_fields(
                                        greenhouse_page, gh_profile["personal"]
                                    )
                                except Exception:
                                    pass
                                try:
                                    self._fill_required(
                                        greenhouse_page,
                                        deepseek_page,
                                        gh_profile,
                                        context_text,
                                        profile_id,
                                        jobs,
                                    )
                                except Exception:
                                    pass
                                try:
                                    submit_application(greenhouse_page)
                                except Exception:
                                    pass
                                time.sleep(1.5)
                                continue

                            # Still on the application form after a few seconds? click again.
                            if not resubmit_used and (time.time() - confirm_started) >= 8:
                                try:
                                    still = greenhouse_page.locator(
                                        ".application--submit button[type='submit']"
                                    )
                                    if still.count() > 0 and still.first.is_visible():
                                        self.set_job_state(
                                            profile_id, jobs, "submitting (retry)"
                                        )
                                        submit_application(greenhouse_page)
                                        resubmit_used = True
                                except Exception:
                                    resubmit_used = True
                            time.sleep(1.0)

                        if not confirmed:
                            errs = detect_validation_errors(greenhouse_page)
                            detail = (
                                " Validation: " + "; ".join(errs[:6])
                                if errs
                                else ""
                            )
                            raise RuntimeError(
                                'Submit was clicked but the Greenhouse confirmation '
                                '("Thank you for applying") was not detected.'
                                f"{detail} Not marking as submitted."
                            )

                        url_item["state"] = "submitted"
                        url_item["confirmed"] = True
                        url_item["pdfPath"] = pdf_path
                        url_item["resumeFolder"] = str(Path(pdf_path).resolve().parent)
                        self.set_job_state(profile_id, jobs, "submitted")
                    except Exception as error:
                        # Fail this job only; keep Chrome open and continue the queue.
                        if url_item.get("state") not in {"submitted", "skipped"}:
                            url_item["state"] = "failed"
                            url_item["error"] = str(error)
                        self.set_job_state(profile_id, jobs, f"failed: {error}")
                        continue
            finally:
                with self._contexts_lock:
                    if context in self._contexts:
                        self._contexts.remove(context)
                if prepared.get("browser_mode") != "live":
                    try:
                        context.close()
                    except Exception:
                        pass
