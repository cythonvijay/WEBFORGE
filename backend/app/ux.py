"""UX Design & Experience Workflow (Phase 11): schemas, cross-artifact provenance, IA tree validation,
wireframe specifications, and deterministic + AI UX review rules.

Artifacts in Phase 11 (in dependency order):
1. `personas`   — Research- and PRD-grounded user personas (depends on approved Research, Strategy, PRD)
2. `journeys`   — Goal-driven user journeys (depends on approved Personas + upstream)
3. `ia`         — Hierarchical information architecture (depends on approved Personas, Journeys + upstream)
4. `wireframes` — Structured low-fidelity wireframe specifications (depends on approved Personas, Journeys, IA + upstream)
5. `ux_review`  — Deterministic + AI UX consistency & coverage review (depends on approved Personas, Journeys, IA, Wireframes + upstream)
"""
import hashlib
import json
import re
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

ArtifactType = Literal["personas", "journeys", "ia", "wireframes", "ux_review"]
ARTIFACT_TYPES: tuple[ArtifactType, ...] = get_args(ArtifactType)

UX_LIMITATIONS: dict[ArtifactType, list[str]] = {
    "personas": [
        "Personas are synthesized from your approved Research, Strategy, and PRD. No live user interviews, surveys, or demographic studies were conducted.",
        "Attributes not backed by confirmed Discovery facts or user-examined Research sources are labeled as hypotheses or assumptions.",
    ],
    "journeys": [
        "User journeys model expected flows for PRD-supported goals; user thoughts and questions are hypotheses until validated with real users.",
        "Every journey must reference an approved Persona and at least one approved PRD requirement.",
    ],
    "ia": [
        "Information architecture defines page hierarchy, navigation groups, and requirement traceability from your approved PRD and user journeys.",
        "Node IDs must be unique and parent-child relationships must form a valid acyclic tree.",
    ],
    "wireframes": [
        "Wireframes are structured low-fidelity layout and state specifications rendered deterministically in the browser—not static screenshots or production code.",
        "Production frontend implementation belongs to Phase 13.",
    ],
    "ux_review": [
        "UX Review combines deterministic cross-artifact consistency/coverage checks with AI design review suggestions.",
        "No live usability testing, automated accessibility audit, or user research session was performed; critical blockers must be resolved or explicitly accepted with a documented rationale before completing the UX stage.",
    ],
}


def S(lo: int, hi: int):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=lo, max_length=hi)]


_URL = re.compile(r"https?://|www\.", re.I)
_NUMERIC_OR_SURVEY = re.compile(
    r"\d+(?:[.,]\d+)?\s?(?:%|percent\b|million\b|billion\b|thousand\b)|[$€£]\s?\d|\b(?:surveyed|interviewed|respondents)\b",
    re.I,
)


def content_hash(content: dict) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()).hexdigest()


class UxBasisSummary(BaseModel):
    research_version: int
    strategy_version: int
    prd_version: int
    personas_version: int | None = None
    journeys_version: int | None = None
    ia_version: int | None = None
    wireframes_version: int | None = None
    valid_req_ids: list[str] = Field(default_factory=list)
    valid_story_ids: list[str] = Field(default_factory=list)
    valid_evidence_refs: list[str] = Field(default_factory=list)
    confirmed_evidence_refs: list[str] = Field(default_factory=list)
    valid_persona_ids: list[str] = Field(default_factory=list)
    valid_journey_ids: list[str] = Field(default_factory=list)
    valid_ia_node_ids: list[str] = Field(default_factory=list)
    valid_wireframe_ids: list[str] = Field(default_factory=list)


def build_ux_basis(
    research_doc: dict,
    research_ver: int,
    strategy_doc: dict,
    strategy_ver: int,
    prd_doc: dict,
    prd_ver: int,
    personas_doc: dict | None = None,
    personas_ver: int | None = None,
    journeys_doc: dict | None = None,
    journeys_ver: int | None = None,
    ia_doc: dict | None = None,
    ia_ver: int | None = None,
    wireframes_doc: dict | None = None,
    wireframes_ver: int | None = None,
) -> UxBasisSummary:
    req_ids = [r["id"] for r in prd_doc.get("functional_requirements", [])] + [r["id"] for r in prd_doc.get("non_functional_requirements", [])]
    story_ids = [s["id"] for s in prd_doc.get("user_stories", [])]

    ev_refs: list[str] = []
    conf_refs: list[str] = []
    inputs = strategy_doc.get("inputs", {})
    for item in inputs.get("confirmed_facts", []):
        ev_refs.append(item["ref_id"])
        conf_refs.append(item["ref_id"])
    for item in inputs.get("ai_suggestions", []):
        ev_refs.append(item["ref_id"])
    for item in inputs.get("unresolved_assumptions", []):
        ev_refs.append(item["ref_id"])
    for f in research_doc.get("findings", []):
        ref = f"res-{f['id']}"
        if ref not in ev_refs:
            ev_refs.append(ref)
        if f.get("evidence") in ("verified_source", "user_provided"):
            conf_refs.append(ref)
    for g in strategy_doc.get("goals", []):
        ev_refs.append(g["id"])
        if g.get("status") == "user_confirmed":
            conf_refs.append(g["id"])
    for u in strategy_doc.get("target_users", []):
        ev_refs.append(u["id"])
        if u.get("status") == "user_confirmed":
            conf_refs.append(u["id"])
    for r in strategy_doc.get("recommendations", []):
        ev_refs.append(r["id"])
        if r.get("status") in ("grounded_in_confirmed", "supported_by_research"):
            conf_refs.append(r["id"])
    for s in story_ids:
        ev_refs.append(s)
    for rq in req_ids:
        ev_refs.append(rq)

    persona_ids = [p["id"] for p in (personas_doc or {}).get("personas", [])]
    journey_ids = [j["id"] for j in (journeys_doc or {}).get("journeys", [])]
    ia_node_ids = [n["id"] for n in (ia_doc or {}).get("nodes", [])]
    wf_ids = [w["id"] for w in (wireframes_doc or {}).get("wireframes", [])]

    return UxBasisSummary(
        research_version=research_ver,
        strategy_version=strategy_ver,
        prd_version=prd_ver,
        personas_version=personas_ver,
        journeys_version=journeys_ver,
        ia_version=ia_ver,
        wireframes_version=wireframes_ver,
        valid_req_ids=req_ids,
        valid_story_ids=story_ids,
        valid_evidence_refs=list(dict.fromkeys(ev_refs)),
        confirmed_evidence_refs=list(dict.fromkeys(conf_refs)),
        valid_persona_ids=persona_ids,
        valid_journey_ids=journey_ids,
        valid_ia_node_ids=ia_node_ids,
        valid_wireframe_ids=wf_ids,
    )


