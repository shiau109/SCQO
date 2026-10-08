"""Unidirectional (cascaded) coupling by Trotterization — record-only.

Excite ONE end of a three-qubit chain, then repeat a **Trotter step** N times:
a partial swap **source -> relay**, a partial swap **relay -> sink**, a
**parametric reset** of the relay, and a per-qubit off-resonant **AC-Stark**
tone that compensates the phase each qubit picks up in the step. Every chain
qubit is read out jointly at the end, so the populations against N draw the
excitation TRANSPORT along the chain.

The relay reset is the whole mechanism. Both swaps are exchanges, so without it
the sink would feed amplitude back through the relay into the source and the
chain would be bidirectional; dumping the relay every round destroys that return
path, leaving a one-way (cascaded) coupling source -> sink. The picture to read
off the figure is therefore: the source decays, the sink fills, and the relay
stays near zero because it is emptied every round.

THE PREP is a map ``prep_operations = {qubit: operation}``, all played at one
instant before the first round; the default (None) is ``{<source>: "x180"}``,
the one excitation the picture above describes. Naming more than one qubit —
``{"q1": "x180", "q3": "x180"}`` excites both chain ends — starts the cascade
with several emitters excited: the source's emission reaches an EXCITED sink,
i.e. stimulated emission, which the cascaded master equation describes. The
Trotter round reproduces it up to one discretization effect: the relay is a
two-level ancilla, so one round cannot carry two excitations (a bosonic time
bin could), which shrinks with the angles (5Q4C 2026-09-30, |101>: the data at
N = 1-3 follow the circuit, not the continuum, at theta2 = 0.6). The phase
compensation is a property of the ROUND — single-qubit Z phases — not of the
prepared state, so the one calibrated with the single excitation carries over.
Read such a run in shot mode: the joint distribution is where it shows.

The angles are baked, not swept: each swap plays a named pair operation at its
fixed amplitude (calibrate it with ``pair_swap_flux_map`` + ``qc_n_swap_amp`` —
TUTORIAL section 12), and each qubit's Stark compensation is a fixed amplitude
FACTOR of the ``stark`` operation's baked amplitude. The only swept axis is the
Trotter-step count; ``round_count = 0`` is the prep-only baseline, the same
convention as ``qc_n_swap_amp`` / ``qc_n_stark_amp``.

Each pair names its OWN operation (``first_pair`` / ``second_pair`` are
``{"pair": ..., "operation": ...}``), because a chip does not carry the same
gate on every couple: 5Q4C has ``partial_swap`` and ``iswap`` on one pair and
only ``iswap`` on the next, which one shared operation name cannot express. The
reserved operation ``"idle"`` plays NOTHING and waits the length that pair's
swap would have taken (``idle_reference_operation``) — the control arm, with the
round's timing left identical so the comparison is about the swap and not about
when everything else happened.

WHEN THE STARK TONES PLAY is ``stark_timing``. ``"after_reset"`` (the default)
plays them once the relay's reset and its gap are over, so the round is strictly
sequential. ``"with_reset"`` starts them together with the reset, and the round
goes on when both the reset with its gap and the tones have ended — a shorter
round, which is the lever against the decay each round costs. The CIRCUIT is the
same one either way: a Z phase on one qubit commutes with the reset of another,
which is why this is a setting of one experiment and not a second experiment.
What does change is everything that belongs to the round's TIMING — the
compensation above all, so rescan it — and one refusal: with ``"with_reset"`` a
tone on ``reset_qubit`` would shift that qubit while its reset is playing (after
the reset it only meets an emptied qubit), so ``compensation_amps`` may not name
it.

WHAT THE SINK DOES **NOT** DO is reach unity, and that is the sequence, not a
miscalibration. The second swap is an exchange like the first, so the sink also
emits back into the relay — which the very next reset dumps. The chain is
therefore a DISSIPATIVE cascade: the sink settles at roughly (first-swap
transfer) x (current source population) and then follows the source down, so its
peak is a fraction of an excitation, reached within a few rounds. Capturing the
excitation instead would need the angles shaped in time, which a fixed named
operation cannot express — so a sink peak around 0.1 is the healthy case, and
"something arrived" is the most any single run of this sequence can say.

TARGETS are the chain QUBITS (not a pair composite): they are the qubits
initialized and read out, and **their order is the chain order**, which is also
the digit order of the ``joint_state`` labels. The two swap pairs, the reset
qubit and the per-qubit compensation are Parameters, not targets — the same
shape ``qubit_tomography`` uses for a multi-qubit circuit.

READOUT (the unified readout schema): digital, both modes. ``readout_mode=
"average"`` (default) stores each qubit's averaged marginal ``population`` over
the count axis; ``"shot"`` keeps every shot as per-qubit integer levels
(``state @ (target, round_count, shot_idx)``) — the full-information /
more-memory trade, and the only mode from which the JOINT chain distribution can
be reconstructed (``estimate()`` derives it, so shot mode gains a second figure
without a second acquisition).

RECORD-ONLY for the DEVICE: there is no ``update()`` and nothing lands on the
device surface; the per-qubit summary lives in ``result.fit``. A scqat estimator
(``qc_unidirectional_trotter``) draws the transport curves and the joint map
under ``analysis/chain/``, but it only VISUALIZES them and proposes nothing.

IDEAL CURVES beside the measured ones: each step's angle is the ``theta_rad``
monitor of the operation it plays (``<pair>.<op>``, written by
``qc_n_stark_amp``), read from the acquisition-time snapshot, and an ``"idle"``
step is angle 0. The estimator overlays the closed form of a perfect round —
source ``cos(theta1)^(2N)``, sink as in its docstring — computed, never fitted.
A step without a usable angle leaves its curve out, and the run says why on
stderr: the operation is undeclared or has no ``theta_rad`` yet, or
``swap_coupler_flux`` overrode the coupler amplitude that angle was measured at.
A run whose prep is anything but the source alone draws no ideal at all — the
closed form is one excitation, starting on the source.

With ``round_duration_ns`` set and the source's and sink's T1 and T2* MEASURED
(physical facts, from the same snapshot), both theories also carry decay: the
discrete Trotter model (hollow points) and the cascaded master equation (line),
with the ideal master equation left as a faint ceiling. The relay's decay is
left out — it holds the excitation only between the two swaps of a round.

There is deliberately NO transport verdict. A run reports SUCCESSFUL when it
produced a usable trace for that qubit, and nothing more: the sequence has an
``"idle"`` control arm whose chain is broken ON PURPOSE, so any fixed floor on
the sink's peak would report a correct control run as a failure. What counts as
enough transport is a question for the analysis layer, once the hardware has
said what these curves actually look like; ``sink_p_max`` is carried in
``result.fit`` as DATA so that judgement can be made later.
"""

