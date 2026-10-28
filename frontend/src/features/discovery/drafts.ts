import type { DiscoveryQuestion, Draft } from "../../types/discovery";

const DEFAULT_MAX = 2000;

/** The form value that corresponds to the answer stored on the server. */
export function draftFromAnswer(q: DiscoveryQuestion): Draft {
  const a = q.answer;
  if (!a) return undefined;
  if (q.qtype === "free_text") return a.text ?? "";
  if (q.qtype === "single_choice") return a.choice;
  if (q.qtype === "multiple_choice") return a.choices ?? [];
  return a.confirmed;
}

export const isFilled = (d: Draft) => d !== undefined && d !== "" && !(Array.isArray(d) && d.length === 0);

function sameAsSaved(q: DiscoveryQuestion, d: Draft): boolean {
  const saved = draftFromAnswer(q);
  if (typeof d === "string" && q.qtype === "free_text") return d.trim() === saved;
  if (Array.isArray(d) && Array.isArray(saved)) return [...d].sort().join("|") === [...saved].sort().join("|");
  return d === saved;
}

/** A draft needs saving when something was entered and it differs from what the server holds. */
export const isPending = (q: DiscoveryQuestion, d: Draft) => isFilled(d) && !(q.status === "answered" && sameAsSaved(q, d));

/** Client-side checks mirror the server's, only to save a round trip. The server stays authoritative. */
export function validateDraft(q: DiscoveryQuestion, d: Draft): string | undefined {
  if (q.qtype === "free_text" && typeof d === "string") {
    if (!d.trim()) return "Answer can't be empty.";
    const max = q.max_length ?? DEFAULT_MAX;
    if (d.trim().length > max) return `Answer must be at most ${max} characters.`;
  }
  return undefined;
}
