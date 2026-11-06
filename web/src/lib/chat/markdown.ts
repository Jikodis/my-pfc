/**
 * A reply turned into HTML the drawer can show.
 *
 * The text comes from a model that has just read this person's files and, often
 * enough, a page on the internet. It is not trusted, whatever it says about itself,
 * so it goes through `marked` and then through DOMPurify before it reaches the page,
 * and this module is the only place that turn happens.
 *
 * What is taken out, and why:
 *
 * - `script`, `iframe`, `object`, `embed`, `form`, `input`, `style`, and every event
 *   handler attribute: a reply may not run code or ask this person to type into it.
 * - every image: the policy allows `https:` images, so a model supplied image URL is
 *   a request to somebody else's server that says when this page was open. The alt
 *   text is shown in brackets instead, which is the part that meant anything.
 * - a link that is not http or https: the href goes and the words stay, so
 *   `javascript:` and `data:` cannot be clicked.
 *
 * Tool output and error text never come through here. Those are written with
 * `textContent`, which cannot be markup at all.
 */
import DOMPurify from 'dompurify'
import { Marked } from 'marked'

/** Text going into HTML as text. The sanitizer would drop the markup; this keeps the characters. */
function escape(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

const marked = new Marked({
  gfm: true,
  // A chat reply is written the way a person types, so one newline is one line break.
  breaks: true,
  renderer: {
    image({ text }) {
      return escape(`[${text || 'image'}]`)
    },
  },
})

const CLEAN: Parameters<typeof DOMPurify.sanitize>[1] = {
  USE_PROFILES: { html: true },
  FORBID_TAGS: [
    'style', 'script', 'iframe', 'form', 'input', 'object', 'embed', 'img', 'picture', 'source',
    'video', 'audio', 'canvas', 'textarea', 'button', 'select', 'option', 'link', 'meta', 'base',
  ],
  // class, id, and name go because the drawer's own look is class driven: with
  // them a reply can draw itself a yellow refusal box, an error box, or a bubble
  // that reads as the person's own words, and can take over an id this script
  // looks up.
  FORBID_ATTR: ['style', 'class', 'id', 'name', 'src', 'srcset', 'background', 'formaction', 'ping'],
  ALLOW_DATA_ATTR: false,
}

let hooked = false

/**
 * Link handling, run after DOMPurify has finished with the attributes.
 *
 * It reads the href that survived and decides from the resolved protocol, rather
 * than from how the text begins, because `java\tscript:` and a stack of slashes are
 * both ways to write something that looks relative and is not.
 */
function addLinkHook(): void {
  if (hooked) return
  hooked = true
  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (!(node instanceof Element) || node.tagName !== 'A') return
    const href = node.getAttribute('href')
    if (href === null) {
      // DOMPurify already took an href it recognized as unsafe; the words stay, and
      // nothing about where the link would have opened stays with them.
      node.removeAttribute('target')
      node.removeAttribute('rel')
      return
    }
    let protocol = ''
    try {
      protocol = new URL(href, document.baseURI).protocol
    } catch {
      protocol = ''
    }
    if (protocol === 'http:' || protocol === 'https:') {
      node.setAttribute('target', '_blank')
      node.setAttribute('rel', 'noopener noreferrer')
    } else {
      // Words with no link, so nothing about where it would have opened stays either.
      node.removeAttribute('href')
      node.removeAttribute('target')
      node.removeAttribute('rel')
    }
  })
}

/** One reply, as HTML that is safe to put in the page. */
export function renderMarkdown(source: string): string {
  if (!source) return ''
  addLinkHook()
  const html = marked.parse(source, { async: false })
  return DOMPurify.sanitize(html, CLEAN)
}
