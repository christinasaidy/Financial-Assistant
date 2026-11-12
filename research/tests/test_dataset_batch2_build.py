"""Batch-2 orchestration contracts; no database or evaluation data is read."""

import json
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pytest

from research.dataset import build
from research.dataset import batch2_build as b
from research.dataset.generator_prompt import LANGUAGES
from research.dataset.templates import Spec


def job(number=1, index=0, base=None):
    spec = Spec("F1" if base else "T1", "sql", "total spending", "SELECT 1", base=base)
    return build.Job(spec, f"b2-{number}-{index}", number,
                     "train" if number <= 27 else "validation", date(2026, 11, 1),
                     build.UserNames([], [], []), 1, f"prompt-{number}-{index}")


def reply(j):
    return json.dumps({"versions": [
        {"language": language, "question": f"spending version {i}",
         **({"first": "earlier spending"} if j.spec.base else {})}
        for i, language in enumerate(LANGUAGES)]})


def write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def log(raw, jobs):
    entries = [{"spec": j.spec_id, "template": j.spec.template, "prompt": j.prompt, "reply": reply(j)}
               for j in jobs]
    (raw / "generator_replies.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return entries


def reviewed(jobs):
    manifest = b.make_review_manifest(jobs, {j.prompt: b.read_reply(reply(j), j.spec) for j in jobs})
    manifest.update(completed=True, reviewer="test reviewer")
    for entry in manifest["entries"]:
        entry.update(decision="keep", reason="Matches the spec and Lebanese seed style")
    return manifest


def test_nested_job_roundtrip_and_tamper_detection(tmp_path):
    jobs = [job(base=Spec("T1", "sql", "earlier", "SELECT 2", (("total",),)))]
    b.save_jobs(jobs, tmp_path, {"shortfalls": "reported separately"}, chunk_size=40)
    assert b.load_jobs(tmp_path) == jobs
    saved = json.loads((tmp_path / "jobs.jsonl").read_text())
    assert saved["spec"]["base"]["target"] == "SELECT 2"
    assert len(list((tmp_path / "jobs").glob("*.jsonl"))) == 1
    saved["spec"]["target"] = "SELECT 3"
    (tmp_path / "jobs.jsonl").write_text(json.dumps(saved) + "\n")
    with pytest.raises(ValueError, match="fingerprint"):
        b.load_jobs(tmp_path)


@pytest.mark.parametrize("jobs", [[job(31)], [job(), job()], [job(), replace(job(2), prompt=job().prompt)]])
def test_invalid_jobs_never_create_outputs(tmp_path, jobs):
    out = tmp_path / "absent"
    with pytest.raises(ValueError):
        b.save_jobs(jobs, out, {})
    assert not out.exists()


@pytest.mark.parametrize("mutation", ["order", "extra", "short", "first", "duplicate_key"])
def test_reply_is_exact_schema_and_language_order(mutation):
    j = job(base=Spec("T1", "sql", "earlier", "SELECT 2"))
    data = json.loads(reply(j))
    if mutation == "order":
        data["versions"][0]["language"] = "english"
    elif mutation == "extra":
        data["versions"][0]["source"] = "citation"
    elif mutation == "short":
        data["versions"].pop()
    elif mutation == "first":
        del data["versions"][0]["first"]
    text = json.dumps(data)
    if mutation == "duplicate_key":
        text = text.replace('"versions":', '"versions": [], "versions":', 1)
    with pytest.raises(ValueError):
        b.read_reply(text, j.spec)


@pytest.mark.parametrize("fault", ["missing", "duplicate", "prompt", "null"])
def test_log_requires_exactly_every_saved_prompt(tmp_path, fault):
    jobs = [job(), job(2)]
    entries = log(tmp_path, jobs)
    if fault == "missing":
        entries.pop()
    elif fault == "duplicate":
        entries.append(entries[0])
    elif fault == "prompt":
        entries[0]["prompt"] += "changed"
    else:
        entries[0]["reply"] = None
    (tmp_path / "generator_replies.jsonl").write_text("\n".join(map(json.dumps, entries)))
    with pytest.raises(ValueError):
        b.load_replies(tmp_path / "generator_replies.jsonl", jobs)


@pytest.mark.parametrize("fault", ["pending", "missing", "duplicate", "first", "reason"])
def test_review_is_complete_and_bound_to_first_text(tmp_path, fault):
    jobs = [job(base=Spec("T1", "sql", "earlier", "SELECT 2"))]
    manifest = reviewed(jobs)
    if fault == "pending":
        manifest["completed"] = False
    elif fault == "missing":
        manifest["entries"].pop()
    elif fault == "duplicate":
        manifest["entries"].append(manifest["entries"][0])
    elif fault == "first":
        manifest["entries"][0]["version"]["first"] = "different"
    else:
        manifest["entries"][0].update(decision="drop", reason="")
    write_json(tmp_path / "review.json", manifest)
    with pytest.raises(ValueError):
        b.load_review(tmp_path / "review.json", jobs,
                      {jobs[0].prompt: b.read_reply(reply(jobs[0]), jobs[0].spec)})


@pytest.mark.parametrize("field", ["description", "target", "base", "prompt", "names", "today", "rows"])
def test_review_rejects_changed_job_with_same_id_and_versions(tmp_path, field):
    original = job(base=Spec("T1", "sql", "earlier", "SELECT 2"))
    manifest = reviewed([original])
    write_json(tmp_path / "review.json", manifest)
    versions = b.read_reply(reply(original), original.spec)
    assert b.load_review(tmp_path / "review.json", [original], {original.prompt: versions})
    if field in ("description", "target"):
        changed = replace(original, spec=replace(original.spec, **{field: "changed"}))
    elif field == "base":
        changed = replace(original, spec=replace(original.spec, base=replace(original.spec.base, target="SELECT 3")))
    else:
        value = {"prompt": "changed prompt", "names": build.UserNames(["bread"], [], []),
                 "today": date(2026, 11, 2), "rows": 2}[field]
        changed = replace(original, **{field: value})
    assert changed.spec_id == original.spec_id
    with pytest.raises(ValueError, match="stale"):
        b.load_review(tmp_path / "review.json", [changed], {changed.prompt: versions})


def test_review_requires_job_fingerprint(tmp_path):
    jobs = [job()]
    manifest = reviewed(jobs)
    for entry in manifest["entries"]:
        entry.pop("job_sha256", None)
    write_json(tmp_path / "review.json", manifest)
    with pytest.raises(ValueError, match="stale"):
        b.load_review(tmp_path / "review.json", jobs, {jobs[0].prompt: b.read_reply(reply(jobs[0]), jobs[0].spec)})


def test_replay_no_db_automatic_holdout_redacted_drops_and_review(tmp_path, monkeypatch):
    raw, out = tmp_path / "raw", tmp_path / "out"
    jobs = [job(base=Spec("T1", "sql", "earlier", "SELECT 2"))]
    b.save_jobs(jobs, raw, {})
    log(raw, jobs)
    manifest = reviewed(jobs)
    manifest["entries"][1].update(decision="drop", reason="Unnatural Lebanese wording")
    write_json(raw / "review.json", manifest)
    monkeypatch.setattr(build, "load_settings", lambda: pytest.fail("replay must not use DB"))
    calls = []
    monkeypatch.setattr(build, "test_questions", lambda extra: calls.append(extra) or ("private holdout",))
    monkeypatch.setattr(b, "problems", lambda v, *args: ["near-duplicate of a test question: private holdout"]
                        if v.question.endswith("0") else [])
    monkeypatch.setattr(b, "near_duplicate", lambda text, tests: "private holdout" if text == "earlier spending" else None)
    summary = b.replay(raw, out, raw / "review.json")
    assert calls == [None]
    assert sum(summary.examples.values()) == 0  # earlier turns are held out too
    drops = (raw / "drops.jsonl").read_text()
    assert "private holdout" not in drops
    assert "Unnatural Lebanese wording" in drops


def test_prepare_plans_each_split_globally_and_cleans_up_before_saving(tmp_path, monkeypatch):
    calls, removed = [], []
    monkeypatch.setattr(b, "load_catalogue", lambda: object())
    monkeypatch.setattr(b, "load_seeds", lambda: object())
    monkeypatch.setattr(b, "make_user", lambda c, n: SimpleNamespace(number=n, today=date(2026, 11, 1)))
    monkeypatch.setattr(b, "UserData", lambda u, c: SimpleNamespace(user=u))

    def plan(data, limits, seed):
        calls.append(limits)
        return SimpleNamespace(specs={n: [Spec("T1", "sql", f"ask {n}-{i}", "SELECT 1")
                                         for i in range(count)] for n, count in limits.items()},
                               item_shortfalls={}, feature_shortfalls={}, feature_counts={}, diversity_shortfalls={})

    monkeypatch.setattr(b, "make_batch2_plan", plan)
    monkeypatch.setattr(build, "load_settings", lambda: SimpleNamespace(readonly_database_url="configured"))
    monkeypatch.setattr(build, "build_evaluation", lambda *a: SimpleNamespace(
        assistant=SimpleNamespace(prompt_names=lambda uid: build.UserNames([], [], []))))
    monkeypatch.setattr(b, "seed_user", lambda s, u: u.number)
    monkeypatch.setattr(b, "remove_user", lambda s, uid: removed.append(uid))
    monkeypatch.setattr(build, "_run", lambda *a: 1)
    monkeypatch.setattr(b, "build_generator_prompt", lambda s, *a: s.description)
    jobs = b.prepare(tmp_path / "ok")
    assert len(jobs) == 960
    assert calls == [dict.fromkeys(range(1, 28), 30), dict.fromkeys(range(28, 31), 50)]
    assert removed == list(range(1, 31))
    assert len(list((tmp_path / "ok" / "jobs").glob("*.jsonl"))) == 24
    removed.clear()
    monkeypatch.setattr(build, "_run", lambda *a: (_ for _ in ()).throw(ValueError("SQL rejected")))
    with pytest.raises(ValueError, match="SQL rejected"):
        b.prepare(tmp_path / "failed")
    assert removed == [1]
    assert not (tmp_path / "failed").exists()


def test_replay_writes_reproducible_examples_and_preserves_outputs_on_incomplete_review(tmp_path, monkeypatch):
    raw, out = tmp_path / "raw", tmp_path / "out"
    jobs = [job(), job(28)]
    b.save_jobs(jobs, raw, {})
    log(raw, jobs)
    manifest = reviewed(jobs)
    manifest["entries"][0].update(decision="drop", reason="Wrong meaning")
    write_json(raw / "review.json", manifest)
    monkeypatch.setattr(build, "test_questions", lambda extra: ())
    monkeypatch.setattr(build, "load_settings", lambda: pytest.fail("No database in replay"))
    summary = b.replay(raw, out, raw / "review.json")
    assert summary.examples == {"train": 5, "validation": 6}
    assert summary.sql_examples == 11
    assert summary.drops == {"dropped in review": 1}
    before = (out / "train.jsonl").read_bytes()
    examples = [json.loads(line) for line in before.decode().splitlines()]
    assert examples[0]["messages"][1] == {"role": "assistant", "content": "SELECT 1"}
    assert all(e["labels"]["spec"] == "b2-1-0" for e in examples)
    b.replay(raw, out, raw / "review.json")
    assert (out / "train.jsonl").read_bytes() == before
    manifest["entries"].pop()
    write_json(raw / "review.json", manifest)
    with pytest.raises(ValueError):
        b.replay(raw, out, raw / "review.json")
    assert (out / "train.jsonl").read_bytes() == before


def test_effective_reply_review_cannot_certify_superseded_writer_reply():
    j = replace(job(), spec=Spec("R1", "reply", "greeting", None))
    text = json.dumps({"versions": [{"language": lang, "question": "hi", "reply": "REPLY: Hello!"}
                                    for lang in LANGUAGES]})
    effective = b.effective_replies([j], {j.prompt: b.read_reply(text, j.spec)}, b.load_catalogue())
    manifest = b.make_review_manifest([j], effective)
    assert manifest["completed"] is False
    assert manifest["entries"][0]["version"]["reply"] != "REPLY: Hello!"
    assert effective[j.prompt][4].reply == "REPLY: Hello!"


def test_cli_exposes_only_prepare_replay_review_and_requires_full_snapshot(monkeypatch):
    with pytest.raises(SystemExit):
        b.main(["--model", "paid"])
    with pytest.raises(SystemExit):
        b.main(["--prepare", "--replay"])
    calls = []
    monkeypatch.setattr(b, "replay", lambda **kw: calls.append(kw) or build.Summary())
    assert b.main(["--replay"]) == 0
    assert calls == [{"review": b.REVIEW_FILE, "complete": True}]
    with pytest.raises(ValueError, match="960"):
        b.validate_jobs([job()], complete=True)


def test_export_assignments_preserves_exact_multiline_prompts_without_sql(tmp_path):
    jobs = [replace(job(index=i), prompt=f"Exact prompt {i}\n\n  Keep spacing.\nLast line") for i in range(41)]
    b.save_jobs(jobs, tmp_path, {})
    paths = b.export_assignments(tmp_path)
    assert [p.name for p in paths] == ["chunk-000.md", "chunk-001.md"]
    first = paths[0].read_text(encoding="utf-8")
    second = paths[1].read_text(encoding="utf-8")
    for j in jobs[:40]:
        assert j.prompt in first
        assert f"## {j.spec_id}\n" in first
    assert jobs[40].prompt in second and "## b2-1-40\n" not in first
    assert "SELECT 1" not in first
    assert json.dumps(b.versions_schema(jobs[0].spec), ensure_ascii=False, indent=2) in first


@pytest.mark.parametrize("fault", [None, "missing", "duplicate", "unknown", "schema", "extra"])
def test_collect_authored_requires_complete_valid_authorship_before_replacing_log(tmp_path, fault):
    jobs = [job(), job(28)]
    b.save_jobs(jobs, tmp_path, {})
    authored = tmp_path / "authored"
    authored.mkdir()
    entries = [{"spec": j.spec_id, **json.loads(reply(j))} for j in jobs]
    if fault == "missing":
        entries.pop()
    elif fault == "duplicate":
        entries.append(entries[0])
    elif fault == "unknown":
        entries[0]["spec"] = "b2-31-0"
    elif fault == "schema":
        entries[0]["versions"][0]["language"] = "english"
    elif fault == "extra":
        entries[0]["source"] = "separate metadata only"
    for i, entry in enumerate(entries):
        (authored / f"chunk-{i:03d}.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")
    output = tmp_path / "generator_replies.jsonl"
    output.write_text("previous log", encoding="utf-8")
    if fault:
        with pytest.raises(ValueError):
            b.collect_authored(tmp_path)
        assert output.read_text() == "previous log"
    else:
        assert b.collect_authored(tmp_path) == output
        records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
        assert [r["prompt"] for r in records] == [j.prompt for j in jobs]
        assert [r["template"] for r in records] == [j.spec.template for j in jobs]
        assert [json.loads(r["reply"]) for r in records] == [json.loads(reply(j)) for j in jobs]
        assert len(b.load_replies(output, jobs)) == 2


def test_transport_cli_modes(monkeypatch):
    calls = []
    monkeypatch.setattr(b, "export_assignments", lambda: calls.append("export") or [])
    monkeypatch.setattr(b, "collect_authored", lambda: calls.append("collect") or b.RAW_DIR / "generator_replies.jsonl")
    assert b.main(["--export-assignments"]) == 0
    assert b.main(["--collect-authored"]) == 0
    assert calls == ["export", "collect"]
