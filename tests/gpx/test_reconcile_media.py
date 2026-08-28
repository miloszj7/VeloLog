"""`manage.py reconcile_media` — the set difference, both modes, and every guard on it.

`tests/conftest.py` points `MEDIA_ROOT` at `tmp_path` autouse, so each test gets its own
empty volume and nothing here needs `override_settings`.

The age guard is driven by back-dating with `os.utime` rather than by freezing the clock:
`Storage.get_modified_time` reads `os.path.getmtime`, so the mtime on disk is the only
input it has, and moving it is both the smallest lever and the most faithful one.
"""

import os
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from gpx.constants import ORPHAN_MIN_AGE_MINUTES
from gpx.management.commands.reconcile_media import _is_walkable_directory
from tests.conftest import StoredTrackFactory
from trips.models import Trip

AGES_AGO = timedelta(days=1)


def back_date(key: str, age: timedelta = AGES_AGO) -> None:
    """Move a file or directory's mtime into the past, past the default age threshold.

    Freshly written test data is younger than `ORPHAN_MIN_AGE_MINUTES` by construction, so
    without this every orphan the suite creates would be spared and every assertion about
    reclamation would pass while proving nothing.
    """
    target = Path(default_storage.path(key))
    stamp = (timezone.now() - age).timestamp()
    os.utime(target, (stamp, stamp))


def write_orphan(key: str, content: bytes = b"<gpx>stray</gpx>", *, aged: bool = True) -> str:
    """Write bytes straight to storage with no row pointing at them, and age them.

    `default_storage.save` may pick a suffixed name if the key is taken, so the name it
    returns is the one the caller must use — the same discipline `/healthz/` follows.
    """
    saved = default_storage.save(key, ContentFile(content))
    if aged:
        back_date(saved)
    return saved


