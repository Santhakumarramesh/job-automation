"""
Portal resume adapter interfaces and LinkedIn Easy Apply implementation.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Tuple

from services.portal_resume_state import PortalResumeState, extract_filename


class ResumePortalAdapter:
    name = "base"

    async def detect_state(self, page: Any) -> PortalResumeState:
        raise NotImplementedError

    async def get_current_resume(self, page: Any) -> dict:
        raise NotImplementedError

    async def remove_current_resume(self, page: Any) -> bool:
        raise NotImplementedError

    async def upload_resume(self, page: Any, resume_path: str) -> bool:
        raise NotImplementedError

    async def verify_uploaded_resume(self, page: Any, expected_filename: str) -> bool:
        raise NotImplementedError


async def _first_match(
    page: Any,
    selectors: Iterable[str],
    *,
    require_visible: bool = False,
) -> Tuple[Optional[Any], Optional[str]]:
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if not el:
                continue
            if require_visible:
                try:
                    if not await el.is_visible():
                        continue
                except Exception:
                    continue
            return el, sel
        except Exception:
            continue
    return None, None


async def _element_text(el: Any) -> str:
    if not el:
        return ""
    for attr in ("aria-label", "title", "data-test-document-name", "data-test-file-name"):
        try:
            val = await el.get_attribute(attr)
            if val:
                return str(val).strip()
        except Exception:
            continue
    try:
        text = await el.inner_text()
        if text:
            return str(text).strip()
    except Exception:
        pass
    try:
        text = await el.text_content()
        if text:
            return str(text).strip()
    except Exception:
        pass
    return ""


class LinkedInEasyApplyResumeAdapter(ResumePortalAdapter):
    name = "linkedin_easy_apply"

    UPLOAD_INPUT_SELECTORS = [
        "input[type='file'][name*='file']",
        "input[type='file'][accept*='pdf']",
        "input[type='file']",
    ]

    RESUME_FILENAME_SELECTORS = [
        "span.jobs-document-upload__file-name",
        "span.artdeco-file__name",
        "span[data-test-document-upload-filename]",
        "span[data-test-file-name]",
    ]

    REMOVE_BUTTON_SELECTORS = [
        "button[aria-label*='Remove']",
        "button[aria-label*='Delete']",
        "button[aria-label*='remove']",
        "button[aria-label*='delete']",
        "button[data-control-name*='remove']",
    ]

    async def _find_upload_input(self, page: Any) -> Optional[Any]:
        el, _ = await _first_match(page, self.UPLOAD_INPUT_SELECTORS, require_visible=False)
        return el

    async def _find_remove_button(self, page: Any) -> Optional[Any]:
        el, _ = await _first_match(page, self.REMOVE_BUTTON_SELECTORS, require_visible=True)
        return el

    async def _find_existing_filename(self, page: Any) -> str:
        # Check known filename selectors first.
        for sel in self.RESUME_FILENAME_SELECTORS:
            try:
                el = await page.query_selector(sel)
                if el:
                    text = await _element_text(el)
                    fname = extract_filename(text)
                    if fname:
                        return fname
            except Exception:
                continue

        # Try to parse filename from the remove button aria-label.
        remove_btn = await self._find_remove_button(page)
        if remove_btn:
            text = await _element_text(remove_btn)
            fname = extract_filename(text)
            if fname:
                return fname

        # Fallback: scan any element with an aria-label containing a file extension.
        try:
            els = await page.query_selector_all("[aria-label]")
            for el in els[:20]:
                text = await _element_text(el)
                fname = extract_filename(text)
                if fname:
                    return fname
        except Exception:
            pass

        return ""

    async def detect_state(self, page: Any) -> PortalResumeState:
        upload_input = await self._find_upload_input(page)
        remove_btn = await self._find_remove_button(page)
        filename = await self._find_existing_filename(page)
        existing = bool(filename)
        resume_slot_present = bool(upload_input or remove_btn or existing)
        upload_control_found = bool(upload_input)
        return PortalResumeState(
            resume_slot_present=resume_slot_present,
            upload_control_found=upload_control_found,
            existing_resume_detected=existing,
            existing_resume_filename=filename,
            can_remove_existing_resume=bool(remove_btn),
            can_replace_existing_resume=bool(upload_input),
        )

    async def get_current_resume(self, page: Any) -> dict:
        state = await self.detect_state(page)
        return {
            "filename": state.existing_resume_filename or "",
            "detected": state.existing_resume_detected,
        }

    async def remove_current_resume(self, page: Any) -> bool:
        btn = await self._find_remove_button(page)
        if not btn:
            return False
        try:
            await btn.click()
            try:
                await page.wait_for_timeout(800)
            except Exception:
                pass
            return True
        except Exception:
            return False

    async def upload_resume(self, page: Any, resume_path: str) -> bool:
        up = await self._find_upload_input(page)
        if not up:
            return False
        try:
            await up.set_input_files(resume_path)
            try:
                await page.wait_for_timeout(1200)
            except Exception:
                pass
            return True
        except Exception:
            return False

    async def verify_uploaded_resume(self, page: Any, expected_filename: str) -> bool:
        state = await self.detect_state(page)
        if not state.existing_resume_detected:
            return False
        return state.matches_filename(expected_filename)
