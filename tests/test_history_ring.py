"""L471: snapshots stay bounded without deleting (the oldest one is renamed and overwritten)."""


def test_snapshot_reuses_oldest_file(tmp_path, monkeypatch):
    from fof import state

    monkeypatch.setattr(state, "game_dir", lambda: tmp_path)
    monkeypatch.setattr(state, "HISTORY_KEEP", 3)
    real_unlink = type(tmp_path).unlink
    monkeypatch.setattr(
        type(tmp_path), "unlink", lambda self, *a, **k: (_ for _ in ()).throw(PermissionError("no delete"))
    )
    for num in range(1, 11):
        state.save_snapshot(num, f'{{"nr": {num}}}')
    monkeypatch.setattr(type(tmp_path), "unlink", real_unlink)
    names = sorted(int(f.stem) for f in (tmp_path / "history").glob("*.json"))
    assert names == [7, 8, 9, 10]  # same window as with deleting: nr - HISTORY_KEEP .. nr
    assert (tmp_path / "history" / "10.json").read_text(encoding="utf-8") == '{"nr": 10}'
