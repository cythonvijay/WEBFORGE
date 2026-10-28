"""QA-ONLY harness: runs the real FastAPI app with a deterministic AI *test double* so the browser flow can be exercised
without a provider key. Never used by the product. Switch behavior by writing ok|unconfigured|error|malformed to the mode file.
    cd backend && DATABASE_URL=... JWT_SECRET=... python ../frontend/qa/qa_backend.py"""
import os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
import uvicorn
from app import ai
from app.brain import IntakeResult
from app.main import app

MODE_FILE = os.environ.get("QA_PROVIDER_MODE_FILE", "/tmp/qa/provider_mode")
import json


def Q(prompt, target, qtype="free_text", options=(), required=False, priority=3):
    return {"prompt": prompt, "rationale": "This changes what the first release must contain.", "target": target, "qtype": qtype,
            "options": [{"id": i, "label": l} for i, l in options], "required": required, "priority": priority}


ROUNDS = {
    1: [Q("Who will use the product first?", "target_users", required=True, priority=1),
        Q("Which feature must the first release include?", "mvp_scope", "single_choice", [("booking", "Online booking"), ("payments", "Payments"), ("reviews", "Reviews")], True, 2),
        Q("Which systems must it connect to?", "integrations", "multiple_choice", [("stripe", "Stripe"), ("calendar", "Calendar"), ("email", "Email")], False, 3),
        Q("Will you store personal customer data?", "security_privacy", "confirmation", priority=3),
        Q("How will the product make money?", "business_model", priority=4)],
    2: [Q("Who will use the product first?", "target_users", priority=1),  # duplicate: must be filtered
        Q("What must a customer be able to do in one visit?", "core_workflows", priority=2, required=True),
        Q("When do you want to launch?", "launch_goals", priority=3)],
}


class QAProvider(ai.AIProvider):
    async def generate(self, prompt):
        mode = open(MODE_FILE).read().strip() if os.path.exists(MODE_FILE) else "ok"
        if mode == "unconfigured": raise ai.ProviderNotConfigured("test double")
        if mode == "error": raise ai.ProviderError("Google AI request failed: ReadTimeout")
        if mode == "malformed": return '{"questions": [{"prompt": "x"}]}'
        if "product analyst" in prompt:
            return IntakeResult(product_name="Local Store Builder", product_type="SaaS e-commerce platform", problem="Small businesses lack the skills to run an online store.",
                                target_users=["Independent shop owners"], goals=["Launch a store in a day"], features=["Guided store setup"],
                                assumptions=["Owners have no developer"], questions=["Which payment providers?"]).model_dump_json()
        if "PRELIMINARY research plan" in prompt:
            F = lambda topic, statement, evidence: {"topic": topic, "statement": statement, "evidence": evidence}  # noqa: E731
            return json.dumps({"objectives": ["Understand how customers choose a photographer", "Learn what makes photographers join a platform"],
                               "research_questions": ["What makes customers trust a photographer online?", "How do customers compare packages today?", "Why might photographers resist booking fees?"],
                               "scope_in": ["Local portrait and event photography"], "scope_out": ["Stock photography"],
                               "findings": [F("user_needs", "Customers probably struggle to compare photographers on price and style.", "hypothesis"),
                                            F("market_context", "Demand for local photography may be seasonal around weddings and holidays.", "unsupported"),
                                            F("competitors_alternatives", "Customers likely rely on social media and word of mouth today.", "hypothesis"),
                                            F("market_context", "About 40% of small studios have no online booking.", "hypothesis"),
                                            F("risks", "Photographers may resist online booking fees.", "ai_suggestion"),
                                            F("recommendations", "Interview five local photographers before building the booking flow.", "ai_suggestion")],
                               "unresolved_questions": ["Which cities should launch first?", "Who pays the platform fee?"]})
        n = int(re.search(r"round (\d+)", prompt).group(1))
        return json.dumps({"questions": ROUNDS.get(n, [])})


ai.get_provider = lambda: QAProvider()
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")), log_level="warning")