from __future__ import annotations

from typing import ClassVar, Literal

import numpy as np
import xarray as xr
from pydantic import Field

from ..contract import DatasetContract
from ..requirements import Requirement
from ..sequence_diagram import Block, SequenceDiagram
from ._capabilities.qubit_reset import QubitResetParameters, reset_step
from ._capabilities.state_readout import (
    ReadoutModeParameters,
    states_to_joint_population,
)
from ._sim import stable_seed
from ..parameters import AveragingParameters, TargetSelection
from ..result import Outcome, Result
from ..experiment import FACT_MEASURED, Experiment
from . import register

#: the artifact subfolder the whole-chain analysis writes into. A ROLE word, not
#: an entity name: the transport curves and the joint map belong to the chain as
#: a whole, so filing them under one member would misattribute them.
CHAIN_LABEL = "chain"

#: the reserved ``operation`` value that plays no pulse at all — the round step
#: waits instead, for as long as that pair's swap would have taken. It lives in
#: the NEUTRAL layer rather than in a driver because ``simulate()`` needs it too:
#: the operation NAME is the only signal either half has that a step contributes
#: no exchange.
IDLE = "idle"

#: the ``stark_timing`` value that starts a round's stark tones together with
#: the relay's reset instead of after it. Named here because three readers must
#: agree on it: the roster gate (``chain_roles``), the sequence diagram and the
#: driver probe.
STARK_WITH_RESET = "with_reset"

#: the exact keys a pair spec carries — the roster name of the pair, and the
#: operation played on it. Two, both required.
PAIR_SPEC_KEYS = ("pair", "operation")

#: what ``prep_operations=None`` plays on the chain source: the single
#: excitation the whole sequence is designed around.
DEFAULT_PREP_OPERATION = "x180"

#: the chain of the offline demo device (``scqo.testing``): q0 -> q1 -> q2 with
#: the relay q1 reset. The two chain experiments' documents are drawn with it
#: (``Experiment.doc_parameters``), because their Parameters have no default
#: topology - and a chain's targets are the chain, not one qubit.
DOC_CHAIN: dict = {
    "targets": ["q0", "q1", "q2"],
    "first_pair": {"pair": "q0_q1", "operation": "partial_swap"},
    "second_pair": {"pair": "q1_q2", "operation": "partial_swap"},
    "reset_qubit": "q1",
}

#: what both chain experiments need of the device. The fields are the chain
#: QUBITS' and the flux lines': the operations themselves (the two swaps, the
#: relay's reset, the stark tone) are stored with the backend's configuration.
CHAIN_REQUIRES: tuple[Requirement, ...] = (
    Requirement("drive_freq_hz",
                "the prep pulses have to be on resonance, and each compensation "
                "tone is set off from its qubit's drive frequency"),
    Requirement("pi_amp", "the default prep is an x180 on the chain source"),
    Requirement("idle_flux",
                "the swaps and the relay's reset are flux pulses on top of each "
                "line's standing bias"),
    Requirement("readout_freq_hz",
                "each chain qubit's readout tone has to sit on its resonator"),
    Requirement("readout_power_dbm",
                "each chain qubit's readout has to be at its working power"),
    Requirement("readout_rotation_rad",
                "every chain qubit is discriminated in every shot: the axis each "
                "is projected on"),
    Requirement("readout_threshold",
                "every chain qubit is discriminated in every shot: what splits "
                "|0> from |1> on that axis"),
)


def chain_sequence_diagram(params, *, stark_axis: str | None = None) -> SequenceDiagram:
    """The chain's shot, for both chain experiments: reset, prep, N rounds of
    [first step, second step, relay reset, stark tones], joint readout. The
    compensation scan passes the axis its swept tone varies with. With
    ``stark_timing="with_reset"`` the tones share the reset's step."""
    (_first, first_op), (_second, second_op) = pair_specs(params)
    diagram = SequenceDiagram({
        "drive": "chain.xy", "first": "first_pair.z", "second": "second_pair.z",
        "reset": "reset_qubit.z", "readout": "chain.ro"})
    reset_step(diagram, params)
    if params.prep_operations is None or params.prep_operations:
        diagram.step(Block("drive", "prep", "gate",
                           note="prep_operations, all at once; by default an x180 "
                                "on the source"))
    gap = bool(params.operation_gap_ns)
    with diagram.repeat("x N", swept="round_count"):
        for lane, operation in (("first", first_op), ("second", second_op)):
            if operation == IDLE:
                diagram.step(Block(
                    lane, "idle", "wait",
                    note="plays nothing, for as long as idle_reference_operation's "
                         "pulse"))
            else:
                diagram.step(Block(
                    lane, "swap", "flattop",
                    note="the pair's named operation, at its stored amplitudes"))
            if gap:
                diagram.step(Block(lane, "gap", "wait"))
        reset = Block(
            "reset", "reset", "tone",
            note="reset_operation on reset_qubit: a parametric reset that empties "
                 "the relay")
        stark = None
        if stark_axis is not None:
            stark = Block(
                "drive", "stark", "tone", swept=stark_axis,
                note="on compensation_target at the swept factor, with the fixed "
                     "compensation_amps tones")
        elif params.compensation_amps:
            stark = Block(
                "drive", "stark", "tone",
                note="on each qubit in compensation_amps, all at once, "
                     "stark_detuning_hz off its drive")
        # with_reset: the tones start with the reset, so they share its column;
        # the gap stays the reset's, since it is the flux pulse that has to settle
        together = stark is not None and params.stark_timing == STARK_WITH_RESET
        if together:
            diagram.step(reset, stark)
        else:
            diagram.step(reset)
        if gap:
            diagram.step(Block("reset", "gap", "wait"))
        if stark is not None and not together:
            diagram.step(stark)
    kept = ("each shot's levels are kept" if params.readout_mode == "shot"
            else "the dataset holds each one's population")
    diagram.step(Block("readout", "readout", "acquire",
                       note=f"every chain qubit, discriminated: {kept}"))
    return diagram


