"""Product Architecture (Phase 13): schemas, cross-artifact reference validation,
diagram-to-inventory consistency, PRD->Architecture->Data/API->Design/Prototype traceability,
and AI generation prompt builders.

Phase 13 turns the approved Product Specification (Phase 9 Research, Phase 10 Strategy & PRD,
Phase 11 UX artifacts, and Phase 12 Design System & Interactive Prototype) into a validated,
versioned technical architecture (`ArchitectureDocument`) for the `architecture` lifecycle stage.
"""
import hashlib
import json
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


def S(lo: int, hi: int):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=lo, max_length=hi)]


_URL = re.compile(r"https?://|www\.", re.I)
_UNSUPPORTED_CLAIM = re.compile(
    r"\b(?:load[-\s]tested|penetration[-\s]tested|soc\s*2\s+certified|iso\s*27001\s+certified|"
    r"benchmark[-\s]verified|production[-\s]deployed|zero[-\s]vulnerability\s+guaranteed)\b",
    re.I,
)

ARCHITECTURE_LIMITATIONS: list[str] = [
    "This Product Architecture specification is synthesized from your approved Research, Strategy, PRD, UX, Design System, and Interactive Prototype artifacts.",
    "Components, domain entities, API contracts, and infrastructure services marked 'proposed_target' describe the target product architecture to be implemented in subsequent stages—not already-deployed production services.",
    "No live load testing, penetration testing, or external cloud provisioning has been executed during architecture specification.",
]


def content_hash(content: dict) -> str:
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()
    ).hexdigest()


def _check_text_guards(val: Any, path: str = "architecture") -> None:
    if isinstance(val, str):
        if _URL.search(val):
            raise ValueError(f"{path} must not contain external URLs ({val[:60]!r})")
        if _UNSUPPORTED_CLAIM.search(val):
            raise ValueError(
                f"{path} contains an unsupported implementation, security, or benchmark claim ({val[:80]!r})"
            )
    elif isinstance(val, list):
        for idx, item in enumerate(val):
            _check_text_guards(item, f"{path}[{idx}]")
    elif isinstance(val, dict):
        for k, v in val.items():
            if k not in ("content_hash", "basis"):
                _check_text_guards(v, f"{path}.{k}")


class PrdRequirementSummary(BaseModel):
    id: S(2, 40)
    title: S(2, 240)
    kind: Literal["functional", "non_functional"] = "functional"


class ArchitectureBasisSummary(BaseModel):
    research_version: int
    strategy_version: int
    prd_version: int
    personas_version: int
    journeys_version: int
    ia_version: int
    wireframes_version: int
    ux_review_version: int
    design_system_version: int
    prototype_version: int
    valid_req_ids: list[str] = Field(default_factory=list)
    valid_persona_ids: list[str] = Field(default_factory=list)
    valid_journey_ids: list[str] = Field(default_factory=list)
    valid_ia_node_ids: list[str] = Field(default_factory=list)
    valid_wireframe_ids: list[str] = Field(default_factory=list)
    valid_ux_finding_ids: list[str] = Field(default_factory=list)
    valid_design_component_ids: list[str] = Field(default_factory=list)
    valid_design_decision_ids: list[str] = Field(default_factory=list)
    valid_token_names: list[str] = Field(default_factory=list)
    valid_prototype_screen_ids: list[str] = Field(default_factory=list)
    valid_prototype_flow_ids: list[str] = Field(default_factory=list)
    prd_requirements: list[PrdRequirementSummary] = Field(default_factory=list)

    def all_upstream_ids(self) -> set[str]:
        return set(
            self.valid_req_ids
            + self.valid_persona_ids
            + self.valid_journey_ids
            + self.valid_ia_node_ids
            + self.valid_wireframe_ids
            + self.valid_ux_finding_ids
            + self.valid_design_component_ids
            + self.valid_design_decision_ids
            + self.valid_prototype_screen_ids
            + self.valid_prototype_flow_ids
        )

    def all_design_and_ux_refs(self) -> set[str]:
        return set(
            self.valid_wireframe_ids
            + self.valid_ia_node_ids
            + self.valid_journey_ids
            + self.valid_design_component_ids
            + self.valid_design_decision_ids
            + self.valid_prototype_screen_ids
            + self.valid_prototype_flow_ids
        )