# ==============================================================================
# 1. PERSONAS
# ==============================================================================
PersonaEvidenceStatus = Literal["evidence_backed", "mixed", "hypothesis"]


class Persona(BaseModel):
    id: str = Field(pattern=r"^P-\d+$")
    name: S(2, 120)
    segment: S(3, 250)
    context: S(10, 800)
    goals: list[S(5, 300)] = Field(min_length=1, max_length=10)
    tasks_behaviors: list[S(5, 300)] = Field(min_length=1, max_length=10)
    needs_pain_points: list[S(5, 300)] = Field(min_length=1, max_length=10)
    frustrations_barriers: list[S(5, 300)] = Field(default_factory=list, max_length=10)
    accessibility_device_notes: list[S(5, 300)] = Field(min_length=1, max_length=8)
    motivations: list[S(5, 300)] = Field(default_factory=list, max_length=8)
    user_story_ids: list[str] = Field(default_factory=list, max_length=12)
    prd_requirement_ids: list[str] = Field(min_length=1, max_length=15)
    evidence_refs: list[str] = Field(default_factory=list, max_length=15)
    unverified_assumptions: list[S(5, 300)] = Field(default_factory=list, max_length=10)
    evidence_status: PersonaEvidenceStatus = "hypothesis"
    needs_evidence: bool = False
    origin: Literal["ai", "user"] = "ai"
    edited_by_user: bool = False
    note: S(1, 300) | None = None


class PersonasContent(BaseModel):
    basis: UxBasisSummary
    personas: list[Persona] = Field(min_length=1, max_length=12)
    limitations: list[str] = Field(default_factory=lambda: list(UX_LIMITATIONS["personas"]))

    @model_validator(mode="after")
    def _integrity(self):
        ids = [p.id for p in self.personas]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate persona ids")
        names = [re.sub(r"\s+", " ", p.name.strip().lower()) for p in self.personas]
        if len(set(names)) != len(names):
            raise ValueError("duplicate persona names are not allowed")

        valid_reqs = set(self.basis.valid_req_ids)
        valid_stories = set(self.basis.valid_story_ids)
        valid_ev = set(self.basis.valid_evidence_refs)
        conf_ev = set(self.basis.confirmed_evidence_refs)

        for p in self.personas:
            bad_reqs = [r for r in p.prd_requirement_ids if r not in valid_reqs]
            if bad_reqs:
                raise ValueError(f"persona {p.id}: unknown prd_requirement_ids {', '.join(bad_reqs)}")
            bad_stories = [s for s in p.user_story_ids if s not in valid_stories]
            if bad_stories:
                raise ValueError(f"persona {p.id}: unknown user_story_ids {', '.join(bad_stories)}")
            bad_ev = [e for e in p.evidence_refs if e not in valid_ev]
            if bad_ev:
                raise ValueError(f"persona {p.id}: unknown evidence_refs {', '.join(bad_ev)}")
            if p.evidence_status == "evidence_backed" and not any(e in conf_ev for e in p.evidence_refs):
                raise ValueError(f"persona {p.id}: evidence_backed requires at least one confirmed or examined evidence_ref")
            if p.evidence_status == "hypothesis" or not p.evidence_refs or len(p.unverified_assumptions) > 0:
                p.needs_evidence = True
        return self


