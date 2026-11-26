import pytest


@pytest.fixture(autouse=True)
def plain_static_storage(settings):
    """Tests must not depend on collectstatic having been run.

    The manifest storage fails on {% static %} (admin pages) when the
    manifest file is missing, e.g. in a fresh clone or in CI.
    """
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
