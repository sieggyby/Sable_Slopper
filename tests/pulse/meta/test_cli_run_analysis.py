"""Regression test: _run_analysis() must pass org= to build_recommendations().

This test covers the exact CLI boundary that regressed: the live caller in
_run_analysis() was missing org=org in its build_recommendations() call, which
silently broke the fatigue penalty for every CLI invocation.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock


def test_run_analysis_passes_org_to_build_recommendations(tmp_path):
    """_run_analysis('testorg') must call build_recommendations(org='testorg')."""
    # Vault must exist so vault_available=True and the recommendations path is taken
    vault_path = tmp_path / "vault" / "testorg"
    vault_path.mkdir(parents=True)

    fake_tweet = {"text": "hello defi", "total_lift": 1.0, "format_bucket": "short_clip"}

    captured_kwargs: dict = {}

    def fake_build(**kwargs):
        captured_kwargs.update(kwargs)
        return {"post_now": [], "stop_doing": [], "gaps_to_fill": []}

    with (
        patch("sable.pulse.meta.db.migrate"),
        patch("sable.pulse.meta.db.get_recent_tweets", return_value=[fake_tweet]),
        patch("sable.pulse.meta.db.get_oldest_tweet_date", return_value=None),
        patch("sable.pulse.meta.db.get_prev_scan_topics", return_value={}),
        patch("sable.pulse.meta.db.get_scan_runs", return_value=[]),
        patch("sable.pulse.meta.db.insert_topic_signals"),
        patch("sable.config.load_config", return_value={}),
        patch("sable.shared.paths.vault_dir", return_value=vault_path),
        patch(
            "sable.pulse.meta.watchlist.list_watchlist",
            return_value=[{"handle": f"@user{i}"} for i in range(25)],
        ),
        patch("sable.pulse.meta.baselines.compute_baselines_from_db", return_value={}),
        patch("sable.pulse.meta.baselines._rows_to_normalized", return_value=[]),
        patch("sable.pulse.meta.trends.analyze_all_formats", return_value={}),
        patch("sable.pulse.meta.topics.aggregate_topic_signals", return_value=[]),
        patch("sable.pulse.meta.topics.load_vault_synonyms", return_value={}),
        patch("sable.pulse.meta.analyzer.fallback_analysis", return_value={}),
        patch(
            "sable.pulse.meta.recommender.build_recommendations",
            side_effect=fake_build,
        ),
        patch("sable.pulse.meta.reporter.render_report"),
        patch(
            "sable.pulse.meta.reporter.write_vault_report",
            return_value=tmp_path / "report.md",
        ),
        patch("sable.roster.manager.list_accounts", return_value=[]),
    ):
        from sable.pulse.meta.cli import _run_analysis

        _run_analysis("testorg", deep=False, cheap=True, trends_only=False, dry_run=False)

    assert captured_kwargs, (
        "build_recommendations() was never called — check that _run_analysis() reaches "
        "the recommendations block (vault must exist and watchlist must be non-empty)"
    )
    assert captured_kwargs.get("org") == "testorg", (
        f"build_recommendations() must receive org='testorg'; "
        f"actual call kwargs: {captured_kwargs}"
    )
