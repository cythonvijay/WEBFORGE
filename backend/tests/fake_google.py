"""A fake Google Generative Language API at the HTTP level (httpx.MockTransport). It speaks the documented generateContent
request/response shapes, so the REAL GoogleAIProvider code runs end to end. It is NOT Google: passing against it proves our
request building, parsing, error handling and workflow, not that Google accepts the key, model or prompts."""
import json
import re

import httpx

from app.brain import IntakeResult


def envelope(text: str, finish: str = "STOP") -> dict:
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": finish}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 10, "totalTokenCount": 20}}


def error_body(code: int, status: str, message: str = "boom") -> dict:
    return {"error": {"code": code, "message": message, "status": status}}


def Q(prompt, target, qtype="free_text", options=(), required=False, priority=3):
    return {"prompt": prompt, "rationale": "This changes what the first release must contain.", "target": target, "qtype": qtype,
            "options": [{"id": i, "label": l} for i, l in options], "required": required, "priority": priority}


ROUNDS = {
    1: [Q("Who will book photographers on the site first?", "target_users", required=True, priority=1),
        Q("Which booking feature must the first release include?", "mvp_scope", "single_choice", [("calendar", "Calendar booking"), ("deposit", "Online deposits")], True, 2),
        Q("Will photographers upload personal client galleries?", "security_privacy", "confirmation", priority=3)],
    2: [Q("Who will book photographers on the site first?", "target_users", priority=1),  # repeat: must be filtered
        Q("How will the platform earn revenue from bookings?", "business_model", priority=2)],
}


class FakeGoogle:
    """Records every request; `handler` can be replaced per test. Routes by prompt content like a (very simple) model would."""

    def __init__(self, key: str, model: str):
        self.key, self.model, self.requests, self.override = key, model, [], None
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.override is not None:
            return self.override(request)
        if request.headers.get("x-goog-api-key") != self.key:
            return httpx.Response(400, json=error_body(400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key."))
        if not request.url.path.endswith(f"/models/{self.model}:generateContent"):
            return httpx.Response(404, json=error_body(404, "NOT_FOUND", "model not found"))
        prompt = json.loads(request.content)["contents"][0]["parts"][0]["text"]
        if '"word": "pong"' in prompt:
            return httpx.Response(200, json=envelope('{"ok": true, "word": "pong"}'))
        if "product analyst" in prompt:
            out = IntakeResult(product_name="PhotoBook", product_type="marketplace", problem="Hard to compare local photographers",
                               target_users=["Couples", "Families"], goals=["Increase bookings"], features=["Package comparison"],
                               assumptions=["Customers pay online"], questions=["Who pays the fee?"])
            return httpx.Response(200, json=envelope(out.model_dump_json()))
        m = re.search(r"round (\d+)", prompt)
        if not m:
            return httpx.Response(200, json=envelope("ok"))
        n = int(m.group(1))
        return httpx.Response(200, json=envelope(json.dumps({"questions": ROUNDS.get(n, [])})))
