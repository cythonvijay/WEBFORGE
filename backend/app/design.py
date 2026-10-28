"""Design System & Interactive Prototype (Phase 12): schemas, token/component/decision validation,
prototype screen/flow/navigation rules, wireframe reuse, and prompt builders.

Artifacts in Phase 12 (in dependency order):
1. `design_system` — Foundations (colors, typography, spacing, grid/breakpoints, surfaces, icons, contrast/a11y),
                     Component Library (`CMP-1`, ...), and Design Decisions (`DD-1`, ...).
                     Depends on approved Research, Strategy, PRD, and all 5 Phase 11 UX artifacts (`ux == complete`).
2. `prototype`     — Interactive low-to-mid fidelity prototype (`SCR-1`, ... and `FLOW-1`, ...) reusing persisted
                     Phase 11 Wireframe layouts and Phase 12 Design System tokens/components, with navigable screen
                     links, journey happy paths, simulated form validation, dialogs, and viewport/state previews.
"""
import hashlib
import json
import re
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .ux import ViewportKind, WireframeRegion, WireframeResponsive, WireframeStates

DesignArtifactType = Literal["design_system", "prototype"]
DESIGN_ARTIFACT_TYPES: tuple[DesignArtifactType, ...] = get_args(DesignArtifactType)

DESIGN_LIMITATIONS: dict[DesignArtifactType, list[str]] = {
    "design_system": [
        "Design tokens, component specifications, and design decisions are synthesized from your approved PRD and UX artifacts.",
        "No live usability testing, eye-tracking, or A/B experiments were conducted; proposed design decisions require your review and approval.",
    ],
    "prototype": [
        "Interactive Prototype is a simulated specification player driven by your approved Wireframes and Design System tokens.",
        "All button clicks, screen transitions, form validations, and dialogs run locally against deterministic mock data—no production backend APIs or real user data are called. Production frontend code belongs to Phase 13.",
    ],
}


def S(lo: int, hi: int):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=lo, max_length=hi)]


_URL = re.compile(r"https?://|www\.", re.I)
_USABILITY_CLAIM = re.compile(r"\b(?:usability[-\s]tested|a/b[-\s]tested|eye[-\s]tracked|user[-\s]tested|focus[-\s]group)\b", re.I)


def content_hash(content: dict) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()).hexdigest()


class DesignBasisSummary(BaseModel):
    research_version: int
    strategy_version: int
    prd_version: int
    personas_version: int
    journeys_version: int
    ia_version: int
    wireframes_version: int
    ux_review_version: int
    design_system_version: int | None = None
    valid_req_ids: list[str] = Field(default_factory=list)
    valid_persona_ids: list[str] = Field(default_factory=list)
    valid_journey_ids: list[str] = Field(default_factory=list)
    valid_ia_node_ids: list[str] = Field(default_factory=list)
    valid_wireframe_ids: list[str] = Field(default_factory=list)
    valid_ux_finding_ids: list[str] = Field(default_factory=list)
    valid_component_ids: list[str] = Field(default_factory=list)
    valid_token_names: list[str] = Field(default_factory=list)
    token_preview: dict[str, str] = Field(default_factory=dict)


