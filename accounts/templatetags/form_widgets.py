"""Bootstrap class injection for Django's default form widget rendering.

Django's `BoundField.__str__` (and bare `{{ field }}`) calls `as_widget()` with no
`attrs`, so a widget never carries a `class` attribute unless a template routes
through one of these filters instead. No `forms.py` in the project is touched — the
class is merged in here, template-side, for every form this project renders.
"""

from __future__ import annotations

from django import template
from django.forms import BoundField
from django.utils.safestring import SafeString

register = template.Library()


@register.filter(name="bootstrap_widget")
def bootstrap_widget(field: BoundField, css_class: str = "form-control") -> SafeString:
    """Render `field` with `css_class` merged into its widget's existing attrs.

    Routes through `as_widget(attrs=...)`, which merges the passed `class` with
    attrs already on the widget (e.g. `TripForm`'s `date` field's
    `attrs={"type": "date"}`) rather than replacing them, and still lets
    `build_widget_attrs` stamp `aria-describedby`/`aria-invalid` as it normally would.
    """
    classes = css_class
    if field.errors:
        classes = f"{classes} is-invalid"
    return field.as_widget(attrs={"class": classes})


@register.filter(name="bootstrap_label")
def bootstrap_label(field: BoundField) -> SafeString:
    """Render `field`'s label with Bootstrap's `form-label` class.

    Goes through `label_tag(attrs=...)` rather than hand-written `<label>` markup —
    templates cannot pass arguments to a bare `{{ field.label_tag }}` call, and a
    hand-written tag would drop `label_suffix` handling and `id_for_label`
    resolution.
    """
    return field.label_tag(attrs={"class": "form-label"})
