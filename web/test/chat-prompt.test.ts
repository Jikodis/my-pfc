// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { promptAction, promptSource } from '../src/lib/chat/input'

function page(html: string): HTMLElement {
  document.body.innerHTML = html
  return document.body
}

describe('promptSource', () => {
  it('acts on a button carrying the prompt', () => {
    page('<button data-chat-prompt="add a task">Ask</button>')
    const button = document.querySelector('button')
    expect(promptSource(button)).toBe(button)
  })

  it('acts on a click inside that button', () => {
    page('<button data-chat-prompt="p"><span id="in">Ask</span></button>')
    expect(promptSource(document.getElementById('in'))?.tagName).toBe('BUTTON')
  })

  it('acts on an element with role button', () => {
    page('<div role="button" data-chat-prompt="p">Ask</div>')
    expect(promptSource(document.querySelector('div'))).not.toBeNull()
  })

  it('ignores the attribute on something that is not a button', () => {
    page('<tr data-chat-prompt="p"><td id="cell">row</td></tr>')
    expect(promptSource(document.getElementById('cell'))).toBeNull()
  })

  it('never acts on a click that landed on a link', () => {
    page('<div role="button" data-chat-prompt="p"><a id="l" href="/tasks">Tasks</a></div>')
    expect(promptSource(document.getElementById('l'))).toBeNull()
  })

  it('never acts on a link that carries the attribute itself', () => {
    page('<a id="l" role="button" href="/tasks" data-chat-prompt="p">Tasks</a>')
    expect(promptSource(document.getElementById('l'))).toBeNull()
  })

  it('reads nothing from a target that is not an element', () => {
    expect(promptSource(null)).toBeNull()
    expect(promptSource(document)).toBeNull()
  })
})

describe('promptAction', () => {
  it('prefills a prompt that names a record and never sends it', () => {
    expect(promptAction('Complete the task "x" (task-1).', {})).toEqual({ text: 'Complete the task "x" (task-1).', send: false })
    expect(promptAction('Complete the task "x" (task-1).', { send: '1' }).send).toBe(false)
  })

  it('sends a bare slash command that asks for it', () => {
    expect(promptAction('/pfc-review', { send: '1' })).toEqual({ text: '/pfc-review', send: true })
  })

  it('prefills a bare slash command that did not ask to send', () => {
    expect(promptAction('/pfc-stuck', {}).send).toBe(false)
  })

  it('prefills a slash command with arguments even when asked to send', () => {
    expect(promptAction('/pfc-revive Web UI', { send: '1' })).toEqual({ text: '/pfc-revive Web UI', send: false })
  })

  it('adds what was typed to the prompt and never sends it', () => {
    expect(promptAction('add task: ', { typed: '  call the bank ' })).toEqual({ text: 'add task: call the bank', send: false })
    expect(promptAction('/pfc-stuck', { send: '1', typed: '' }).send).toBe(false)
  })
})