def pair_specs(params) -> tuple[tuple[str, str], tuple[str, str]]:
    """``((pair, operation), (pair, operation))`` for the two round steps.

    The key-set check lives here rather than in a nested pydantic model on
    purpose: a nested model renders as a ``$ref`` in ``model_json_schema()``, and
    the CLI's schema epilog (``cli/_engine.py``) prints the field's ``type`` and
    ``description`` straight out of that schema — so the catalog, which is the
    decision surface an operator AND an AI read, would lose the type and gain an
    indirection. A plain ``dict[str, str]`` keeps the surface flat and puts the
    refusal here, where ``compensation_amps`` and ``swap_coupler_flux`` are
    already checked.

    Callers that only want the topology use ``chain_roles`` (which validates
    through this). This is for the two that also need to know WHICH operation
    each step plays: ``simulate()`` and the driver probe.
    """
    problems: list[str] = []
    out: list[tuple[str, str]] = []
    for field in ("first_pair", "second_pair"):
        spec = getattr(params, field)
        unknown = sorted(set(spec) - set(PAIR_SPEC_KEYS))
        blank = [key for key in PAIR_SPEC_KEYS if not spec.get(key)]
        if unknown or blank:
            detail = []
            if blank:
                detail.append(f"missing or empty {blank}")
            if unknown:
                detail.append(f"unknown key(s) {unknown}")
            problems.append(
                f"{field}={spec!r}: " + " and ".join(detail) + " — it takes "
                f"exactly {{'pair': <roster pair>, 'operation': <macro name, or "
                f"{IDLE!r} to play nothing>}}")
            continue
        out.append((spec["pair"], spec["operation"]))
    if problems:
        raise ValueError("qc_unidirectional_trotter: " + "; ".join(problems))
    return out[0], out[1]


