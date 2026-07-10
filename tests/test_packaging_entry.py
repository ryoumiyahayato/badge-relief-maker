import packaging_entry


def test_packaged_entry_opens_gui_without_arguments(monkeypatch):
    calls = []
    monkeypatch.setattr(packaging_entry, "run_gui", lambda: calls.append("gui") or 0)
    monkeypatch.setattr(packaging_entry, "main", lambda argv: calls.append(tuple(argv)) or 0)

    assert packaging_entry.packaged_main([]) == 0
    assert calls == ["gui"]


def test_packaged_entry_preserves_explicit_cli_arguments(monkeypatch):
    calls = []
    monkeypatch.setattr(packaging_entry, "run_gui", lambda: calls.append("gui") or 0)
    monkeypatch.setattr(packaging_entry, "main", lambda argv: calls.append(tuple(argv)) or 0)

    assert packaging_entry.packaged_main(["--help"]) == 0
    assert calls == [("--help",)]