def build_architecture_basis(
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
    design_system_doc: dict,
    design_system_ver: int,
    prototype_doc: dict,
    prototype_ver: int,
) -> ArchitectureBasisSummary:
    prd_reqs: list[PrdRequirementSummary] = []
    req_ids: list[str] = []
    for r in prd_doc.get("functional_requirements", []):
        req_ids.append(r["id"])
        prd_reqs.append(
            PrdRequirementSummary(
                id=r["id"],
                title=r.get("title") or r.get("statement", r["id"])[:160],
                kind="functional",
            )
        )
    for r in prd_doc.get("non_functional_requirements", []):
        req_ids.append(r["id"])
        prd_reqs.append(
            PrdRequirementSummary(
                id=r["id"],
                title=f"{r.get('category', 'NFR')}: {r.get('requirement', r['id'])[:140]}",
                kind="non_functional",
            )
        )

    persona_ids = [p["id"] for p in personas_doc.get("personas", [])]
    journey_ids = [j["id"] for j in journeys_doc.get("journeys", [])]
    ia_node_ids = [n["id"] for n in ia_doc.get("nodes", [])]
    wf_ids = [w["id"] for w in wireframes_doc.get("wireframes", [])]
    uxf_ids = [f["id"] for f in ux_review_doc.get("findings", [])]

    cmp_ids = [c["id"] for c in design_system_doc.get("components", [])]
    dd_ids = [d["id"] for d in design_system_doc.get("decisions", [])]
    token_names: list[str] = []
    fnd = design_system_doc.get("foundations", {})
    for ct in fnd.get("color_tokens", []):
        token_names.append(ct["token"])
    for tt in fnd.get("typography_scale", []):
        token_names.append(tt["token"])
    for st in fnd.get("spacing_scale", []):
        token_names.append(st["token"])

    scr_ids = [s["id"] for s in prototype_doc.get("screens", [])]
    flow_ids = [fl["id"] for fl in prototype_doc.get("flows", [])]

    return ArchitectureBasisSummary(
        research_version=research_ver,
        strategy_version=strategy_ver,
        prd_version=prd_ver,
        personas_version=personas_ver,
        journeys_version=journeys_ver,
        ia_version=ia_ver,
        wireframes_version=wireframes_ver,
        ux_review_version=ux_review_ver,
        design_system_version=design_system_ver,
        prototype_version=prototype_ver,
        valid_req_ids=req_ids,
        valid_persona_ids=persona_ids,
        valid_journey_ids=journey_ids,
        valid_ia_node_ids=ia_node_ids,
        valid_wireframe_ids=wf_ids,
        valid_ux_finding_ids=uxf_ids,
        valid_design_component_ids=cmp_ids,
        valid_design_decision_ids=dd_ids,
        valid_token_names=token_names,
        valid_prototype_screen_ids=scr_ids,
        valid_prototype_flow_ids=flow_ids,
        prd_requirements=prd_reqs,
    )


# ==============================================================================
# A. SYSTEM OVERVIEW
# ==============================================================================
ComponentLayer = Literal["frontend", "backend", "data", "integration", "infrastructure"]
TrustZone = Literal[
    "public_unauthenticated",
    "authenticated_user",
    "privileged_admin",
    "internal_service",
    "external_third_party",
]
ImplementationStatus = Literal["proposed_target", "verified_existing"]