def chain_roles(roster, params) -> tuple[str, str, str, dict[str, str]]:
    """``(source, relay, sink, prep)`` — the chain topology, from the two pairs,
    and the RESOLVED prep ``{qubit: operation}`` (``prep_operations=None``
    becomes ``{source: "x180"}`` here, the one place that knows the source).

    The RELAY is the one member the two swap pairs share; the source and the
    sink are their remaining members. Everything else is derived or checked
    against the roster here, so a mis-wired chain refuses with one message
    naming every problem — before any instrument time is booked. Called from
    ``define_sweep`` (the earliest hook that can see both params and roster;
    ``validate_targets`` sees only targets) and reused by the driver probe.

    The topology is the same whichever operation each step plays: an ``IDLE``
    step still names a real pair, and which member is the relay is a fact of
    the roster, not of the pulse. So this returns four names and nothing about
    the operations — those come from ``pair_specs``.
    """
    (first_name, first_op), (second_name, second_op) = pair_specs(params)

    problems: list[str] = []
    members: dict[str, list[str]] = {}
    for field, name in (("first_pair", first_name), ("second_pair", second_name)):
        entity = roster.entities.get(name)
        if entity is None:
            problems.append(f"{field}={name!r} is not in the roster")
            continue
        if entity.kind != "qubit_pair":
            problems.append(
                f"{field}={name!r} is a {entity.kind!r}, not a qubit_pair")
            continue
        roles = getattr(entity, "roles", {}) or {}
        found = [m for role in ("high", "low") for m in roles.get(role, ())]
        if len(found) != 2:
            problems.append(
                f"{field}={name!r} declares {len(found)} high/low member(s) "
                f"{found} — a pair needs exactly one of each")
            continue
        members[field] = found
    if problems:
        raise ValueError("qc_unidirectional_trotter: " + "; ".join(problems))

    first, second = members["first_pair"], members["second_pair"]
    shared = [m for m in first if m in second]
    if len(shared) != 1:
        raise ValueError(
            f"qc_unidirectional_trotter: {first_name} {first} and "
            f"{second_name} {second} share {len(shared)} member(s) "
            f"{shared} — the chain needs exactly ONE, the relay both swaps touch")
    relay = shared[0]
    source = next(m for m in first if m != relay)
    sink = next(m for m in second if m != relay)
    prep = (dict(params.prep_operations) if params.prep_operations is not None
            else {source: DEFAULT_PREP_OPERATION})

    # The parametric reset rides the reset qubit's own z line, and every Stark
    # tone rides its qubit's drive line — both are channel-existence questions,
    # which is the greenfield capability gate (see _flux_component.py).
    if (params.reset_qubit, "flux") not in roster.defaults:
        problems.append(
            f"reset_qubit={params.reset_qubit!r} has no flux channel — the "
            f"parametric reset is played on the qubit's own z line")
    for qubit in sorted(prep):
        if not prep[qubit]:
            problems.append(
                f"prep_operations names {qubit!r} with an empty operation — "
                f"leave the qubit out to prepare nothing on it")
        elif (qubit, "drive") not in roster.defaults:
            problems.append(
                f"prep_operations names {qubit!r}, which has no drive channel — "
                f"nothing to play {prep[qubit]!r} on")
    for qubit in sorted(params.compensation_amps):
        if (qubit, "drive") not in roster.defaults:
            problems.append(
                f"compensation_amps names {qubit!r}, which has no drive "
                f"channel — nothing to play {params.stark_operation!r} on")
    # After the reset a tone on the reset qubit meets an emptied qubit and does
    # nothing; DURING the reset it detunes the qubit the reset is acting on.
    if (params.stark_timing == STARK_WITH_RESET
            and params.reset_qubit in params.compensation_amps):
        problems.append(
            f"compensation_amps names the reset qubit {params.reset_qubit!r} "
            f"while stark_timing={STARK_WITH_RESET!r} plays the tones during its "
            f"reset — the tone would shift that qubit off the reset's resonance. "
            f"Drop it from compensation_amps (a tone on the reset qubit never "
            f"enters the transport), or use stark_timing='after_reset'")
    # The swap coupler flux names PAIRS, and only the two the chain declares:
    # a third name is a typo that would otherwise be silently ignored.
    operation_of = {first_name: first_op, second_name: second_op}
    for pair in sorted(getattr(params, "swap_coupler_flux", {}) or {}):
        if pair not in operation_of:
            problems.append(
                f"swap_coupler_flux names {pair!r}, which is neither first_pair "
                f"({first_name!r}) nor second_pair ({second_name!r})")
            continue
        if operation_of[pair] == IDLE:
            problems.append(
                f"swap_coupler_flux names {pair!r}, whose operation is {IDLE!r} — "
                f"an idle step plays no pulse at all, so it has no coupler "
                f"amplitude to set. Drop it from swap_coupler_flux, or give that "
                f"pair a real swap operation")
            continue
        entity = roster.entities.get(pair)
        couplers = (getattr(entity, "roles", {}) or {}).get("coupler", ())
        if not couplers:
            problems.append(
                f"swap_coupler_flux names {pair!r}, which declares no coupler role "
                f"— there is no coupler flux to set")
        elif (couplers[0], "flux") not in roster.defaults:
            problems.append(
                f"swap_coupler_flux names {pair!r}, whose coupler {couplers[0]!r} "
                f"has no flux channel")
    if problems:
        raise ValueError("qc_unidirectional_trotter: " + "; ".join(problems))
    return source, relay, sink, prep