def build_design_basis(
    research_ver: int,
    strategy_ver: int,
    prd_doc: dict,
    prd_ver: int,
    personas_doc: dict,
    personas_ver: int,
    journeys_doc: dict,
    journeys_ver: int,
    ia_doc: dict,
    ia_ver: int,
    wireframes_doc: dict,
    wireframes_ver: int,
    ux_review_doc: dict,
    ux_review_ver: int,
    design_system_doc: dict | None = None,
    design_system_ver: int | None = None,
) -> DesignBasisSummary:
    req_ids = [r["id"] for r in prd_doc.get("functional_requirements", [])] + [r["id"] for r in prd_doc.get("non_functional_requirements", [])]
    persona_ids = [p["id"] for p in personas_doc.get("personas", [])]
    journey_ids = [j["id"] for j in journeys_doc.get("journeys", [])]
    ia_node_ids = [n["id"] for n in ia_doc.get("nodes", [])]
    wf_ids = [w["id"] for w in wireframes_doc.get("wireframes", [])]
    uxf_ids = [f["id"] for f in ux_review_doc.get("findings", [])]

    cmp_ids: list[str] = []
    token_names: list[str] = []
    token_preview: dict[str, str] = {}
    if design_system_doc:
        cmp_ids = [c["id"] for c in design_system_doc.get("components", [])]
        fnd = design_system_doc.get("foundations", {})
        for ct in fnd.get("color_tokens", []):
            token_names.append(ct["token"])
            token_preview[ct["token"]] = ct["hex_value"]
        for tt in fnd.get("typography_scale", []):
            token_names.append(tt["token"])
        for st in fnd.get("spacing_scale", []):
            token_names.append(st["token"])

    return DesignBasisSummary(
        research_version=research_ver,
        strategy_version=strategy_ver,
        prd_version=prd_ver,
        personas_version=personas_ver,
        journeys_version=journeys_ver,
        ia_version=ia_ver,
        wireframes_version=wireframes_ver,
        ux_review_version=ux_review_ver,
        design_system_version=design_system_ver,
        valid_req_ids=req_ids,
        valid_persona_ids=persona_ids,
        valid_journey_ids=journey_ids,
        valid_ia_node_ids=ia_node_ids,
        valid_wireframe_ids=wf_ids,
        valid_ux_finding_ids=uxf_ids,
        valid_component_ids=cmp_ids,
        valid_token_names=token_names,
        token_preview=token_preview,
    )


# ==============================================================================
# 1. DESIGN SYSTEM
# ==============================================================================
ComponentCategory = Literal[
    "buttons_links",
    "inputs_controls",
    "validation_feedback",
    "navigation",
    "containers_dialogs",
    "tables_lists",
    "states",
]
ComponentState = Literal["default", "hover", "focus", "active", "disabled", "loading", "error", "success", "empty"]
DecisionStatus = Literal["proposed", "reviewed", "approved"]


class ColorToken(BaseModel):
    token: str = Field(pattern=r"^--color-[a-z0-9-]+$")
    role: S(2, 100)
    hex_value: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    usage: S(5, 300)
    contrast_note: S(5, 300)


class TypographyToken(BaseModel):
    token: str = Field(pattern=r"^--font-[a-z0-9-]+$")
    role: S(2, 100)
    font_family: S(2, 120)
    font_size: S(2, 40)
    line_height: S(2, 40)
    font_weight: S(2, 40)


class SpacingToken(BaseModel):
    token: str = Field(pattern=r"^--space-[a-z0-9-]+$")
    value: S(2, 40)
    usage: S(3, 250)


class GridAndBreakpoints(BaseModel):
    columns: int = Field(ge=1, le=24, default=12)
    gutter: S(2, 60)
    max_width: S(2, 60)
    desktop: S(5, 250)
    tablet: S(5, 250)
    mobile: S(5, 250)


class SurfaceTokens(BaseModel):
    radii: list[S(3, 200)] = Field(min_length=1, max_length=8)
    borders: list[S(3, 200)] = Field(min_length=1, max_length=8)
    elevation_shadows: list[S(3, 200)] = Field(min_length=1, max_length=8)


class DesignFoundations(BaseModel):
    color_tokens: list[ColorToken] = Field(min_length=4, max_length=20)
    typography_scale: list[TypographyToken] = Field(min_length=3, max_length=15)
    spacing_scale: list[SpacingToken] = Field(min_length=3, max_length=15)
    grid_breakpoints: GridAndBreakpoints
    surface_tokens: SurfaceTokens
    icon_guidelines: list[S(5, 300)] = Field(min_length=1, max_length=10)
    accessibility_notes: list[S(5, 300)] = Field(min_length=1, max_length=10)


