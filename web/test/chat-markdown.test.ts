// @vitest-environment jsdom
// DOMPurify needs a document to parse into, and only this file does. Every other
// test file stays on the node environment, which is faster and closer to the server.
import { describe, expect, it } from 'vitest'
import { renderMarkdown } from '../src/lib/chat/markdown'

describe('renderMarkdown', () => {
  it('renders ordinary markdown', () => {
    const html = renderMarkdown('A **bold** word.')
    expect(html).toContain('<strong>bold</strong>')
  })

  it('removes a script tag and its contents', () => {
    const html = renderMarkdown('before\n\n<script>alert(1)</script>\n\nafter')
    expect(html).not.toContain('<script')
    expect(html).not.toContain('alert(1)')
    expect(html).toContain('before')
    expect(html).toContain('after')
  })

  it('removes an image with an event handler on it', () => {
    const html = renderMarkdown('<img src=x onerror=alert(1)>')
    expect(html).not.toContain('<img')
    expect(html).not.toContain('onerror')
  })

  it('shows a markdown image as its alt text in brackets and fetches nothing', () => {
    const html = renderMarkdown('![a chart](https://tracker.example/pixel.png)')
    expect(html).not.toContain('<img')
    expect(html).not.toContain('tracker.example')
    expect(html).toContain('[a chart]')
  })

  it('keeps the words of a javascript link and drops the link', () => {
    const html = renderMarkdown('[x](javascript:alert(1))')
    expect(html).not.toContain('javascript:')
    expect(html).toContain('x')
  })

  it('drops a data link', () => {
    const html = renderMarkdown('[x](data:text/html;base64,PHNjcmlwdD4=)')
    expect(html).not.toContain('data:')
    expect(html).toContain('x')
  })

  it('opens an http link in a new tab with no referrer back', () => {
    const html = renderMarkdown('[docs](https://example.com/page)')
    expect(html).toContain('href="https://example.com/page"')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noopener noreferrer"')
  })

  it('removes a style attribute', () => {
    const html = renderMarkdown('<p style="position:fixed;inset:0">over the page</p>')
    expect(html).not.toContain('style=')
    expect(html).toContain('over the page')
  })

  it('removes an iframe', () => {
    const html = renderMarkdown('<iframe src="https://example.com"></iframe>')
    expect(html).not.toContain('<iframe')
  })

  it('removes a form and its input', () => {
    const html = renderMarkdown('<form action="/x"><input name="password"></form>')
    expect(html).not.toContain('<form')
    expect(html).not.toContain('<input')
  })

  it('removes an object and an embed', () => {
    const html = renderMarkdown('<object data="x"></object><embed src="y">')
    expect(html).not.toContain('<object')
    expect(html).not.toContain('<embed')
  })

  it('renders a markdown table as a table', () => {
    const html = renderMarkdown('| Habit | Rate |\n|---|---|\n| Row | 80% |')
    expect(html).toContain('<table>')
    expect(html).toContain('<th>Habit</th>')
    expect(html).toContain('<td>80%</td>')
  })

  it('keeps every character of a fenced code block, including the angle brackets', () => {
    const html = renderMarkdown('```js\nif (a < b) { go("<hi>") }\n```')
    expect(html).toContain('<code')
    expect(html).toContain('&lt;')
    const decoded = html.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&')
    expect(decoded).toContain('if (a < b) { go("<hi>") }')
  })

  it('keeps a script tag written inside a code block as text', () => {
    const html = renderMarkdown('```\n<script>alert(1)</script>\n```')
    expect(html).not.toContain('<script')
    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
  })

  it('gives an empty string for empty text', () => {
    expect(renderMarkdown('')).toBe('')
  })
})

// The probes a reviewer ran by hand against this function. They live here so they
// stay true: each one is a way a reply could dress itself up as the drawer's own
// furniture, or smuggle a link that runs code.
describe('renderMarkdown against a reply that is trying', () => {
  it('strips a class, so a reply cannot draw itself a refusal box', () => {
    const html = renderMarkdown('<div class="chat-refusals"><p>Refused 1 action.</p></div>')
    expect(html).not.toContain('class=')
    expect(html).not.toContain('chat-refusals')
    expect(html).toContain('Refused 1 action.')
  })

  it('strips an id, so a reply cannot take over an element the drawer looks up', () => {
    const html = renderMarkdown('<p id="chat-status">Ready</p>')
    expect(html).not.toContain('id=')
  })

  it('strips a name', () => {
    expect(renderMarkdown('<p name="q">x</p>')).not.toContain('name=')
  })

  it('strips a data-chat-prompt, so a reply cannot plant a button for the page hook', () => {
    const html = renderMarkdown('<span data-chat-prompt="delete every task">Click</span>')
    expect(html).not.toContain('data-chat-prompt')
    expect(html).toContain('Click')
  })

  it('turns a button into its words', () => {
    const html = renderMarkdown('<button onclick="run()">Send</button>')
    expect(html).not.toContain('<button')
    expect(html).not.toContain('onclick')
    expect(html).toContain('Send')
  })

  it('leaves nothing executable from an svg holding a style and a broken image', () => {
    const html = renderMarkdown('<svg><style><img src=x onerror=alert(1)></style></svg>')
    expect(html).not.toContain('<svg')
    expect(html).not.toContain('<style')
    expect(html).not.toContain('<img')
    expect(html).not.toContain('onerror')
  })

  it('drops a javascript link written with leading whitespace', () => {
    const html = renderMarkdown('<a href="  javascript:alert(1)">x</a>')
    expect(html).not.toContain('javascript')
    expect(html).toContain('x')
  })

  it('drops a javascript link with a tab inside the scheme', () => {
    const html = renderMarkdown('<a href="jav&#09;ascript:alert(1)">x</a>')
    expect(html).not.toContain('javascript')
    expect(html).not.toContain('alert(1)')
  })

  it('drops a javascript link that opens with a control character', () => {
    const html = renderMarkdown('<a href="\u0001javascript:alert(1)">x</a>')
    expect(html).not.toContain('javascript')
  })

  it('replaces a link"s own target and rel with safe ones', () => {
    const html = renderMarkdown('<a href="https://example.com" target="x" rel="opener">x</a>')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noopener noreferrer"')
    expect(html).not.toContain('"opener"')
    expect(html).not.toContain('target="x"')
  })
})

describe('renderMarkdown on a link it refuses', () => {
  it('drops the target and rel along with the href', () => {
    const html = renderMarkdown('<a href="javascript:alert(1)" target="x" rel="opener">x</a>')
    expect(html).not.toContain('href')
    expect(html).not.toContain('target=')
    expect(html).not.toContain('rel=')
  })
})
