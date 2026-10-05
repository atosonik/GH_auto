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
    detect_security_code_field,
    detect_submission_success,
    extract_job_description,
    fill_greenhouse_form,
    fill_security_code,
    fill_selects_playwright,
    submit_application,
    upload_resume,
)
from app.automation.imap_client import wait_for_security_code
from app.automation.resume import ResumeBridge


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
                        fill_result = fill_greenhouse_form(greenhouse_page, gh_profile) or {}

                        url_item["state"] = "uploading resume"
                        self.set_job_state(profile_id, jobs, "uploading resume")
                        upload_resume(greenhouse_page, pdf_path)

                        # Remaining required questions. Skip opening every dropdown:
                        # rule-covered Yes/No selects are filled locally (fast).
                        rules = list(gh_profile.get("dropdownRules") or [])
                        checkbox_rules = list(gh_profile.get("checkboxRules") or [])
                        questions = collect_questions(
                            greenhouse_page,
                            read_choices=True,
                            dropdown_rules=rules,
                            checkbox_rules=checkbox_rules,
                        )
                        if not questions:
                            questions = [
                                g
                                for g in (fill_result.get("gaps") or [])
                                if g.get("required", True)
                                and not re.search(
                                    r"location\s*\(city\)|^location\b|city,\s*state|currently located",
                                    str(g.get("label") or ""),
                                    re.I,
                                )
                            ]
                        answers: dict[str, Any] = {}

                        # Instant-fill selects / checkboxes we already know from rules.
                        ruled_bound: list[dict[str, Any]] = []
                        for question in list(questions):
                            ruled = question.get("ruleValue")
                            if not ruled:
                                continue
                            kind = str(question.get("kind") or "select")
                            ruled_bound.append(
                                {
                                    "label": str(question.get("label") or "").strip(),
                                    "name": question.get("name")
                                    or question.get("id")
                                    or question.get("label"),
                                    "kind": kind if kind in {"select", "checkbox"} else "select",
                                    "choices": list(question.get("choices") or []),
                                    "answer": ruled,
                                }
                            )
                        if ruled_bound:
                            apply_gap_answers(
                                greenhouse_page,
                                ruled_bound,
                                use_playwright_fallback=False,
                            )
                            # Drop rule-filled fields so DeepSeek only sees real gaps.
                            ruled_labels = {
                                str(q.get("label") or "").strip().lower()
                                for q in questions
                                if q.get("ruleValue")
                            }
                            questions = [
                                q
                                for q in questions
                                if str(q.get("label") or "").strip().lower()
                                not in ruled_labels
                            ]

                        if questions:
                            url_item["state"] = "answering questions"
                            self.set_job_state(profile_id, jobs, "answering questions")
                            focus_page(deepseek_page)
                            answers = ask_deepseek_gaps(
                                deepseek_page,
                                questions,
                                profile_context=profile_context,
                            ) or {}
                            url_item["state"] = "filling answers"
                            self.set_job_state(profile_id, jobs, "filling answers")
                            focus_page(greenhouse_page, retries=4)
                            if answers:
                                # Bind each answer to the exact collected field (id/label/kind).
                                bound: list[dict[str, Any]] = []
                                for idx, question in enumerate(questions, start=1):
                                    label = str(question.get("label") or "").strip()
                                    value = (
                                        answers.get(label)
                                        or answers.get(str(idx))
                                        or answers.get(f"Q{idx}")
                                        or answers.get(f"q{idx}")
                                    )
                                    if value is None:
                                        # Fuzzy label match against model keys.
                                        label_l = label.lower()
                                        for key, candidate in answers.items():
                                            key_l = str(key).lower()
                                            if key_l == label_l or label_l in key_l or key_l in label_l:
                                                value = candidate
                                                break
                                    if value is None:
                                        continue
                                    choices = [
                                        str(c).strip()
                                        for c in (question.get("choices") or [])
                                        if str(c).strip()
                                    ]
                                    if choices:
                                        value = _snap_to_choice(str(value), choices)
                                    bound.append(
                                        {
                                            "label": label,
                                            "name": question.get("name")
                                            or question.get("id")
                                            or label,
                                            "kind": question.get("kind") or "text",
                                            "choices": choices,
                                            "answer": value,
                                        }
                                    )
                                applied = apply_gap_answers(greenhouse_page, bound) or {}
                                filled = int(
                                    applied.get("filled") or len(applied.get("log") or [])
                                )
                                if filled <= 0:
                                    self.set_job_state(
                                        profile_id,
                                        jobs,
                                        "warning: answers parsed but no fields matched",
                                    )
                            else:
                                self.set_job_state(
                                    profile_id,
                                    jobs,
                                    "warning: no question answers parsed from DeepSeek",
                                )

                        # Last pass: any required dropdown / checkbox still empty.
                        remaining = collect_questions(
                            greenhouse_page,
                            read_choices=False,
                            dropdown_rules=rules,
                            checkbox_rules=checkbox_rules,
                        ) or []
                        select_fixup: list[dict[str, Any]] = []
                        for q in remaining:
                            kind = str(q.get("kind") or "")
                            if kind not in {"select", "checkbox"}:
                                continue
                            label = str(q.get("label") or "").strip()
                            label_l = label.lower()
                            value = None
                            for key, candidate in answers.items():
                                key_l = str(key).lower()
                                if key_l == label_l or label_l in key_l or key_l in label_l:
                                    value = candidate
                                    break
                            if value is None:
                                rule_list = checkbox_rules if kind == "checkbox" else rules
                                for rule in rule_list:
                                    needle = str(rule.get("includes") or "").lower()
                                    if needle and needle in label_l:
                                        value = rule.get("value")
                                        break
                            if value is None and q.get("ruleValue"):
                                value = q.get("ruleValue")
                            if value is None and kind == "select" and any(
                                x in label_l for x in ("visa", "sponsorship")
                            ):
                                value = "No"
                            if value is None and kind == "select" and any(
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
                            choices = [
                                str(c).strip()
                                for c in (q.get("choices") or [])
                                if str(c).strip()
                            ]
                            if choices and kind == "select":
                                value = _snap_to_choice(str(value), choices)
                            select_fixup.append(
                                {
                                    "label": label,
                                    "name": q.get("name") or q.get("id") or label,
                                    "kind": kind,
                                    "choices": choices,
                                    "answer": value,
                                }
                            )
                        if select_fixup:
                            self.set_job_state(
                                profile_id, jobs, "filling required dropdowns"
                            )
                            apply_gap_answers(greenhouse_page, select_fixup)
                            fill_selects_playwright(
                                greenhouse_page,
                                [x for x in select_fixup if x.get("kind") == "select"],
                            )

                        focus_page(greenhouse_page, retries=3)
                        try:
                            greenhouse_page.bring_to_front()
                        except Exception:
                            pass
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
                        # Re-click Submit once if we are still sitting on the form.
                        confirmed = False
                        resubmit_used = False
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
                                code = wait_for_security_code(profile.get("imap") or {})
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
                            raise RuntimeError(
                                'Submit was clicked but the Greenhouse confirmation '
                                '("Thank you for applying") was not detected. '
                                "Not marking as submitted."
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