class QcUnidirectionalTrotterParameters(TargetSelection, AveragingParameters,
                                        QubitResetParameters, ReadoutModeParameters):
    """Inputs for the unidirectional-coupling Trotter chain. ``targets`` are the
    chain QUBITS, in chain order."""

    first_pair: dict[str, str] = Field(
        ...,
        description="The FIRST round step, carrying the excitation from the chain source "
                    "into the relay, as {'pair': <roster pair>, 'operation': <name>} — "
                    "e.g. {'pair': 'q1_q2', 'operation': 'partial_swap'}. Exactly those "
                    "two keys. 'operation' is a named pair operation played at its FIXED "
                    "baked amplitude (the driver resolves it on the vendor pair and "
                    "refuses a missing one by name); a partial swap — not a full iswap — "
                    "is the Trotter step, since the angle is what discretizes the "
                    "continuous cascaded coupling. The reserved value 'idle' plays "
                    "nothing and waits as long as that pair's swap would have taken "
                    "(idle_reference_operation), which is the control arm: the round "
                    "keeps its timing, so the comparison isolates the swap.")
    second_pair: dict[str, str] = Field(
        ...,
        description="The SECOND round step, carrying the relay into the chain sink, in "
                    "the same {'pair': ..., 'operation': ...} form — e.g. {'pair': "
                    "'q2_q3', 'operation': 'iswap'}. Its pair must share exactly ONE "
                    "member with first_pair's; that shared member is the relay. Each "
                    "step names its OWN operation because a chip does not carry the same "
                    "gate on every couple, and 'idle' is accepted here too.")
    reset_qubit: str = Field(
        ...,
        description="Qubit whose parametric-reset macro fires after both swaps, dumping "
                    "the relay. Normally the relay itself: emptying it is what removes "
                    "the sink's return path and makes the coupling one-way. Its flux "
                    "(z) channel must exist — the reset is a flux-line technique.")
    compensation_amps: dict[str, float] = Field(
        default_factory=dict,
        description="Per-qubit AC-Stark compensation, as {qubit name: amplitude FACTOR "
                    "of the stark operation's baked amplitude}. The tone is off-resonant "
                    "(stark_detuning_hz), so it SHIFTS the qubit rather than rotating it, "
                    "and the shift integrated over the pulse is the phase it compensates. "
                    "A qubit absent from the map gets no tone; {} disables compensation "
                    "entirely. Dimensionless, and each factor must stay inside the "
                    "instrument's amplitude-scale range (the driver refuses by name).")
    max_rounds: int = Field(
        20, ge=0,
        description="N_max: the Trotter step is applied 0, 1, ... max_rounds times, one "
                    "sweep point each. 0 is the prep-only baseline, so the axis always "
                    "carries max_rounds + 1 points.")
    idle_reference_operation: str = Field(
        "partial_swap",
        description="Which named pair operation sets how long an 'idle' step waits: the "
                    "idle plays nothing, but holds that pair's channels for the length "
                    "of THIS operation's flux pulse, so an idle round and a swapping "
                    "round take the same time and the two are comparable. Only consulted "
                    "when a step names 'idle', and resolved per pair on the vendor tree "
                    "(the driver refuses by name when the pair does not carry it).")
    reset_operation: str = Field(
        "reset",
        description="The named MACRO on reset_qubit applied each round — the mid-circuit "
                    "parametric reset (quam_config/register_reset_macro.py registers it "
                    "under this key; the z pulse it plays is a separate name). This is "
                    "NOT reset_method, which is how targets return to |g> BETWEEN shots.")
    swap_coupler_flux: dict[str, float] = Field(
        default_factory=dict,
        description="Per-pair COUPLER flux amplitude for the swap, as {pair name: volts "
                    "at the DAC}. This is the swap ANGLE knob (TUTORIAL section 12: the "
                    "member's own flux sets resonance, the coupler sets the angle), so "
                    "this is how a run picks a (theta_1, theta_2) pair without "
                    "re-registering pulses. Absolute VOLTS, not an angle and not a "
                    "factor: theta = J_eff(Phi_c) * t_p is not linear in coupler flux, "
                    "so calibrate the curve with pair_swap_angle and read the volts off "
                    "it. A pair absent from the map plays its baked coupler amplitude; "
                    "{} leaves both pairs alone, which is the pre-existing behaviour. "
                    "Only first_pair and second_pair may be named — and not one whose "
                    "operation is 'idle', which plays no pulse to set an amplitude on. "
                    "The driver refuses a coupler that has no flux channel or is baked "
                    "at zero amplitude (unsettable, since it is the divisor of the "
                    "volts->amplitude-scale conversion).")
    stark_operation: str = Field(
        "stark",
        description="The named XY (RF) operation played on each compensated qubit at the "
                    "end of a round; its baked amplitude is the reference each "
                    "compensation factor multiplies. NOT x180 — a dedicated off-resonant "
                    "tone (the driver refuses by name if the operation is missing).")
    stark_detuning_hz: float = Field(
        50e6,
        description="FIXED off-resonant detuning (Hz) of the compensation tones from each "
                    "qubit's drive frequency. Must be off-resonant for a genuine Stark "
                    "shift (a resonant tone drives Rabi rotations instead); tune per chip. "
                    "Not a sweep axis, and shared by every compensated qubit.")
    stark_timing: Literal["after_reset", "with_reset"] = Field(
        "after_reset",
        description="When a round's compensation tones play. 'after_reset' (default): "
                    "once the reset of reset_qubit and its gap are over, so the round is "
                    "strictly sequential. 'with_reset': they start together with that "
                    "reset, and the round goes on when both the reset with its gap and "
                    "the tones have ended — a shorter round, by the tone's length when the "
                    "tone is no longer than the reset plus its gap. The circuit is the "
                    "same (a phase on one qubit commutes with the reset of another) and so "
                    "is the analysis, but the compensation belongs to the round's timing: "
                    "rescan it with qc_trotter_compensation at the SAME setting, and give "
                    "round_duration_ns the new round. With 'with_reset' a tone on "
                    "reset_qubit is refused by name — it would shift that qubit while its "
                    "reset is playing. Without any tone the two settings are one round.")
    prep_operations: dict[str, str] | None = Field(
        None,
        description="The state preparation, played ONCE before the rounds begin, as "
                    "{qubit name: named XY operation} — e.g. {'q1': 'x180', 'q3': 'x180'} "
                    "excites both chain ends. Every entry plays at the same instant, each "
                    "on its own drive line, so the map has no order. None = {<chain "
                    "source>: 'x180'}: one excitation on the first_pair member that is not "
                    "the relay, the normal case. {} prepares nothing (the chain starts in "
                    "its between-shots state). The ideal and decayed theory curves are the "
                    "single-excitation closed form from the source, so they are drawn only "
                    "when the source is the ONE qubit prepared. A multi-qubit prep leaves "
                    "the single-excitation sector; readout_mode='shot' is how to see the "
                    "joint states it passes through.")
    operation_gap_ns: int = Field(
        0, ge=0,
        description="Idle gap (ns) inserted between the operations of a round, so each "
                    "flux pulse settles before the next fires. 0 disables; the QM backend "
                    "requires a multiple of 4 ns.")
    round_duration_ns: float | None = Field(
        None, gt=0,
        description="The period of ONE round (ns), an analysis input only: it turns the "
                    "source's and sink's measured T1 / T2* into per-round decay for the "
                    "theory curves (discrete Trotter model and master equation). None = "
                    "draw them without decay. It is the ACTUAL round, longer than the sum "
                    "of the pulses: 5Q4C's gap-20 round measures 360 ns on the gateway "
                    "simulator. Nothing on the instrument changes with it.")


class QcUnidirectionalTrotterResult(Result):
    """``fit[qubit]``: that qubit's transport summary over the count axis —
    ``p_initial`` / ``p_final`` / ``p_max`` / ``p_min`` and ``n_at_max`` (the
    Trotter-step count where it peaks) — plus the run-wide ``sink_p_max`` and
    ``n_round_count``, repeated on every row so one target's record is readable
    on its own. So are the ideal curves' inputs ``theta_first_rad`` /
    ``theta_second_rad``, the ideal sink's ``ideal_sink_p_max`` /
    ``ideal_sink_n_at_max`` (NaN where an angle is unknown), and the same peak
    of the discrete model WITH T1/T2* decay, ``model_sink_p_max`` /
    ``model_sink_n_at_max`` (NaN unless ``round_duration_ns`` and both ends'
    measured T1 and T2* are known).

    The OUTCOME is ACQUISITION, not physics: SUCCESSFUL means this qubit came
    back with a finite trace. There is no transport threshold — an ``"idle"``
    control arm breaks the chain on purpose, so any fixed floor on
    ``sink_p_max`` would report a correct run as a failure. That number is
    carried here as DATA; how much transport is enough is the analysis layer's
    question. Record-only: no ``update()``, nothing written to the device."""


