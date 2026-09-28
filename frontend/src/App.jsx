import { useEffect, useRef, useState } from 'react'
import { ArrowDown, ArrowUpRight, BookOpen, CalendarDays, Check, ChevronDown, Compass, CornerDownLeft, Library, MapPin, Menu, MessageCircle, Plus, Search, Settings2, Sparkles, X } from 'lucide-react'

const prompts = [
  { icon: CalendarDays, text: 'Where is my next class?', tag: 'SCHEDULE' },
  { icon: BookOpen, text: 'Find intro to algorithms', tag: 'LIBRARY' },
  { icon: Compass, text: 'How do I get to the CS building?', tag: 'DIRECTIONS' },
]

async function api(path, options) {
  const response = await fetch(`/api/${path}`, { headers: { 'Content-Type': 'application/json' }, ...options })
  if (!response.ok) throw new Error((await response.json()).detail || 'Campus service is unavailable')
  return response.json()
}

function App() {
  const [view, setView] = useState('chat')
  const [messages, setMessages] = useState([])
  const [courses, setCourses] = useState([])
  const [approvals, setApprovals] = useState([])
  const [analytics, setAnalytics] = useState({ by_intent: [], pending_approvals: 0 })
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [preferences, setPreferences] = useState({ home_location: 'Student Center', reminder_minutes: 10 })
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [mobileMenu, setMobileMenu] = useState(false)
  const scrollRef = useRef(null)
  const inputRef = useRef(null)

  const refresh = async () => {
    try {
      const [history, schedule, prefs, approvalData, stats] = await Promise.all([
        api('history'), api('schedule'), api('preferences'), api('approvals'), api('analytics'),
      ])
      setMessages(history.messages)
      setCourses(schedule.courses)
      setPreferences(prefs)
      setApprovals(approvalData.approvals)
      setAnalytics(stats)
      setNotice('')
    } catch {
      setNotice('Could not connect to campus services. Start the API server and try again.')
    }
  }

  useEffect(() => { refresh() }, [])
  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }) }, [messages, busy])

  const send = async (text = input, context = null) => {
    const message = text.trim()
    if (!message || busy) return
    setView('chat')
    setInput('')
    setBusy(true)
    setMessages((current) => [...current, { role: 'user', content: message }, { role: 'pending', content: '' }])
    try {
      const result = await api('chat', { method: 'POST', body: JSON.stringify({ message, context }) })
      setMessages((current) => [...current.slice(0, -1), { role: 'assistant', content: result.answer, intent: result.intent, records: result.records }])
      if (result.intent === 'library') api('approvals').then((data) => setApprovals(data.approvals))
      api('analytics').then(setAnalytics)
    } catch (error) {
      setMessages((current) => [...current.slice(0, -1), { role: 'assistant', content: error.message, intent: 'error' }])
    } finally {
      setBusy(false)
      inputRef.current?.focus()
    }
  }

  const updatePreference = async (key, value) => {
    const updated = { ...preferences, [key]: value }
    setPreferences(updated)
    try {
      await api('preferences', { method: 'PUT', body: JSON.stringify(updated) })
    } catch { setNotice('Preference could not be saved.') }
  }

  const resolveApproval = async (id, status) => {
    try {
      await api(`approvals/${id}?status=${status}`, { method: 'PATCH' })
      const data = await api('approvals')
      setApprovals(data.approvals)
      setAnalytics(await api('analytics'))
    } catch (error) { setNotice(error.message) }
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileMenu ? 'sidebar-open' : ''}`}>
        <div className="brand-row"><div className="brand-mark"><span /></div><span className="brand-name">commons<span>.</span></span><button className="icon-button mobile-close" aria-label="Close menu" onClick={() => setMobileMenu(false)}><X size={18} /></button></div>
        <button className="new-chat" onClick={() => { setView('chat'); setMessages([]); setMobileMenu(false) }}><Plus size={16} /> New conversation <span>⌘ K</span></button>
        <div className="nav-label">YOUR CAMPUS</div>
        <nav className="main-nav">
          <button className={view === 'chat' ? 'nav-item active' : 'nav-item'} onClick={() => { setView('chat'); setMobileMenu(false) }}><MessageCircle size={17} /> Assistant</button>
          <button className={view === 'schedule' ? 'nav-item active' : 'nav-item'} onClick={() => { setView('schedule'); setMobileMenu(false) }}><CalendarDays size={17} /> My schedule</button>
          <button className={view === 'library' ? 'nav-item active' : 'nav-item'} onClick={() => { setView('library'); setMobileMenu(false) }}><Library size={17} /> Library desk</button>
          <button className={view === 'approvals' ? 'nav-item active' : 'nav-item'} onClick={() => { setView('approvals'); setMobileMenu(false) }}><Check size={17} /> Requests <span className="nav-count">{analytics.pending_approvals}</span></button>
        </nav>
        <div className="sidebar-spacer" />
        <div className="campus-card"><div className="campus-card-top"><span className="live-dot" /> CAMPUS STATUS</div><div className="campus-name">Northbridge University</div><div className="campus-caption">Academic year 2026–27</div><div className="campus-weather"><span>☀</span><span>Clear skies</span><span>18°</span></div></div>
        <button className="profile-row" onClick={() => setSettingsOpen(true)}><div className="avatar">AM</div><div className="profile-copy"><strong>Alex Morgan</strong><span>Undergraduate · CS</span></div><Settings2 size={17} className="profile-settings" /></button>
      </aside>
      {mobileMenu && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMobileMenu(false)} />}

      <main className="main-panel">
        <header className="topbar"><div className="topbar-left"><button className="icon-button mobile-menu" aria-label="Open menu" onClick={() => setMobileMenu(true)}><Menu size={19} /></button><span className="breadcrumb">Campus / <strong>{view === 'chat' ? 'Assistant' : view === 'schedule' ? 'My schedule' : view === 'library' ? 'Library desk' : 'Requests'}</strong></span></div><div className="topbar-right"><span className="today-label">MONDAY, SEPTEMBER 28</span><span className="topbar-separator" /><button className="icon-button" aria-label="Search" onClick={() => inputRef.current?.focus()}><Search size={17} /></button><button className="help-button" onClick={() => setSettingsOpen(true)}>Preferences <ChevronDown size={14} /></button></div></header>
        {notice && <div className="notice"><span>{notice}</span><button onClick={() => setNotice('')} aria-label="Dismiss"><X size={15} /></button></div>}

        {view === 'chat' && <section className="chat-layout">
          <div className="chat-column">
            <div className="chat-scroll" ref={scrollRef}>
              {messages.length === 0 ? <div className="welcome-block">
                <div className="eyebrow"><span className="eyebrow-line" /> YOUR DAY, IN ONE PLACE <span className="eyebrow-line" /></div>
                <h1>Good morning,<br /><em>Alex.</em></h1>
                <p className="welcome-subtitle">What can I help you find on campus?</p>
                <div className="prompt-grid">{prompts.map(({ icon: Icon, text, tag }) => <button key={text} className="prompt-card" onClick={() => send(text)}><span className="prompt-icon"><Icon size={17} /></span><span className="prompt-tag">{tag}</span><span className="prompt-text">{text}</span><ArrowUpRight size={16} className="prompt-arrow" /></button>)}</div>
                <div className="today-strip"><div className="today-date"><span className="date-day">28</span><span>SEP<br />MON</span></div><div className="today-divider" /><div className="today-class"><span className="today-class-label">UP NEXT · 9:00 AM</span><strong>Introduction to Computer Science</strong><span>North Hall 204 <span className="dot-sep">·</span> Dr. Maya Chen</span></div><button className="strip-action" onClick={() => send('Where is my next class?')} aria-label="Ask about next class"><ArrowUpRight size={17} /></button></div>
              </div> : <div className="message-list">{messages.map((item, index) => <div key={`${item.id || index}-${index}`} className={`message-row ${item.role}`}>
                {item.role === 'assistant' && <div className="assistant-mark"><Sparkles size={14} /></div>}
                {item.role === 'pending' ? <div className="typing"><i /><i /><i /></div> : <div className="message-body"><div className="message-content">{item.content}</div>{item.records?.length > 0 && <div className="result-list">{item.records.map((record) => <Result key={`${item.intent}-${record.id}`} record={record} intent={item.intent} />)}</div>}{item.role === 'assistant' && item.intent === 'schedule' && !item.content.startsWith('Reminder set') && <button className="followup-link" onClick={() => send('Set a reminder 10 minutes before')}>Set a reminder <ArrowUpRight size={13} /></button>}</div>}
              </div>)}</div>}
            </div>
            <div className="composer-wrap"><form className="composer" onSubmit={(event) => { event.preventDefault(); send() }}><textarea ref={inputRef} value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); send() } }} placeholder="Ask anything about your campus..." rows="1" /><div className="composer-bottom"><span className="composer-hint"><CornerDownLeft size={13} /> Enter to send <span>·</span> Shift + Enter for a new line</span><button className="send-button" disabled={!input.trim() || busy} aria-label="Send message"><ArrowDown size={16} /></button></div></form><div className="privacy-note">Commons can make mistakes. Verify important campus information.</div></div>
          </div>
          <CampusRail courses={courses} send={send} setView={setView} />
        </section>}

        {view === 'schedule' && <section className="page-content"><div className="page-heading"><div><div className="eyebrow page-eyebrow">WEEKLY OVERVIEW</div><h1>Your <em>schedule.</em></h1><p>Classes and rooms for the week ahead.</p></div><button className="outline-button" onClick={() => send('Where is my next class?')}><Compass size={16} /> Find my next class</button></div><div className="schedule-list">{['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'].map((day) => { const items = courses.filter((course) => course.day === day); return <div className="day-row" key={day}><div className="day-heading"><span>{day}</span><span>{items.length ? `${items.length} ${items.length === 1 ? 'class' : 'classes'}` : 'Open'}</span></div><div className="day-events">{items.length ? items.map((course) => <article className="event-row" key={course.id}><span className="event-time">{course.start_time}<small>{course.end_time}</small></span><span className="event-accent" /><span className="event-info"><strong>{course.title}</strong><span>{course.code} <i>·</i> {course.instructor}</span></span><span className="event-room"><MapPin size={14} />{course.room}</span><button className="icon-button event-action" aria-label={`Get directions to ${course.room}`} onClick={() => send(`Directions to ${course.room}`)}><ArrowUpRight size={16} /></button></article>) : <div className="open-day">No classes scheduled</div>}</div></div> })}</div><div className="schedule-footnote"><span className="live-dot" /> Times are shown in local campus time <span>·</span> Schedule synced just now</div></section>}

        {view === 'library' && <LibraryView send={(text) => send(text, 'library')} />}
        {view === 'approvals' && <section className="page-content"><div className="page-heading"><div><div className="eyebrow page-eyebrow">LIBRARY & CAMPUS SERVICES</div><h1>Requests <em>desk.</em></h1><p>Staff review queue for student requests.</p></div><span className="request-count">{analytics.pending_approvals} awaiting review</span></div><div className="approval-list">{approvals.length ? approvals.map((item) => <article className="approval-row" key={item.id}><div className="approval-icon"><BookOpen size={18} /></div><div className="approval-copy"><span className="approval-kind">{item.kind.replace('_', ' ')}</span><strong>{item.details.title || item.details.request}</strong><small>Requested by {item.student_id} · {new Date(`${item.created_at.replace(' ', 'T')}Z`).toLocaleDateString()}</small></div><span className={`approval-status ${item.status}`}>{item.status}</span>{item.status === 'pending' && <div className="approval-actions"><button onClick={() => resolveApproval(item.id, 'declined')}>Decline</button><button onClick={() => resolveApproval(item.id, 'approved')}>Approve <Check size={14} /></button></div>}</article>) : <div className="empty-state"><span className="empty-icon"><Check size={20} /></span><strong>All caught up</strong><p>New reservation and exception requests will appear here.</p></div>}</div><div className="analytics-line"><div><span>REQUESTS BY SERVICE</span><strong>{analytics.by_intent.reduce((total, item) => total + item.requests, 0)}<small> total</small></strong></div>{analytics.by_intent.map((item) => <div key={item.intent}><span>{item.intent.toUpperCase()}</span><strong>{item.requests}<small> requests</small></strong></div>)}</div></section>}
      </main>
      {settingsOpen && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setSettingsOpen(false) }}><section className="settings-modal"><div className="modal-header"><div><span className="eyebrow page-eyebrow">YOUR ACCOUNT</span><h2>Preferences</h2></div><button className="icon-button" aria-label="Close preferences" onClick={() => setSettingsOpen(false)}><X size={18} /></button></div><label className="field-label">Starting point for directions<select value={preferences.home_location} onChange={(event) => updatePreference('home_location', event.target.value)}>{['Student Center', 'Science Library', 'North Hall', 'Innovation Center', 'West Hall'].map((place) => <option key={place}>{place}</option>)}</select></label><label className="field-label">Class reminder lead time<select value={preferences.reminder_minutes} onChange={(event) => updatePreference('reminder_minutes', Number(event.target.value))}>{[0, 5, 10, 15, 30].map((minutes) => <option key={minutes} value={minutes}>{minutes === 0 ? 'No reminder' : `${minutes} minutes before`}</option>)}</select></label><div className="modal-note">Preferences are saved to this campus demo profile.</div><button className="modal-done" onClick={() => setSettingsOpen(false)}>Done <Check size={15} /></button></section></div>}
    </div>
  )
}

function CampusRail({ courses, send, setView }) {
  const dayCourses = courses.filter((course) => course.day === 'Monday')
  return <aside className="right-rail">
    <div className="rail-heading"><span>MONDAY, SEPTEMBER 28</span><button aria-label="Open full schedule" onClick={() => setView('schedule')}><ArrowUpRight size={15} /></button></div>
    <div className="rail-title">On your calendar</div>
    <div className="timeline">{dayCourses.slice(0, 4).map((course, index) => <div className={`timeline-item ${index === 0 ? 'timeline-current' : ''}`} key={course.id}>
      <div className="timeline-time">{course.start_time}</div><div className="timeline-track"><span className="timeline-dot" /><span className="timeline-stem" /></div>
      <div className="timeline-content"><strong>{course.title}</strong><span>{course.room}</span><span className="timeline-code">{course.code} · {course.end_time}</span></div>
    </div>)}{dayCourses.length === 0 && <div className="rail-empty">Your week is still open.</div>}</div>
    <button className="rail-link" onClick={() => setView('schedule')}>View full schedule <ArrowUpRight size={14} /></button>
    <div className="rail-rule" /><div className="rail-heading"><span>QUICK LOOKUP</span><MapPin size={14} /></div>
    <button className="lookup-row" onClick={() => send('Where is the Science Library?')}><span className="lookup-marker"><Library size={15} /></span><span><strong>Science Library</strong><small>Open until 10:00 PM</small></span><ArrowUpRight size={14} /></button>
    <button className="lookup-row" onClick={() => send('How do I get to the Student Center?')}><span className="lookup-marker orange"><MapPin size={15} /></span><span><strong>Student Center</strong><small>Central campus</small></span><ArrowUpRight size={14} /></button>
    <div className="rail-footer"><span className="status-indicator" /> All campus systems operational</div>
  </aside>
}

function Result({ record, intent }) {
  if (intent === 'schedule') return <article className="result-card"><div className="result-symbol"><CalendarDays size={16} /></div><div className="result-copy"><strong>{record.title}</strong><span>{record.code} · {record.day} at {record.start_time} · {record.room}</span><small>{record.instructor}</small></div><span className="result-arrow"><ArrowUpRight size={15} /></span></article>
  if (intent === 'library') return <article className="result-card"><div className="result-symbol book-symbol"><BookOpen size={16} /></div><div className="result-copy"><strong>{record.title}</strong><span>{record.author}</span><small>{record.call_number} · {record.location}</small></div><span className={`availability ${record.copies ? 'available' : 'unavailable'}`}>{record.copies ? `${record.copies} available` : 'Checked out'}</span></article>
  return <article className="result-card"><div className="result-symbol map-symbol"><MapPin size={16} /></div><div className="result-copy"><strong>{record.name}</strong><span>{record.building}</span><small>{record.details}</small><small className="route-copy">{record.route}</small></div><span className="result-arrow"><ArrowUpRight size={15} /></span></article>
}

function LibraryView({ send }) {
  const [query, setQuery] = useState('')
  return <section className="page-content"><div className="page-heading"><div><div className="eyebrow page-eyebrow">CATALOG & COLLECTIONS</div><h1>Library <em>desk.</em></h1><p>Search the campus collection or ask Commons for a match.</p></div></div><form className="library-search" onSubmit={(event) => { event.preventDefault(); send(query); setQuery('') }}><Search size={19} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Title, author, or a few keywords" /><button disabled={!query.trim()}>Search catalog <ArrowUpRight size={15} /></button></form><div className="library-note"><span className="library-note-icon"><Library size={18} /></span><div><strong>Campus collection</strong><p>Seeded catalog with shelf locations, availability, and staff-reviewed reservation requests.</p></div><span className="catalog-count">5 TITLES</span></div><div className="library-suggestions"><span>TRY A SEARCH</span>{['intro to comp sci', 'algorithms', 'design', 'pragmatic programmer'].map((item) => <button key={item} onClick={() => { setQuery(item); send(item) }}>{item}<ArrowUpRight size={13} /></button>)}</div><button className="outline-button library-chat-link" onClick={() => send('How do I reserve a book?')}><MessageCircle size={16} /> Ask about a reservation</button></section>
}

export default App