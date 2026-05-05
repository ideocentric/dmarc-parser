"""
Unit tests for ingestion/scanner.py — ClamAV integration.

All tests mock the clamd library; no live ClamAV daemon is required.
"""
import importlib
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers — reset the lru_cache between tests so each test gets a fresh client
# ---------------------------------------------------------------------------

def _reload_scanner():
    """Force a fresh import of scanner so lru_cache state is clean."""
    import ingestion.scanner as mod
    importlib.reload(mod)
    return mod


# ---------------------------------------------------------------------------
# Disabled (default)
# ---------------------------------------------------------------------------

class TestScannerDisabled:
    def test_scan_bytes_noop_when_disabled(self, monkeypatch):
        mod = _reload_scanner()
        monkeypatch.setattr(mod.settings, "clamav_enabled", False)
        # No clamd import attempted, no exception raised
        mod.scan_bytes(b"anything", "report.xml.gz")

    def test_ping_returns_true_when_disabled(self, monkeypatch):
        mod = _reload_scanner()
        monkeypatch.setattr(mod.settings, "clamav_enabled", False)
        assert mod.ping() is True


# ---------------------------------------------------------------------------
# Enabled — clean file
# ---------------------------------------------------------------------------

class TestScannerClean:
    def test_clean_file_passes(self, monkeypatch):
        mod = _reload_scanner()
        monkeypatch.setattr(mod.settings, "clamav_enabled", True)
        monkeypatch.setattr(mod.settings, "clamav_host", "localhost")
        monkeypatch.setattr(mod.settings, "clamav_port", 3310)

        fake_clamd = MagicMock()
        fake_clamd.instream.return_value = {"stream": ("OK", None)}

        with patch.object(mod, "_get_clamd", return_value=fake_clamd):
            mod.scan_bytes(b"clean data", "clean.xml.gz")  # no exception


# ---------------------------------------------------------------------------
# Enabled — malware detected
# ---------------------------------------------------------------------------

class TestScannerInfected:
    def test_infected_file_raises(self, monkeypatch, caplog):
        mod = _reload_scanner()
        monkeypatch.setattr(mod.settings, "clamav_enabled", True)

        fake_clamd = MagicMock()
        fake_clamd.instream.return_value = {"stream": ("FOUND", "Eicar-Test-Signature")}

        with patch.object(mod, "_get_clamd", return_value=fake_clamd):
            with pytest.raises(ValueError, match="Malware detected"):
                mod.scan_bytes(b"X5O!P%@AP[4\\PZX54(P^)7CC)7}", "eicar.xml.gz")

        assert "[SECURITY]" in caplog.text
        assert "MALWARE DETECTED" in caplog.text
        assert "Eicar-Test-Signature" in caplog.text

    def test_error_status_raises(self, monkeypatch, caplog):
        mod = _reload_scanner()
        monkeypatch.setattr(mod.settings, "clamav_enabled", True)

        fake_clamd = MagicMock()
        fake_clamd.instream.return_value = {"stream": ("ERROR", "scan failed")}

        with patch.object(mod, "_get_clamd", return_value=fake_clamd):
            with pytest.raises(ValueError, match="ClamAV scan error"):
                mod.scan_bytes(b"data", "report.xml.gz")

        assert "[SECURITY]" in caplog.text


# ---------------------------------------------------------------------------
# Enabled — clamd unreachable, fail closed (default)
# ---------------------------------------------------------------------------

class TestScannerUnreachableFailClosed:
    def test_unreachable_fail_closed_raises(self, monkeypatch, caplog):
        mod = _reload_scanner()
        monkeypatch.setattr(mod.settings, "clamav_enabled", True)
        monkeypatch.setattr(mod.settings, "clamav_fail_open", False)

        fake_clamd = MagicMock()
        fake_clamd.instream.side_effect = ConnectionRefusedError("Connection refused")

        with patch.object(mod, "_get_clamd", return_value=fake_clamd):
            with pytest.raises(ValueError, match="CLAMAV_FAIL_OPEN=false"):
                mod.scan_bytes(b"data", "report.xml.gz")

        assert "[SECURITY]" in caplog.text
        assert "unavailable" in caplog.text.lower()

    def test_ping_returns_false_when_unreachable(self, monkeypatch):
        mod = _reload_scanner()
        monkeypatch.setattr(mod.settings, "clamav_enabled", True)

        fake_clamd = MagicMock()
        fake_clamd.ping.side_effect = ConnectionRefusedError("Connection refused")

        with patch.object(mod, "_get_clamd", return_value=fake_clamd):
            assert mod.ping() is False


# ---------------------------------------------------------------------------
# Enabled — clamd unreachable, fail open
# ---------------------------------------------------------------------------

class TestScannerUnreachableFailOpen:
    def test_unreachable_fail_open_allows(self, monkeypatch, caplog):
        mod = _reload_scanner()
        monkeypatch.setattr(mod.settings, "clamav_enabled", True)
        monkeypatch.setattr(mod.settings, "clamav_fail_open", True)

        fake_clamd = MagicMock()
        fake_clamd.instream.side_effect = ConnectionRefusedError("Connection refused")

        with patch.object(mod, "_get_clamd", return_value=fake_clamd):
            mod.scan_bytes(b"data", "report.xml.gz")  # no exception

        assert "[SECURITY]" in caplog.text
        assert "FAIL_OPEN=true" in caplog.text


# ---------------------------------------------------------------------------
# Enabled — python-clamd not installed
# ---------------------------------------------------------------------------

class TestScannerMissingPackage:
    def test_missing_package_raises_runtime_error(self, monkeypatch):
        mod = _reload_scanner()
        monkeypatch.setattr(mod.settings, "clamav_enabled", True)
        # Clear the lru_cache so _get_clamd runs fresh
        mod._get_clamd.cache_clear()

        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "clamd":
                raise ImportError("No module named 'clamd'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(RuntimeError, match="pip install python-clamd"):
                mod.scan_bytes(b"data", "report.xml.gz")