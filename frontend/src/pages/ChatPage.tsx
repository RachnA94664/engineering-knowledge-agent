import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { api, ApiError } from '../api/client'
import type { ChatResult } from '../api/types'
import { Badge } from '../components/Badge'
import { Icon } from '../components/Icon'
import { RecordList, ToolTrace } from '../components/Evidence'
import { ProposalCard } from '../components/ProposalCard'
import { MESSAGE_MAX_LENGTH } from '../lib/format'

interface Turn {
  id: number
  role: 'user' | 'assistant' | 'error' | 'note'
  text: string
  result?: ChatResult
}

const SUGGESTIONS = [
  'Which requirements have no test cases?',
  'Show me high-risk items',
  'Show me requirement REQ-001',
  'Which test cases are associated with REQ-001?',
  'Set REQ-006 priority to high',
  'What is the impact of REQ-009?',
  'Which risks need review?',
]

function Verdict({ result }: { result: ChatResult }) {
  if (result.refused) return <Badge value="refused" label="Declined" />
  if (result.grounded) return <Badge value="pass" label="Checked against the database" />
  return <Badge value="blocked" label="Not verified" />
}

export function ChatPage() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const abortRef = useRef<AbortController | null>(null)
  const endRef = useRef<HTMLDivElement | null>(null)
  const nextId = useRef(1)

  // Count the seconds while the AI is working: on a slow computer an answer can take a minute.
  useEffect(() => {
    if (!busy) return
    const started = Date.now()
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 500)
    return () => window.clearInterval(timer)
  }, [busy])

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' })
  }, [turns, busy])

  function add(turn: Omit<Turn, 'id'>) {
    setTurns((all) => [...all, { ...turn, id: nextId.current++ }])
  }

  async function send(raw: string) {
    const message = raw.trim()
    if (!message || busy) return
    if (message.length > MESSAGE_MAX_LENGTH) return
    add({ role: 'user', text: message })
    setInput('')
    setElapsed(0)
    setBusy(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const result = await api.chat(message, controller.signal)
      add({ role: 'assistant', text: result.answer, result })
    } catch (error) {
      if (error instanceof ApiError && error.code === 'cancelled') {
        add({ role: 'note', text: 'Cancelled. The server may still finish the request.' })
      } else {
        add({ role: 'error', text: error instanceof ApiError ? error.message : 'Unexpected error.' })
      }
    } finally {
      abortRef.current = null
      setBusy(false)
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    void send(input)
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void send(input)
    }
  }

  const tooLong = input.length > MESSAGE_MAX_LENGTH

  return (
    <section className="page chat" aria-labelledby="chat-title">
      <header className="page-header">
        <h2 id="chat-title">Ask the knowledge base</h2>
        <p className="lead">
          Answers come only from the database. The AI can <strong>propose</strong> a change, but a
          person must confirm it.
        </p>
      </header>

      <div className="conversation" aria-live="polite">
        {turns.length === 0 && (
          <div className="suggestions">
            <p className="suggestions-title">Try asking</p>
            <div className="suggestion-grid">
              {SUGGESTIONS.map((text) => (
                <button key={text} type="button" className="suggestion" onClick={() => void send(text)}>
                  {text}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn) => (
          <div key={turn.id} className={`turn turn-${turn.role}`}>
            {turn.role === 'user' && <div className="bubble bubble-user">{turn.text}</div>}
            {turn.role === 'note' && <div className="notice">{turn.text}</div>}
            {turn.role === 'error' && (
              <div className="notice notice-error" role="alert">
                {turn.text}
              </div>
            )}
            {turn.role === 'assistant' && turn.result && (
              <div className="bubble bubble-assistant">
                <span className="avatar" aria-hidden="true">
                  <Icon name="spark" size={14} />
                </span>
                <div className="bubble-body">
                <div className="answer">{turn.text}</div>
                <div className="verdict">
                  <Badge value={turn.result.intent} />
                  <Verdict result={turn.result} />
                </div>
                <RecordList records={turn.result.records} />
                <ToolTrace calls={turn.result.tool_calls} />
                {turn.result.pending_changes.map((proposal) => (
                  <ProposalCard key={proposal.change.id} change={proposal.change} preview={proposal.preview} />
                ))}
                </div>
              </div>
            )}
          </div>
        ))}

        {busy && (
          <div className="turn" role="status">
            <div className="bubble bubble-assistant thinking">
              <span className="spinner" aria-hidden="true" /> Thinking… {elapsed}s <span className="muted">(a small local model can take a minute)</span>
              <button type="button" className="btn btn-small" onClick={() => abortRef.current?.abort()}>
                Cancel
              </button>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form className="composer" onSubmit={onSubmit}>
        <label htmlFor="message" className="visually-hidden">
          Your message
        </label>
        <div className="composer-box">
          <textarea
            id="message"
            rows={2}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask a question, or say what to change…  (Enter to send, Shift+Enter for a new line)"
            aria-invalid={tooLong}
          />
          <div className="composer-row">
            <span className={tooLong ? 'counter counter-bad' : 'counter'}>
              {input.length}/{MESSAGE_MAX_LENGTH}
            </span>
            <button
              type="submit"
              className="btn btn-primary btn-send"
              aria-label="Send"
              disabled={busy || !input.trim() || tooLong}
            >
              <Icon name="send" size={16} />
            </button>
          </div>
        </div>
      </form>
    </section>
  )
}
