#!/usr/bin/env python3
"""
Automated screenshot capture for DMARC Intelligence Platform documentation.

Requires:
  - Platform running at --base-url (default: http://localhost:5010)
  - Sample data already populated in the target client
  - scripts/.screenshot_state.json created by screenshot_accounts.py

Usage:
    python scripts/capture_screenshots.py [options]

Options:
    --base-url URL        Platform URL (default: http://localhost:5010)
    --output-dir PATH     Screenshot output directory (default: docs/images)
    --state-file PATH     Credentials/MFA state file (default: scripts/.screenshot_state.json)
    --only ID             Capture a single screenshot by ID (e.g. --only SS-U-03)
    --headed              Show the browser window (useful for debugging)
    --slow-mo MS          Slow down interactions by N milliseconds (default: 0)
"""
import argparse
import json
import sys
import time
from pathlib import Path

import pyotp
from playwright.sync_api import sync_playwright, Page, BrowserContext, Playwright

VIEWPORT = {"width": 1280, "height": 800}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class Capturer:
    def __init__(self, base_url: str, output_dir: Path, state: dict,
                 headed: bool, slow_mo: int, only: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.out = output_dir
        self.state = state
        self.headed = headed
        self.slow_mo = slow_mo
        self.only = only
        self.out.mkdir(parents=True, exist_ok=True)
        self._results: dict[str, str] = {}   # id → "ok" | "skip" | "error: ..."

    # ── Browser helpers ───────────────────────────────────────────────────

    def _new_context(self, pw: Playwright) -> BrowserContext:
        browser = pw.chromium.launch(headless=not self.headed, slow_mo=self.slow_mo)
        return browser.new_context(viewport=VIEWPORT)

    def _login(self, page: Page, email: str, password: str,
               mfa_secret: str | None = None) -> None:
        """Navigate to login page and authenticate. Handles MFA automatically."""
        page.goto(f"{self.base_url}/login")
        page.wait_for_load_state("networkidle")
        page.fill("input[type=email]", email)
        page.fill("input[type=password]", password)
        page.click("button[type=submit]")

        # Check if MFA screen appeared (3-second window)
        try:
            page.wait_for_selector("input[inputmode=numeric]", timeout=3000)
            if not mfa_secret:
                raise RuntimeError(f"MFA required for {email} but no secret available")
            code = pyotp.TOTP(mfa_secret).now()
            page.fill("input[inputmode=numeric]", code)
            page.click("button[type=submit]")
        except Exception as e:
            if "Timeout" not in str(e):
                raise

        # Poll until we navigate away from /login — handles the race where the
        # React redirect completes before wait_for_url() is even called.
        page.wait_for_function(
            "() => !window.location.pathname.startsWith('/login')",
            timeout=12000,
        )
        page.wait_for_load_state("networkidle")

        # If the account has must_change_password=True the app redirects here
        if "/change-password" in page.url:
            raise RuntimeError(
                f"Account {email} requires a password change before it can be used.\n"
                "Fix: python scripts/screenshot_accounts.py --rebuild"
            )

    def _set_client(self, page: Page, slug: str) -> None:
        """Set the active client via localStorage and reload."""
        page.evaluate(f"localStorage.setItem('current_client', '{slug}')")
        page.reload()
        page.wait_for_load_state("networkidle")

    def _nav(self, page: Page, path: str) -> None:
        """Navigate to a path and wait for data to load."""
        page.goto(f"{self.base_url}{path}")
        page.wait_for_load_state("networkidle")

    def _shot(self, page: Page, shot_id: str, selector: str | None = None,
              clip: dict | None = None) -> None:
        """Take a screenshot and save it to docs/images/."""
        filename = shot_id.lower().replace("_", "-") + ".png"
        # Map IDs to filenames matching the docs
        name_map = {
            "ss-u-01": "ss-u-01-login.png",
            "ss-u-02": "ss-u-02-mfa-screen.png",
            "ss-u-03": "ss-u-03-dashboard-overview.png",
            "ss-u-04": "ss-u-04-stat-cards.png",
            "ss-u-05": "ss-u-05-world-map-tooltip.png",
            "ss-u-06": "ss-u-06-reports-list.png",
            "ss-u-07": "ss-u-07-report-detail.png",
            "ss-u-08": "ss-u-08-records-table-badges.png",
            "ss-u-09": "ss-u-09-record-expanded.png",
            "ss-u-10": "ss-u-10-flags-list.png",
            "ss-u-11": "ss-u-11-flag-type-tooltip.png",
            "ss-u-12": "ss-u-12-analytics-top-ips.png",
            "ss-u-13": "ss-u-13-user-menu.png",
            "ss-u-14": "ss-u-14-change-password.png",
            "ss-u-15": "ss-u-15-mfa-setup-qr.png",
            "ss-u-16": "ss-u-16-mfa-disable.png",
            "ss-a-01": "ss-a-01-flag-acknowledge.png",
            "ss-a-02": "ss-a-02-users-list.png",
            "ss-a-03": "ss-a-03-create-user-form.png",
            "ss-a-04": "ss-a-04-reset-password.png",
            "ss-a-05": "ss-a-05-clients-card-expanded.png",
            "ss-a-06": "ss-a-06-add-domain.png",
            "ss-a-07": "ss-a-07-imap-empty-state.png",
            "ss-a-08": "ss-a-08-imap-standard-form.png",
            "ss-a-09": "ss-a-09-imap-m365-form.png",
            "ss-a-10": "ss-a-10-imap-test-connection.png",
        }
        dest = self.out / name_map.get(shot_id.lower(), filename)
        if selector:
            page.locator(selector).screenshot(path=str(dest))
        elif clip:
            page.screenshot(path=str(dest), clip=clip)
        else:
            page.screenshot(path=str(dest))
        print(f"  ✓ {shot_id} → {dest.name}")
        self._results[shot_id] = "ok"

    def _should_run(self, shot_id: str) -> bool:
        if self.only:
            return shot_id.upper() == self.only.upper()
        return True

    # ── Individual screenshot functions ───────────────────────────────────

    def _ss_u_01(self, ctx: BrowserContext) -> None:
        """Login page — unauthenticated."""
        page = ctx.new_page()
        self._nav(page, "/login")
        self._shot(page, "SS-U-01")
        page.close()

    def _ss_u_02(self, ctx: BrowserContext) -> None:
        """MFA code entry screen — pause before entering code."""
        page = ctx.new_page()
        page.goto(f"{self.base_url}/login")
        page.wait_for_load_state("networkidle")
        page.fill("input[type=email]", self.state["mfa_test_email"])
        page.fill("input[type=password]", self.state["mfa_test_password"])
        page.click("button[type=submit]")
        # Wait for MFA input to appear, then screenshot BEFORE filling
        page.wait_for_selector("input[inputmode=numeric]", timeout=8000)
        page.wait_for_load_state("networkidle")
        self._shot(page, "SS-U-02")
        page.close()

    def _ss_u_03(self, page: Page) -> None:
        """Dashboard overview — full page."""
        self._nav(page, "/dashboard")
        self._shot(page, "SS-U-03")

    def _ss_u_04(self, page: Page) -> None:
        """Stat cards — cropped to the four-card row."""
        self._nav(page, "/dashboard")
        self._shot(page, "SS-U-04", selector="div.grid.gap-4")

    def _ss_u_05(self, page: Page) -> None:
        """World map with tooltip — hover over a country with data."""
        self._nav(page, "/dashboard")
        # Scroll the map into view
        map_el = page.locator("div.relative.overflow-hidden.rounded-md")
        map_el.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        # Hover over a filled country (blue fill — data present)
        # Try to find a coloured SVG path; fall back to a fixed geographic coordinate
        try:
            # Countries with data have a non-muted fill — target any blue hsl path
            colored = page.locator("svg path").filter(
                has_not=page.locator("[fill*='hsl(var(--muted))']")
            ).first
            colored.hover(timeout=3000)
        except Exception:
            # Fallback: hover over approximate US position in the map viewport
            box = map_el.bounding_box()
            if box:
                page.mouse.move(box["x"] + box["width"] * 0.22,
                                box["y"] + box["height"] * 0.45)
        page.wait_for_timeout(400)   # let tooltip render
        self._shot(page, "SS-U-05")

    def _ss_u_06(self, page: Page) -> None:
        """Reports list."""
        self._nav(page, "/reports")
        self._shot(page, "SS-U-06")

    def _ss_u_07_08_09(self, page: Page) -> None:
        """Report detail, records table, expanded record."""
        self._nav(page, "/reports")
        # Click the first report row
        page.locator("table tbody tr").first.click()
        page.wait_for_load_state("networkidle")
        self._shot(page, "SS-U-07")
        # Records table close-up
        self._shot(page, "SS-U-08", selector="table")
        # Expand the first record row
        page.locator("table tbody tr").first.click()
        page.wait_for_timeout(300)
        self._shot(page, "SS-U-09")

    def _ss_u_10_11(self, page: Page) -> None:
        """Flags list and flag type tooltip."""
        self._nav(page, "/flags")
        # Turn off 'Open only' to ensure flags are visible
        open_btn = page.locator("button", has_text="Open only")
        if open_btn.get_attribute("class") and "bg-primary" in (open_btn.get_attribute("class") or ""):
            open_btn.click()
            page.wait_for_timeout(300)
        self._shot(page, "SS-U-10")
        # Hover over first dotted-underline flag type span for tooltip
        tooltip_trigger = page.locator("span.decoration-dotted").first
        tooltip_trigger.scroll_into_view_if_needed()
        tooltip_trigger.hover()
        page.wait_for_timeout(400)
        self._shot(page, "SS-U-11")

    def _ss_u_12(self, page: Page) -> None:
        """Analytics page — top IPs table."""
        self._nav(page, "/analytics")
        self._shot(page, "SS-U-12")

    def _ss_u_13(self, page: Page) -> None:
        """User menu open."""
        self._nav(page, "/dashboard")
        # Click the user menu button in the header
        page.locator("header button", has_text="@").click()
        page.wait_for_timeout(300)
        self._shot(page, "SS-U-13")

    def _ss_u_14(self, page: Page) -> None:
        """Change password page."""
        self._nav(page, "/change-password")
        self._shot(page, "SS-U-14")

    def _ss_u_15(self, page: Page) -> None:
        """MFA setup page — QR code visible (viewer has no MFA)."""
        self._nav(page, "/mfa-setup")
        # Wait for the QR code image to load
        page.wait_for_selector("img[alt*='QR']", timeout=8000)
        self._shot(page, "SS-U-15")

    def _ss_u_16(self, ctx: BrowserContext) -> None:
        """MFA disable page — mfa-test account (MFA is enabled)."""
        page = ctx.new_page()
        self._login(page, self.state["mfa_test_email"], self.state["mfa_test_password"],
                    mfa_secret=self.state["mfa_test_secret"])
        self._set_client(page, self.state["client_slug"])
        self._nav(page, "/mfa-setup")
        # mfa-test has MFA enabled so /mfa-setup shows the Disable view
        self._shot(page, "SS-U-16")
        page.close()

    # ── Admin screenshots ─────────────────────────────────────────────────

    def _expand_client(self, page: Page, slug: str) -> None:
        """Expand a client card by clicking its header row (which is a div, not a button)."""
        # The slug is in a <p class="...font-mono"> inside the clickable header div
        page.locator(f"p.font-mono", has_text=slug).first.click()
        page.wait_for_timeout(500)

    def _ss_a_01(self, page: Page) -> None:
        """Flags list — acknowledge button visible (admin session)."""
        self._nav(page, "/flags")
        # Show all flags (acknowledged + open) so both states are visible
        open_btn = page.locator("button", has_text="Open only")
        cls = open_btn.get_attribute("class") or ""
        if "bg-primary" in cls:
            open_btn.click()
            page.wait_for_timeout(300)
        self._shot(page, "SS-A-01")

    def _ss_a_02(self, page: Page) -> None:
        """Users list."""
        self._nav(page, "/users")
        self._shot(page, "SS-A-02")

    def _ss_a_03(self, page: Page) -> None:
        """Create user form — open and partially filled."""
        self._nav(page, "/users")
        # The button is labelled "New User" (Plus icon + text)
        page.locator("button", has_text="New User").click()
        page.wait_for_selector("text=Create User", timeout=4000)
        page.wait_for_timeout(200)
        # Fill in sample data without submitting
        page.locator("input[type=email]").fill("newuser@example.com")
        self._shot(page, "SS-A-03")

    def _ss_a_04(self, page: Page) -> None:
        """Reset password dialog — opened via the key icon on a user row."""
        self._nav(page, "/users")
        # The reset button is an icon-only button with title="Reset password"
        page.locator("button[title='Reset password']").first.click()
        page.wait_for_selector("text=Reset Password —", timeout=4000)
        page.wait_for_timeout(200)
        self._shot(page, "SS-A-04")

    def _ss_a_05(self, page: Page) -> None:
        """Clients card expanded — shows domains tab."""
        self._nav(page, "/clients")
        self._expand_client(page, self.state["client_slug"])
        self._shot(page, "SS-A-05")

    def _ss_a_06(self, page: Page) -> None:
        """Add domain input — domain input field and Add Domain button visible."""
        self._nav(page, "/clients")
        self._expand_client(page, self.state["client_slug"])
        # Domains tab is the default; fill the input for a better screenshot
        page.locator("input[placeholder='example.com']").fill("mail.example.com")
        self._shot(page, "SS-A-06")

    def _open_imap_tab(self, page: Page, slug: str) -> None:
        """Expand a client card and switch to the Mail Ingestion tab."""
        self._expand_client(page, slug)
        page.locator("button", has_text="Mail Ingestion").click()
        page.wait_for_timeout(500)

    def _ss_a_07(self, page: Page) -> None:
        """IMAP tab — empty state showing 'Configure Mail Ingestion' button."""
        self._nav(page, "/clients")
        # Use the secondary client (globex-test) — less likely to have IMAP configured
        secondary = "globex-test"
        self._open_imap_tab(page, secondary)
        # If already configured, show the summary; either state is acceptable
        self._shot(page, "SS-A-07")

    def _ss_a_08(self, page: Page) -> None:
        """Standard IMAP form — click Configure, fill example values."""
        self._nav(page, "/clients")
        self._open_imap_tab(page, "globex-test")
        # Click 'Configure Mail Ingestion' if in empty state
        configure_btn = page.locator("button", has_text="Configure Mail Ingestion")
        if configure_btn.count() > 0:
            configure_btn.click()
            page.wait_for_timeout(300)
        # If in edit mode for existing config, 'Standard IMAP' button is already visible
        # Ensure Standard IMAP tab is selected (it's the default)
        std_btn = page.locator("button", has_text="Standard IMAP")
        if std_btn.count() > 0:
            std_btn.click()
            page.wait_for_timeout(200)
        # Fill example values — placeholders match the actual component strings
        page.locator("input[placeholder='imap.gmail.com']").fill("imap.gmail.com")
        page.locator("input[placeholder='user@example.com']").fill("dmarc@example.com")
        page.locator("input[type='password']").first.fill("app-password-example")
        self._shot(page, "SS-A-08")

    def _ss_a_09(self, page: Page) -> None:
        """Microsoft 365 IMAP form."""
        self._nav(page, "/clients")
        self._open_imap_tab(page, "globex-test")
        configure_btn = page.locator("button", has_text="Configure Mail Ingestion")
        if configure_btn.count() > 0:
            configure_btn.click()
            page.wait_for_timeout(300)
        # Switch to Microsoft 365 (OAuth2) auth type
        page.locator("button", has_text="Microsoft 365 (OAuth2)").click()
        page.wait_for_timeout(300)
        self._shot(page, "SS-A-09")

    def _ss_a_10(self, page: Page) -> None:
        """IMAP test connection result — save a config then click Test Connection."""
        self._nav(page, "/clients")
        self._open_imap_tab(page, "globex-test")

        # If no config exists yet, create one so the Test Connection button appears
        configure_btn = page.locator("button", has_text="Configure Mail Ingestion")
        if configure_btn.count() > 0:
            configure_btn.click()
            page.wait_for_timeout(300)
            # Standard IMAP is default; fill minimum required fields
            page.locator("input[placeholder='imap.gmail.com']").fill("imap.gmail.com")
            page.locator("input[placeholder='user@example.com']").fill("dmarc-screenshots@example.com")
            page.locator("input[type='password']").first.fill("placeholder-password")
            page.locator("button", has_text="Save").click()
            page.wait_for_timeout(1000)

        # Test Connection button is now in the summary view
        page.locator("button", has_text="Test Connection").click()
        page.wait_for_timeout(4000)   # wait for connection attempt (will fail — no real server)
        self._shot(page, "SS-A-10")

    # ── Orchestration ──────────────────────────────────────────────────────

    def run_all(self, pw: Playwright) -> None:
        slug = self.state["client_slug"]

        # ── Unauthenticated screenshots ───────────────────────────────────
        print("\n[Unauthenticated]")
        with self._new_context(pw) as ctx:
            if self._should_run("SS-U-01"):
                self._ss_u_01(ctx)

        # ── MFA mid-login (dedicated context per shot) ────────────────────
        print("\n[MFA mid-login]")
        if self._should_run("SS-U-02"):
            with self._new_context(pw) as ctx:
                self._ss_u_02(ctx)

        # ── Viewer session ─────────────────────────────────────────────────
        viewer_ids = {"SS-U-03", "SS-U-04", "SS-U-05", "SS-U-06", "SS-U-07",
                      "SS-U-08", "SS-U-09", "SS-U-10", "SS-U-11", "SS-U-12",
                      "SS-U-13", "SS-U-14", "SS-U-15"}
        if not self.only or self.only.upper() in viewer_ids:
            print("\n[Viewer session]")
            with self._new_context(pw) as ctx:
                page = ctx.new_page()
                self._login(page, self.state["viewer_email"], self.state["viewer_password"])
                self._set_client(page, slug)

                if self._should_run("SS-U-03"): self._ss_u_03(page)
                if self._should_run("SS-U-04"): self._ss_u_04(page)
                if self._should_run("SS-U-05"): self._ss_u_05(page)
                if self._should_run("SS-U-06"): self._ss_u_06(page)

                if any(self._should_run(i) for i in ("SS-U-07", "SS-U-08", "SS-U-09")):
                    self._ss_u_07_08_09(page)

                if any(self._should_run(i) for i in ("SS-U-10", "SS-U-11")):
                    self._ss_u_10_11(page)

                if self._should_run("SS-U-12"): self._ss_u_12(page)
                if self._should_run("SS-U-13"): self._ss_u_13(page)
                if self._should_run("SS-U-14"): self._ss_u_14(page)
                if self._should_run("SS-U-15"): self._ss_u_15(page)
                page.close()

        # ── MFA disable page (mfa-test account, MFA on) ───────────────────
        print("\n[MFA-test session — disable page]")
        if self._should_run("SS-U-16"):
            with self._new_context(pw) as ctx:
                self._ss_u_16(ctx)

        # ── Admin (super_admin) session ────────────────────────────────────
        admin_ids = {"SS-A-01", "SS-A-02", "SS-A-03", "SS-A-04", "SS-A-05",
                     "SS-A-06", "SS-A-07", "SS-A-08", "SS-A-09", "SS-A-10"}
        if not self.only or self.only.upper() in admin_ids:
            print("\n[Admin session]")
            with self._new_context(pw) as ctx:
                page = ctx.new_page()
                self._login(page, self.state["admin_email"], self.state["admin_password"])
                self._set_client(page, slug)

                if self._should_run("SS-A-01"): self._ss_a_01(page)
                if self._should_run("SS-A-02"): self._ss_a_02(page)
                if self._should_run("SS-A-03"): self._ss_a_03(page)
                if self._should_run("SS-A-04"): self._ss_a_04(page)
                if self._should_run("SS-A-05"): self._ss_a_05(page)
                if self._should_run("SS-A-06"): self._ss_a_06(page)
                if self._should_run("SS-A-07"): self._ss_a_07(page)
                if self._should_run("SS-A-08"): self._ss_a_08(page)
                if self._should_run("SS-A-09"): self._ss_a_09(page)
                if self._should_run("SS-A-10"): self._ss_a_10(page)
                page.close()

    def print_summary(self) -> None:
        print("\n── Summary ──")
        ok = [k for k, v in self._results.items() if v == "ok"]
        errors = {k: v for k, v in self._results.items() if v.startswith("error")}
        print(f"  Captured: {len(ok)}/26")
        if errors:
            print("  Errors:")
            for k, v in errors.items():
                print(f"    {k}: {v}")
        print(f"\n  Output: {self.out.resolve()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:5010")
    parser.add_argument("--output-dir", default="docs/images")
    parser.add_argument("--state-file", default="scripts/.screenshot_state.json")
    parser.add_argument("--only", metavar="ID",
                        help="Capture a single screenshot by ID (e.g. SS-U-03)")
    parser.add_argument("--headed", action="store_true",
                        help="Show the browser window")
    parser.add_argument("--slow-mo", type=int, default=0,
                        help="Slow down interactions by N ms (useful with --headed)")
    args = parser.parse_args()

    state_file = Path(args.state_file)
    if not state_file.exists():
        print(f"ERROR: State file not found: {state_file}")
        print("Run first: python scripts/screenshot_accounts.py")
        sys.exit(1)

    state = json.loads(state_file.read_text())

    capturer = Capturer(
        base_url=args.base_url,
        output_dir=Path(args.output_dir),
        state=state,
        headed=args.headed,
        slow_mo=args.slow_mo,
        only=args.only,
    )

    print(f"\n── DMARC Screenshot Capture ──")
    print(f"  URL:    {args.base_url}")
    print(f"  Client: {state.get('client_slug')}")
    print(f"  Output: {Path(args.output_dir).resolve()}")
    if args.only:
        print(f"  Only:   {args.only}")

    with sync_playwright() as pw:
        capturer.run_all(pw)

    capturer.print_summary()


if __name__ == "__main__":
    main()