class ComponentSpec(BaseModel):
    id: str = Field(pattern=r"^CMP-\d+$")
    name: S(2, 120)
    category: ComponentCategory
    purpose: S(5, 400)
    variants: list[S(2, 150)] = Field(min_length=1, max_length=10)
    states: list[ComponentState] = Field(min_length=2, max_length=9)
    design_tokens_used: list[str] = Field(min_length=1, max_length=15)
    responsive_behavior: S(5, 300)
    accessibility_notes: S(5, 300)
    wireframe_ids: list[str] = Field(min_length=1, max_length=15)
    prd_requirement_ids: list[str] = Field(min_length=1, max_length=15)
    origin: Literal["ai", "user"] = "ai"
    edited_by_user: bool = False


class DesignDecision(BaseModel):
    id: str = Field(pattern=r"^DD-\d+$")
    title: S(3, 200)
    chosen_value_or_rule: S(5, 400)
    rationale: S(5, 500)
    supporting_refs: list[str] = Field(min_length=1, max_length=15)
    assumptions: list[S(5, 300)] = Field(default_factory=list, max_length=10)
    unresolved_questions: list[S(5, 300)] = Field(default_factory=list, max_length=10)
    status: DecisionStatus = "proposed"
    origin: Literal["ai", "user"] = "ai"
    edited_by_user: bool = False
    note: S(1, 300) | None = None


class DesignSystemContent(BaseModel):
    basis: DesignBasisSummary
    foundations: DesignFoundations
    components: list[ComponentSpec] = Field(min_length=1, max_length=30)
    decisions: list[DesignDecision] = Field(min_length=1, max_length=25)
    limitations: list[str] = Field(default_factory=lambda: list(DESIGN_LIMITATIONS["design_system"]))

    @model_validator(mode="after")
    def _integrity(self):
        token_names = (
            [c.token for c in self.foundations.color_tokens]
            + [t.token for t in self.foundations.typography_scale]
            + [s.token for s in self.foundations.spacing_scale]
        )
        if len(set(token_names)) != len(token_names):
            raise ValueError("duplicate design token names in foundations")
        token_set = set(token_names)

        c_ids = [c.id for c in self.components]
        if len(set(c_ids)) != len(c_ids):
            raise ValueError("duplicate component ids")
        c_names = [re.sub(r"\s+", " ", c.name.strip().lower()) for c in self.components]
        if len(set(c_names)) != len(c_names):
            raise ValueError("duplicate component names are not allowed")

        d_ids = [d.id for d in self.decisions]
        if len(set(d_ids)) != len(d_ids):
            raise ValueError("duplicate design decision ids")

        valid_wfs = set(self.basis.valid_wireframe_ids)
        valid_reqs = set(self.basis.valid_req_ids)
        valid_refs = (
            valid_wfs
            | valid_reqs
            | set(self.basis.valid_ia_node_ids)
            | set(self.basis.valid_journey_ids)
            | set(self.basis.valid_persona_ids)
            | set(self.basis.valid_ux_finding_ids)
        )

        for c in self.components:
            bad_tok = [t for t in c.design_tokens_used if t not in token_set]
            if bad_tok:
                raise ValueError(f"component {c.id}: unknown design_tokens_used {', '.join(bad_tok)}")
            bad_wf = [w for w in c.wireframe_ids if w not in valid_wfs]
            if bad_wf:
                raise ValueError(f"component {c.id}: unknown wireframe_ids {', '.join(bad_wf)}")
            bad_req = [r for r in c.prd_requirement_ids if r not in valid_reqs]
            if bad_req:
                raise ValueError(f"component {c.id}: unknown prd_requirement_ids {', '.join(bad_req)}")

        for d in self.decisions:
            bad_ref = [r for r in d.supporting_refs if r not in valid_refs]
            if bad_ref:
                raise ValueError(f"decision {d.id}: unknown supporting_refs {', '.join(bad_ref)}")

        return self


class GeneratedComponentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: S(2, 120)
    category: ComponentCategory
    purpose: S(5, 400)
    variants: list[S(2, 150)] = Field(min_length=1, max_length=8)
    states: list[ComponentState] = Field(min_length=2, max_length=9)
    design_tokens_used: list[str] = Field(min_length=1, max_length=12)
    responsive_behavior: S(5, 300)
    accessibility_notes: S(5, 300)
    wireframe_ids: list[str] = Field(min_length=1, max_length=12)
    prd_requirement_ids: list[str] = Field(min_length=1, max_length=12)


class GeneratedDesignDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: S(3, 200)
    chosen_value_or_rule: S(5, 400)
    rationale: S(5, 500)
    supporting_refs: list[str] = Field(min_length=1, max_length=12)
    assumptions: list[S(5, 300)] = Field(default_factory=list, max_length=8)
    unresolved_questions: list[S(5, 300)] = Field(default_factory=list, max_length=8)


class GeneratedDesignSystem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    foundations: DesignFoundations
    components: list[GeneratedComponentSpec] = Field(min_length=1, max_length=25)
    decisions: list[GeneratedDesignDecision] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _no_urls(self):
        blobs = [
            *self.foundations.icon_guidelines,
            *self.foundations.accessibility_notes,
            *[f"{c.name} {c.purpose} {c.responsive_behavior} {c.accessibility_notes}" for c in self.components],
            *[f"{d.title} {d.chosen_value_or_rule} {d.rationale} {' '.join(d.assumptions)} {' '.join(d.unresolved_questions)}" for d in self.decisions],
        ]
        for b in blobs:
            if _URL.search(b):
                raise ValueError("design system output must not contain external URLs")
        return self


def to_design_system_content(basis: DesignBasisSummary, gen: GeneratedDesignSystem) -> DesignSystemContent:
    token_set = {
        *(c.token for c in gen.foundations.color_tokens),
        *(t.token for t in gen.foundations.typography_scale),
        *(s.token for s in gen.foundations.spacing_scale),
    }
    valid_wfs = set(basis.valid_wireframe_ids)
    valid_reqs = set(basis.valid_req_ids)
    valid_refs = (
        valid_wfs
        | valid_reqs
        | set(basis.valid_ia_node_ids)
        | set(basis.valid_journey_ids)
        | set(basis.valid_persona_ids)
        | set(basis.valid_ux_finding_ids)
    )

    comps: list[ComponentSpec] = []
    for i, gc in enumerate(gen.components, 1):
        toks = [t for t in dict.fromkeys(gc.design_tokens_used) if t in token_set]
        if not toks:
            raise ValueError(f"AI component '{gc.name}' did not reference any defined foundation design token")
        wfs = [w for w in dict.fromkeys(gc.wireframe_ids) if w in valid_wfs]
        if not wfs:
            raise ValueError(f"AI component '{gc.name}' did not reference any valid wireframe_id")
        reqs = [r for r in dict.fromkeys(gc.prd_requirement_ids) if r in valid_reqs]
        if not reqs:
            raise ValueError(f"AI component '{gc.name}' did not reference any valid prd_requirement_id")
        comps.append(
            ComponentSpec(
                id=f"CMP-{i}",
                name=gc.name,
                category=gc.category,
                purpose=gc.purpose,
                variants=list(gc.variants),
                states=list(dict.fromkeys(gc.states)),
                design_tokens_used=toks,
                responsive_behavior=gc.responsive_behavior,
                accessibility_notes=gc.accessibility_notes,
                wireframe_ids=wfs,
                prd_requirement_ids=reqs,
                origin="ai",
                edited_by_user=False,
            )
        )

    decs: list[DesignDecision] = []
    for i, gd in enumerate(gen.decisions, 1):
        refs = [r for r in dict.fromkeys(gd.supporting_refs) if r in valid_refs]
        if not refs:
            raise ValueError(f"AI design decision '{gd.title}' did not reference any valid upstream artifact ID")
        assumptions = list(gd.assumptions)
        note: str | None = None
        if _USABILITY_CLAIM.search(f"{gd.title} {gd.chosen_value_or_rule} {gd.rationale}"):
            assumptions.append("Contains an unverified usability/testing claim; requires real user validation.")
            note = "Flagged unverified usability-testing language; kept as proposed."
        decs.append(
            DesignDecision(
                id=f"DD-{i}",
                title=gd.title,
                chosen_value_or_rule=gd.chosen_value_or_rule,
                rationale=gd.rationale,
                supporting_refs=refs,
                assumptions=assumptions,
                unresolved_questions=list(gd.unresolved_questions),
                status="proposed",
                origin="ai",
                edited_by_user=False,
                note=note,
            )
        )

    return DesignSystemContent(
        basis=basis,
        foundations=gen.foundations,
        components=comps,
        decisions=decs,
    )


