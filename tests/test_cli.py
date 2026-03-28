import io
from pathlib import Path

from click.testing import CliRunner

from edown import DownloadResult, DownloadSummary
from edown.cli import _build_download_progress, main


def test_search_cli_writes_manifest(tmp_path: Path, monkeypatch) -> None:
    class DummyResult:
        images = ()

    monkeypatch.setattr("edown.cli.search_images", lambda config: DummyResult())
    monkeypatch.setattr(
        "edown.cli.build_manifest_document", lambda config, result: {"search": {"images": []}}
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "search",
            "--collection-id",
            "TEST/COLLECTION",
            "--start-date",
            "2024-06-01",
            "--end-date",
            "2024-06-01",
            "--bbox",
            "-0.5",
            "-0.5",
            "0.5",
            "0.5",
            "--manifest-path",
            str(tmp_path / "manifest.json"),
        ],
    )
    assert result.exit_code == 0
    assert (tmp_path / "manifest.json").exists()


def test_download_cli_reports_skip_reasons(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "edown.cli.download_images",
        lambda config, progress=None: DownloadSummary(
            manifest_path=tmp_path / "manifest.json",
            output_root=tmp_path,
            results=(
                DownloadResult(image_id="IMG_1", status="skipped_existing"),
                DownloadResult(image_id="IMG_2", status="skipped_existing"),
            ),
        ),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "download",
            "--collection-id",
            "TEST/COLLECTION",
            "--start-date",
            "2024-06-01",
            "--end-date",
            "2024-06-01",
            "--bbox",
            "-0.5",
            "-0.5",
            "0.5",
            "0.5",
            "--manifest-path",
            str(tmp_path / "manifest.json"),
        ],
    )

    assert result.exit_code == 0
    assert "Downloaded=0 Skipped=2 Failed=0 (skipped_existing=2)" in result.output


def test_build_download_progress_disables_for_dumb_term(monkeypatch) -> None:
    class TtyStream(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr("click.get_text_stream", lambda name: TtyStream())
    monkeypatch.setenv("TERM", "dumb")

    assert _build_download_progress() is None


def test_build_download_progress_enables_for_ansi_tty(monkeypatch) -> None:
    class TtyStream(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr("click.get_text_stream", lambda name: TtyStream())
    monkeypatch.setenv("TERM", "xterm-256color")

    assert _build_download_progress() is not None
