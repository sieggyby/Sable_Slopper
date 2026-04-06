"""Weekly automation runner — orchestrates the full weekly cycle for an org."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """Outcome of a single weekly step."""

    name: str
    status: str  # "ok" | "error" | "skipped"
    duration_s: float = 0.0
    cost_usd: float = 0.0
    error: str | None = None


class WeeklyRunner:
    """Run the full weekly cycle for a single org."""

    STEPS = [
        "pulse_track",
        "meta_scan",
        "advise",
        "calendar",
        "vault_sync",
    ]

    def __init__(self, org: str) -> None:
        self.org = org
        self._results: list[StepResult] = []

    def run(self) -> list[StepResult]:
        """Execute all weekly steps in sequence, continuing on failure."""
        self._results = []
        for step_name in self.STEPS:
            method = getattr(self, f"_step_{step_name}")
            t0 = time.monotonic()
            try:
                cost = method()
                elapsed = time.monotonic() - t0
                self._results.append(StepResult(
                    name=step_name, status="ok",
                    duration_s=elapsed, cost_usd=cost,
                ))
            except Exception as e:
                elapsed = time.monotonic() - t0
                logger.warning("Weekly step %s failed for org %s: %s",
                               step_name, self.org, e, exc_info=True)
                self._results.append(StepResult(
                    name=step_name, status="error",
                    duration_s=elapsed, error=str(e),
                ))
        return self._results

    def _get_accounts(self) -> list:
        from sable.roster.manager import list_accounts
        return list_accounts(org=self.org, active_only=True)

    def _get_spend_before(self) -> float:
        """Get current weekly spend for cost delta calculation."""
        try:
            from sable.platform.db import get_db
            from sable.platform.cost import get_weekly_spend
            conn = get_db()
            try:
                return get_weekly_spend(conn, self.org)
            finally:
                conn.close()
        except Exception:
            return 0.0

    def _step_pulse_track(self) -> float:
        """Run pulse track for all rostered accounts in the org."""
        from sable.pulse.tracker import snapshot_account

        spend_before = self._get_spend_before()
        accounts = self._get_accounts()
        if not accounts:
            logger.info("No active accounts for org %s — skipping pulse_track", self.org)
            return 0.0

        for acc in accounts:
            logger.info("pulse_track: %s", acc.handle)
            snapshot_account(acc.handle)

        return max(0.0, self._get_spend_before() - spend_before)

    def _step_meta_scan(self) -> float:
        """Run pulse meta scan for the org."""
        from sable.pulse.meta import db as meta_db
        from sable.pulse.meta.watchlist import list_watchlist
        from sable.pulse.meta.scanner import Scanner
        from sable import config as sable_cfg

        spend_before = self._get_spend_before()

        meta_db.migrate()
        watchlist = list_watchlist(self.org)
        if not watchlist:
            logger.info("No watchlist for org %s — skipping meta_scan", self.org)
            return 0.0

        meta_cfg = sable_cfg.load_config().get("pulse_meta", {})
        max_cost = meta_cfg.get("max_cost_per_run", 1.00)

        scanner = Scanner(
            org=self.org,
            watchlist=watchlist,
            db=meta_db,
            cfg_meta=meta_cfg,
            deep=False,
            full=False,
            dry_run=False,
            max_cost=max_cost,
        )

        scan_id = meta_db.create_scan_run(
            self.org, mode="incremental", watchlist_size=len(watchlist),
        )

        result = scanner.run(scan_id)

        meta_db.complete_scan_run(
            scan_id=scan_id,
            tweets_collected=result["tweets_collected"],
            tweets_new=result["tweets_new"],
            estimated_cost=result.get("estimated_cost", 0.0),
        )

        # Log SocialData cost to sable.db
        socialdata_cost = result.get("estimated_cost", 0.0)
        if socialdata_cost > 0:
            try:
                from sable.platform.db import get_db
                from sable.platform.cost import log_cost
                conn = get_db()
                try:
                    log_cost(conn, self.org, "socialdata_meta_scan", socialdata_cost,
                             model="socialdata", input_tokens=0, output_tokens=0)
                finally:
                    conn.close()
            except Exception:
                logger.warning("Failed to log SocialData cost", exc_info=True)

        return max(0.0, self._get_spend_before() - spend_before)

    def _step_advise(self) -> float:
        """Generate strategy briefs for all rostered accounts."""
        from sable.advise.generate import generate_advise

        spend_before = self._get_spend_before()
        accounts = self._get_accounts()
        if not accounts:
            logger.info("No active accounts for org %s — skipping advise", self.org)
            return 0.0

        for acc in accounts:
            logger.info("advise: %s", acc.handle)
            generate_advise(acc.handle, org=self.org)

        return max(0.0, self._get_spend_before() - spend_before)

    def _step_calendar(self) -> float:
        """Generate and save posting calendars for all rostered accounts."""
        from sable.calendar.planner import build_calendar, render_calendar
        from sable.shared.paths import pulse_db_path, meta_db_path, vault_dir, sable_home
        from sable.shared.handles import strip_handle

        spend_before = self._get_spend_before()
        accounts = self._get_accounts()
        if not accounts:
            logger.info("No active accounts for org %s — skipping calendar", self.org)
            return 0.0

        for acc in accounts:
            logger.info("calendar: %s", acc.handle)
            plan = build_calendar(
                handle=acc.handle,
                org=self.org,
                days=7,
                formats_target=4,
                pulse_db_path=pulse_db_path(),
                meta_db_path=meta_db_path(),
                vault_root=vault_dir(self.org),
            )
            output = render_calendar(plan)

            # Save to playbooks
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            playbooks_dir = sable_home() / "playbooks"
            playbooks_dir.mkdir(parents=True, exist_ok=True)
            filename = f"calendar_{strip_handle(acc.handle)}_{today}.md"
            save_path = playbooks_dir / filename
            save_path.write_text(output, encoding="utf-8")

        return max(0.0, self._get_spend_before() - spend_before)

    def _step_vault_sync(self) -> float:
        """Sync platform vault for the org."""
        from sable.vault.platform_sync import platform_vault_sync

        spend_before = self._get_spend_before()
        platform_vault_sync(self.org)
        return max(0.0, self._get_spend_before() - spend_before)


def format_summary(org: str, results: list[StepResult]) -> str:
    """Format a human-readable summary of the weekly cycle."""
    ok_count = sum(1 for r in results if r.status == "ok")
    total = len(results)
    total_cost = sum(r.cost_usd for r in results)
    total_duration = sum(r.duration_s for r in results)

    mins = int(total_duration) // 60
    secs = int(total_duration) % 60

    lines = [
        f"Weekly cycle complete for {org}: "
        f"{ok_count}/{total} steps succeeded, "
        f"total cost: ${total_cost:.2f}, "
        f"duration: {mins}m {secs}s",
    ]

    for r in results:
        if r.status == "error":
            lines.append(f"  FAILED: {r.name} — {r.error}")

    return "\n".join(lines)


def discover_orgs() -> list[str]:
    """Return sorted unique org slugs that have active rostered accounts."""
    from sable.roster.manager import list_accounts
    accounts = list_accounts(active_only=True)
    orgs = sorted({a.org for a in accounts if a.org})
    return orgs


def estimate_org_cost(org: str) -> float:
    """Estimate the cost of a full weekly cycle for an org (no API calls)."""
    from sable.roster.manager import list_accounts
    from sable.shared.pricing import compute_cost

    accounts = list_accounts(org=org, active_only=True)
    n = len(accounts)
    if n == 0:
        return 0.0

    # SocialData: pulse_track = $0.002/account, meta_scan ~$0.10 base
    socialdata = 0.002 * n + 0.10

    # Claude: advise ~2k input + 1.5k output per account (sonnet)
    advise_per = compute_cost(2000, 1500, "claude-sonnet-4-6")
    advise_total = advise_per * n

    # Claude: calendar ~1.5k input + 1k output per account (sonnet)
    calendar_per = compute_cost(1500, 1000, "claude-sonnet-4-6")
    calendar_total = calendar_per * n

    # vault_sync: $0 (no AI)
    return socialdata + advise_total + calendar_total