# ==============================================================================
# 2. INTERACTIVE PROTOTYPE
# ==============================================================================
TriggerKind = Literal["primary_button", "secondary_button", "nav_link", "form_submit", "row_action"]
InteractionAction = Literal["navigate", "open_dialog", "submit_form", "set_state"]
UiStateKind = Literal["default", "loading", "empty", "error", "success"]


class PrototypeFormField(BaseModel):
    name: S(2, 100)
    label: S(2, 120)
    field_type: Literal["text", "textarea", "select", "checkbox", "radio", "date", "number"] = "text"
    required: bool = True
    placeholder: S(1, 150) = "Enter value…"
    default_mock_value: str = ""
    validation_rule: S(3, 300)


class PrototypeInteraction(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    trigger_label: S(2, 150)
    trigger_kind: TriggerKind = "primary_button"
    action_type: InteractionAction
    target_screen_id: str | None = None
    dialog_title: S(2, 150) | None = None
    dialog_body: S(5, 400) | None = None
    resulting_state: UiStateKind = "default"
    simulation_note: S(5, 300)


class PrototypeScreen(BaseModel):
    id: str = Field(pattern=r"^SCR-\d+$")
    wireframe_id: str = Field(pattern=r"^WF-\d+$")
    ia_node_id: str = Field(pattern=r"^IA-\d+$")
    title: S(2, 150)
    route_path: S(1, 200)
    purpose: S(5, 500)
    component_ids: list[str] = Field(min_length=1, max_length=15)
    regions: list[WireframeRegion] = Field(min_length=1, max_length=8)
    form_fields: list[PrototypeFormField] = Field(default_factory=list, max_length=15)
    interactions: list[PrototypeInteraction] = Field(min_length=1, max_length=15)
    states: WireframeStates
    responsive_behavior: WireframeResponsive
    mock_data_note: S(5, 300)
    journey_ids: list[str] = Field(min_length=1, max_length=10)
    prd_requirement_ids: list[str] = Field(min_length=1, max_length=15)
    origin: Literal["ai", "user"] = "ai"
    edited_by_user: bool = False


class PrototypeFlow(BaseModel):
    id: str = Field(pattern=r"^FLOW-\d+$")
    journey_id: str = Field(pattern=r"^J-\d+$")
    title: S(3, 200)
    start_screen_id: str = Field(pattern=r"^SCR-\d+$")
    ordered_screen_ids: list[str] = Field(min_length=1, max_length=15)
    happy_path_steps: list[S(5, 300)] = Field(min_length=1, max_length=12)


class PrototypeContent(BaseModel):
    basis: DesignBasisSummary
    screens: list[PrototypeScreen] = Field(min_length=1, max_length=30)
    flows: list[PrototypeFlow] = Field(min_length=1, max_length=20)
    limitations: list[str] = Field(default_factory=lambda: list(DESIGN_LIMITATIONS["prototype"]))

    @model_validator(mode="after")
    def _integrity(self):
        scr_ids = [s.id for s in self.screens]
        if len(set(scr_ids)) != len(scr_ids):
            raise ValueError("duplicate prototype screen ids")
        scr_set = set(scr_ids)

        flow_ids = [f.id for f in self.flows]
        if len(set(flow_ids)) != len(flow_ids):
            raise ValueError("duplicate prototype flow ids")

        valid_wfs = set(self.basis.valid_wireframe_ids)
        valid_ia = set(self.basis.valid_ia_node_ids)
        valid_cmps = set(self.basis.valid_component_ids)
        valid_js = set(self.basis.valid_journey_ids)
        valid_reqs = set(self.basis.valid_req_ids)

        covered_wfs = set()
        for s in self.screens:
            if s.wireframe_id not in valid_wfs:
                raise ValueError(f"screen {s.id}: unknown wireframe_id '{s.wireframe_id}'")
            covered_wfs.add(s.wireframe_id)
            if s.ia_node_id not in valid_ia:
                raise ValueError(f"screen {s.id}: unknown ia_node_id '{s.ia_node_id}'")
            bad_c = [c for c in s.component_ids if c not in valid_cmps]
            if bad_c:
                raise ValueError(f"screen {s.id}: unknown component_ids {', '.join(bad_c)}")
            bad_j = [j for j in s.journey_ids if j not in valid_js]
            if bad_j:
                raise ValueError(f"screen {s.id}: unknown journey_ids {', '.join(bad_j)}")
            bad_r = [r for r in s.prd_requirement_ids if r not in valid_reqs]
            if bad_r:
                raise ValueError(f"screen {s.id}: unknown prd_requirement_ids {', '.join(bad_r)}")

            ix_ids = [ix.id for ix in s.interactions]
            if len(set(ix_ids)) != len(ix_ids):
                raise ValueError(f"screen {s.id}: duplicate interaction ids")
            for ix in s.interactions:
                if ix.action_type == "navigate" and not ix.target_screen_id:
                    raise ValueError(f"screen {s.id} interaction {ix.id}: navigate action requires target_screen_id")
                if ix.target_screen_id is not None and ix.target_screen_id not in scr_set:
                    raise ValueError(f"screen {s.id} interaction {ix.id}: unknown target_screen_id '{ix.target_screen_id}'")
                if ix.action_type == "open_dialog" and (not ix.dialog_title or not ix.dialog_body):
                    raise ValueError(f"screen {s.id} interaction {ix.id}: open_dialog requires dialog_title and dialog_body")

        missing_wfs = [w for w in self.basis.valid_wireframe_ids if w not in covered_wfs]
        if missing_wfs:
            raise ValueError(f"prototype is missing required wireframe screen(s): {', '.join(missing_wfs)}")

        covered_js = set()
        for fl in self.flows:
            if fl.journey_id not in valid_js:
                raise ValueError(f"flow {fl.id}: unknown journey_id '{fl.journey_id}'")
            covered_js.add(fl.journey_id)
            if fl.start_screen_id not in scr_set:
                raise ValueError(f"flow {fl.id}: unknown start_screen_id '{fl.start_screen_id}'")
            bad_scr = [sid for sid in fl.ordered_screen_ids if sid not in scr_set]
            if bad_scr:
                raise ValueError(f"flow {fl.id}: unknown ordered_screen_ids {', '.join(bad_scr)}")
            if fl.ordered_screen_ids[0] != fl.start_screen_id:
                raise ValueError(f"flow {fl.id}: ordered_screen_ids must begin with start_screen_id '{fl.start_screen_id}'")

        missing_js = [j for j in self.basis.valid_journey_ids if j not in covered_js]
        if missing_js:
            raise ValueError(f"prototype is missing required journey flow(s): {', '.join(missing_js)}")

        return self


class GeneratedPrototypeScreen(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^SCR-\d+$")
    wireframe_id: str
    ia_node_id: str
    title: S(2, 150)
    route_path: S(1, 200)
    purpose: S(5, 500)
    component_ids: list[str] = Field(min_length=1, max_length=12)
    form_fields: list[PrototypeFormField] = Field(default_factory=list, max_length=10)
    interactions: list[PrototypeInteraction] = Field(min_length=1, max_length=10)
    mock_data_note: S(5, 300)
    journey_ids: list[str] = Field(min_length=1, max_length=8)
    prd_requirement_ids: list[str] = Field(min_length=1, max_length=12)


class GeneratedPrototype(BaseModel):
    model_config = ConfigDict(extra="forbid")
    screens: list[GeneratedPrototypeScreen] = Field(min_length=1, max_length=25)
    flows: list[PrototypeFlow] = Field(min_length=1, max_length=15)

    @model_validator(mode="after")
    def _no_urls(self):
        for s in self.screens:
            for b in [s.title, s.purpose, s.mock_data_note, *[ix.simulation_note for ix in s.interactions]]:
                if _URL.search(b):
                    raise ValueError("prototype output must not contain external URLs")
        return self


def to_prototype_content(basis: DesignBasisSummary, wireframes_content: dict, gen: GeneratedPrototype) -> PrototypeContent:
    """Build PrototypeContent by merging persisted Phase 11 wireframe layout/state specs with generated interactive behaviors."""
    wf_by_id = {w["id"]: w for w in wireframes_content.get("wireframes", [])}
    valid_cmps = set(basis.valid_component_ids)
    valid_js = set(basis.valid_journey_ids)
    valid_reqs = set(basis.valid_req_ids)

    screens: list[PrototypeScreen] = []
    for gs in gen.screens:
        wf = wf_by_id.get(gs.wireframe_id)
        if wf is None:
            raise ValueError(f"AI prototype screen {gs.id} referenced unknown wireframe_id '{gs.wireframe_id}'")
        cmps = [c for c in dict.fromkeys(gs.component_ids) if c in valid_cmps]
        if not cmps:
            raise ValueError(f"AI prototype screen {gs.id} did not reference any valid Design System component_id")
        js = [j for j in dict.fromkeys(gs.journey_ids) if j in valid_js]
        if not js:
            raise ValueError(f"AI prototype screen {gs.id} did not reference any valid journey_id")
        reqs = [r for r in dict.fromkeys(gs.prd_requirement_ids) if r in valid_reqs]
        if not reqs:
            raise ValueError(f"AI prototype screen {gs.id} did not reference any valid prd_requirement_id")

        # Seed form fields from wireframe if AI omitted them
        fields = list(gs.form_fields)
        if not fields and wf.get("form_fields"):
            fields = [
                PrototypeFormField(
                    name=f["name"],
                    label=f["name"],
                    field_type=f["field_type"],
                    required=f["required"],
                    placeholder=f"Enter {f['name'].lower()}…",
                    default_mock_value="",
                    validation_rule=f["validation_rule"],
                )
                for f in wf["form_fields"]
            ]

        screens.append(
            PrototypeScreen(
                id=gs.id,
                wireframe_id=gs.wireframe_id,
                ia_node_id=gs.ia_node_id,
                title=gs.title,
                route_path=gs.route_path,
                purpose=gs.purpose,
                component_ids=cmps,
                regions=[WireframeRegion.model_validate(r) for r in wf["regions"]],
                form_fields=fields,
                interactions=list(gs.interactions),
                states=WireframeStates.model_validate(wf["states"]),
                responsive_behavior=WireframeResponsive.model_validate(wf["responsive_behavior"]),
                mock_data_note=gs.mock_data_note,
                journey_ids=js,
                prd_requirement_ids=reqs,
                origin="ai",
                edited_by_user=False,
            )
        )

    return PrototypeContent(basis=basis, screens=screens, flows=list(gen.flows))


# ==============================================================================
# PROMPT BUILDERS
# ==============================================================================
def build_design_system_prompt(
    basis: DesignBasisSummary,
    prd_content: dict,
    personas_content: dict,
    ia_content: dict,
    wireframes_content: dict,
    ux_review_content: dict,
) -> str:
    ctx = {
        "basis": basis.model_dump(mode="json"),
        "personas": [{"id": p["id"], "name": p["name"], "accessibility_device_notes": p["accessibility_device_notes"]} for p in personas_content.get("personas", [])],
        "ia_nodes": [{"id": n["id"], "name": n["name"], "navigation_group": n["navigation_group"]} for n in ia_content.get("nodes", [])],
        "wireframes": [{"id": w["id"], "page_name": w["page_name"], "regions": w["regions"], "form_fields": w["form_fields"], "prd_requirement_ids": w["prd_requirement_ids"]} for w in wireframes_content.get("wireframes", [])],
        "ux_review_summary": ux_review_content.get("summary", ""),
        "prd_requirements": [{"id": r["id"], "title": r["title"]} for r in prd_content.get("functional_requirements", [])],
    }
    return (
        "You are a design systems architect defining Foundations, Component Specifications (`CMP-1`, ...), and Design Decisions (`DD-1`, ...) "
        "from approved Phase 11 UX Wireframes, Personas, IA, UX Review, and Phase 10 PRD requirements.\n"
        "Hard rules:\n"
        "- Never invent usability test results, eye-tracking studies, A/B test metrics, or external URLs.\n"
        "- Every component must reference defined foundation token names in `design_tokens_used`, valid `wireframe_ids` from `basis.valid_wireframe_ids`, "
        "and valid `prd_requirement_ids` from `basis.valid_req_ids`.\n"
        "- Every design decision must reference valid upstream IDs in `supporting_refs`.\n"
        f"<project_context>{json.dumps(ctx, ensure_ascii=False)}</project_context>"
    )


def build_prototype_prompt(
    basis: DesignBasisSummary,
    prd_content: dict,
    journeys_content: dict,
    ia_content: dict,
    wireframes_content: dict,
    design_system_content: dict,
) -> str:
    ctx = {
        "basis": basis.model_dump(mode="json"),
        "wireframes": [{"id": w["id"], "page_name": w["page_name"], "ia_node_id": w["ia_node_id"], "primary_actions": w["primary_actions"], "secondary_actions": w["secondary_actions"], "form_fields": w["form_fields"], "journey_ids": w["journey_ids"], "prd_requirement_ids": w["prd_requirement_ids"]} for w in wireframes_content.get("wireframes", [])],
        "journeys": [{"id": j["id"], "title": j["title"], "entry_point": j["entry_point"], "desired_outcome": j["desired_outcome"], "prd_requirement_ids": j["prd_requirement_ids"]} for j in journeys_content.get("journeys", [])],
        "ia_nodes": [{"id": n["id"], "name": n["name"], "path": n["path"]} for n in ia_content.get("nodes", [])],
        "components": [{"id": c["id"], "name": c["name"], "category": c["category"]} for c in design_system_content.get("components", [])],
        "prd_requirements": [{"id": r["id"], "title": r["title"]} for r in prd_content.get("functional_requirements", [])],
    }
    return (
        "You are an interactive prototype architect building navigable Prototype Screens (`SCR-1`, ...) and Journey Flows (`FLOW-1`, ...) "
        "from approved Phase 11 Wireframes, User Journeys, IA, and Phase 12 Design System components.\n"
        "Hard rules:\n"
        "- Every wireframe in `basis.valid_wireframe_ids` must be represented by a screen (`SCR-1`, `SCR-2`, ...); its layout regions and states are automatically reused from the persisted wireframe.\n"
        "- Every journey in `basis.valid_journey_ids` must be represented by a flow (`FLOW-1`, ...).\n"
        "- Every `navigate` interaction must reference a valid `target_screen_id` (`SCR-N`), and all `component_ids` must exist in `basis.valid_component_ids`.\n"
        "- Label all interactions and mock data honestly as local prototype simulations. Never include external URLs.\n"
        f"<project_context>{json.dumps(ctx, ensure_ascii=False)}</project_context>"
    )
