"""Tests for data_repo_sync pull-rebase-push flow."""

from unittest.mock import MagicMock, patch

from magma_cycling_tools.ops import data_repo_sync


def _result(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    r = MagicMock()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


class TestSyncDataRepo:
    """Tests for sync_data_repo() pull-rebase-push sequence."""

    @patch("magma_cycling_tools.ops.data_repo_sync.ensure_safe_directory")
    @patch("magma_cycling_tools.ops.data_repo_sync.run_git")
    def test_no_changes_returns_false(self, mock_run_git, _mock_safe):
        mock_run_git.return_value = _result(0, stdout="")
        assert data_repo_sync.sync_data_repo("/repo") is False
        args_list = [c.args[0] for c in mock_run_git.call_args_list]
        assert args_list == [["status", "--porcelain"]]

    @patch("magma_cycling_tools.ops.data_repo_sync.ensure_safe_directory")
    @patch("magma_cycling_tools.ops.data_repo_sync.run_git")
    def test_happy_path_runs_pull_rebase_before_push(self, mock_run_git, _mock_safe):
        mock_run_git.side_effect = [
            _result(0, stdout=" M file.txt\n"),  # status
            _result(0),  # add
            _result(0),  # commit
            _result(0),  # fetch
            _result(0),  # pull --rebase
            _result(0),  # push
        ]
        assert data_repo_sync.sync_data_repo("/repo") is True
        commands = [c.args[0] for c in mock_run_git.call_args_list]
        assert commands[0] == ["status", "--porcelain"]
        assert commands[1] == ["add", "-A"]
        assert commands[2][0] == "commit"
        assert commands[3] == ["fetch", "origin", "main"]
        assert commands[4] == ["pull", "--rebase", "origin", "main"]
        assert commands[5] == ["push", "origin", "main"]

    @patch("magma_cycling_tools.ops.data_repo_sync._alert_talk")
    @patch("magma_cycling_tools.ops.data_repo_sync.ensure_safe_directory")
    @patch("magma_cycling_tools.ops.data_repo_sync.run_git")
    def test_rebase_conflict_aborts_and_returns_false(self, mock_run_git, _mock_safe, mock_alert):
        mock_run_git.side_effect = [
            _result(0, stdout=" M file.txt\n"),  # status
            _result(0),  # add
            _result(0),  # commit
            _result(0),  # fetch
            _result(1, stderr="CONFLICT (content): Merge conflict in file.txt"),  # pull --rebase
            _result(0),  # rebase --abort
        ]
        assert data_repo_sync.sync_data_repo("/repo") is False
        commands = [c.args[0] for c in mock_run_git.call_args_list]
        assert commands[-1] == ["rebase", "--abort"]
        # push must not have been called after a failed rebase
        assert not any(cmd[0] == "push" for cmd in commands)
        mock_alert.assert_called_once()
        assert mock_alert.call_args.args[0] == "rebase"

    @patch("magma_cycling_tools.ops.data_repo_sync._alert_talk")
    @patch("magma_cycling_tools.ops.data_repo_sync.ensure_safe_directory")
    @patch("magma_cycling_tools.ops.data_repo_sync.run_git")
    def test_fetch_failure_returns_false_without_rebase(self, mock_run_git, _mock_safe, mock_alert):
        mock_run_git.side_effect = [
            _result(0, stdout=" M file.txt\n"),  # status
            _result(0),  # add
            _result(0),  # commit
            _result(1, stderr="Could not resolve host: github.com"),  # fetch
        ]
        assert data_repo_sync.sync_data_repo("/repo") is False
        commands = [c.args[0] for c in mock_run_git.call_args_list]
        assert not any(cmd[:2] == ["pull", "--rebase"] for cmd in commands)
        assert not any(cmd[0] == "push" for cmd in commands)
        mock_alert.assert_called_once()
        assert mock_alert.call_args.args[0] == "fetch"

    @patch("magma_cycling_tools.ops.data_repo_sync._alert_talk")
    @patch("magma_cycling_tools.ops.data_repo_sync.ensure_safe_directory")
    @patch("magma_cycling_tools.ops.data_repo_sync.run_git")
    def test_push_failure_triggers_alert(self, mock_run_git, _mock_safe, mock_alert):
        mock_run_git.side_effect = [
            _result(0, stdout=" M file.txt\n"),  # status
            _result(0),  # add
            _result(0),  # commit
            _result(0),  # fetch
            _result(0),  # pull --rebase
            _result(1, stderr="! [remote rejected] main -> main (protected branch hook declined)"),
        ]
        assert data_repo_sync.sync_data_repo("/repo") is False
        mock_alert.assert_called_once()
        assert mock_alert.call_args.args[0] == "push"

    @patch("magma_cycling_tools.ops.data_repo_sync._alert_talk")
    @patch("magma_cycling_tools.ops.data_repo_sync.ensure_safe_directory")
    @patch("magma_cycling_tools.ops.data_repo_sync.run_git")
    def test_happy_path_does_not_alert(self, mock_run_git, _mock_safe, mock_alert):
        mock_run_git.side_effect = [
            _result(0, stdout=" M file.txt\n"),  # status
            _result(0),  # add
            _result(0),  # commit
            _result(0),  # fetch
            _result(0),  # pull --rebase
            _result(0),  # push
        ]
        assert data_repo_sync.sync_data_repo("/repo") is True
        mock_alert.assert_not_called()

    @patch("magma_cycling_tools.ops.data_repo_sync.send_message", create=True)
    def test_alert_talk_swallows_import_error(self, _mock_send, caplog=None):
        """Alert path must never raise, even when the Talk stack is absent."""
        import builtins

        real_import = builtins.__import__

        def block_talk_import(name, *args, **kwargs):
            if name == "outillages.nextcloud_talk":
                raise ImportError("simulated: nextcloud_talk not installed")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=block_talk_import):
            data_repo_sync._alert_talk("fetch", "boom", "/repo")

    @patch("magma_cycling_tools.ops.data_repo_sync.ensure_safe_directory")
    @patch("magma_cycling_tools.ops.data_repo_sync.run_git")
    def test_dry_run_does_not_touch_git_write_ops(self, mock_run_git, _mock_safe):
        mock_run_git.return_value = _result(0, stdout=" M file.txt\n")
        assert data_repo_sync.sync_data_repo("/repo", dry_run=True) is False
        commands = [c.args[0] for c in mock_run_git.call_args_list]
        assert commands == [["status", "--porcelain"]]
