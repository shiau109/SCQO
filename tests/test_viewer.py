"""Run-viewer: pages render from a real (simulated-run) datastore; the only write
is tag/note editing; file serving never escapes the run folder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
# python-multipart backs FastAPI's Form(...) (the tag-edit POST). The QM lock env
# deliberately omits the viewer extras — skip there instead of erroring 14 tests
# (INSTALL §3 blesses the view venv for the suite).
pytest.importorskip("multipart")
from fastapi.testclient import TestClient  # noqa: E402

from scqo import Session, register  # noqa: E402
from scqo.experiments import QubitRamsey, QubitRelaxation, ResonatorSpectroscopy  # noqa: E402
from scqo.testing import InMemoryDevice, SimulatedBackend  # noqa: E402
from scqo.viewer.app import create_app  # noqa: E402


@register
class _VRes(ResonatorSpectroscopy):
    def probe(self):
        return None


@register
class _VRamsey(QubitRamsey):
    def probe(self):
        return None


@register
class _VT1(QubitRelaxation):
    def probe(self):
        return None


def _device() -> InMemoryDevice:
    return InMemoryDevice(
        {
            "q0": {"readout_freq": 5.95e9, "drive_freq": 3.87e9, "pi_amp": 0.2, "readout_amp": 0.25},
            "q1": {"readout_freq": 6.05e9, "drive_freq": 4.01e9, "pi_amp": 0.18, "readout_amp": 0.22},
        }
    )


@pytest.fixture(scope="module")
def lab(tmp_path_factory):
    """A datastore with three APPLIED runs (res spec, ramsey, t1), one run left
    PENDING, a SECOND sample sharing the same data_root (multi-device paths), and a
    viewer client over it all."""
    root = tmp_path_factory.mktemp("data")
    # State file at the <data_root>/<device>/ convention (THE rule since v0.5).
    (root / "devV").mkdir()
    state = root / "devV" / "scqo_state.json"
    # Cycle registry BEFORE the runs, so they are stamped with cycle + setup name
    # (a single-setup cycle auto-resolves for an unbound session — notebook parity).
    (root / "devV" / "cooldowns.toml").write_text(
        '[cdV]\nstart = 2026-07-01\nfridge = "BlueforsA"\npackaging = "PCB v3"\n\n'
        '[cdV.setup.sim_main]\nbackend = "simulated"\n',
        encoding="utf-8",
    )
    sess = Session(
        SimulatedBackend(_device()), data_root=root, device_name="devV",
        state_path=str(state), state_sync="push",
    )
    r_res = sess.run("resonator_spectroscopy", {"qubits": ["q0"]}, update="apply", tags=["cool1"])
    # a second applied run SUPERSEDES r_res's readout_freq (live-source tests)
    r_res2 = sess.run("resonator_spectroscopy", {"qubits": ["q0"]}, update="apply", tags=["cool1"])
    r_ram = sess.run("qubit_ramsey", {"qubits": ["q1"], "num_points": 201}, update="apply",
                     tags=["cool1", "special"])
    r_t1 = sess.run("qubit_relaxation", {"qubits": ["q1"]}, update="apply", tags=["cool1"])
    r_pend = sess.run("resonator_spectroscopy", {"qubits": ["q0"]}, tags=["cool1"])  # left pending
    # a q0-only physical value -> heterogeneous columns + a "(manual)" source
    sess.physical.record("q0", "g_hz", 80e6)
    sess.physical.save()

    # second physical sample; its state file follows the
    # <data_root>/<device>/scqo_state.json convention the viewer resolves
    (root / "chipZ").mkdir()
    sess_z = Session(
        SimulatedBackend(_device()), data_root=root, device_name="chipZ",
        state_path=str(root / "chipZ" / "scqo_state.json"), state_sync="push",
    )
    r_z = sess_z.run("resonator_spectroscopy", {"qubits": ["q0"]}, update="apply", tags=["zcool"])
    (root / "devices.toml").write_text(
        '[chipZ]\ndescription = "second sample on the other fridge"\n',
        encoding="utf-8",
    )

    client = TestClient(create_app(root, device_name="devV"))
    return {"client": client, "root": root, "res": r_res, "res2": r_res2, "ram": r_ram,
            "t1": r_t1, "pend": r_pend, "chipz": r_z}


def test_runs_page_lists_and_filters(lab):
    c = lab["client"]
    page = c.get("/").text
    assert lab["res"]["run_id"] in page and lab["ram"]["run_id"] in page

    filtered = c.get("/", params={"tag": "special"}).text
    assert lab["ram"]["run_id"] in filtered
    assert lab["res"]["run_id"] not in filtered


def test_run_page_shows_fit_figure_and_diff(lab):
    c = lab["client"]
    page = c.get(f"/run/{lab['ram']['run_id']}").text
    assert "t2_star_s" in page  # fit table
    assert "<img" in page and "/file/analysis/" in page  # inline figure
    assert "Device before" in page and "changed" in page  # diff with a highlighted change

    # the figure actually serves
    img_rel = page.split('/file/', 1)[1].split('"', 1)[0]
    resp = c.get(f"/run/{lab['ram']['run_id']}/file/{img_rel}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")


def test_file_endpoint_rejects_traversal(lab):
    c = lab["client"]
    resp = c.get(f"/run/{lab['res']['run_id']}/file/../../../scqo_state.json")
    assert resp.status_code == 404
    resp = c.get(f"/run/{lab['res']['run_id']}/file/..%2f..%2frecord.json")
    assert resp.status_code == 404


def test_tag_editing_is_the_only_write(lab):
    c = lab["client"]
    rid = lab["res"]["run_id"]
    resp = c.post(f"/run/{rid}/tags", data={"add": "viewer-tag", "remove": "", "note": "from browser"},
                  follow_redirects=False)
    assert resp.status_code == 303

    record_path = next(Path(lab["root"]).glob(f"devV/*/{rid}/record.json"))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert "viewer-tag" in record["tags"] and record["note"] == "from browser"

    # no other mutating routes exist
    posts = [r.path for r in c.app.routes if hasattr(r, "methods") and "POST" in (r.methods or set())]
    assert posts == [f"/run/{{run_id}}/tags".replace("{{", "{").replace("}}", "}")]


def test_trends_page_charts_t1(lab):
    c = lab["client"]
    page = c.get("/trends", params={"qubit": "q1", "quantity": "t1_s"}).text
    assert "<svg" in page and "<circle" in page
    assert lab["t1"]["run_id"] in page


def test_device_page_state_and_history(lab):
    c = lab["client"]
    page = c.get("/device").text
    assert "Device: devV" in page  # default = the configured sample
    assert "readout_amp" in page  # last-observed calibration table
    assert "Change history" in page
    assert lab["res"]["run_id"] in page  # history entry links to its run


def test_device_page_history_operator_column(lab):
    """P3 attribution: the change history shows WHO made each change."""
    import getpass

    page = lab["client"].get("/device").text
    assert "<th>operator</th>" in page
    assert getpass.getuser() in page  # this test process's login, stamped on the runs


def test_physical_panel_stable_columns_with_heterogeneous_fields(lab):
    """Only q1 was T1/Ramsey-measured (t1_s, t2_star_s) and only q0 has g_hz — the
    physical panel must show ALL observed columns with '-' for unmeasured cells
    (the first qubit's fields are NOT a valid header). The '-' assertion is scoped
    to the VALUES table itself: the page carries unrelated '-' cells (open-cycle
    end date, history run column), which must not satisfy this test."""
    page = lab["client"].get("/device").text
    assert "Physical parameters" in page
    values_table = page.split("Physical parameters", 1)[1].split("</table>", 1)[0]
    assert "<th>t1_s</th>" in values_table
    assert "<th>t2_star_s</th>" in values_table
    assert "<th>g_hz</th>" in values_table
    assert ">-</td>" in values_table  # unmeasured cells render as '-'


def test_run_page_shows_suggestions_table(lab):
    c = lab["client"]
    # a pending run: highlighted rows + the decide-at-the-terminal hint
    page = c.get(f"/run/{lab['pend']['run_id']}").text
    assert "Suggested updates" in page
    assert "<b>pending</b>" in page
    assert f"scqo accept {lab['pend']['run_id']}" in page
    # an applied run still shows its audit trail
    page_applied = c.get(f"/run/{lab['res']['run_id']}").text
    assert "Suggested updates" in page_applied and "accepted" in page_applied


def test_runs_page_pending_filter_and_updates_column(lab):
    c = lab["client"]
    page = c.get("/", params={"pending": "1"}).text
    assert lab["pend"]["run_id"] in page
    assert lab["res"]["run_id"] not in page  # applied at run time -> nothing pending
    full = c.get("/").text
    assert "1 pending" in full  # the updates column flags the undecided run


def test_trends_offer_descriptor_quantities(lab):
    page = lab["client"].get("/trends").text
    assert "t2_echo_s" in page
    assert "readout_fidelity" in page


def test_runs_page_cooldown_filter_and_column(lab):
    c = lab["client"]
    page = c.get("/", params={"cooldown": "cdV"}).text
    assert lab["res"]["run_id"] in page  # devV runs were stamped with the active cycle
    assert c.get("/", params={"cooldown": "nope"}).text.count("/run/") == 0


def test_runs_page_setup_filter_and_column(lab):
    """Runs stamped with a setup NAME show it in the setup column; ?setup= filters."""
    c = lab["client"]
    page = c.get("/").text
    assert "<th>setup</th>" in page
    # devV's single-setup cycle auto-stamped its runs with the name
    assert "<td>sim_main</td>" in _row_chunk(page, lab["res"]["run_id"])
    # chipZ has no registry -> its run carries no setup name
    assert "sim_main" not in _row_chunk(page, lab["chipz"]["run_id"])

    filtered = c.get("/", params={"setup": "sim_main"}).text
    assert lab["res"]["run_id"] in filtered and lab["ram"]["run_id"] in filtered
    assert lab["chipz"]["run_id"] not in filtered
    assert c.get("/", params={"setup": "nope"}).text.count("/run/") == 0


def test_device_page_shows_cycle_and_setup(lab):
    page = lab["client"].get("/device").text
    assert "Cooldown cycles" in page
    assert "cdV" in page and "(active)" in page
    assert "PCB v3" in page  # packaging is a cycle fact
    # the ACTIVE cycle's named-setups table: name + backend rendered
    assert "<b>sim_main</b>" in page
    assert "simulated" in page
    assert "(built-in)" in page  # simulated setups carry no instrument_config


def test_multi_device_filter_and_device_page(lab):
    c = lab["client"]
    rid = lab["chipz"]["run_id"]

    only_z = c.get("/", params={"device": "chipZ"}).text
    assert rid in only_z and lab["res"]["run_id"] not in only_z

    page_z = c.get("/device", params={"device": "chipZ"}).text
    assert "Device: chipZ" in page_z
    assert "second sample on the other fridge" in page_z  # devices.toml card rendered
    assert rid in page_z  # history via the <data_root>/<device>/scqo_state.json convention


def test_main_initializes_fresh_data_root_but_rejects_typos(tmp_path, monkeypatch):
    """A fresh (existing, empty) data_root gets an empty index automatically; a
    nonexistent path still fails loudly — a typo must never serve an empty lab."""
    import uvicorn

    from scqo.viewer.__main__ import main

    served = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: served.update(kw))

    fresh = tmp_path / "fresh_lab"
    fresh.mkdir()
    assert main(["--data-root", str(fresh), "--host", "127.0.0.1"]) == 0
    assert (fresh / "index.sqlite").is_file()  # empty index created
    assert served["host"] == "127.0.0.1"

    with pytest.raises(SystemExit, match="does not exist"):
        main(["--data-root", str(tmp_path / "typo_lab")])


def _row_chunk(page: str, run_id: str) -> str:
    """The runs-table row fragment following this run's link (up to </tr>)."""
    return page.split(f"/run/{run_id}", 1)[1].split("</tr>", 1)[0]


def test_runs_page_live_column(lab):
    """The updates column names the fields a run keeps LIVE on the device; a
    superseded run carries no live line; a pending run keeps its pending line."""
    page = lab["client"].get("/").text
    live_row = _row_chunk(page, lab["res2"]["run_id"])
    assert "live:" in live_row and "readout_freq (q0)" in live_row
    superseded_row = _row_chunk(page, lab["res"]["run_id"])
    assert "live:" not in superseded_row and "1/1 applied" in superseded_row
    pending_row = _row_chunk(page, lab["pend"]["run_id"])
    assert "1 pending" in pending_row


def test_device_page_values_link_to_source_runs(lab):
    """Strict match: each value links to the run that set it; manual writes are
    marked; the assertions are scoped to the VALUE tables (history links too)."""
    page = lab["client"].get("/device").text
    # slice to the value TABLE itself — the caption above it links the latest run
    state_table = page.split("Current calibration", 1)[1].split("<table>", 1)[1].split("</table>", 1)[0]
    assert f"/run/{lab['res2']['run_id']}" in state_table  # readout_freq -> its run
    assert f"/run/{lab['res']['run_id']}" not in state_table  # superseded: no credit
    physical_table = page.split("Physical parameters", 1)[1].split("</table>", 1)[0]
    assert f"/run/{lab['t1']['run_id']}" in physical_table  # t1_s -> its run
    assert "(manual)" in physical_table  # the notebook-written g_hz


def test_run_page_live_and_superseded_badges(lab):
    c = lab["client"]
    assert "LIVE on device" in c.get(f"/run/{lab['res2']['run_id']}").text
    superseded_page = c.get(f"/run/{lab['res']['run_id']}").text
    assert "LIVE on device" not in superseded_page
    assert f'<a href="/run/{lab["res2"]["run_id"]}" title=' in superseded_page  # superseded -> by whom


def test_device_page_flags_external_change(lab):
    """Hand-edit chipZ's state file: the strict-match rule must show the value as
    externally changed and credit NO run. (chipZ so devV fixtures stay pristine.)"""
    state_path = Path(lab["root"]) / "chipZ" / "scqo_state.json"
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["config"]["q0"]["readout_freq"] = 9.9e9  # another tool wrote the config
    state_path.write_text(json.dumps(data), encoding="utf-8")

    page = lab["client"].get("/device", params={"device": "chipZ"}).text
    state_table = page.split("Current calibration", 1)[1].split("<table>", 1)[1].split("</table>", 1)[0]
    assert "(externally changed)" in state_table
    assert f"/run/{lab['chipz']['run_id']}" not in state_table  # never a false credit


def test_trends_never_mix_samples(lab):
    c = lab["client"]
    # q0 readout_freq exists on BOTH samples ("q1 exists on every chip" problem):
    # the default trend is scoped to the configured device, not the union.
    dev = c.get("/trends", params={"qubit": "q0", "quantity": "readout_freq"}).text
    assert lab["res"]["run_id"] in dev
    assert lab["chipz"]["run_id"] not in dev
    z = c.get("/trends", params={"qubit": "q0", "quantity": "readout_freq", "device": "chipZ"}).text
    assert lab["chipz"]["run_id"] in z and lab["res"]["run_id"] not in z
