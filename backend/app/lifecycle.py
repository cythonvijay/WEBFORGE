STAGE_DEPS: dict[str, list[str]] = {
    "research": [], "product": ["research"], "ux": ["product"], "design": ["ux"],
    "architecture": ["design"], "frontend": ["architecture"], "backend": ["architecture"],
    "database": ["architecture"], "api": ["backend", "database"],
    "testing": ["frontend", "api"], "security": ["testing"], "docker": ["security"],
    "cicd": ["docker"], "infrastructure": ["cicd"], "deployment": ["infrastructure"],
    "monitoring": ["deployment"], "seo": ["design", "frontend"],
    "analytics": ["frontend", "backend"], "documentation": ["architecture"],
}
STAGES = list(STAGE_DEPS)
STATUSES = {"not_started", "in_progress", "needs_review", "complete", "blocked"}
NEEDS_DEPS = {"in_progress", "needs_review", "complete"}


def unmet_deps(stage: str, statuses: dict[str, str]) -> list[str]:
    return [d for d in STAGE_DEPS[stage] if statuses.get(d) != "complete"]


def next_action(statuses: dict[str, str]) -> str | None:
    for s in STAGES:
        if statuses[s] == "in_progress":
            return s
    for s in STAGES:
        if statuses[s] in ("not_started", "needs_review") and not unmet_deps(s, statuses):
            return s
    return None