@pytest.mark.django_db
def test_a_referenced_file_is_never_reported(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The whole command is a set difference; this is the half that must stay untouched."""
    track = make_stored_track(trip)
    name = track.file.name
    assert name is not None
    back_date(name)

    call_command("reconcile_media")

    captured = capsys.readouterr()
    assert name not in captured.err
    assert "Scanned 1, referenced 1, orphaned 0" in captured.out
    assert default_storage.exists(name)


@pytest.mark.django_db
def test_an_unreferenced_file_is_reported_and_left_alone_by_default(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Report-only is the default because `--delete` has no undo on a Volume.

    A referenced file sits alongside the orphan deliberately: it is what keeps the
    point-in-time-skew warning off this case, so the assertion is about the orphan report
    rather than about the refusal.
    """
    track = make_stored_track(trip)
    referenced = track.file.name
    assert referenced is not None
    back_date(referenced)
    orphan = write_orphan("gpx/1/1/stray.gpx")

    call_command("reconcile_media")

    captured = capsys.readouterr()
    assert f"Orphan {orphan}" in captured.err
    assert "Scanned 2, referenced 1, orphaned 1" in captured.out
    assert "Nothing was removed. This is a report;" in captured.out
    assert default_storage.exists(orphan)
    assert default_storage.exists(referenced)


@pytest.mark.django_db
def test_delete_reclaims_the_orphan_and_keeps_the_referenced_file(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    track = make_stored_track(trip)
    referenced = track.file.name
    assert referenced is not None
    back_date(referenced)
    orphan = write_orphan("gpx/1/1/stray.gpx")

    call_command("reconcile_media", "--delete")

    captured = capsys.readouterr()
    assert "reclaimed 1, skipped 0" in captured.out
    assert "Nothing was removed" not in captured.out
    assert not default_storage.exists(orphan)
    assert default_storage.exists(referenced)


@pytest.mark.django_db
def test_a_freshly_written_orphan_is_spared_until_the_threshold_is_lifted(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The age guard is the only thing separating an orphan from an in-flight write.

    `FileField.pre_save` commits the upload to storage before the INSERT it belongs to, so
    for the width of that window a perfectly ordinary upload looks exactly like an orphan.
    Both halves are asserted in one test on purpose: that the guard spares the file, *and*
    that `--min-age-minutes 0` is what makes the same file reportable — a guard that could
    not be lifted would be indistinguishable from one that never fired.
    """
    track = make_stored_track(trip)
    back_date(str(track.file.name))
    fresh = write_orphan("gpx/1/1/in-flight.gpx", aged=False)

    call_command("reconcile_media")
    spared_run = capsys.readouterr()
    assert f"Spared {fresh}" in spared_run.err
    assert f"in the last {ORPHAN_MIN_AGE_MINUTES} minute(s)" in spared_run.err
    assert "orphaned 0, spared 1" in spared_run.out

    call_command("reconcile_media", "--min-age-minutes", "0")
    lifted_run = capsys.readouterr()
    assert f"Orphan {fresh}" in lifted_run.err
    assert "orphaned 1, spared 0" in lifted_run.out


@pytest.mark.django_db
def test_a_negative_min_age_minutes_is_refused() -> None:
    """A negative cutoff lands in the future and would spare nothing at all.

    `timezone.now() - timedelta(minutes=-30)` is 30 minutes from now, so every file —
    including one a request is writing right now — would clear `modified > cutoff` and be
    treated as an orphan.
    """
    with pytest.raises(CommandError, match="must not be negative"):
        call_command("reconcile_media", "--min-age-minutes", "-30")


@pytest.mark.django_db
def test_a_freshly_written_orphan_spared_line_reports_its_size(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The spared-recent-file line should carry the size the orphan line already does."""
    back_date(str(make_stored_track(trip).file.name))
    content = b"<gpx>in-flight</gpx>"
    fresh = write_orphan("gpx/1/1/in-flight.gpx", content=content, aged=False)

    call_command("reconcile_media")

    captured = capsys.readouterr()
    assert (
        f"Spared {fresh}: modified in the last {ORPHAN_MIN_AGE_MINUTES} minute(s) "
        f"({len(content)} bytes)." in captured.err
    )


@pytest.mark.django_db
def test_an_orphan_outside_the_gpx_prefix_is_found(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The restore-nesting shape: a whole tree written where no upload would put it.

    A walk scoped to the `gpx/` prefix would miss the two highest-ranked sources in the
    frame by construction, which is why the scope is the whole of `MEDIA_ROOT`.
    """
    back_date(str(make_stored_track(trip).file.name))
    nested = write_orphan("restore-2026-08-01/gpx/1/1/old.gpx")

    call_command("reconcile_media")

    captured = capsys.readouterr()
    assert f"Orphan {nested}" in captured.err


@pytest.mark.django_db
def test_delete_prunes_an_emptied_directory_and_never_media_root(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """A reclaimed file leaves its directory behind; the prune is what finishes the job.

    Deepest-first is what makes it reach anything at all — `os.rmdir` refuses a non-empty
    directory, so `gpx/9/9` has to go before `gpx/9` can. The directories are back-dated
    along with the file for the reason the command reads every mtime up front: a directory
    whose mtime were read *after* its file was deleted would carry this command's own
    timestamp and spare itself.
    """
    back_date(str(make_stored_track(trip).file.name))
    orphan = write_orphan("gpx/9/9/stray.gpx")
    for directory in ("gpx/9/9", "gpx/9"):
        back_date(directory)

    call_command("reconcile_media", "--delete")

    captured = capsys.readouterr()
    assert "directories pruned 2" in captured.out
    assert not default_storage.exists(orphan)
    assert not (tmp_path / "media" / "gpx" / "9").exists()
    # The trip's own directory still holds the referenced file, so it is not a candidate.
    assert (tmp_path / "media" / "gpx").is_dir()
    assert (tmp_path / "media").is_dir()


@pytest.mark.django_db
def test_report_only_names_a_directory_that_holds_nothing(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An already-empty directory is invisible to an orphan report unless it is named.

    This is the shape the local volume is actually in — four `gpx/<owner>/<trip>/`
    directories holding no files at all — so a report that only listed orphaned *files*
    would answer "nothing to do" while leaving every one of them behind. Emptiness is
    derived from the walk rather than probed after the fact, which is also what lets a
    directory holding only orphans be previewed as a prune candidate before `--delete`.
    """
    back_date(str(make_stored_track(trip).file.name))
    default_storage.save("gpx/9/9/stray.gpx", ContentFile(b"<gpx/>"))
    default_storage.delete("gpx/9/9/stray.gpx")
    for directory in ("gpx/9/9", "gpx/9"):
        back_date(directory)

    call_command("reconcile_media")

    captured = capsys.readouterr()
    assert "Empty directory gpx/9/9." in captured.err
    assert "Empty directory gpx/9." in captured.err
    assert "orphaned 0" in captured.out
    assert "Nothing was removed" in captured.out


@pytest.mark.django_db
def test_a_freshly_created_directory_is_spared(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """`_save` makes the directory and only then opens the file inside it.

    A prune landing in that window removes the directory an upload is about to write into
    and the upload 500s, so a directory gets the same age guard a file does.
    """
    back_date(str(make_stored_track(trip).file.name))
    orphan = write_orphan("gpx/9/9/stray.gpx")
    # The file is old enough to reclaim; its directories are not old enough to prune.

    call_command("reconcile_media", "--delete")

    captured = capsys.readouterr()
    assert not default_storage.exists(orphan)
    assert "Spared directory gpx/9/9" in captured.err
    assert "directories pruned 0" in captured.out
    assert (tmp_path / "media" / "gpx" / "9" / "9").is_dir()


@pytest.mark.django_db
def test_a_directory_that_is_not_empty_is_left_alone_without_a_skip(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Over-reach is impossible, and the ordinary case must not read as a failure.

    Attempting every directory would make each populated one fail on every run, so the
    emptiness re-check is what keeps a real finding from drowning in noise. The refusal of
    `os.rmdir` remains underneath it as the backstop — see the next test.
    """
    track = make_stored_track(trip)
    referenced = track.file.name
    assert referenced is not None
    back_date(referenced)
    for directory in (f"gpx/{trip.owner_id}/{trip.pk}", f"gpx/{trip.owner_id}", "gpx"):
        back_date(directory)

    call_command("reconcile_media", "--delete")

    captured = capsys.readouterr()
    assert "Could not prune" not in captured.err
    assert "skipped 0, directories pruned 0" in captured.out
    assert default_storage.exists(referenced)


@pytest.mark.django_db
def test_an_unreadable_subdirectory_is_a_counted_skip_not_a_crash(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `PermissionError` on one subdirectory must not abort the whole walk.

    The walk precedes every delete, so losing one branch is a loss of signal, never of
    data — but it must still leave a tally for the other 99% of the tree, matching what
    `_prune` already does for the identical `OSError` around the same call.
    """
    back_date(str(make_stored_track(trip).file.name))
    write_orphan("gpx/9/9/stray.gpx")
    for directory in ("gpx/9/9", "gpx/9"):
        back_date(directory)
    original_listdir = default_storage.listdir

    def refuse_gpx_9(path: str) -> tuple[list[str], list[str]]:
        if path == "gpx/9":
            raise PermissionError(path)
        return original_listdir(path)

    monkeypatch.setattr(default_storage, "listdir", refuse_gpx_9, raising=True)

    call_command("reconcile_media")

    captured = capsys.readouterr()
    assert "Could not read gpx/9." in captured.err
    assert "Scanned 1, referenced 1, orphaned 0" in captured.out


@pytest.mark.django_db
def test_a_directory_whose_mtime_cannot_be_read_is_not_called_recently_modified(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreadable directory mtime must be reported as unreadable, not as 'recent'.

    `if modified is None or modified > cutoff:` used to collapse both states into one
    'modified recently' message — wrong when the mtime simply could not be read. Sparing
    is correct either way; only the reported reason was wrong.
    """
    back_date(str(make_stored_track(trip).file.name))
    write_orphan("gpx/9/9/stray.gpx")
    back_date("gpx/9/9")
    back_date("gpx/9")
    real_get_modified_time = default_storage.get_modified_time

    def vanish(name: str) -> object:
        if name == "gpx/9/9":
            raise FileNotFoundError(name)
        return real_get_modified_time(name)

    monkeypatch.setattr(default_storage, "get_modified_time", vanish, raising=True)

    call_command("reconcile_media")

    captured = capsys.readouterr()
    assert "Spared directory gpx/9/9: it could not be read." in captured.err
    assert "Spared directory gpx/9/9: modified in the last" not in captured.err


@pytest.mark.django_db
def test_a_directory_that_refuses_removal_is_a_counted_skip_not_a_crash(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A directory refilled between the emptiness check and the removal must not abort.

    `FileSystemStorage.delete` absorbs `FileNotFoundError` and nothing else, so `os.rmdir`'s
    `ENOTEMPTY` would escape `handle` — after files have already been reclaimed and before
    the tally prints, which is the one exit this command's contract forbids.
    """
    original_delete = default_storage.delete

    def refuse_directories(name: str) -> None:
        if name.endswith(".gpx"):
            original_delete(name)
            return
        raise OSError(39, "Directory not empty", name)

    back_date(str(make_stored_track(trip).file.name))
    orphan = write_orphan("gpx/9/9/stray.gpx")
    for directory in ("gpx/9/9", "gpx/9"):
        back_date(directory)
    monkeypatch.setattr(default_storage, "delete", refuse_directories, raising=True)

    call_command("reconcile_media", "--delete")

    captured = capsys.readouterr()
    assert not default_storage.exists(orphan)
    assert "Could not prune gpx/9/9." in captured.err
    assert "reclaimed 1, skipped 1, directories pruned 0" in captured.out


@pytest.mark.django_db
def test_delete_refuses_a_tree_in_which_nothing_is_referenced(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A database and a volume from different points in time make everything look orphaned.

    Both documented skew states produce this one shape, and in both the age guard says
    nothing — every file is older than any threshold by construction. So the shape itself
    is the signal, and `--delete` declines rather than deleting a volume's worth of files
    that are still in use.
    """
    orphan = write_orphan("gpx/1/1/restored-without-its-database.gpx")

    call_command("reconcile_media", "--delete")

    captured = capsys.readouterr()
    assert "not one of them is referenced" in captured.err
    assert "Refusing --delete." in captured.err
    assert "--allow-full-sweep" in captured.err
    assert "reclaimed 0" in captured.out
    assert default_storage.exists(orphan)


@pytest.mark.django_db
def test_allow_full_sweep_overrides_the_refusal(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The refusal has to be a speed bump, not a permanent block.

    An empty database with files still on the volume is a real state — every trip deleted,
    say — and there has to be a way to reclaim it.
    """
    orphan = write_orphan("gpx/1/1/genuinely-unreferenced.gpx")

    call_command("reconcile_media", "--delete", "--allow-full-sweep")

    captured = capsys.readouterr()
    assert "not one of them is referenced" in captured.err
    assert "Refusing --delete." not in captured.err
    assert "reclaimed 1" in captured.out
    assert not default_storage.exists(orphan)


@pytest.mark.django_db
def test_one_referenced_file_suppresses_the_refusal(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The ordinary case must not be turned into a no-op by the guard.

    This is the regression the refusal is most likely to cause: a guard keyed on "any
    orphans at all" rather than on "nothing referenced" would block every real run.
    """
    back_date(str(make_stored_track(trip).file.name))
    orphan = write_orphan("gpx/1/1/stray.gpx")

    call_command("reconcile_media", "--delete")

    captured = capsys.readouterr()
    assert "Refusing --delete." not in captured.err
    assert "not one of them is referenced" not in captured.err
    assert "reclaimed 1" in captured.out
    assert not default_storage.exists(orphan)


@pytest.mark.django_db
def test_report_only_warns_about_the_skew_without_needing_the_flag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An operator should meet the warning before reaching for `--delete`, not after."""
    write_orphan("gpx/1/1/restored-without-its-database.gpx")

    call_command("reconcile_media")

    captured = capsys.readouterr()
    assert "not one of them is referenced" in captured.err
    assert "Refusing --delete." not in captured.err


@pytest.mark.django_db
def test_the_resolved_media_root_is_the_first_stderr_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The operator's whole safety story rests on knowing which tree was walked.

    Nothing else in this command's output names `MEDIA_ROOT` — only its docstrings did,
    before this — yet `DEPLOY.md`'s precondition and the `MSYS_NO_PATHCONV` trap both
    assume the operator can see what was actually confirmed.
    """
    call_command("reconcile_media")

    captured = capsys.readouterr()
    assert captured.err.splitlines()[0] == f"MEDIA_ROOT: {settings.MEDIA_ROOT}"


@pytest.mark.django_db
def test_a_missing_media_root_reports_zero_rather_than_crashing(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """A deployment that has taken no uploads yet has no `MEDIA_ROOT` on disk at all.

    `Storage.listdir` raises `FileNotFoundError` from `os.scandir` there, and a
    reconciliation command that crashed on an empty volume would be useless in exactly the
    situation an operator reaches for it first.
    """
    assert not (tmp_path / "media").exists()

    call_command("reconcile_media", "--delete")

    captured = capsys.readouterr()
    assert "Scanned 0, referenced 0, orphaned 0" in captured.out


@pytest.mark.django_db
def test_a_failing_delete_is_a_counted_skip_not_a_crash(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unmounted Volume or a permission change must still produce a tally.

    The operator runs this precisely because something is already wrong; aborting would
    leave an arbitrary prefix of files reclaimed and print no count at all.
    """

    def refuse_delete(self: object, name: str) -> None:
        raise PermissionError(name)

    back_date(str(make_stored_track(trip).file.name))
    orphan = write_orphan("gpx/1/1/stray.gpx")
    monkeypatch.setattr(
        "django.core.files.storage.FileSystemStorage.delete", refuse_delete, raising=True
    )

    call_command("reconcile_media", "--delete")

    captured = capsys.readouterr()
    assert f"Could not reclaim {orphan}." in captured.err
    assert "reclaimed 0, skipped 1" in captured.out
    assert default_storage.exists(orphan)


@pytest.mark.django_db
def test_a_file_that_vanishes_between_the_walk_and_the_stat_is_spared(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reconciling a live volume means candidates can disappear underfoot.

    A key the walk saw and the stat cannot read needs no reclaiming, so it is spared rather
    than aborting the run — and spared is the conservative direction, since the alternative
    reading of an unreadable file is "delete it".
    """
    back_date(str(make_stored_track(trip).file.name))
    orphan = write_orphan("gpx/1/1/stray.gpx")
    real_get_modified_time = default_storage.get_modified_time

    def vanish(name: str) -> object:
        if name == orphan:
            raise FileNotFoundError(name)
        return real_get_modified_time(name)

    monkeypatch.setattr(default_storage, "get_modified_time", vanish, raising=True)

    call_command("reconcile_media", "--delete")

    captured = capsys.readouterr()
    assert f"Spared {orphan}: it could not be read." in captured.err
    assert "orphaned 0, spared 1, reclaimed 0, skipped 0" in captured.out


@pytest.mark.django_db
def test_a_second_delete_run_is_a_clean_no_op(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Idempotence, because an operator who is unsure will run it twice."""
    track = make_stored_track(trip)
    back_date(str(track.file.name))
    write_orphan("gpx/9/9/stray.gpx")
    for directory in ("gpx/9/9", "gpx/9"):
        back_date(directory)

    call_command("reconcile_media", "--delete")
    capsys.readouterr()

    call_command("reconcile_media", "--delete")

    captured = capsys.readouterr()
    assert "Scanned 1, referenced 1, orphaned 0, spared 0, reclaimed 0, skipped 0" in captured.out
    assert "directories pruned 0" in captured.out


def _symlink_or_skip(link: Path, target: Path) -> None:
    """Create a directory symlink, skipping where the platform refuses to make one.

    Windows permits this only for a privileged process or one in Developer Mode. CI runs on
    Linux, where it always works, so a local skip never weakens the guard where it counts.
    """
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - platform dependent
        pytest.skip(f"platform does not permit directory symlinks: {exc}")


@pytest.mark.django_db
def test_a_symlinked_directory_is_never_walked_or_reclaimed(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A symlink under `MEDIA_ROOT` must not let `--delete` reach the real file behind it.

    `safe_join` compares `abspath` and never `realpath`, so `MEDIA_ROOT/archive/backup.gpx`
    clears containment; `FileSystemStorage.delete`'s `os.remove` then follows the symlinked
    parent and unlinks the real file. Staging a backup beside the volume and linking it in
    is the shape this protects — the runbook sits next to the restore material, which is
    exactly when someone would.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    protected = outside / "backup.gpx"
    protected.write_bytes(b"<gpx>backup</gpx>")

    media_root = Path(settings.MEDIA_ROOT)
    media_root.mkdir(parents=True, exist_ok=True)
    _symlink_or_skip(media_root / "archive", outside)

    track = make_stored_track(trip)
    back_date(str(track.file.name))

    call_command("reconcile_media", "--delete")

    captured = capsys.readouterr()
    assert protected.exists(), "the real file behind the symlink was reclaimed"
    assert "backup.gpx" not in captured.err
    assert "Scanned 1, referenced 1, orphaned 0" in captured.out


@pytest.mark.django_db
def test_a_symlink_loop_does_not_run_the_walk_out_of_stack(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`ln -s . loop` resolves to `MEDIA_ROOT` itself, so containment alone cannot stop it.

    Refusing to descend through a symlink at all is what terminates the walk — without it
    this recurses `loop/loop/loop/…` until the interpreter runs out of stack.
    """
    media_root = Path(settings.MEDIA_ROOT)
    media_root.mkdir(parents=True, exist_ok=True)
    _symlink_or_skip(media_root / "loop", media_root)

    track = make_stored_track(trip)
    back_date(str(track.file.name))

    call_command("reconcile_media")

    captured = capsys.readouterr()
    assert "Scanned 1, referenced 1, orphaned 0" in captured.out


def test_the_walk_guard_rejects_a_directory_that_resolves_outside_media_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The containment half of the guard, exercised without needing symlink privileges.

    The two symlink tests above skip on a Windows box that is not in Developer Mode, so
    without this the guard would go unproven on every local run and only ever be checked
    in CI. Here the escape is injected at `storage.path`, which is the single point every
    real escape — symlink, bind mount, Windows junction — arrives through.
    """
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    inside = Path(settings.MEDIA_ROOT) / "gpx"
    inside.mkdir(parents=True, exist_ok=True)

    assert _is_walkable_directory("gpx") is True

    monkeypatch.setattr(default_storage, "path", lambda key: str(outside), raising=True)
    assert _is_walkable_directory("gpx") is False
