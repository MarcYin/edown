from pathlib import Path

from click.testing import CliRunner

from edown.cli import main


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
