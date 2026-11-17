/**
 * The Review page's two pure pieces: the line that says why the review is up, and the
 * answers object a filled form becomes.
 *
 * Which review is due, and what its form asks, come from Python
 * (`automations/scripts/review_forms.py` through `getReview`). This module rewords a
 * stored number and reshapes what was tapped and typed; it decides nothing.
 */
import { PROMPTS, chatPrompt } from './chat/prompts'

/** The words for how late the review is. `overdueDays` is null for a review never done. */
export function reviewDue(overdueDays: number | null): string {
  if (overdueDays === null) return 'Never done yet.'
  if (overdueDays <= 0) return 'Due today.'
  return `${overdueDays} ${overdueDays === 1 ? 'day' : 'days'} overdue.`
}

/** How many reviews wait, said so it is clear only one is shown. */
export function dueCountLine(count: number): string {
  return `${count} ${count === 1 ? 'review' : 'reviews'} due; one at a time.`
}

/** What the page holds: the option tapped per row, the note per row, the text per prompt. */
export type FormState = {
  choices: Record<string, string>
  notes: Record<string, string>
  prompts: Record<string, string>
}

export type Answers = {
  review: string
  choices: Record<string, string>
  notes: Record<string, string>
  prompts: Record<string, string>
  /** Every row the form showed, so a review too long for one form carries on after them. */
  shown?: string[]
}

/** One map with every blank entry left out and the rest trimmed. */
function filled(map: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [key, value] of Object.entries(map)) {
    const text = (value ?? '').trim()
    if (text) out[key] = text
  }
  return out
}

/**
 * The answers shape `review_forms.py` documents. A blank row or prompt is not an
 * answer, so it is left out rather than sent empty.
 */
export function buildAnswers(review: string, state: FormState, shown: string[] = []): Answers {
  const answers: Answers = { review, choices: filled(state.choices), notes: filled(state.notes), prompts: filled(state.prompts) }
  if (shown.length) answers.shown = shown
  return answers
}

/** True when nothing was answered, so there is nothing to apply. */
export function isEmpty(answers: Answers): boolean {
  return !Object.keys(answers.choices).length && !Object.keys(answers.notes).length && !Object.keys(answers.prompts).length
}

/** The command that applies the form: `/pfc-review <id> answers <json>`. */
export function answersPrompt(answers: Answers): string {
  return chatPrompt(PROMPTS.reviewAnswers, { id: answers.review, json: JSON.stringify(answers) })
}
