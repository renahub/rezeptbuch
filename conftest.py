import os
import pytest


@pytest.fixture(autouse=True)
def _media_root_tmp(tmp_path, settings):
    """Lege MEDIA_ROOT pro Test in ein temporäres Verzeichnis, damit hochgeladene
    Testbilder die echten Mediendaten nicht überschreiben."""
    settings.MEDIA_ROOT = str(tmp_path / "media")
    os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
    yield