class GeneratedPersona(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: S(2, 120)
    segment: S(3, 250)
    context: S(10, 800)
    goals: list[S(5, 300)] = Field(min_length=1, max_length=8)
    tasks_behaviors: list[S(5, 300)] = Field(min_length=1, max_length=8)
    needs_pain_points: list[S(5, 300)] = Field(min_length=1, max_length=8)
    frustrations_barriers: list[S(5, 300)] = Field(default_factory=list, max_length=8)
    accessibility_device_notes: list[S(5, 300)] = Field(min_length=1, max_length=6)
    motivations: list[S(5, 300)] = Field(default_factory=list, max_length=6)
    user_story_ids: list[str] = Field(default_factory=list, max_length=10)
    prd_requirement_ids: list[str] = Field(min_length=1, max_length=12)
    evidence_refs: list[str] = Field(default_factory=list, max_length=12)
    unverified_assumptions: list[S(5, 300)] = Field(default_factory=list, max_length=8)
    evidence_status: PersonaEvidenceStatus = "hypothesis"


class GeneratedPersonas(BaseModel):
    model_config = ConfigDict(extra="forbid")
    personas: list[GeneratedPersona] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def _no_urls(self):
        for p in self.personas:
            blobs = [p.name, p.segment, p.context, *p.goals, *p.tasks_behaviors, *p.needs_pain_points, *p.frustrations_barriers, *p.accessibility_device_notes, *p.motivations, *p.unverified_assumptions]
            for b in blobs:
                if _URL.search(b):
                    raise ValueError("personas output must not contain URLs")
        return self


def to_personas_content(basis: UxBasisSummary, gen: GeneratedPersonas) -> PersonasContent:
    valid_reqs = set(basis.valid_req_ids)
    valid_stories = set(basis.valid_story_ids)
    valid_ev = set(basis.valid_evidence_refs)
    conf_ev = set(basis.confirmed_evidence_refs)

    out = []
    for i, gp in enumerate(gen.personas, 1):
        reqs = [r for r in dict.fromkeys(gp.prd_requirement_ids) if r in valid_reqs]
        if not reqs and basis.valid_req_ids:
            reqs = [basis.valid_req_ids[0]]
        stories = [s for s in dict.fromkeys(gp.user_story_ids) if s in valid_stories]
        evs = [e for e in dict.fromkeys(gp.evidence_refs) if e in valid_ev]

        st: PersonaEvidenceStatus = gp.evidence_status
        note: str | None = None
        if st == "evidence_backed" and not any(e in conf_ev for e in evs):
            st = "mixed" if evs else "hypothesis"
            note = "Adjusted from evidence_backed because no confirmed fact or examined source was cited."
        elif not evs and st != "hypothesis":
            st = "hypothesis"
            note = "No upstream evidence reference cited; classified as hypothesis."

        all_text = " ".join([gp.context, *gp.goals, *gp.tasks_behaviors, *gp.needs_pain_points, *gp.frustrations_barriers, *gp.motivations])
        if _NUMERIC_OR_SURVEY.search(all_text) and st != "hypothesis":
            st = "hypothesis"
            note = "Contains numeric/statistical or interview/survey language without verified study data; downgraded to hypothesis."

        needs_ev = st == "hypothesis" or not evs or len(gp.unverified_assumptions) > 0
        out.append(
            Persona(
                id=f"P-{i}",
                name=gp.name,
                segment=gp.segment,
                context=gp.context,
                goals=list(gp.goals),
                tasks_behaviors=list(gp.tasks_behaviors),
                needs_pain_points=list(gp.needs_pain_points),
                frustrations_barriers=list(gp.frustrations_barriers),
                accessibility_device_notes=list(gp.accessibility_device_notes),
                motivations=list(gp.motivations),
                user_story_ids=stories,
                prd_requirement_ids=reqs,
                evidence_refs=evs,
                unverified_assumptions=list(gp.unverified_assumptions),
                evidence_status=st,
                needs_evidence=needs_ev,
                origin="ai",
                edited_by_user=False,
                note=note,
            )
        )
    return PersonasContent(basis=basis, personas=out)


# ==============================================================================
# 2. USER JOURNEYS
# ==============================================================================
class JourneyStage(BaseModel):
    stage_number: int = Field(ge=1, le=20)
    stage_name: S(2, 150)
    user_actions: list[S(5, 300)] = Field(min_length=1, max_length=8)
    thoughts_questions: list[S(5, 300)] = Field(default_factory=list, max_length=8)
    thoughts_status: Literal["hypothesis", "evidence_backed"] = "hypothesis"
    touchpoints: list[S(2, 200)] = Field(min_length=1, max_length=8)
    pain_points: list[S(5, 300)] = Field(default_factory=list, max_length=8)
    system_responses: list[S(5, 300)] = Field(min_length=1, max_length=8)
    failure_recovery_paths: list[S(5, 400)] = Field(min_length=1, max_length=8)


class UserJourney(BaseModel):
    id: str = Field(pattern=r"^J-\d+$")
    title: S(3, 200)
    persona_id: str = Field(pattern=r"^P-\d+$")
    scenario: S(10, 600)
    desired_outcome: S(5, 400)
    entry_point: S(3, 300)
    preconditions: list[S(3, 300)] = Field(default_factory=list, max_length=8)
    stages: list[JourneyStage] = Field(min_length=1, max_length=12)
    accessibility_considerations: list[S(5, 300)] = Field(min_length=1, max_length=8)
    prd_requirement_ids: list[str] = Field(min_length=1, max_length=15)
    opportunities: list[S(5, 300)] = Field(default_factory=list, max_length=8)
    unresolved_questions: list[S(5, 300)] = Field(default_factory=list, max_length=8)
    origin: Literal["ai", "user"] = "ai"
    edited_by_user: bool = False


class JourneysContent(BaseModel):
    basis: UxBasisSummary
    journeys: list[UserJourney] = Field(min_length=1, max_length=20)
    limitations: list[str] = Field(default_factory=lambda: list(UX_LIMITATIONS["journeys"]))

    @model_validator(mode="after")
    def _integrity(self):
        ids = [j.id for j in self.journeys]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate journey ids")
        valid_personas = set(self.basis.valid_persona_ids)
        valid_reqs = set(self.basis.valid_req_ids)
        for j in self.journeys:
            if j.persona_id not in valid_personas:
                raise ValueError(f"journey {j.id}: unknown persona_id '{j.persona_id}'")
            bad_reqs = [r for r in j.prd_requirement_ids if r not in valid_reqs]
            if bad_reqs:
                raise ValueError(f"journey {j.id}: unknown prd_requirement_ids {', '.join(bad_reqs)}")
            for idx, st in enumerate(j.stages, 1):
                st.stage_number = idx
        return self


class GeneratedJourneyStage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage_name: S(2, 150)
    user_actions: list[S(5, 300)] = Field(min_length=1, max_length=6)
    thoughts_questions: list[S(5, 300)] = Field(default_factory=list, max_length=6)
    touchpoints: list[S(2, 200)] = Field(min_length=1, max_length=6)
    pain_points: list[S(5, 300)] = Field(default_factory=list, max_length=6)
    system_responses: list[S(5, 300)] = Field(min_length=1, max_length=6)
    failure_recovery_paths: list[S(5, 400)] = Field(min_length=1, max_length=6)


class GeneratedJourney(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: S(3, 200)
    persona_id: str
    scenario: S(10, 600)
    desired_outcome: S(5, 400)
    entry_point: S(3, 300)
    preconditions: list[S(3, 300)] = Field(default_factory=list, max_length=6)
    stages: list[GeneratedJourneyStage] = Field(min_length=1, max_length=8)
    accessibility_considerations: list[S(5, 300)] = Field(min_length=1, max_length=6)
    prd_requirement_ids: list[str] = Field(min_length=1, max_length=12)
    opportunities: list[S(5, 300)] = Field(default_factory=list, max_length=6)
    unresolved_questions: list[S(5, 300)] = Field(default_factory=list, max_length=6)


class GeneratedJourneys(BaseModel):
    model_config = ConfigDict(extra="forbid")
    journeys: list[GeneratedJourney] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def _no_urls(self):
        for j in self.journeys:
            blobs = [j.title, j.scenario, j.desired_outcome, j.entry_point, *j.preconditions, *j.accessibility_considerations, *j.opportunities, *j.unresolved_questions]
            for st in j.stages:
                blobs.extend([st.stage_name, *st.user_actions, *st.thoughts_questions, *st.touchpoints, *st.pain_points, *st.system_responses, *st.failure_recovery_paths])
            for b in blobs:
                if _URL.search(b):
                    raise ValueError("journeys output must not contain URLs")
        return self


def to_journeys_content(basis: UxBasisSummary, gen: GeneratedJourneys) -> JourneysContent:
    valid_personas = set(basis.valid_persona_ids)
    valid_reqs = set(basis.valid_req_ids)
    out = []
    for i, gj in enumerate(gen.journeys, 1):
        if gj.persona_id not in valid_personas:
            raise ValueError(f"AI generated unknown persona_id '{gj.persona_id}'")
        reqs = [r for r in dict.fromkeys(gj.prd_requirement_ids) if r in valid_reqs]
        if not reqs:
            raise ValueError(f"AI journey '{gj.title}' did not reference any valid PRD requirement ID")
        stages = [
            JourneyStage(
                stage_number=idx,
                stage_name=s.stage_name,
                user_actions=list(s.user_actions),
                thoughts_questions=list(s.thoughts_questions),
                thoughts_status="hypothesis",
                touchpoints=list(s.touchpoints),
                pain_points=list(s.pain_points),
                system_responses=list(s.system_responses),
                failure_recovery_paths=list(s.failure_recovery_paths),
            )
            for idx, s in enumerate(gj.stages, 1)
        ]
        out.append(
            UserJourney(
                id=f"J-{i}",
                title=gj.title,
                persona_id=gj.persona_id,
                scenario=gj.scenario,
                desired_outcome=gj.desired_outcome,
                entry_point=gj.entry_point,
                preconditions=list(gj.preconditions),
                stages=stages,
                accessibility_considerations=list(gj.accessibility_considerations),
                prd_requirement_ids=reqs,
                opportunities=list(gj.opportunities),
                unresolved_questions=list(gj.unresolved_questions),
                origin="ai",
                edited_by_user=False,
            )
        )
    return JourneysContent(basis=basis, journeys=out)


# ==============================================================================
# 3. INFORMATION ARCHITECTURE (IA)
# ==============================================================================
NavGroup = Literal["primary", "secondary", "utility", "contextual"]


class IaNavigationModel(BaseModel):
    primary_nav: list[S(2, 120)] = Field(default_factory=list, max_length=15)
    secondary_nav: list[S(2, 120)] = Field(default_factory=list, max_length=15)
    utility_nav: list[S(2, 120)] = Field(default_factory=list, max_length=15)


class IaNode(BaseModel):
    id: str = Field(pattern=r"^IA-\d+$")
    name: S(2, 150)
    path: S(1, 200)
    parent_id: str | None = None
    order: int = 0
    purpose: S(5, 500)
    navigation_group: NavGroup = "primary"
    content_groups: list[S(2, 250)] = Field(min_length=1, max_length=10)
    key_actions: list[S(2, 250)] = Field(min_length=1, max_length=10)
    access_role: S(2, 150) = "Authenticated user"
    prd_requirement_ids: list[str] = Field(min_length=1, max_length=15)
    origin: Literal["ai", "user"] = "ai"
    edited_by_user: bool = False


class IaContent(BaseModel):
    basis: UxBasisSummary
    navigation_model: IaNavigationModel = Field(default_factory=IaNavigationModel)
    nodes: list[IaNode] = Field(min_length=1, max_length=50)
    open_questions: list[S(5, 300)] = Field(default_factory=list, max_length=15)
    assumptions: list[S(5, 300)] = Field(default_factory=list, max_length=15)
    limitations: list[str] = Field(default_factory=lambda: list(UX_LIMITATIONS["ia"]))

    @model_validator(mode="after")
    def _integrity(self):
        ids = [n.id for n in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate IA node ids")
        by_id = {n.id: n for n in self.nodes}
        valid_reqs = set(self.basis.valid_req_ids)

        for n in self.nodes:
            if n.parent_id is not None:
                if n.parent_id == n.id:
                    raise ValueError(f"node {n.id}: a node cannot be its own parent")
                if n.parent_id not in by_id:
                    raise ValueError(f"node {n.id}: parent_id '{n.parent_id}' does not exist")
            bad_reqs = [r for r in n.prd_requirement_ids if r not in valid_reqs]
            if bad_reqs:
                raise ValueError(f"node {n.id}: unknown prd_requirement_ids {', '.join(bad_reqs)}")

        # Cycle check across all nodes
        for n in self.nodes:
            seen = {n.id}
            cur = n.parent_id
            while cur is not None:
                if cur in seen:
                    raise ValueError(f"node {n.id}: cycle detected in information architecture hierarchy")
                seen.add(cur)
                cur = by_id[cur].parent_id

        return self


class GeneratedIaNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^IA-\d+$")
    name: S(2, 150)
    path: S(1, 200)
    parent_id: str | None = None
    order: int = 0
    purpose: S(5, 500)
    navigation_group: NavGroup = "primary"
    content_groups: list[S(2, 250)] = Field(min_length=1, max_length=8)
    key_actions: list[S(2, 250)] = Field(min_length=1, max_length=8)
    access_role: S(2, 150) = "Authenticated user"
    prd_requirement_ids: list[str] = Field(min_length=1, max_length=12)


class GeneratedIa(BaseModel):
    model_config = ConfigDict(extra="forbid")
    navigation_model: IaNavigationModel
    nodes: list[GeneratedIaNode] = Field(min_length=1, max_length=30)
    open_questions: list[S(5, 300)] = Field(default_factory=list, max_length=10)
    assumptions: list[S(5, 300)] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _no_urls(self):
        for n in self.nodes:
            for b in [n.name, n.purpose, *n.content_groups, *n.key_actions]:
                if _URL.search(b):
                    raise ValueError("IA output must not contain external URLs")
        return self


def to_ia_content(basis: UxBasisSummary, gen: GeneratedIa) -> IaContent:
    valid_reqs = set(basis.valid_req_ids)
    nodes = []
    for n in gen.nodes:
        reqs = [r for r in dict.fromkeys(n.prd_requirement_ids) if r in valid_reqs]
        if not reqs:
            raise ValueError(f"IA node {n.id} did not reference any valid PRD requirement ID")
        nodes.append(
            IaNode(
                id=n.id,
                name=n.name,
                path=n.path,
                parent_id=n.parent_id,
                order=n.order,
                purpose=n.purpose,
                navigation_group=n.navigation_group,
                content_groups=list(n.content_groups),
                key_actions=list(n.key_actions),
                access_role=n.access_role,
                prd_requirement_ids=reqs,
                origin="ai",
                edited_by_user=False,
            )
        )
    return IaContent(
        basis=basis,
        navigation_model=gen.navigation_model,
        nodes=nodes,
        open_questions=list(gen.open_questions),
        assumptions=list(gen.assumptions),
    )


# ==============================================================================
# 4. WIREFRAMES
# ==============================================================================
ComponentKind = Literal["nav_bar", "hero", "section_header", "card_grid", "data_table", "form", "action_bar", "callout", "empty_state", "status_banner"]
RegionKind = Literal["header", "navigation", "main", "sidebar", "footer", "modal"]
ViewportKind = Literal["desktop", "tablet", "mobile", "responsive"]


class WireframeComponent(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    kind: ComponentKind
    label: S(2, 150)
    content_role: S(3, 300)
    elements: list[S(2, 200)] = Field(min_length=1, max_length=10)


class WireframeRegion(BaseModel):
    region: RegionKind
    heading: S(2, 150)
    components: list[WireframeComponent] = Field(min_length=1, max_length=12)


class WireframeField(BaseModel):
    name: S(2, 100)
    field_type: Literal["text", "textarea", "select", "checkbox", "radio", "date", "number"] = "text"
    required: bool = True
    validation_rule: S(3, 300)


class WireframeStates(BaseModel):
    loading: S(5, 300)
    empty: S(5, 300)
    error: S(5, 300)
    success: S(5, 300)


class WireframeResponsive(BaseModel):
    desktop: S(5, 300)
    tablet: S(5, 300)
    mobile: S(5, 300)


class WireframeSpec(BaseModel):
    id: str = Field(pattern=r"^WF-\d+$")
    page_name: S(2, 150)
    purpose: S(5, 500)
    ia_node_id: str = Field(pattern=r"^IA-\d+$")
    target_viewport: ViewportKind = "responsive"
    regions: list[WireframeRegion] = Field(min_length=1, max_length=8)
    primary_actions: list[S(2, 200)] = Field(min_length=1, max_length=8)
    secondary_actions: list[S(2, 200)] = Field(default_factory=list, max_length=8)
    form_fields: list[WireframeField] = Field(default_factory=list, max_length=15)
    states: WireframeStates
    responsive_behavior: WireframeResponsive
    accessibility_keyboard: list[S(5, 300)] = Field(min_length=1, max_length=10)
    persona_ids: list[str] = Field(min_length=1, max_length=10)
    journey_ids: list[str] = Field(min_length=1, max_length=10)
    prd_requirement_ids: list[str] = Field(min_length=1, max_length=15)
    origin: Literal["ai", "user"] = "ai"
    edited_by_user: bool = False


class WireframesContent(BaseModel):
    basis: UxBasisSummary
    wireframes: list[WireframeSpec] = Field(min_length=1, max_length=30)
    limitations: list[str] = Field(default_factory=lambda: list(UX_LIMITATIONS["wireframes"]))

    @model_validator(mode="after")
    def _integrity(self):
        ids = [w.id for w in self.wireframes]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate wireframe ids")
        valid_ia = set(self.basis.valid_ia_node_ids)
        valid_p = set(self.basis.valid_persona_ids)
        valid_j = set(self.basis.valid_journey_ids)
        valid_reqs = set(self.basis.valid_req_ids)

        for w in self.wireframes:
            if w.ia_node_id not in valid_ia:
                raise ValueError(f"wireframe {w.id}: unknown ia_node_id '{w.ia_node_id}'")
            bad_p = [p for p in w.persona_ids if p not in valid_p]
            if bad_p:
                raise ValueError(f"wireframe {w.id}: unknown persona_ids {', '.join(bad_p)}")
            bad_j = [j for j in w.journey_ids if j not in valid_j]
            if bad_j:
                raise ValueError(f"wireframe {w.id}: unknown journey_ids {', '.join(bad_j)}")
            bad_reqs = [r for r in w.prd_requirement_ids if r not in valid_reqs]
            if bad_reqs:
                raise ValueError(f"wireframe {w.id}: unknown prd_requirement_ids {', '.join(bad_reqs)}")
        return self


class GeneratedWireframeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_name: S(2, 150)
    purpose: S(5, 500)
    ia_node_id: str
    target_viewport: ViewportKind = "responsive"
    regions: list[WireframeRegion] = Field(min_length=1, max_length=6)
    primary_actions: list[S(2, 200)] = Field(min_length=1, max_length=6)
    secondary_actions: list[S(2, 200)] = Field(default_factory=list, max_length=6)
    form_fields: list[WireframeField] = Field(default_factory=list, max_length=10)
    states: WireframeStates
    responsive_behavior: WireframeResponsive
    accessibility_keyboard: list[S(5, 300)] = Field(min_length=1, max_length=8)
    persona_ids: list[str] = Field(min_length=1, max_length=8)
    journey_ids: list[str] = Field(min_length=1, max_length=8)
    prd_requirement_ids: list[str] = Field(min_length=1, max_length=12)


class GeneratedWireframes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wireframes: list[GeneratedWireframeSpec] = Field(min_length=1, max_length=15)

    @model_validator(mode="after")
    def _no_urls(self):
        for w in self.wireframes:
            for b in [w.page_name, w.purpose, *w.primary_actions, *w.secondary_actions, *w.accessibility_keyboard]:
                if _URL.search(b):
                    raise ValueError("wireframes output must not contain external URLs")
        return self


def to_wireframes_content(basis: UxBasisSummary, gen: GeneratedWireframes) -> WireframesContent:
    valid_ia = set(basis.valid_ia_node_ids)
    valid_p = set(basis.valid_persona_ids)
    valid_j = set(basis.valid_journey_ids)
    valid_reqs = set(basis.valid_req_ids)

    out = []
    for i, gw in enumerate(gen.wireframes, 1):
        if gw.ia_node_id not in valid_ia:
            raise ValueError(f"AI wireframe '{gw.page_name}' referenced unknown ia_node_id '{gw.ia_node_id}'")
        p_ids = [p for p in dict.fromkeys(gw.persona_ids) if p in valid_p]
        if not p_ids:
            raise ValueError(f"AI wireframe '{gw.page_name}' did not reference any valid persona_id")
        j_ids = [j for j in dict.fromkeys(gw.journey_ids) if j in valid_j]
        if not j_ids:
            raise ValueError(f"AI wireframe '{gw.page_name}' did not reference any valid journey_id")
        reqs = [r for r in dict.fromkeys(gw.prd_requirement_ids) if r in valid_reqs]
        if not reqs:
            raise ValueError(f"AI wireframe '{gw.page_name}' did not reference any valid PRD requirement ID")
        out.append(
            WireframeSpec(
                id=f"WF-{i}",
                page_name=gw.page_name,
                purpose=gw.purpose,
                ia_node_id=gw.ia_node_id,
                target_viewport=gw.target_viewport,
                regions=list(gw.regions),
                primary_actions=list(gw.primary_actions),
                secondary_actions=list(gw.secondary_actions),
                form_fields=list(gw.form_fields),
                states=gw.states,
                responsive_behavior=gw.responsive_behavior,
                accessibility_keyboard=list(gw.accessibility_keyboard),
                persona_ids=p_ids,
                journey_ids=j_ids,
                prd_requirement_ids=reqs,
                origin="ai",
                edited_by_user=False,
            )
        )
    return WireframesContent(basis=basis, wireframes=out)


# ==============================================================================
# 5. UX REVIEW
# ==============================================================================
FindingSeverity = Literal["critical", "high", "medium", "low"]
FindingCategory = Literal[
    "prd_coverage",
    "task_navigation",
    "consistency",
    "responsive",
    "accessibility",
    "error_recovery",
    "ui_states",
    "missing_requirement",
    "unsupported_assumption",
    "traceability",
]
FindingStatus = Literal["open", "accepted", "resolved", "needs_evidence"]
AffectedArtifact = Literal["personas", "journeys", "ia", "wireframes", "cross_artifact"]


class UxReviewFinding(BaseModel):
    id: str = Field(pattern=r"^UXF-\d+$")
    severity: FindingSeverity
    category: FindingCategory
    affected_artifact: AffectedArtifact
    affected_version: int = Field(ge=1)
    affected_item_id: str | None = None
    title: S(5, 250)
    reasoning: S(10, 800)
    prd_requirement_ids: list[str] = Field(default_factory=list, max_length=15)
    recommended_action: S(5, 600)
    status: FindingStatus = "open"
    resolution_note: S(3, 500) | None = None
    origin: Literal["deterministic", "ai", "user"] = "ai"
    edited_by_user: bool = False


class UxReviewContent(BaseModel):
    basis: UxBasisSummary
    summary: S(10, 1000)
    findings: list[UxReviewFinding] = Field(default_factory=list, max_length=60)
    limitations: list[str] = Field(default_factory=lambda: list(UX_LIMITATIONS["ux_review"]))

    @model_validator(mode="after")
    def _integrity(self):
        ids = [f.id for f in self.findings]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate UX review finding ids")
        valid_reqs = set(self.basis.valid_req_ids)
        for f in self.findings:
            bad_reqs = [r for r in f.prd_requirement_ids if r not in valid_reqs]
            if bad_reqs:
                raise ValueError(f"finding {f.id}: unknown prd_requirement_ids {', '.join(bad_reqs)}")
            if f.status in ("accepted", "resolved") and not f.resolution_note:
                raise ValueError(f"finding {f.id}: status '{f.status}' requires a resolution_note explaining the fix or accepted risk")
        return self


class GeneratedUxFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    severity: FindingSeverity
    category: FindingCategory
    affected_artifact: AffectedArtifact
    affected_item_id: str | None = None
    title: S(5, 250)
    reasoning: S(10, 800)
    prd_requirement_ids: list[str] = Field(default_factory=list, max_length=10)
    recommended_action: S(5, 600)
    status: Literal["open", "needs_evidence"] = "open"


class GeneratedUxReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: S(10, 1000)
    findings: list[GeneratedUxFinding] = Field(default_factory=list, max_length=25)

    @model_validator(mode="after")
    def _no_urls(self):
        if _URL.search(self.summary):
            raise ValueError("UX review summary must not contain URLs")
        for f in self.findings:
            if _URL.search(f.title) or _URL.search(f.reasoning) or _URL.search(f.recommended_action):
                raise ValueError("UX review findings must not contain URLs")
        return self


def build_deterministic_ux_findings(
    basis: UxBasisSummary,
    prd_content: dict,
    personas_content: dict,
    journeys_content: dict,
    ia_content: dict,
    wireframes_content: dict,
) -> list[dict]:
    """Run deterministic cross-artifact consistency and coverage checks before adding AI review suggestions."""
    det: list[dict] = []

    # 1. Check whether any must_have in_mvp functional requirement is missing from Journeys, IA, or Wireframes
    must_frs = [
        r["id"]
        for r in prd_content.get("functional_requirements", [])
        if r.get("priority") == "must_have" and r.get("mvp_boundary") == "in_mvp"
    ]
    j_reqs = {r for j in journeys_content.get("journeys", []) for r in j.get("prd_requirement_ids", [])}
    ia_reqs = {r for n in ia_content.get("nodes", []) for r in n.get("prd_requirement_ids", [])}
    wf_reqs = {r for w in wireframes_content.get("wireframes", []) for r in w.get("prd_requirement_ids", [])}

    missing_j = [r for r in must_frs if r not in j_reqs]
    if missing_j:
        det.append({
            "severity": "high",
            "category": "missing_requirement",
            "affected_artifact": "journeys",
            "affected_version": basis.journeys_version or 1,
            "affected_item_id": None,
            "title": f"Must-have MVP requirement(s) not covered by any User Journey: {', '.join(missing_j)}",
            "reasoning": "Deterministic check: every must-have MVP functional requirement should be exercised by at least one user journey.",
            "prd_requirement_ids": missing_j,
            "recommended_action": f"Link or add a user journey covering {', '.join(missing_j)}.",
            "status": "open",
            "resolution_note": None,
            "origin": "deterministic",
            "edited_by_user": False,
        })

    missing_wf = [r for r in must_frs if r not in wf_reqs]
    if missing_wf:
        det.append({
            "severity": "high",
            "category": "missing_requirement",
            "affected_artifact": "wireframes",
            "affected_version": basis.wireframes_version or 1,
            "affected_item_id": None,
            "title": f"Must-have MVP requirement(s) not covered by any Wireframe: {', '.join(missing_wf)}",
            "reasoning": "Deterministic check: every must-have MVP functional requirement should appear in at least one wireframe specification.",
            "prd_requirement_ids": missing_wf,
            "recommended_action": f"Add or update a wireframe covering {', '.join(missing_wf)}.",
            "status": "open",
            "resolution_note": None,
            "origin": "deterministic",
            "edited_by_user": False,
        })

    missing_ia = [r for r in must_frs if r not in ia_reqs]
    if missing_ia:
        det.append({
            "severity": "medium",
            "category": "prd_coverage",
            "affected_artifact": "ia",
            "affected_version": basis.ia_version or 1,
            "affected_item_id": None,
            "title": f"Must-have MVP requirement(s) not mapped to any IA node: {', '.join(missing_ia)}",
            "reasoning": "Deterministic check: IA nodes should trace to all must-have MVP functional requirements.",
            "prd_requirement_ids": missing_ia,
            "recommended_action": f"Link {', '.join(missing_ia)} to the corresponding IA page node(s).",
            "status": "open",
            "resolution_note": None,
            "origin": "deterministic",
            "edited_by_user": False,
        })

    # 2. Check whether any Persona has no User Journey
    j_personas = {j.get("persona_id") for j in journeys_content.get("journeys", [])}
    for p in personas_content.get("personas", []):
        if p["id"] not in j_personas:
            det.append({
                "severity": "medium",
                "category": "consistency",
                "affected_artifact": "personas",
                "affected_version": basis.personas_version or 1,
                "affected_item_id": p["id"],
                "title": f"Persona {p['id']} ({p['name']}) has no linked User Journey",
                "reasoning": "Deterministic check: every defined persona should have at least one user journey modeling their core task flow.",
                "prd_requirement_ids": p.get("prd_requirement_ids", [])[:5],
                "recommended_action": f"Add a user journey for {p['id']} or remove the persona if redundant.",
                "status": "open",
                "resolution_note": None,
                "origin": "deterministic",
                "edited_by_user": False,
            })
        if p.get("needs_evidence") or p.get("unverified_assumptions"):
            det.append({
                "severity": "low",
                "category": "unsupported_assumption",
                "affected_artifact": "personas",
                "affected_version": basis.personas_version or 1,
                "affected_item_id": p["id"],
                "title": f"Persona {p['id']} ({p['name']}) contains unverified hypotheses or assumptions",
                "reasoning": "Deterministic check: persona includes unverified assumptions or hypothesis-level attributes without confirmed source backing.",
                "prd_requirement_ids": p.get("prd_requirement_ids", [])[:5],
                "recommended_action": "Attach examined research evidence or document acceptance of these persona hypotheses.",
                "status": "needs_evidence",
                "resolution_note": None,
                "origin": "deterministic",
                "edited_by_user": False,
            })

    # 3. Check whether any primary IA node has no Wireframe
    wf_ia_nodes = {w.get("ia_node_id") for w in wireframes_content.get("wireframes", [])}
    for n in ia_content.get("nodes", []):
        if n.get("navigation_group") == "primary" and n["id"] not in wf_ia_nodes:
            det.append({
                "severity": "medium",
                "category": "consistency",
                "affected_artifact": "ia",
                "affected_version": basis.ia_version or 1,
                "affected_item_id": n["id"],
                "title": f"Primary IA node {n['id']} ({n['name']}) has no Wireframe specification",
                "reasoning": "Deterministic check: every primary navigation page in the IA should have a corresponding low-fidelity wireframe.",
                "prd_requirement_ids": n.get("prd_requirement_ids", [])[:5],
                "recommended_action": f"Add a wireframe specification for IA node {n['id']} ({n['path']}).",
                "status": "open",
                "resolution_note": None,
                "origin": "deterministic",
                "edited_by_user": False,
            })

    return det


def to_ux_review_content(
    basis: UxBasisSummary,
    det_findings: list[dict],
    gen: GeneratedUxReview,
) -> UxReviewContent:
    valid_reqs = set(basis.valid_req_ids)
    ver_map: dict[str, int] = {
        "personas": basis.personas_version or 1,
        "journeys": basis.journeys_version or 1,
        "ia": basis.ia_version or 1,
        "wireframes": basis.wireframes_version or 1,
        "cross_artifact": basis.prd_version,
    }
    all_findings: list[UxReviewFinding] = []
    idx = 1
    for df in det_findings:
        all_findings.append(UxReviewFinding(id=f"UXF-{idx}", **df))
        idx += 1

    for gf in gen.findings:
        reqs = [r for r in dict.fromkeys(gf.prd_requirement_ids) if r in valid_reqs]
        all_findings.append(
            UxReviewFinding(
                id=f"UXF-{idx}",
                severity=gf.severity,
                category=gf.category,
                affected_artifact=gf.affected_artifact,
                affected_version=ver_map.get(gf.affected_artifact, 1),
                affected_item_id=gf.affected_item_id,
                title=gf.title,
                reasoning=gf.reasoning,
                prd_requirement_ids=reqs,
                recommended_action=gf.recommended_action,
                status=gf.status,
                resolution_note=None,
                origin="ai",
                edited_by_user=False,
            )
        )
        idx += 1

    return UxReviewContent(basis=basis, summary=gen.summary, findings=all_findings)


def review_counts(content: dict) -> dict[str, int]:
    findings = content.get("findings", [])
    return {
        "total": len(findings),
        "critical_open": sum(f["severity"] == "critical" and f["status"] in ("open", "needs_evidence") for f in findings),
        "open": sum(f["status"] == "open" for f in findings),
        "needs_evidence": sum(f["status"] == "needs_evidence" for f in findings),
        "accepted": sum(f["status"] == "accepted" for f in findings),
        "resolved": sum(f["status"] == "resolved" for f in findings),
        "deterministic": sum(f["origin"] == "deterministic" for f in findings),
        "ai": sum(f["origin"] == "ai" for f in findings),
        "user": sum(f["origin"] == "user" for f in findings),
    }


# ==============================================================================
# PROMPT BUILDERS
# ==============================================================================
def build_personas_prompt(basis: UxBasisSummary, research_content: dict, strategy_content: dict, prd_content: dict) -> str:
    ctx = {
        "basis": basis.model_dump(mode="json"),
        "research_findings": [{"id": f"res-{f['id']}", "topic": f["topic"], "statement": f["statement"], "evidence": f["evidence"]} for f in research_content.get("findings", [])],
        "strategy_target_users": strategy_content.get("target_users", []),
        "strategy_goals": strategy_content.get("goals", []),
        "prd_user_stories": prd_content.get("user_stories", []),
        "prd_requirements": [{"id": r["id"], "title": r["title"], "priority": r["priority"]} for r in prd_content.get("functional_requirements", [])],
    }
    return (
        "You are a UX researcher generating structured, decision-relevant Personas from approved Research, Strategy, and PRD artifacts.\n"
        "Hard rules:\n"
        "- Never invent user interviews, survey statistics, percentages, demographic numbers, quotations, or URLs.\n"
        "- Reference valid `prd_requirement_ids` from `basis.valid_req_ids`, `user_story_ids` from `basis.valid_story_ids`, and `evidence_refs` from `basis.valid_evidence_refs`.\n"
        "- Distinguish `evidence_backed` (supported by confirmed facts or examined sources) from `mixed` and `hypothesis`.\n"
        f"<project_context>{json.dumps(ctx, ensure_ascii=False)}</project_context>"
    )


def build_journeys_prompt(basis: UxBasisSummary, prd_content: dict, personas_content: dict) -> str:
    ctx = {
        "basis": basis.model_dump(mode="json"),
        "personas": [{"id": p["id"], "name": p["name"], "segment": p["segment"], "goals": p["goals"]} for p in personas_content.get("personas", [])],
        "prd_user_stories": prd_content.get("user_stories", []),
        "prd_requirements": [{"id": r["id"], "title": r["title"], "acceptance_criteria": r["acceptance_criteria"]} for r in prd_content.get("functional_requirements", [])],
    }
    return (
        "You are a UX designer creating stage-by-stage User Journeys for approved Personas and PRD requirements.\n"
        "Hard rules:\n"
        "- Every `persona_id` must be in `basis.valid_persona_ids` and every `prd_requirement_ids` entry must be in `basis.valid_req_ids`.\n"
        "- Include explicit failure and recovery paths in every stage, and accessibility considerations on every journey.\n"
        "- Never include URLs or fabricated statistics.\n"
        f"<project_context>{json.dumps(ctx, ensure_ascii=False)}</project_context>"
    )


def build_ia_prompt(basis: UxBasisSummary, prd_content: dict, personas_content: dict, journeys_content: dict) -> str:
    ctx = {
        "basis": basis.model_dump(mode="json"),
        "personas": [{"id": p["id"], "name": p["name"]} for p in personas_content.get("personas", [])],
        "journeys": [{"id": j["id"], "title": j["title"], "entry_point": j["entry_point"], "prd_requirement_ids": j["prd_requirement_ids"]} for j in journeys_content.get("journeys", [])],
        "prd_requirements": [{"id": r["id"], "title": r["title"], "mvp_boundary": r["mvp_boundary"]} for r in prd_content.get("functional_requirements", [])],
    }
    return (
        "You are an information architect designing a hierarchical sitemap and navigation structure (`IA-1`, `IA-2`, ...) from approved PRD requirements and user journeys.\n"
        "Hard rules:\n"
        "- Node IDs (`IA-1`, `IA-2`, ...) must be unique; `parent_id` must be null (for root nodes) or reference an existing `IA-N` node with no cycles.\n"
        "- Every node must reference valid `prd_requirement_ids` from `basis.valid_req_ids`.\n"
        "- Never include external URLs.\n"
        f"<project_context>{json.dumps(ctx, ensure_ascii=False)}</project_context>"
    )


def build_wireframes_prompt(basis: UxBasisSummary, prd_content: dict, personas_content: dict, journeys_content: dict, ia_content: dict) -> str:
    ctx = {
        "basis": basis.model_dump(mode="json"),
        "ia_nodes": [{"id": n["id"], "name": n["name"], "path": n["path"], "purpose": n["purpose"], "key_actions": n["key_actions"], "prd_requirement_ids": n["prd_requirement_ids"]} for n in ia_content.get("nodes", [])],
        "personas": [{"id": p["id"], "name": p["name"]} for p in personas_content.get("personas", [])],
        "journeys": [{"id": j["id"], "title": j["title"], "persona_id": j["persona_id"]} for j in journeys_content.get("journeys", [])],
        "prd_requirements": [{"id": r["id"], "title": r["title"], "acceptance_criteria": r["acceptance_criteria"], "edge_cases": r["edge_cases"]} for r in prd_content.get("functional_requirements", [])],
    }
    return (
        "You are a UX architect producing structured low-fidelity Wireframe Specifications for each key IA page.\n"
        "Hard rules:\n"
        "- Each wireframe must reference a valid `ia_node_id` from `basis.valid_ia_node_ids`, `persona_ids` from `basis.valid_persona_ids`, `journey_ids` from `basis.valid_journey_ids`, and `prd_requirement_ids` from `basis.valid_req_ids`.\n"
        "- Include explicit layout regions, components, loading/empty/error/success states, desktop/tablet/mobile responsive rules, and keyboard accessibility behaviors.\n"
        "- Never include external URLs.\n"
        f"<project_context>{json.dumps(ctx, ensure_ascii=False)}</project_context>"
    )


def build_ux_review_prompt(basis: UxBasisSummary, prd_content: dict, personas_content: dict, journeys_content: dict, ia_content: dict, wireframes_content: dict, det_findings: list[dict]) -> str:
    ctx = {
        "basis": basis.model_dump(mode="json"),
        "deterministic_findings": det_findings,
        "personas": personas_content.get("personas", []),
        "journeys": journeys_content.get("journeys", []),
        "ia_nodes": ia_content.get("nodes", []),
        "wireframes": wireframes_content.get("wireframes", []),
        "prd_requirements": prd_content.get("functional_requirements", []),
    }
    return (
        "You are a principal UX reviewer evaluating approved Personas, User Journeys, Information Architecture, and Wireframes against the approved PRD.\n"
        "Hard rules:\n"
        "- Never claim that a live usability test, automated accessibility audit, or user interview occurred.\n"
        "- Do not duplicate the `deterministic_findings` already listed; add complementary AI review findings on task flow clarity, responsive behavior, error recovery, accessibility, and edge-case coverage.\n"
        "- Reference only valid `prd_requirement_ids` from `basis.valid_req_ids`. Never include URLs.\n"
        f"<project_context>{json.dumps(ctx, ensure_ascii=False)}</project_context>"
    )
