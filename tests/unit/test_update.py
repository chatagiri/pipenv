"""Unit tests for pipenv.routines.update helpers."""
from unittest.mock import MagicMock

from pipenv.routines.update import _clean_unused_dependencies


def _make_project(verbose=False):
    """Return a minimal project mock."""
    project = MagicMock()
    project.s.is_verbose.return_value = verbose
    return project


# ---------------------------------------------------------------------------
# _clean_unused_dependencies
# ---------------------------------------------------------------------------


def test_clean_unused_deps_removes_unused_package():
    """Packages absent from full_lock_resolution are removed from the lockfile."""
    project = _make_project()
    lockfile = {
        "default": {
            "django": {"version": "==4.2.7"},
            "sqlparse": {"version": "==0.4.4"},
            "pytz": {"version": "==2023.3"},  # no longer needed by django 4.2.7
        }
    }
    original_lockfile = {
        "default": {
            "django": {"version": "==3.2.10"},
            "sqlparse": {"version": "==0.4.4"},
            "pytz": {"version": "==2023.3"},
        }
    }
    full_lock_resolution = {
        "django": {"version": "==4.2.7"},
        "sqlparse": {"version": "==0.4.4"},
        # pytz is NOT here – it's no longer a transitive dep
    }

    _clean_unused_dependencies(
        project, lockfile, "default", full_lock_resolution, original_lockfile
    )

    assert "pytz" not in lockfile["default"]
    assert "django" in lockfile["default"]
    assert "sqlparse" in lockfile["default"]


def test_clean_unused_deps_keeps_packages_still_needed():
    """Packages present in full_lock_resolution are NOT removed."""
    project = _make_project()
    lockfile = {
        "default": {
            "requests": {"version": "==2.31.0"},
            "urllib3": {"version": "==2.0.0"},
        }
    }
    original_lockfile = {
        "default": {
            "requests": {"version": "==2.28.0"},
            "urllib3": {"version": "==1.26.0"},
        }
    }
    full_lock_resolution = {
        "requests": {"version": "==2.31.0"},
        "urllib3": {"version": "==2.0.0"},
    }

    _clean_unused_dependencies(
        project, lockfile, "default", full_lock_resolution, original_lockfile
    )

    assert "requests" in lockfile["default"]
    assert "urllib3" in lockfile["default"]


def test_clean_unused_deps_noop_when_category_missing_from_lockfile():
    """Returns immediately when category is not present in current lockfile."""
    project = _make_project()
    lockfile = {}  # no "default" key
    original_lockfile = {"default": {"pytz": {"version": "==2023.3"}}}
    full_lock_resolution = {}

    # Should not raise; lockfile is unchanged
    _clean_unused_dependencies(
        project, lockfile, "default", full_lock_resolution, original_lockfile
    )

    assert lockfile == {}


def test_clean_unused_deps_noop_when_category_missing_from_original():
    """Returns immediately when category is not present in original_lockfile."""
    project = _make_project()
    lockfile = {"default": {"django": {"version": "==4.2.7"}}}
    original_lockfile = {}  # no "default" key
    full_lock_resolution = {"django": {"version": "==4.2.7"}}

    _clean_unused_dependencies(
        project, lockfile, "default", full_lock_resolution, original_lockfile
    )

    # lockfile is unchanged
    assert "django" in lockfile["default"]


def test_clean_unused_deps_noop_when_full_resolution_is_empty():
    """Returns immediately when full_lock_resolution is empty (resolution failure guard).

    Without this guard an empty resolution would cause all packages to be
    incorrectly treated as unused and deleted.
    """
    project = _make_project()
    lockfile = {
        "default": {
            "django": {"version": "==4.2.7"},
            "sqlparse": {"version": "==0.4.4"},
        }
    }
    original_lockfile = {
        "default": {
            "django": {"version": "==3.2.10"},
            "sqlparse": {"version": "==0.4.4"},
        }
    }
    full_lock_resolution = {}  # empty – simulates a failed resolution

    _clean_unused_dependencies(
        project, lockfile, "default", full_lock_resolution, original_lockfile
    )

    # Nothing should have been removed
    assert "django" in lockfile["default"]
    assert "sqlparse" in lockfile["default"]


