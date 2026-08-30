"""Unit tests for `accounts/templatetags/form_widgets.py`.

New branching Python logic (default vs. argument class, errors vs. no errors) — not a
styling change — so `pyproject.toml`'s `branch = true` coverage setting means both
branches must be exercised here directly. Each assertion runs against a real
`BoundField` built from a minimal form, not a mock.
"""

from django import forms

from accounts.templatetags.form_widgets import bootstrap_label, bootstrap_widget


class _SampleForm(forms.Form):
    name = forms.CharField()
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))


def test_bootstrap_widget_applies_the_default_class() -> None:
    field = _SampleForm()["name"]

    rendered = bootstrap_widget(field)

    assert 'class="form-control"' in rendered
    assert "is-invalid" not in rendered


def test_bootstrap_widget_applies_an_argument_override() -> None:
    field = _SampleForm()["name"]

    rendered = bootstrap_widget(field, "custom-class")

    assert 'class="custom-class"' in rendered
    assert "form-control" not in rendered


def test_bootstrap_widget_appends_is_invalid_only_when_the_field_has_errors() -> None:
    valid_form = _SampleForm(data={"name": "Alps Loop", "date": "2026-06-01"})
    valid_form.is_valid()
    invalid_form = _SampleForm(data={"name": "", "date": "2026-06-01"})
    invalid_form.is_valid()

    valid_rendered = bootstrap_widget(valid_form["name"])
    invalid_rendered = bootstrap_widget(invalid_form["name"])

    assert "is-invalid" not in valid_rendered
    assert "is-invalid" in invalid_rendered


def test_bootstrap_widget_preserves_existing_widget_attrs() -> None:
    field = _SampleForm()["date"]

    rendered = bootstrap_widget(field)

    assert 'type="date"' in rendered
    assert 'class="form-control"' in rendered


def test_bootstrap_label_adds_the_form_label_class() -> None:
    field = _SampleForm()["name"]

    rendered = bootstrap_label(field)

    assert 'class="form-label"' in rendered
    assert rendered.strip().endswith(":</label>") or rendered.strip().endswith("</label>")
