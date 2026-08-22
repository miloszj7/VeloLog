from django.conf import settings


def test_settings_module_resolves() -> None:
    assert settings.ROOT_URLCONF == "velo_log.urls"
