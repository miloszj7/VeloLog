from typing import TYPE_CHECKING, Any

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile

from gpx.constants import ALLOWED_GPX_EXTENSIONS, MAX_GPX_FILE_BYTES, MAX_GPX_FILE_MEGABYTES
from gpx.exceptions import GpxContentError, GpxSyntaxError
from gpx.models import GpxTrack
from gpx.parsing import parse_gpx_bytes

if TYPE_CHECKING:
    _GpxUploadFormBase = forms.ModelForm[GpxTrack]
else:
    _GpxUploadFormBase = forms.ModelForm


class GpxUploadForm(_GpxUploadFormBase):
    """Validates an uploaded GPX file and parses it once, where the user can still fix it."""

    class Meta:
        model = GpxTrack
        fields = ("file",)
        labels = {"file": "GPX file"}

    def clean_file(self) -> UploadedFile[Any]:
        """Enforce size, then extension, then parseability — cheapest rejection first.

        On success this also fills in the instance columns derived from the upload. They
        have no form field, so Django's own `construct_instance` never sets them; doing
        it here, with the parse result in hand, is what keeps the view from having to
        remember to copy them across, and keeps a route and the file that produced it
        from ever disagreeing.

        Returns:
            The uploaded file, rewound so the storage write persists all of it.

        Raises:
            ValidationError: The file is too large, is not a `.gpx`, or does not parse.
        """
        uploaded: UploadedFile[Any] = self.cleaned_data["file"]
        if uploaded.size is None or uploaded.size > MAX_GPX_FILE_BYTES:
            raise ValidationError(f"That file is larger than {MAX_GPX_FILE_MEGABYTES} MB.")
        filename = uploaded.name or ""
        if not filename.lower().endswith(ALLOWED_GPX_EXTENSIONS):
            raise ValidationError("That is not a .gpx file.")

        try:
            parsed = parse_gpx_bytes(uploaded.read())
        except GpxSyntaxError as e:
            # A file rejected for carrying a DOCTYPE lands here too. The message stays
            # about the file being unusable and does not explain the mitigation.
            raise ValidationError("That file could not be read as XML.") from e
        except GpxContentError as e:
            raise ValidationError("That file is not a usable GPX track.") from e
        finally:
            # Reading the upload to parse it left the cursor at EOF. Without this rewind
            # the storage write that follows persists zero bytes — a bug that passes a
            # status-code test and fails only a content test.
            uploaded.seek(0)

        self.instance.original_filename = filename
        self.instance.points = parsed.json_points()
        self.instance.min_latitude = parsed.min_latitude
        self.instance.min_longitude = parsed.min_longitude
        self.instance.max_latitude = parsed.max_latitude
        self.instance.max_longitude = parsed.max_longitude
        return uploaded