class TrustBoundaryRole(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: S(2, 100)
    persona_ids: list[S(3, 30)] = Field(min_length=1, max_length=8)
    trust_zone: TrustZone = "authenticated_user"
    allowed_capabilities: list[S(4, 300)] = Field(min_length=1, max_length=10)


class ArchitectureComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: S(3, 20)
    name: S(2, 120)
    layer: ComponentLayer
    purpose: S(10, 600)
    responsibilities: list[S(4, 300)] = Field(min_length=1, max_length=10)
    communicates_with: list[S(3, 20)] = Field(default_factory=list, max_length=15)
    prd_requirement_ids: list[S(3, 30)] = Field(min_length=1, max_length=25)
    design_refs: list[S(3, 30)] = Field(default_factory=list, max_length=25)


class ExternalIntegration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: S(3, 20)
    name: S(2, 120)
    purpose: S(8, 500)
    protocol_or_contract: S(4, 300)
    failure_mode_and_fallback: S(8, 500)
    implementation_status: ImplementationStatus = "proposed_target"
    prd_requirement_ids: list[S(3, 30)] = Field(min_length=1, max_length=15)


class SystemOverview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_scope: S(15, 1200)
    system_boundaries: list[S(8, 500)] = Field(min_length=2, max_length=12)
    user_roles_and_trust_boundaries: list[TrustBoundaryRole] = Field(min_length=1, max_length=10)
    components: list[ArchitectureComponent] = Field(min_length=2, max_length=20)
    external_integrations: list[ExternalIntegration] = Field(default_factory=list, max_length=12)


# ==============================================================================
# B. APPLICATION ARCHITECTURE
# ==============================================================================
class FrontendModuleBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: S(3, 20)
    module_name: S(2, 120)
    route_or_feature_scope: S(2, 300)
    component_id: S(3, 20)
    prototype_screen_ids: list[S(3, 30)] = Field(min_length=1, max_length=15)
    design_component_ids: list[S(3, 30)] = Field(min_length=1, max_length=15)
    design_tokens_used: list[S(2, 80)] = Field(min_length=1, max_length=20)
    prd_requirement_ids: list[S(3, 30)] = Field(min_length=1, max_length=20)


class BackendModuleBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: S(3, 20)
    module_name: S(2, 120)
    service_responsibility: S(8, 500)
    component_id: S(3, 20)
    prd_requirement_ids: list[S(3, 30)] = Field(min_length=1, max_length=20)


class ApplicationArchitecture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frontend_boundaries: list[FrontendModuleBoundary] = Field(min_length=1, max_length=16)
    backend_modules: list[BackendModuleBoundary] = Field(min_length=1, max_length=16)
    authentication_and_authorization: S(15, 1000)
    state_management_and_data_fetching: S(15, 1000)
    error_handling_and_logging: S(15, 1000)
    configuration_and_env_separation: S(15, 1000)


# ==============================================================================
# C. DATA ARCHITECTURE
# ==============================================================================
EntityDecisionStatus = Literal["approved_scope", "proposed", "requires_review"]
RelationshipCardinality = Literal["1:1", "1:N", "M:N"]


class DomainEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: S(3, 20)
    name: S(2, 120)
    description: S(8, 500)
    owning_component_id: S(3, 20)
    key_fields: list[S(2, 160)] = Field(min_length=2, max_length=16)
    access_boundary: S(6, 400)
    retention_and_lifecycle: S(6, 400)
    sensitive_data_handling: S(6, 400)
    status: EntityDecisionStatus = "proposed"
    prd_requirement_ids: list[S(3, 30)] = Field(min_length=1, max_length=20)


class EntityRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_entity_id: S(3, 20)
    target_entity_id: S(3, 20)
    cardinality: RelationshipCardinality = "1:N"
    description: S(4, 300)


class DataArchitecture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entities: list[DomainEntity] = Field(min_length=1, max_length=20)
    relationships: list[EntityRelationship] = Field(default_factory=list, max_length=30)
    transaction_and_integrity_rules: list[S(6, 500)] = Field(min_length=1, max_length=12)
    migration_strategy: S(10, 800)


# ==============================================================================
# D. API & INTEGRATION ARCHITECTURE
# ==============================================================================
HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
ApiAuthRequirement = Literal["public", "authenticated", "role_restricted", "internal_service"]


class ApiBoundarySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: S(3, 20)
    method: HttpMethod
    path: S(2, 200)
    summary: S(6, 400)
    component_id: S(3, 20)
    entity_ids: list[S(3, 20)] = Field(default_factory=list, max_length=12)
    auth_requirement: ApiAuthRequirement = "authenticated"
    request_contract: S(2, 500)
    response_contract: S(2, 500)
    validation_and_error_handling: S(6, 500)
    pagination_and_filtering: S(2, 300)
    implementation_status: ImplementationStatus = "proposed_target"
    prototype_screen_ids: list[S(3, 30)] = Field(default_factory=list, max_length=15)
    prd_requirement_ids: list[S(3, 30)] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _check_path(self):
        if not self.path.startswith("/"):
            raise ValueError(f"API endpoint path {self.path!r} must start with '/'")
        return self


class ApiArchitecture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    endpoints: list[ApiBoundarySpec] = Field(min_length=1, max_length=25)
    request_response_conventions: S(10, 800)
    validation_and_error_conventions: S(10, 800)
    integration_contracts_and_failure_behavior: S(10, 800)


# ==============================================================================
# E. DEPLOYMENT & OPERATIONAL ARCHITECTURE
# ==============================================================================
ServiceEnvironment = Literal["local_dev", "staging", "production", "all"]
ServiceStatus = Literal["proposed_target", "verified_current"]


class DeploymentServiceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: S(3, 20)
    name: S(2, 120)
    environment: ServiceEnvironment = "all"
    responsibility: S(6, 400)
    component_ids: list[S(3, 20)] = Field(min_length=1, max_length=15)
    implementation_status: ServiceStatus = "proposed_target"


class DeploymentArchitecture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    local_development_environment: S(10, 800)
    services_and_infrastructure: list[DeploymentServiceSpec] = Field(min_length=1, max_length=15)
    configuration_and_secret_management: S(10, 800)
    deployment_boundaries: S(10, 800)
    health_checks_and_observability: S(10, 800)
    backup_recovery_and_failure: S(10, 800)


# ==============================================================================
# F. TECHNICAL DECISIONS (ADRs)
# ==============================================================================
DecisionStatus = Literal["proposed", "accepted", "requires_review"]


class ArchitectureDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: S(3, 20)
    title: S(4, 180)
    status: DecisionStatus = "proposed"
    context_and_problem: S(10, 800)
    decision: S(10, 800)
    alternatives_and_tradeoffs: list[S(6, 400)] = Field(min_length=1, max_length=8)
    rationale: S(10, 800)
    consequences_and_risks: list[S(6, 400)] = Field(min_length=1, max_length=8)
    prd_requirement_ids: list[S(3, 30)] = Field(min_length=1, max_length=20)
    source_refs: list[S(3, 30)] = Field(min_length=1, max_length=25)


# ==============================================================================
# G. ARCHITECTURE DIAGRAMS
# ==============================================================================
DiagramType = Literal[
    "system_context",
    "component",
    "data_relationship",
    "request_flow",
    "deployment",
]


class DiagramNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: S(2, 40)
    label: S(2, 120)
    reference_id: S(3, 30)


class DiagramEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_node: S(2, 40)
    to_node: S(2, 40)
    label: S(2, 160)


class ArchitectureDiagram(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: S(3, 20)
    diagram_type: DiagramType
    title: S(4, 160)
    summary: S(8, 500)
    nodes: list[DiagramNode] = Field(min_length=2, max_length=25)
    edges: list[DiagramEdge] = Field(min_length=1, max_length=40)
    mermaid: S(10, 4000)

    @model_validator(mode="after")
    def _validate_structure(self):
        node_ids = {n.id for n in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError(f"Diagram {self.id} contains duplicate node IDs")
        for edge in self.edges:
            if edge.from_node not in node_ids:
                raise ValueError(f"Diagram {self.id} edge from_node '{edge.from_node}' not found in diagram nodes")
            if edge.to_node not in node_ids:
                raise ValueError(f"Diagram {self.id} edge to_node '{edge.to_node}' not found in diagram nodes")
        m_trim = self.mermaid.strip()
        if not any(m_trim.startswith(prefix) for prefix in ("flowchart", "graph", "erDiagram", "sequenceDiagram")):
            raise ValueError(
                f"Diagram {self.id} mermaid definition must begin with flowchart, graph, erDiagram, or sequenceDiagram"
            )
        return self


def render_mermaid_from_spec(diagram_type: DiagramType, nodes: list[DiagramNode], edges: list[DiagramEdge]) -> str:
    """Deterministically generate a valid Mermaid diagram from structured nodes and edges."""
    lines = ["flowchart LR"]
    for n in nodes:
        safe_label = n.label.replace('"', "'")
        lines.append(f'    {n.id}["{safe_label} ({n.reference_id})"]')
    for e in edges:
        safe_edge = e.label.replace('"', "'")
        lines.append(f'    {e.from_node} -->|"{safe_edge}"| {e.to_node}')
    return "\n".join(lines)


# ==============================================================================
# H. TRACEABILITY MATRIX & FULL CONTENT
# ==============================================================================
class TraceabilityRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_id: S(2, 40)
    requirement_title: S(2, 240)
    requirement_kind: Literal["functional", "non_functional"] = "functional"
    component_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    endpoint_ids: list[str] = Field(default_factory=list)
    integration_ids: list[str] = Field(default_factory=list)
    frontend_module_ids: list[str] = Field(default_factory=list)
    backend_module_ids: list[str] = Field(default_factory=list)
    decision_ids: list[str] = Field(default_factory=list)
    design_refs: list[str] = Field(default_factory=list)
    fully_traced: bool = False
    coverage_gaps: list[str] = Field(default_factory=list)


class ArchitectureContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    basis: ArchitectureBasisSummary
    system_overview: SystemOverview
    application_architecture: ApplicationArchitecture
    data_architecture: DataArchitecture
    api_architecture: ApiArchitecture
    deployment_architecture: DeploymentArchitecture
    decisions: list[ArchitectureDecision] = Field(min_length=1, max_length=25)
    diagrams: list[ArchitectureDiagram] = Field(min_length=2, max_length=10)
    traceability: list[TraceabilityRow] = Field(default_factory=list)
    methodology_limitations: list[str] = Field(default_factory=lambda: list(ARCHITECTURE_LIMITATIONS))

    @model_validator(mode="after")
    def _validate_all(self):
        _check_text_guards(self.model_dump(exclude={"basis", "traceability"}))
        b = self.basis
        req_set = set(b.valid_req_ids)
        persona_set = set(b.valid_persona_ids)
        scr_set = set(b.valid_prototype_screen_ids)
        cmp_set = set(b.valid_design_component_ids)
        tok_set = set(b.valid_token_names)
        design_ux_set = b.all_design_and_ux_refs()
        upstream_all = b.all_upstream_ids()

        # 1. Validate Component IDs & communication references
        comp_ids: list[str] = []
        for idx, c in enumerate(self.system_overview.components, 1):
            expected = f"COMP-{idx}"
            if c.id != expected:
                raise ValueError(f"Component IDs must be sequential COMP-1..COMP-N (got {c.id!r}, expected {expected!r})")
            comp_ids.append(c.id)
        comp_set = set(comp_ids)

        int_ids: list[str] = []
        for idx, ext in enumerate(self.system_overview.external_integrations, 1):
            expected = f"INT-{idx}"
            if ext.id != expected:
                raise ValueError(f"Integration IDs must be sequential INT-1..INT-N (got {ext.id!r}, expected {expected!r})")
            int_ids.append(ext.id)
        int_set = set(int_ids)

        comm_targets = comp_set | int_set
        for role in self.system_overview.user_roles_and_trust_boundaries:
            for pid in role.persona_ids:
                if persona_set and pid not in persona_set:
                    raise ValueError(f"Trust boundary role '{role.role}' references unknown Persona ID {pid!r}")

        for c in self.system_overview.components:
            for target in c.communicates_with:
                if target == c.id:
                    raise ValueError(f"Component {c.id} cannot list itself in communicates_with")
                if target not in comm_targets:
                    raise ValueError(f"Component {c.id} communicates_with unknown component/integration {target!r}")
            for rid in c.prd_requirement_ids:
                if req_set and rid not in req_set:
                    raise ValueError(f"Component {c.id} references unknown PRD requirement {rid!r}")
            for dref in c.design_refs:
                if design_ux_set and dref not in design_ux_set:
                    raise ValueError(f"Component {c.id} references unknown UX/Design artifact ID {dref!r}")

        for ext in self.system_overview.external_integrations:
            for rid in ext.prd_requirement_ids:
                if req_set and rid not in req_set:
                    raise ValueError(f"External integration {ext.id} references unknown PRD requirement {rid!r}")

        # 2. Validate Application Architecture boundaries
        for idx, fe in enumerate(self.application_architecture.frontend_boundaries, 1):
            expected = f"FE-{idx}"
            if fe.id != expected:
                raise ValueError(f"Frontend boundary IDs must be sequential FE-1..FE-N (got {fe.id!r}, expected {expected!r})")
            if fe.component_id not in comp_set:
                raise ValueError(f"Frontend boundary {fe.id} references unknown component {fe.component_id!r}")
            for sid in fe.prototype_screen_ids:
                if scr_set and sid not in scr_set:
                    raise ValueError(f"Frontend boundary {fe.id} references unknown Prototype screen {sid!r}")
            for cid in fe.design_component_ids:
                if cmp_set and cid not in cmp_set:
                    raise ValueError(f"Frontend boundary {fe.id} references unknown Design System component {cid!r}")
            for tok in fe.design_tokens_used:
                if tok_set and tok not in tok_set:
                    raise ValueError(f"Frontend boundary {fe.id} references unknown Design System token {tok!r}")
            for rid in fe.prd_requirement_ids:
                if req_set and rid not in req_set:
                    raise ValueError(f"Frontend boundary {fe.id} references unknown PRD requirement {rid!r}")

        for idx, be in enumerate(self.application_architecture.backend_modules, 1):
            expected = f"BE-{idx}"
            if be.id != expected:
                raise ValueError(f"Backend module IDs must be sequential BE-1..BE-N (got {be.id!r}, expected {expected!r})")
            if be.component_id not in comp_set:
                raise ValueError(f"Backend module {be.id} references unknown component {be.component_id!r}")
            for rid in be.prd_requirement_ids:
                if req_set and rid not in req_set:
                    raise ValueError(f"Backend module {be.id} references unknown PRD requirement {rid!r}")

        # 3. Validate Data Architecture entities & relationships
        ent_ids: list[str] = []
        for idx, ent in enumerate(self.data_architecture.entities, 1):
            expected = f"ENT-{idx}"
            if ent.id != expected:
                raise ValueError(f"Entity IDs must be sequential ENT-1..ENT-N (got {ent.id!r}, expected {expected!r})")
            if ent.owning_component_id not in comp_set:
                raise ValueError(f"Entity {ent.id} owning_component_id {ent.owning_component_id!r} is not a valid component")
            for rid in ent.prd_requirement_ids:
                if req_set and rid not in req_set:
                    raise ValueError(f"Entity {ent.id} references unknown PRD requirement {rid!r}; domain entities must be backed by the approved PRD")
            ent_ids.append(ent.id)
        ent_set = set(ent_ids)

        for rel in self.data_architecture.relationships:
            if rel.source_entity_id not in ent_set:
                raise ValueError(f"Relationship references unknown source_entity_id {rel.source_entity_id!r}")
            if rel.target_entity_id not in ent_set:
                raise ValueError(f"Relationship references unknown target_entity_id {rel.target_entity_id!r}")

        # 4. Validate API Architecture endpoints
        api_ids: list[str] = []
        for idx, ep in enumerate(self.api_architecture.endpoints, 1):
            expected = f"API-{idx}"
            if ep.id != expected:
                raise ValueError(f"API endpoint IDs must be sequential API-1..API-N (got {ep.id!r}, expected {expected!r})")
            if ep.component_id not in comp_set:
                raise ValueError(f"API endpoint {ep.id} references unknown component {ep.component_id!r}")
            for eid in ep.entity_ids:
                if eid not in ent_set:
                    raise ValueError(f"API endpoint {ep.id} references unknown entity {eid!r}")
            for sid in ep.prototype_screen_ids:
                if scr_set and sid not in scr_set:
                    raise ValueError(f"API endpoint {ep.id} references unknown Prototype screen {sid!r}")
            for rid in ep.prd_requirement_ids:
                if req_set and rid not in req_set:
                    raise ValueError(f"API endpoint {ep.id} references unknown PRD requirement {rid!r}")
            api_ids.append(ep.id)
        api_set = set(api_ids)

        # 5. Validate Deployment Services
        svc_ids: list[str] = []
        for idx, svc in enumerate(self.deployment_architecture.services_and_infrastructure, 1):
            expected = f"SVC-{idx}"
            if svc.id != expected:
                raise ValueError(f"Service IDs must be sequential SVC-1..SVC-N (got {svc.id!r}, expected {expected!r})")
            for cid in svc.component_ids:
                if cid not in comp_set:
                    raise ValueError(f"Deployment service {svc.id} references unknown component {cid!r}")
            svc_ids.append(svc.id)
        svc_set = set(svc_ids)

        # 6. Validate Architecture Decisions (ADRs)
        internal_ids = comp_set | int_set | ent_set | api_set | svc_set
        valid_source_refs = upstream_all | internal_ids
        for idx, adr in enumerate(self.decisions, 1):
            expected = f"ADR-{idx}"
            if adr.id != expected:
                raise ValueError(f"Decision IDs must be sequential ADR-1..ADR-N (got {adr.id!r}, expected {expected!r})")
            for rid in adr.prd_requirement_ids:
                if req_set and rid not in req_set:
                    raise ValueError(f"Decision {adr.id} references unknown PRD requirement {rid!r}")
            for sref in adr.source_refs:
                if valid_source_refs and sref not in valid_source_refs:
                    raise ValueError(f"Decision {adr.id} references unknown source artifact/component ID {sref!r}")

        # 7. Validate Diagrams against written inventory
        valid_diag_refs = comp_set | int_set | ent_set | api_set | svc_set | persona_set | scr_set
        comp_comm_map = {c.id: set(c.communicates_with) for c in self.system_overview.components}
        ent_rel_pairs = {
            (r.source_entity_id, r.target_entity_id) for r in self.data_architecture.relationships
        } | {
            (r.target_entity_id, r.source_entity_id) for r in self.data_architecture.relationships
        }

        for idx, dg in enumerate(self.diagrams, 1):
            expected = f"DIAG-{idx}"
            if dg.id != expected:
                raise ValueError(f"Diagram IDs must be sequential DIAG-1..DIAG-N (got {dg.id!r}, expected {expected!r})")
            node_ref_map: dict[str, str] = {}
            for node in dg.nodes:
                if valid_diag_refs and node.reference_id not in valid_diag_refs:
                    raise ValueError(
                        f"Diagram {dg.id} node '{node.id}' references '{node.reference_id}', which does not exist in the architecture inventory"
                    )
                if dg.diagram_type == "data_relationship" and node.reference_id not in ent_set:
                    raise ValueError(
                        f"Data relationship diagram {dg.id} node '{node.id}' must reference a valid ENT-* entity (got {node.reference_id!r})"
                    )
                if dg.diagram_type == "deployment" and node.reference_id not in (svc_set | comp_set):
                    raise ValueError(
                        f"Deployment diagram {dg.id} node '{node.id}' must reference a valid SVC-* or COMP-* ID (got {node.reference_id!r})"
                    )
                node_ref_map[node.id] = node.reference_id

            for edge in dg.edges:
                src_ref = node_ref_map[edge.from_node]
                dst_ref = node_ref_map[edge.to_node]
                if dg.diagram_type == "component":
                    if src_ref in comp_comm_map and dst_ref in (comp_set | int_set) and src_ref != dst_ref:
                        if dst_ref not in comp_comm_map.get(src_ref, set()) and src_ref not in comp_comm_map.get(dst_ref, set()):
                            raise ValueError(
                                f"Component diagram {dg.id} connects {src_ref} and {dst_ref}, contradicting the written component communication inventory"
                            )
                if dg.diagram_type == "data_relationship" and src_ref != dst_ref:
                    if ent_rel_pairs and (src_ref, dst_ref) not in ent_rel_pairs:
                        raise ValueError(
                            f"Data relationship diagram {dg.id} connects {src_ref} and {dst_ref}, which is not declared in data_architecture.relationships"
                        )

        # 8. Recompute deterministic Traceability Matrix
        self.traceability = compute_traceability(self)
        return self


def compute_traceability(arch: ArchitectureContent) -> list[TraceabilityRow]:
    """Build deterministic PRD requirement -> component -> data/API -> design/prototype traceability."""
    b = arch.basis
    reqs = b.prd_requirements or [
        PrdRequirementSummary(
            id=rid,
            title=rid,
            kind="non_functional" if rid.startswith("NFR-") else "functional",
        )
        for rid in b.valid_req_ids
    ]

    comp_design_map: dict[str, list[str]] = {
        c.id: list(c.design_refs) for c in arch.system_overview.components
    }
    fe_design_map: dict[str, list[str]] = {
        fe.id: list(dict.fromkeys(fe.prototype_screen_ids + fe.design_component_ids))
        for fe in arch.application_architecture.frontend_boundaries
    }
    ep_design_map: dict[str, list[str]] = {
        ep.id: list(ep.prototype_screen_ids) for ep in arch.api_architecture.endpoints
    }

    rows: list[TraceabilityRow] = []
    for req in reqs:
        rid = req.id
        c_ids = [c.id for c in arch.system_overview.components if rid in c.prd_requirement_ids]
        e_ids = [e.id for e in arch.data_architecture.entities if rid in e.prd_requirement_ids]
        a_ids = [ep.id for ep in arch.api_architecture.endpoints if rid in ep.prd_requirement_ids]
        i_ids = [ext.id for ext in arch.system_overview.external_integrations if rid in ext.prd_requirement_ids]
        fe_ids = [fe.id for fe in arch.application_architecture.frontend_boundaries if rid in fe.prd_requirement_ids]
        be_ids = [be.id for be in arch.application_architecture.backend_modules if rid in be.prd_requirement_ids]
        adr_ids = [adr.id for adr in arch.decisions if rid in adr.prd_requirement_ids]

        d_refs: list[str] = []
        for cid in c_ids:
            d_refs.extend(comp_design_map.get(cid, []))
        for fid in fe_ids:
            d_refs.extend(fe_design_map.get(fid, []))
        for aid in a_ids:
            d_refs.extend(ep_design_map.get(aid, []))
        d_refs = list(dict.fromkeys(d_refs))

        gaps: list[str] = []
        if not c_ids:
            gaps.append("No architecture component (COMP-*) covers this requirement.")
        if not (e_ids or a_ids or be_ids or i_ids):
            gaps.append("No data entity (ENT-*), API boundary (API-*), or backend service (BE-*) covers this requirement.")
        if req.kind == "functional" and not d_refs:
            gaps.append("No approved design/prototype reference (SCR-*, CMP-*, WF-*) is linked for this functional requirement.")

        rows.append(
            TraceabilityRow(
                requirement_id=rid,
                requirement_title=req.title,
                requirement_kind=req.kind,
                component_ids=c_ids,
                entity_ids=e_ids,
                endpoint_ids=a_ids,
                integration_ids=i_ids,
                frontend_module_ids=fe_ids,
                backend_module_ids=be_ids,
                decision_ids=adr_ids,
                design_refs=d_refs,
                fully_traced=len(gaps) == 0,
                coverage_gaps=gaps,
            )
        )
    return rows


def evaluate_architecture_completeness(content: dict | ArchitectureContent) -> dict[str, Any]:
    """Inspect an ArchitectureContent document for uncovered requirements, unreferenced components, and unresolved decisions."""
    arch = content if isinstance(content, ArchitectureContent) else ArchitectureContent.model_validate(content)
    uncovered_reqs = [r.requirement_id for r in arch.traceability if not r.fully_traced]

    used_comps = (
        {fe.component_id for fe in arch.application_architecture.frontend_boundaries}
        | {be.component_id for be in arch.application_architecture.backend_modules}
        | {e.owning_component_id for e in arch.data_architecture.entities}
        | {ep.component_id for ep in arch.api_architecture.endpoints}
        | {cid for svc in arch.deployment_architecture.services_and_infrastructure for cid in svc.component_ids}
    )
    unreferenced_components = [
        c.id for c in arch.system_overview.components if c.id not in used_comps or not c.prd_requirement_ids
    ]
    requires_review_decisions = [d.id for d in arch.decisions if d.status == "requires_review"]
    proposed_decisions = [d.id for d in arch.decisions if d.status == "proposed"]
    requires_review_entities = [e.id for e in arch.data_architecture.entities if e.status == "requires_review"]

    return {
        "complete_traceability": len(uncovered_reqs) == 0 and len(unreferenced_components) == 0,
        "uncovered_requirements": uncovered_reqs,
        "unreferenced_components": unreferenced_components,
        "requires_review_decisions": requires_review_decisions,
        "proposed_decisions": proposed_decisions,
        "requires_review_entities": requires_review_entities,
        "total_requirements": len(arch.traceability),
        "traced_requirements": sum(1 for r in arch.traceability if r.fully_traced),
    }


# ==============================================================================
# AI GENERATION SCHEMA & CONVERTER
# ==============================================================================
class GeneratedArchitecture(BaseModel):
    system_overview: SystemOverview
    application_architecture: ApplicationArchitecture
    data_architecture: DataArchitecture
    api_architecture: ApiArchitecture
    deployment_architecture: DeploymentArchitecture
    decisions: list[ArchitectureDecision] = Field(min_length=1, max_length=25)
    diagrams: list[ArchitectureDiagram] = Field(min_length=2, max_length=10)


def to_architecture_content(gen: GeneratedArchitecture, basis: ArchitectureBasisSummary) -> ArchitectureContent:
    return ArchitectureContent(
        basis=basis,
        system_overview=gen.system_overview,
        application_architecture=gen.application_architecture,
        data_architecture=gen.data_architecture,
        api_architecture=gen.api_architecture,
        deployment_architecture=gen.deployment_architecture,
        decisions=gen.decisions,
        diagrams=gen.diagrams,
    )


def build_architecture_prompt(
    project_name: str,
    prd_doc: dict,
    personas_doc: dict,
    journeys_doc: dict,
    ia_doc: dict,
    wireframes_doc: dict,
    ux_review_doc: dict,
    design_system_doc: dict,
    prototype_doc: dict,
    basis: ArchitectureBasisSummary,
) -> str:
    return (
        f"You are a principal systems architect designing the Phase 13 Product Architecture for '{project_name}'.\n"
        "Generate a schema-valid GeneratedArchitecture JSON object based strictly on the approved upstream artifacts:\n"
        f"- Valid PRD Requirement IDs: {basis.valid_req_ids}\n"
        f"- Valid Persona IDs: {basis.valid_persona_ids}\n"
        f"- Valid Journey IDs: {basis.valid_journey_ids}\n"
        f"- Valid IA Node IDs: {basis.valid_ia_node_ids}\n"
        f"- Valid Wireframe IDs: {basis.valid_wireframe_ids}\n"
        f"- Valid UX Finding IDs: {basis.valid_ux_finding_ids}\n"
        f"- Valid Design System Component IDs: {basis.valid_design_component_ids}\n"
        f"- Valid Design System Decision IDs: {basis.valid_design_decision_ids}\n"
        f"- Valid Design System Token Names: {basis.valid_token_names}\n"
        f"- Valid Interactive Prototype Screen IDs: {basis.valid_prototype_screen_ids}\n"
        f"- Valid Interactive Prototype Flow IDs: {basis.valid_prototype_flow_ids}\n\n"
        "STRICT RULES:\n"
        "1. Use sequential deterministic IDs: COMP-1..N, INT-1..N, FE-1..N, BE-1..N, ENT-1..N, API-1..N, SVC-1..N, ADR-1..N, DIAG-1..N.\n"
        "2. Cover EVERY PRD requirement ID in basis.valid_req_ids across components, data/API/backend modules, and design/prototype references.\n"
        "3. Do NOT invent domain entities unsupported by PRD requirements. Mark target endpoints/integrations/services as 'proposed_target'.\n"
        "4. Do NOT include any URLs (http://, https://, www.) or unsupported claims (load-tested, penetration-tested, SOC2 certified, production-deployed).\n"
        "5. Ensure every diagram node reference_id matches a valid COMP-*, INT-*, ENT-*, API-*, SVC-*, PER-*, or SCR-* ID and edges match component communications / entity relationships.\n\n"
        f"Approved PRD Summary: {json.dumps(prd_doc, default=str)[:3500]}\n"
        f"Approved Design System Components: {json.dumps(design_system_doc.get('components', []), default=str)[:2000]}\n"
        f"Approved Prototype Screens: {json.dumps(prototype_doc.get('screens', []), default=str)[:2000]}\n"
    )
