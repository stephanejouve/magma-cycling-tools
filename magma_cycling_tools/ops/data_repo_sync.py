#!/usr/bin/env python3
"""Auto-commit and push changes in the training data repo.

Designed to run as a cron job in the Docker container (supercronic).
Commits any pending changes and pushes to origin/main.

Usage:
    poetry run data-repo-sync           # Commit + push if changes
    poetry run data-repo-sync --dry-run # Show what would be committed
"""

import logging
import os
import socket
import subprocess
import sys
from datetime import datetime

logger = logging.getLogger("data-repo-sync")

ALERT_ROOM = "infra-alerts"


def _alert_talk(stage: str, detail: str, repo_path: str) -> None:
    """Send a best-effort Talk alert on sync failure.

    Non-blocking: any exception during the alert is swallowed and logged.
    Runtime environments without the Talk stack (minimal containers) will
    fall through the ImportError branch — the failure is still logged at
    ERROR level by the caller, the alert is just a bonus channel.
    """
    try:
        from outillages.nextcloud_talk import send_message
    except ImportError:
        logger.info("Talk alerting unavailable (nextcloud_talk module not installed)")
        return

    host = socket.gethostname()
    detail_short = detail[:500] if detail else "(no stderr)"
    message = (
        f"🚨 data-repo-sync {stage} failed\n"
        f"host: {host}\n"
        f"repo: {repo_path}\n"
        f"detail: {detail_short}"
    )
    try:
        send_message(message, ALERT_ROOM)
    except Exception as exc:
        logger.warning("Talk alert send failed: %s", exc)


def run_git(args: list[str], repo_path: str) -> subprocess.CompletedProcess:
    """Run a git command in the data repo."""
    cmd = ["git", "-C", repo_path] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def ensure_safe_directory(repo_path: str) -> None:
    """Add repo to git safe.directory if not already configured."""
    result = subprocess.run(
        ["git", "config", "--global", "--get-all", "safe.directory"],
        capture_output=True,
        text=True,
    )
    if repo_path not in result.stdout.splitlines():
        subprocess.run(
            ["git", "config", "--global", "--add", "safe.directory", repo_path],
            check=True,
        )
        logger.info("Added %s to safe.directory", repo_path)


def sync_data_repo(repo_path: str, dry_run: bool = False) -> bool:
    """Commit and push pending changes in the data repo.

    Returns True if changes were pushed, False if nothing to do.
    """
    ensure_safe_directory(repo_path)

    # Check for changes
    status = run_git(["status", "--porcelain"], repo_path)
    if status.returncode != 0:
        logger.error("git status failed: %s", status.stderr.strip())
        return False

    changed_files = [line for line in status.stdout.strip().splitlines() if line.strip()]
    if not changed_files:
        logger.info("No changes to commit")
        return False

    n_files = len(changed_files)
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    commit_msg = f"auto: sync {date_str} ({n_files} files changed)"

    logger.info("Found %d changed files", n_files)
    for line in changed_files:
        logger.info("  %s", line.strip())

    if dry_run:
        logger.info("[DRY RUN] Would commit: %s", commit_msg)
        return False

    # Stage all changes
    result = run_git(["add", "-A"], repo_path)
    if result.returncode != 0:
        logger.error("git add failed: %s", result.stderr.strip())
        return False

    # Commit
    result = run_git(["commit", "-m", commit_msg], repo_path)
    if result.returncode != 0:
        logger.error("git commit failed: %s", result.stderr.strip())
        return False
    logger.info("Committed: %s", commit_msg)

    # Rebase local commits on top of origin/main before push.
    # Prevents silent push rejections when origin has advanced
    # (incident cf. docs/architecture/training-logs-sync.md Section 1).
    result = run_git(["fetch", "origin", "main"], repo_path)
    if result.returncode != 0:
        logger.error("git fetch failed: %s", result.stderr.strip())
        _alert_talk("fetch", result.stderr.strip(), repo_path)
        return False

    result = run_git(["pull", "--rebase", "origin", "main"], repo_path)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        logger.error("git pull --rebase failed: %s", stderr)
        abort = run_git(["rebase", "--abort"], repo_path)
        if abort.returncode != 0:
            logger.error(
                "git rebase --abort also failed: %s — manual cleanup required",
                abort.stderr.strip(),
            )
        _alert_talk("rebase", stderr, repo_path)
        return False
    logger.info("Rebased on origin/main")

    # Push
    result = run_git(["push", "origin", "main"], repo_path)
    if result.returncode != 0:
        logger.error("git push failed: %s", result.stderr.strip())
        _alert_talk("push", result.stderr.strip(), repo_path)
        return False
    logger.info("Pushed to origin/main")

    return True


def main():
    """Entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    dry_run = "--dry-run" in sys.argv

    repo_path = os.environ.get("TRAINING_DATA_REPO") or os.environ.get("TRAINING_LOGS_PATH")
    if not repo_path:
        logger.error("TRAINING_DATA_REPO or TRAINING_LOGS_PATH must be set")
        sys.exit(1)

    if not os.path.isdir(repo_path):
        logger.error("Data repo not found: %s", repo_path)
        sys.exit(1)

    try:
        sync_data_repo(repo_path, dry_run=dry_run)
    except Exception:
        logger.exception("data-repo-sync failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
