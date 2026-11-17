/**
 * The user's own words, shown as words. Statements and titles are written in
 * markdown files, so a few of them carry emphasis markers that mean nothing once
 * the text is already inside an HTML element.
 */

/**
 * Strips the asterisks and underscores markdown uses for emphasis and leaves every
 * other character alone. A lone asterisk stays (it is arithmetic, not emphasis),
 * and an underscore inside a name such as sleep_hours stays.
 */
export function plainText(s: string): string {
  return (s ?? '')
    .replace(/\*\*(\S(?:[^*\n]*\S)?)\*\*/g, '$1')
    .replace(/__(\S(?:[^_\n]*\S)?)__/g, '$1')
    .replace(/\*(\S(?:[^*\n]*\S)?)\*/g, '$1')
    .replace(/(^|[\s(["'])_(\S(?:[^_\n]*\S)?)_(?=$|[\s).,;:!?"'])/g, '$1$2')
}

/**
 * A stored value written in one lower-case word, or several joined by underscores,
 * reads as words: 'with_fat' shows as 'With fat'. Free text, ids, file paths, and
 * anything with a capital letter or a digit are left exactly as they are.
 */
export function readableValue(value: string): string {
  return /^[a-z]+(_[a-z]+)+$/.test(value ?? '') ? areaLabel(value) : value
}

/**
 * A slug reads as a name on the page while the link keeps the slug itself:
 * 'health' shows as 'Health', 'master_bathroom' as 'Master bathroom'.
 */
export function areaLabel(slug: string): string {
  const words = (slug ?? '').replace(/[_-]+/g, ' ').trim()
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : ''
}