def test_clean_unused_deps_verbose_prints_removed_package(capsys):
    """In verbose mode a message is printed for each removed package."""
    project = _make_project(verbose=True)
    lockfile = {
        "default": {
            "pytz": {"version": "==2023.3"},
        }
    }
    original_lockfile = {
        "default": {
            "pytz": {"version": "==2023.3"},
        }
    }
    # Use a non-empty resolution to actually trigger a removal
    full_lock_resolution_with_removal = {"other-pkg": {"version": "==1.0"}}
    _clean_unused_dependencies(
        project,
        lockfile,
        "default",
        full_lock_resolution_with_removal,
        original_lockfile,
    )

    assert "pytz" not in lockfile["default"]
    # project.s.is_verbose() was called and err.print was invoked through the mock
    project.s.is_verbose.assert_called()


# ---------------------------------------------------------------------------
# _clean_unused_dependencies with upgrade_lock_data (issue #6573)
# ---------------------------------------------------------------------------


def test_clean_unused_deps_keeps_deps_when_no_upgrades():
    """Transitive dependencies must not be removed when no packages were
    actually upgraded.

    Regression test for https://github.com/pypa/pipenv/issues/6573
    When upgrade_lock_data is provided but no version changes occurred,
    the full_lock_resolution (based on latest versions) may not match
    the pinned lockfile state, so cleanup should be skipped entirely.
    """
    project = _make_project()
    # google-auth==2.43.0 requires cachetools and rsa, but latest
    # google-auth (2.49.1) does not.  google-auth was NOT upgraded.
    lockfile = {
        "default": {
            "google-auth": {"version": "==2.43.0"},
            "cachetools": {"version": "==6.2.2"},
            "rsa": {"version": "==4.9.1"},
        }
    }
    original_lockfile = {
        "default": {
            "google-auth": {"version": "==2.43.0"},
            "cachetools": {"version": "==6.2.2"},
            "rsa": {"version": "==4.9.1"},
        }
    }
    # full_lock_resolution from latest versions does NOT include
    # cachetools or rsa (latest google-auth dropped them)
    full_lock_resolution = {
        "google-auth": {"version": "==2.49.1"},
    }
    # Only timeout_decorator was "upgraded" but its version didn't change
    upgrade_lock_data = {"timeout-decorator": {"version": "==4.4.0"}}

    _clean_unused_dependencies(
        project, lockfile, "default", full_lock_resolution, original_lockfile,
        upgrade_lock_data,
    )

    # All packages should be retained
    assert "google-auth" in lockfile["default"]
    assert "cachetools" in lockfile["default"]
    assert "rsa" in lockfile["default"]


def test_clean_unused_deps_removes_when_upgrade_happened():
    """When packages ARE upgraded, unused dependencies should still be removed.

    Ensures the fix for #6573 doesn't prevent legitimate cleanup.
    """
    project = _make_project()
    # django upgraded from 3.2.10 -> 4.2.7, pytz no longer needed
    lockfile = {
        "default": {
            "django": {"version": "==4.2.7"},
            "sqlparse": {"version": "==0.4.4"},
            "pytz": {"version": "==2023.3"},
        }
    }
    original_lockfile = {
        "default": {
            "django": {"version": "==3.2.10"},
            "sqlparse": {"version": "==0.4.4"},
            "pytz": {"version": "==2023.3"},
        }
    }
    full_lock_resolution = {
        "django": {"version": "==4.2.7"},
        "sqlparse": {"version": "==0.4.4"},
    }
    # django was upgraded (version changed)
    upgrade_lock_data = {"django": {"version": "==4.2.7"}}

    _clean_unused_dependencies(
        project, lockfile, "default", full_lock_resolution, original_lockfile,
        upgrade_lock_data,
    )

    assert "pytz" not in lockfile["default"]
    assert "django" in lockfile["default"]
    assert "sqlparse" in lockfile["default"]