def _exchange_matrix(i: int, j: int, p: float, n_modes: int) -> np.ndarray:
    """Row-stochastic map: exchange bits ``i`` and ``j`` with probability ``p``.

    The classical shadow of a partial swap, and exact for every basis input —
    the exchange is the identity on ``|00>`` and ``|11>``, and sends ``|10>`` to
    ``|01>`` with probability ``sin^2(theta)`` on the single-excitation
    subspace, which is what a readout in the computational basis sees."""
    size = 1 << n_modes
    out = np.zeros((size, size))
    for state in range(size):
        bits = [(state >> (n_modes - 1 - k)) & 1 for k in range(n_modes)]
        out[state, state] += 1.0 - p
        bits[i], bits[j] = bits[j], bits[i]
        swapped = sum(b << (n_modes - 1 - k) for k, b in enumerate(bits))
        out[state, swapped] += p
    return out


def _decay_matrix(i: int, p: float, n_modes: int) -> np.ndarray:
    """Row-stochastic map: bit ``i`` drops to 0 with probability ``p``.

    Serves BOTH the relay's parametric reset (a large p, on purpose) and each
    qubit's per-round relaxation (a small one) — they are the same channel with
    different rates, so writing it twice would be two chances to get it wrong."""
    size = 1 << n_modes
    out = np.zeros((size, size))
    for state in range(size):
        bit = (state >> (n_modes - 1 - i)) & 1
        if bit == 0:
            out[state, state] = 1.0
            continue
        out[state, state] += 1.0 - p
        out[state, state & ~(1 << (n_modes - 1 - i))] += p
    return out


