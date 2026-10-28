from typing import Any, Literal

from pydantic import BaseModel, Field


class Idea(BaseModel):
    raw: str = ""
    product_name: str = ""
    product_type: str = ""
    problem: str = ""
    features: list[str] = []
    assumptions: list[str] = []
    open_questions: list[str] = []


class ConfirmedFact(BaseModel):
    """Information the user explicitly provided in discovery. Only the discovery workflow writes these."""
    question_id: str
    target: str
    question: str
    answer: Any
    source: Literal["user_confirmed"] = "user_confirmed"
    recorded_at: str


class Assumption(BaseModel):
    id: str
    text: str
    source: Literal["ai_suggested", "user_declared", "unanswered_question"]
    status: Literal["unverified", "accepted"] = "unverified"


class DiscoveryBrain(BaseModel):
    confirmed: list[ConfirmedFact] = []
    assumptions: list[Assumption] = []


class ResearchBrain(BaseModel):
    """Pointer to the last APPROVED research report version (the report itself lives in research_reports; no duplicated truth).
    Written only by the approval action, never from AI output, and it never changes confirmed sections."""
    approved_version: int | None = None
    report_id: str | None = None
    content_hash: str | None = None
    approved_at: str | None = None
    basis_brain_version: int | None = None
    mode: str | None = None
    finding_counts: dict[str, int] = {}
    source_count: int = 0
    unverified_acknowledged: bool = False


class StrategyBrain(BaseModel):
    """Pointer to the last APPROVED product strategy version (the document itself lives in strategy_documents).
    Written only by the approval action, never from AI output, and never overwrites confirmed sections."""
    approved_version: int | None = None
    document_id: str | None = None
    content_hash: str | None = None
    approved_at: str | None = None
    basis_brain_version: int | None = None
    research_version: int | None = None
    recommendation_counts: dict[str, int] = {}
    unsupported_count: int = 0
    unverified_acknowledged: bool = False


class PrdBrain(BaseModel):
    """Pointer to the last APPROVED PRD version (the document itself lives in prd_documents).
    Written only by the approval action, never from AI output, and never overwrites confirmed sections."""
    approved_version: int | None = None
    document_id: str | None = None
    content_hash: str | None = None
    approved_at: str | None = None
    basis_brain_version: int | None = None
    strategy_version: int | None = None
    research_version: int | None = None
    requirement_counts: dict[str, int] = {}
    approved_requirement_count: int = 0
    unverified_acknowledged: bool = False




class UxArtifactPointer(BaseModel):
    """Pointer to the last APPROVED version of one UX artifact type in ux_artifacts."""
    approved_version: int | None = None
    document_id: str | None = None
    content_hash: str | None = None
    approved_at: str | None = None
    basis_versions: dict[str, int] = {}
    item_count: int = 0
    unverified_acknowledged: bool = False


class UxBrain(BaseModel):
    """Pointers to the last APPROVED Phase 11 UX artifacts (stored in ux_artifacts; written only by approval actions)."""
    personas: UxArtifactPointer = UxArtifactPointer()
    journeys: UxArtifactPointer = UxArtifactPointer()
    ia: UxArtifactPointer = UxArtifactPointer()
    wireframes: UxArtifactPointer = UxArtifactPointer()
    ux_review: UxArtifactPointer = UxArtifactPointer()




class DesignBrain(BaseModel):
    """Pointers to the last APPROVED Phase 12 Design artifacts (stored in design_artifacts; written only by approval actions)."""
    design_system: UxArtifactPointer = UxArtifactPointer()
    prototype: UxArtifactPointer = UxArtifactPointer()




class ArchitectureBrain(BaseModel):
    """Pointer to the last APPROVED Phase 13 Architecture document (stored in architecture_documents; written only on approval)."""
    approved_version: int | None = None
    document_id: str | None = None
    content_hash: str | None = None
    approved_at: str | None = None
    basis_versions: dict[str, int] = {}
    component_count: int = 0
    entity_count: int = 0
    endpoint_count: int = 0
    decision_count: int = 0
    diagram_count: int = 0
    unverified_acknowledged: bool = False


class OptimizationBrain(BaseModel):
    """Pointers to the last APPROVED Phase 16 Optimization artifacts (stored in optimization_artifacts; written only by approval actions)."""
    seo: UxArtifactPointer = UxArtifactPointer()
    analytics: UxArtifactPointer = UxArtifactPointer()
    performance: UxArtifactPointer = UxArtifactPointer()


class DocumentationBrain(BaseModel):
    """Pointer to the latest official Phase 17 Documentation & Export bundle (stored in documentation_exports)."""
    approved_version: int | None = None
    export_id: str | None = None
    manifest_sha256: str | None = None
    bundle_sha256: str | None = None
    exported_at: str | None = None
    included_section_count: int = 0
    source_versions: dict[str, Any] = {}


class ProjectBrain(BaseModel):
    idea: Idea = Idea()
    business: dict = {}
    target_users: list = []
    personas: list = []
    requirements: list = []
    goals: list = []
    competitors: list = []
    product_strategy: dict = {}
    user_journeys: list = []
    information_architecture: dict = {}
    design: dict = {}
    architecture: dict = {}
    frontend: dict = {}
    backend: dict = {}
    database: dict = {}
    api: dict = {}
    testing: dict = {}
    security: dict = {}
    devops: dict = {}
    deployment: dict = {}
    seo: dict = {}
    analytics: dict = {}
    discovery: DiscoveryBrain = DiscoveryBrain()
    research: ResearchBrain = ResearchBrain()
    strategy: StrategyBrain = StrategyBrain()
    prd: PrdBrain = PrdBrain()
    ux: UxBrain = UxBrain()
    design_spec: DesignBrain = DesignBrain()
    architecture_spec: ArchitectureBrain = ArchitectureBrain()
    optimization_spec: OptimizationBrain = OptimizationBrain()
    documentation_spec: DocumentationBrain = DocumentationBrain()


SECTIONS = list(ProjectBrain.model_fields)
# Sections the generic brain-edit endpoint must not write (provenance would be forgeable).
PROTECTED_SECTIONS = {"discovery", "research", "strategy", "prd", "ux", "design_spec", "architecture_spec", "optimization_spec", "documentation_spec"}


class IntakeResult(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    product_type: str = Field(min_length=1, max_length=200)
    problem: str = Field(min_length=1, max_length=2000)
    target_users: list[str] = Field(default_factory=list, max_length=20)
    goals: list[str] = Field(default_factory=list, max_length=20)
    features: list[str] = Field(default_factory=list, max_length=30)
    assumptions: list[str] = Field(default_factory=list, max_length=30)
    questions: list[str] = Field(default_factory=list, max_length=10)
