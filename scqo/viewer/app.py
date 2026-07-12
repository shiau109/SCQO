"""The SCQO run-viewer — the lab's daily data GUI (port 8080 by convention).

Reads ONLY the datastore (run folders + index) and the scqo state JSON (history).
No Session, no backend, no vendor imports — it runs anywhere the data drive is
mounted. The single mutating route is tag/note editing, which writes to
``record.json`` + the index exactly like ``tag_run.py`` (never instruments, never
measurement data).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..config import FIELDS
from ..datastore import (
    DataStore,
    active_cooldown,
    load_cooldowns,
    load_device_registry,
)
from ..physical import PHYSICAL_FIELDS, PHYSICAL_FILE
from ..provenance import live_run_map, live_sources, summarize_live

#: quantities never tracked as device state (instrument-dependent; recorded decision)
_FIT_ONLY_TRENDS = ("p_e_given_g",)
#: fit quantities offered as one-click trend links (free-text also accepted):
#: measured physics first, then calibration knobs — derived from the field tables.
TREND_QUANTITIES = (
    *PHYSICAL_FIELDS,
    *(f for f, s in FIELDS.items() if not s.push),
    *(f for f, s in FIELDS.items() if s.push),
    *_FIT_ONLY_TRENDS,
)


def create_app(
    data_root: str | Path,
    device_name: str = "device",
) -> FastAPI:
    store = DataStore(data_root, device_name=device_name)
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    app = FastAPI(title="SCQO run viewer", docs_url=None, redoc_url=None)

    def _run_dir(record: dict) -> Path:
        return store.data_root / record["path"]

    def _read_json(path: Path) -> dict | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _sources_for(dev: str) -> tuple[dict, dict]:
        """(instrument, physical) live-source maps for a device, from its two state
        JSONs (({}, {}) where absent). The state files ARE the viewer's current-
        value authority — the strict-match rule credits a run only while its
        recorded value still equals the live one (see scqo.provenance)."""
        sfile = _state_file_for(dev)
        state = (_read_json(sfile) if sfile else None) or {}
        physical = _read_json(store.data_root / dev / PHYSICAL_FILE) or {}
        return (
            live_sources(state.get("config", {}), state.get("history", [])),
            live_sources(physical.get("values", {}), physical.get("history", [])),
        )

    @app.get("/", response_class=HTMLResponse)
    def runs_page(
        request: Request,
        experiment: str = "",
        qubit: str = "",
        tag: str = "",
        outcome: str = "",
        since: str = "",
        until: str = "",
        device: str = "",
        operator: str = "",
        cooldown: str = "",
        setup: str = "",
        pending: str = "",
        limit: int = 50,
    ):
        rows = store.find_runs(
            experiment=experiment or None,
            qubit=qubit or None,
            tag=tag or None,
            outcome=outcome or None,
            since=since or None,
            until=until or None,
            device=device or None,
            operator=operator or None,
            cooldown=cooldown or None,
            setup=setup or None,
            pending=True if pending else None,
            limit=limit,
        )
        # Which of these runs CONTRIBUTE to a device's current values ("the runs
        # the device is built from") — run_ids are globally unique by construction.
        live_by_run: dict[str, str] = {}
        for dev in {r["device"] for r in rows}:
            inst, phys = _sources_for(dev)
            for rid, pairs in live_run_map(inst, phys).items():
                live_by_run[rid] = summarize_live(pairs)
        return templates.TemplateResponse(
            request,
            "runs.html",
            {
                "rows": rows,
                "live_by_run": live_by_run,
                "experiments": store.distinct_experiments(),
                "devices": store.distinct_devices(),
                "filters": {"experiment": experiment, "qubit": qubit, "tag": tag,
                            "outcome": outcome, "since": since, "until": until,
                            "device": device, "operator": operator,
                            "cooldown": cooldown, "setup": setup,
                            "pending": pending, "limit": limit},
                "data_root": str(store.data_root),
            },
        )

    @app.get("/run/{run_id}", response_class=HTMLResponse)
    def run_page(request: Request, run_id: str):
        try:
            loaded = store.load_run(run_id)
        except KeyError:
            raise HTTPException(404, f"unknown run_id {run_id!r}")
        record = loaded["record"]
        run_dir = _run_dir(record)
        figures = [str(Path(p).relative_to(run_dir).as_posix()) for p in loaded["figures"]]
        before = _read_json(run_dir / "device_before.json") or {}
        after = _read_json(run_dir / "device_after.json") or {}
        diff = []
        for q in sorted(set(before) | set(after)):
            for field in sorted(set(before.get(q, {})) | set(after.get(q, {}))):
                b, a = before.get(q, {}).get(field), after.get(q, {}).get(field)
                diff.append({"qubit": q, "field": field, "before": b, "after": a,
                             "changed": b != a})
        # Is each ACCEPTED value still the one the device runs? (aligned with the
        # suggestions list; None for non-accepted rows / no source info)
        inst_sources, phys_sources = _sources_for(record["device"])
        on_device = []
        for s in record.get("suggestions", []):
            sources = phys_sources if s.get("store") == "physical" else inst_sources
            src = sources.get(s.get("qubit"), {}).get(s.get("field"))
            if s.get("status") != "accepted" or src is None:
                on_device.append(None)
            elif src["status"] == "run" and src["run_id"] == run_id:
                on_device.append({"kind": "live"})
            elif src["status"] == "run":
                on_device.append({"kind": "superseded", "run_id": src["run_id"]})
            elif src["status"] == "external":
                on_device.append({"kind": "external"})
            else:  # manual
                on_device.append({"kind": "manual"})
        return templates.TemplateResponse(
            request,
            "run.html",
            {
                "record": record,
                "parameters": loaded["parameters"],
                "result": loaded["result"],
                "figures": figures,
                "suggestions": record.get("suggestions", []),
                "on_device": on_device,
                "diff": diff,
                "path": str(run_dir),
            },
        )

    @app.get("/run/{run_id}/file/{relpath:path}")
    def run_file(run_id: str, relpath: str):
        try:
            loaded = store.load_run(run_id)
        except KeyError:
            raise HTTPException(404, f"unknown run_id {run_id!r}")
        base = _run_dir(loaded["record"]).resolve()
        target = (base / relpath).resolve()
        # strict containment: never serve anything outside this run's folder
        if base != target and base not in target.parents:
            raise HTTPException(404, "not in this run's folder")
        if not target.is_file():
            raise HTTPException(404, "no such file")
        return FileResponse(target)

    @app.post("/run/{run_id}/tags")
    def edit_tags(run_id: str, add: str = Form(""), remove: str = Form(""), note: str = Form(None)):
        # The viewer's ONLY write: record.json + index, same as tag_run.py.
        try:
            store.tag_run(
                run_id,
                add=[t for t in add.replace(",", " ").split() if t],
                remove=[t for t in remove.replace(",", " ").split() if t],
                note=note if note is not None and note != "" else None,
            )
        except KeyError:
            raise HTTPException(404, f"unknown run_id {run_id!r}")
        return RedirectResponse(url=f"/run/{run_id}", status_code=303)

    @app.get("/trends", response_class=HTMLResponse)
    def trends_page(request: Request, qubit: str = "q1", quantity: str = "t1_s", device: str = ""):
        # qubit names repeat across samples ("q1" exists on every chip), so the
        # trend defaults to the configured device rather than mixing samples.
        dev = device or device_name
        rows = store.fit_trend(qubit, quantity, device=dev) if qubit and quantity else []
        svg = _trend_svg(rows)
        return templates.TemplateResponse(
            request,
            "trends.html",
            {"qubit": qubit, "quantity": quantity, "rows": rows, "svg": svg,
             "quantities": TREND_QUANTITIES, "device": dev,
             "devices": store.distinct_devices()},
        )

    def _state_file_for(device: str) -> Path | None:
        """The device's scqo state JSON: the configured path for the default device,
        the ``<data_root>/<device>/scqo_state.json`` convention (THE rule since v0.5)."""
        candidate = store.data_root / device / "scqo_state.json"
        return candidate if candidate.is_file() else None

    @app.get("/device", response_class=HTMLResponse)
    def device_page(request: Request, device: str = ""):
        dev = device or device_name
        latest = store.find_runs(device=dev, limit=1)
        history: list[dict] = []
        state = None
        state_authority = ""
        sfile = _state_file_for(dev)
        if sfile and sfile.is_file():
            # The state file is the authority since v0.6: it reflects deferred
            # accepts too, and is what the live-source annotations are computed
            # against (annotating a run snapshot with state-file provenance would
            # contradict itself whenever an accept ran after the latest run).
            data = _read_json(sfile) or {}
            state = data.get("config") or None
            history = list(reversed(data.get("history", [])))[:200]
            state_authority = "state"
        if state is None and latest:  # no state file yet: last run's snapshot
            state = _read_json(_run_dir(latest[0]) / "device_after.json")
            state_authority = "snapshot"
        inst_sources, phys_sources = _sources_for(dev)
        registry = load_device_registry(store.data_root)
        # Stable column order: descriptor order first, then any extra observed fields.
        # (Fields are heterogeneous per qubit — only measured qubits carry a value —
        # so the first qubit's keys are NOT a valid header.)
        observed = {f for fields in (state or {}).values() for f in fields}
        state_fields = [f for f in FIELDS if f in observed] + sorted(observed - set(FIELDS))
        # The sample's measured physics (physical.json) — same heterogeneity rule.
        physical = _read_json(store.data_root / dev / PHYSICAL_FILE) or {}
        phys_values = physical.get("values", {})
        phys_history = list(reversed(physical.get("history", [])))[:200]
        observed_phys = {f for fields in phys_values.values() for f in fields}
        physical_fields = [f for f in PHYSICAL_FIELDS if f in observed_phys] + sorted(
            observed_phys - set(PHYSICAL_FIELDS)
        )
        # Cooldown cycles + the ACTIVE cycle's named setups. The registry validates
        # loudly at RUN time; the viewer must render regardless. No user context
        # here, so ALL setups are shown — never "the selected one".
        cooldown_error = ""
        try:
            cycles = load_cooldowns(store.data_root, dev)
        except ValueError as err:
            cycles, cooldown_error = {}, str(err)
        active = active_cooldown(cycles)
        setups = active[1].get("setup", {}) if active else {}
        return templates.TemplateResponse(
            request,
            "device.html",
            {"state": state or {}, "state_fields": state_fields,
             "state_authority": state_authority,
             "state_sources": inst_sources, "physical_sources": phys_sources,
             "latest": latest[0] if latest else None,
             "history": history, "state_path": str(sfile or ""),
             "physical": phys_values, "physical_fields": physical_fields,
             "physical_history": phys_history,
             "device": dev, "devices": store.distinct_devices(),
             "registry": registry.get(dev) or {},
             "cycles": cycles, "active_cycle": active[0] if active else None,
             "setups": setups,
             "cooldown_error": cooldown_error},
        )

    return app


def _trend_svg(rows: list[dict], width: int = 860, height: int = 300) -> str:
    """Server-rendered SVG polyline of value vs run index (no JS, no assets)."""
    pts = [(i, float(r["value"])) for i, r in enumerate(rows) if r["value"] is not None]
    if not pts:
        return ""
    pad, w, h = 60, width, height
    ys = [y for _, y in pts]
    y_lo, y_hi = min(ys), max(ys)
    if y_hi == y_lo:
        y_lo, y_hi = y_lo - abs(y_lo) * 0.05 - 1e-30, y_hi + abs(y_hi) * 0.05 + 1e-30
    span_x = max(len(pts) - 1, 1)

    def sx(i: float) -> float:
        return pad + (w - 2 * pad) * (i / span_x)

    def sy(y: float) -> float:
        return h - pad - (h - 2 * pad) * ((y - y_lo) / (y_hi - y_lo))

    line = " ".join(f"{sx(i):.1f},{sy(y):.1f}" for i, y in pts)
    circles = "".join(
        f'<circle cx="{sx(i):.1f}" cy="{sy(y):.1f}" r="4"><title>{rows[i]["run_id"]}\n{y:.6g}</title></circle>'
        for i, y in pts
    )
    first, last = rows[0]["started_at"][:16], rows[-1]["started_at"][:16]
    return (
        f'<svg viewBox="0 0 {w} {h}" role="img">'
        f'<line x1="{pad}" y1="{h - pad}" x2="{w - pad}" y2="{h - pad}" class="axis"/>'
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{h - pad}" class="axis"/>'
        f'<text x="{pad - 8}" y="{sy(y_hi) + 4}" text-anchor="end" class="tick">{y_hi:.4g}</text>'
        f'<text x="{pad - 8}" y="{sy(y_lo) + 4}" text-anchor="end" class="tick">{y_lo:.4g}</text>'
        f'<text x="{pad}" y="{h - pad + 18}" class="tick">{first}</text>'
        f'<text x="{w - pad}" y="{h - pad + 18}" text-anchor="end" class="tick">{last}</text>'
        f'<polyline points="{line}" class="trend"/>{circles}</svg>'
    )