@register
class QcUnidirectionalTrotter(Experiment):
    """Backend-agnostic unidirectional-coupling Trotter chain. ``probe()`` is
    supplied by a driver."""

    name: ClassVar[str] = "qc_unidirectional_trotter"
    project: ClassVar[str | None] = "MpembaEP_trotter"
    requires: ClassVar[tuple[Requirement, ...]] = CHAIN_REQUIRES
    extracts: ClassVar[dict[str, str]] = {
        "p_initial": "this qubit's population before the first round",
        "p_final": "its population after the last round",
        "p_max": "its largest population over the rounds",
        "p_min": "its smallest population over the rounds",
        "n_at_max": "the round count at which it peaks",
        "sink_p_max": "the sink's largest population over the rounds; the same on "
                      "every row",
        "n_round_count": "the number of points on the round axis",
        "theta_first_rad": "the angle of the first step, read from its operation's "
                           "theta_rad; 0 for an idle step, NaN when unknown",
        "theta_second_rad": "the same for the second step",
        "ideal_sink_p_max": "the sink's peak for a perfect round with those angles; "
                            "NaN when an angle is unknown",
        "ideal_sink_n_at_max": "the round count of that peak",
        "model_sink_p_max": "the sink's peak of the round model with T1 and T2* "
                            "decay; NaN without round_duration_ns and both ends' "
                            "measured T1 and T2*",
        "model_sink_n_at_max": "the round count of that peak",
    }
    #: drawn with a compensation tone on the sink, so that the round shows its
    #: stark step; the simulated figure does not depend on it
    doc_parameters: ClassVar[dict] = {**DOC_CHAIN, "compensation_amps": {"q2": 0.3}}
    #: the round with the tone inside the reset's step. The tone is restated so
    #: the variant stands on its own: a tone on the reset qubit is refused here.
    doc_variants: ClassVar[dict[str, dict]] = {
        "with_reset": {"stark_timing": STARK_WITH_RESET,
                       "compensation_amps": {"q2": 0.3}}}

    @classmethod
    def sequence_diagram(cls, params: QcUnidirectionalTrotterParameters) -> SequenceDiagram:
        return chain_sequence_diagram(params)

    description: ClassVar[str] = (
        "Unidirectional (cascaded) coupling by Trotterization on a three-qubit chain: "
        "excite the chain source once (prep_operations can prepare other qubits too, "
        "e.g. both chain ends), then repeat N times a partial swap source->relay, "
        "a partial swap relay->sink, a parametric reset of the relay and a per-qubit "
        "off-resonant AC-Stark phase compensation, reading every chain qubit out at the "
        "end. Dumping the relay each round destroys the sink's return path, so the "
        "coupling is one-way and the populations vs N show the excitation walking from "
        "source to sink while the relay stays empty. stark_timing='with_reset' plays the "
        "compensation during the relay's reset instead of after it, for a shorter round "
        "of the same circuit. readout_mode='shot' keeps every shot "
        "and additionally reconstructs the JOINT chain distribution. Record-only "
        "diagnostic: the per-qubit summary lands in result.fit and nothing is written "
        "back to the device."
    )
    Parameters: ClassVar[type] = QcUnidirectionalTrotterParameters
    Result: ClassVar[type] = QcUnidirectionalTrotterResult
    Contract: ClassVar[DatasetContract] = DatasetContract(
        sweeps=("round_count",), sweep_units=("",),
        # readout_mode="average": each chain qubit's averaged marginal...
        variables=("population",), readout_dims=(),
        # ...readout_mode="shot": every shot's per-qubit integer level.
        alt_variables=(("state",),),
        alt_readout_dims=(("shot_idx",),),
    )
    #: none, deliberately — same rationale as pair_swap_chevron and the two
    #: qc_n_* maps: a composite's operations are DECLARED, and this sequence is
    #: run while the two-qubit gates are still being brought up. Requiring
    #: "partial_swap" would refuse exactly the chip it is for.
    required_operations: ClassVar[tuple[str, ...]] = ()

    params: QcUnidirectionalTrotterParameters

    def define_sweep(self) -> dict[str, np.ndarray]:
        # The roster gate for the pair/reset/compensation PARAMETERS lives here:
        # validate_targets cannot see params, and this still runs before the
        # backend is asked for anything.
        chain_roles(self.device.roster, self.params)
        return {"round_count": np.arange(0, self.params.max_rounds + 1, dtype=int)}

    def readout_coords(self) -> dict:
        if self.params.readout_mode == "shot":
            return {"shot_idx": np.arange(self.params.num_averages)}
        return {}

    def _round_map(self, rng, n_modes: int = 3) -> np.ndarray:
        """One Trotter step as a row-stochastic map over the chain's basis
        states (bit order source, relay, sink)."""
        # Partial-swap angles. The FIRST is small — a round has to be a Trotter
        # SLICE of a continuous coupling, not a full exchange, so the source
        # empties over many rounds. The SECOND is large: draining the relay into
        # the sink faster than the source refills it is what keeps the relay near
        # |0> and makes the reset a drain rather than the dominant loss.
        #
        # An IDLE step exchanges NOTHING. It still costs the round its time, but
        # time is not a coordinate here — the axis is the step COUNT — so the
        # idle's only trace in this model is the exchange it does not perform.
        # The angles are still drawn for the idle steps, so that idling one pair
        # leaves the OTHER pair's angle exactly where it was and the two runs
        # differ by the one thing under test.
        (_first_name, first_op), (_second_name, second_op) = pair_specs(self.params)
        p_first = float(np.sin(rng.uniform(0.30, 0.50)) ** 2)
        p_second = float(np.sin(rng.uniform(0.80, 1.10)) ** 2)
        if first_op == IDLE:
            p_first = 0.0
        if second_op == IDLE:
            p_second = 0.0
        reset_fidelity = float(rng.uniform(0.90, 0.99))
        relaxation = float(rng.uniform(0.005, 0.02))   # per round, per qubit
        step = (_exchange_matrix(0, 1, p_first, n_modes)
                @ _exchange_matrix(1, 2, p_second, n_modes)
                @ _decay_matrix(1, reset_fidelity, n_modes))
        for mode in range(n_modes):
            step = step @ _decay_matrix(mode, relaxation, n_modes)
        return step

    def simulate(self, coords: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """The Trotter step as a stochastic map on the chain's 8 basis states.

        Not per-qubit marginals with independent draws: both swaps CORRELATE the
        members (an excitation is in one place at a time), so a product-of-
        marginals simulator would draw a joint distribution the sequence can
        never produce. The chain state is propagated as a distribution over
        ``(source, relay, sink)`` basis states — exchange, exchange, relay reset,
        relaxation — and the marginals are its partial trace, so shot mode draws
        genuinely correlated outcomes. A step whose operation is ``IDLE``
        contributes no exchange, which is what makes the offline round trip show
        the control arm going flat.

        A target that is not a chain member is initialized and read out but
        never touched, so it stays in |0>."""
        n = np.asarray(coords["round_count"]).astype(int)
        targets = list(self.params.targets)
        source, relay, sink, prep = chain_roles(self.device.roster, self.params)
        chain = [source, relay, sink]
        rng = np.random.default_rng(stable_seed("qc_unidirectional_trotter", *targets))
        step = self._round_map(rng)

        # The prep: every prepared chain member excited up to pi-pulse fidelity,
        # independently — |100> by default, |101> for both ends. Each entry is
        # modelled as a pi pulse whatever its name; a prepared qubit off the
        # chain touches none of the chain's bits.
        prep_fidelity = float(rng.uniform(0.94, 0.99))
        p_excited = np.array([prep_fidelity if m in prep else 0.0 for m in chain])
        codes = np.arange(8)
        bits = np.stack([(codes >> (2 - k)) & 1 for k in range(3)])   # (3, 8)
        dist = np.prod(np.where(bits == 1, p_excited[:, None],
                                1.0 - p_excited[:, None]), axis=0)

        history = [dist]
        for _ in range(int(n.max()) if n.size else 0):
            history.append(history[-1] @ step)
        # (round, joint_state) — index BY VALUE, so a non-contiguous count axis
        # would still line up.
        joint = np.stack([history[int(v)] for v in n])

        shot_mode = self.params.readout_mode == "shot"
        num_shots = int(self.params.num_averages)

        if shot_mode:
            # One draw of the JOINT outcome per (round, shot) — inverse CDF —
            # then split into the members' levels, so the correlations survive.
            u = rng.random((n.size, num_shots))
            cumulative = np.cumsum(joint, axis=1)                      # (round, 8)
            code = (u[:, :, None] > cumulative[:, None, :]).sum(axis=2)
            code = np.clip(code, 0, 7)
            rows = []
            for name in targets:
                if name in chain:
                    rows.append(bits[chain.index(name)][code])
                else:
                    rows.append(np.zeros_like(code))

            return {"state": (("target", "round_count", "shot_idx"),
                              np.stack(rows).astype(np.int64))}

        marginals = joint @ bits.T                                     # (round, 3)
        rows = []
        for name in targets:
            if name in chain:
                row = marginals[:, chain.index(name)]
            else:
                row = np.zeros(n.size)
            rows.append(np.clip(row + rng.normal(0.0, 0.01, n.size), 0.0, 1.0))
        return {"population": (("target", "round_count"), np.stack(rows))}

    def _swap_angles(self, source: str, prep: dict[str, str]) -> dict[str, float]:
        """``{theta_first_rad, theta_second_rad}`` for the ideal curves — NaN
        where no angle applies, with the reason printed to stderr once."""
        import sys

        angles = {"theta_first_rad": float("nan"),
                  "theta_second_rad": float("nan")}
        if set(prep) != {source}:
            print(f"scqo: no ideal curves - the run preps {sorted(prep)}, and the "
                  f"closed form starts on the source {source!r} alone",
                  file=sys.stderr)
            return angles
        overridden = getattr(self.params, "swap_coupler_flux", {}) or {}
        why: list[str] = []
        for key, (pair, op) in zip(angles, pair_specs(self.params)):
            if op == IDLE:
                angles[key] = 0.0
                continue
            entity = f"{pair}.{op}"
            if pair in overridden:
                why.append(f"{entity}: swap_coupler_flux overrides the coupler "
                           f"amplitude its theta_rad was measured at")
                continue
            if entity not in self.device.roster:
                why.append(f"{entity} is not declared in the roster")
                continue
            theta = self.device.operation(pair, op).read_knob("theta_rad")
            if theta is None:
                why.append(f"{entity} has no theta_rad yet (qc_n_stark_amp "
                           f"proposes it)")
                continue
            angles[key] = float(theta)
        if why:
            print("scqo: ideal curves incomplete - " + "; ".join(why),
                  file=sys.stderr)
        return angles

    def _decay_inputs(self, source: str, sink: str) -> dict[str, float]:
        """The five decay inputs for the theory curves: ``round_duration_ns``
        and the source's and sink's MEASURED T1 / T2* (a design value is no
        measurement of this chip). All NaN unless every one is known; a
        partial set is named on stderr."""
        import sys

        keys = {"source_t1_s": (source, "t1_s"),
                "source_t2_star_s": (source, "t2_star_s"),
                "sink_t1_s": (sink, "t1_s"),
                "sink_t2_star_s": (sink, "t2_star_s")}
        nan = {"round_duration_ns": float("nan"), **{k: float("nan") for k in keys}}
        values, missing = {}, []
        for key, (qubit, field) in keys.items():
            value, tier = self.fact_sourced(qubit, field)
            if value is None or tier != FACT_MEASURED:
                missing.append(f"{qubit}.{field}")
            else:
                values[key] = float(value)
        round_ns = self.params.round_duration_ns
        if round_ns is None:
            if not missing:
                print("scqo: T1/T2* are known but round_duration_ns is not set, so "
                      "the theory curves carry no decay", file=sys.stderr)
            return nan
        if missing:
            print("scqo: theory curves without decay - no measured "
                  + ", ".join(missing), file=sys.stderr)
            return nan
        return {"round_duration_ns": float(round_ns), **values}

    def estimate(self) -> QcUnidirectionalTrotterResult:
        assert self.dataset is not None, "run() populates self.dataset before estimate()"
        source, relay, sink, prep = chain_roles(self.device.roster, self.params)
        targets = [str(t) for t in np.atleast_1d(self.dataset["target"].values)]

        if "state" in self.dataset.data_vars:
            # shot mode: reduce per-shot levels to the same averaged marginals
            # average mode stores, AND reconstruct the joint distribution the
            # shots make available for free (the target order is the digit
            # order — the chain order, as the module docstring states).
            state = self.dataset["state"].transpose("target", "round_count", "shot_idx")
            prepared = xr.Dataset({
                "population": state.clip(0, 1).mean("shot_idx"),
                "joint_population": states_to_joint_population(
                    state, member_dim="target", shot_dim="shot_idx"),
            })
        else:
            prepared = self.dataset[["population"]]
        prepared = prepared.rename({"target": "qubit"})

        # ONE analysis over the whole chain: the joint distribution spans every
        # member, so per_qubit_results' per-target split cannot draw it.
        from scqat.estimators.qc_unidirectional_trotter import (
            QcUnidirectionalTrotterEstimator,
        )
        from .._scqat import whole_dataset_results

        angles = self._swap_angles(source, prep)
        decay = self._decay_inputs(source, sink)
        analysis = whole_dataset_results(
            prepared, QcUnidirectionalTrotterEstimator(),
            artifact_dir=self.artifact_dir, label=CHAIN_LABEL,
            source=source, relay=relay, sink=sink, **angles, **decay)

        per_qubit = analysis.get("per_qubit", {})
        # DATA, not a verdict: the sink's peak is reported on every row and
        # judged nowhere. A run may be an idle control arm, where no transport
        # is the correct result — see the Result docstring.
        sink_peak = float(analysis.get("sink_p_max", float("nan")))
        result = QcUnidirectionalTrotterResult()
        for name in targets:
            fit = {k: float(v) for k, v in per_qubit.get(name, {}).items()}
            fit["sink_p_max"] = sink_peak
            fit["n_round_count"] = float(analysis.get("n_round_count", 0))
            # the ideal curves' inputs and the ideal sink peak, repeated on
            # every row like sink_p_max — the number it is read against
            for key in ("theta_first_rad", "theta_second_rad",
                        "ideal_sink_p_max", "ideal_sink_n_at_max",
                        "model_sink_p_max", "model_sink_n_at_max"):
                fit[key] = float(analysis.get(key, float("nan")))
            result.fit[name] = fit
            own_ok = bool(np.isfinite(fit.get("p_max", float("nan"))))
            result.outcomes[name] = (Outcome.SUCCESSFUL if own_ok
                                     else Outcome.FAILED)
        return result

    @classmethod
    def validate_targets(cls, roster, targets):
        """Every target is initialized, pulsed and read out in ONE circuit, so
        each needs a drive channel of its own. The chain topology itself
        (pairs, relay, reset qubit) is checked in ``define_sweep`` — those live
        in Parameters, which this hook cannot see."""
        return [f"{t}: no drive channel — it cannot be initialized or excited"
                for t in targets if (t, "drive") not in roster.defaults]

    def probe(self):  # pragma: no cover - driver half
        raise NotImplementedError("a driver backend supplies probe()")
