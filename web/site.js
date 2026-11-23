// Shared by the three pages: the top bar, the theme switch, and how a turn is drawn.

// Set the theme before the page paints, so there is no flash of the wrong one.
document.documentElement.dataset.theme = localStorage.getItem("theme")
  || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");

function topBar(current) {
  const link = (href, name) => `<a href="${href}" ${href === current ? 'aria-current="page"' : ""}>${name}</a>`;
  document.body.insertAdjacentHTML("afterbegin", `
    <header class="bar">
      <a class="brand" href="/">Help<i>line</i></a>
      <nav>${link("/", "Call")}${link("/how", "How it works")}${link("/history", "Calls")}</nav>
      <button id="theme" aria-label="Switch between light and dark">
        <svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
          <circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19"/></svg>
        <svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round">
          <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z"/></svg>
      </button>
    </header>`);
  document.getElementById("theme").onclick = () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("theme", next);
    document.dispatchEvent(new Event("themechange"));
  };
}

const esc = t => (t ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));

const REASONS = {
  out_of_scope: "the six articles do not cover this",
  account_lookup: "it cannot look up accounts or transfers",
  asked_for_human: "the caller asked for a person",
  needs_human: "this needs a person straight away",
  rule_bending: "the caller tried to change its rules",
  other_language: "it only handles English",
  unclear_twice: "it could not understand twice in a row",
  bad_label: "the model's reply was not in the required form, so it was not spoken",
  unsupported_number: "the reply had a number that is not in the article, so it was not spoken",
  not_plain_speech: "the reply had markup or a link in it, so it was not spoken",
  too_long: "the reply was too long to read out, so it was not spoken",
  model_error: "the model did not respond in time",
  silence: "the caller stayed silent",
};
const KINDS = {greeting: "Greeting", still_there: "Checking the caller is there", identity: "Asked what it is",
               repeat: "Asked to repeat", wait: "Asked to wait", other: "No question yet"};
const TAGS = {answer: "Answer", handoff: "Handoff", chat: "Fixed line", unclear: "Ask again", end: "Goodbye"};

function because(turn, articles) {
  if (turn.action === "answer") {
    const a = articles[turn.detail];
    return a ? `from <a href="${esc(a.source)}" target="_blank" rel="noopener">${esc(a.title)}</a>` : `from article ${esc(turn.detail)}`;
  }
  if (turn.action === "handoff") return REASONS[turn.detail] || esc(turn.detail);
  if (turn.action === "end") return turn.detail === "silence" ? REASONS.silence : "the caller was finished";
  if (turn.action === "unclear") return "could not make out a question";
  return (KINDS[turn.detail] || esc(turn.detail || "")).toLowerCase();
}

function turnHtml(turn, articles) {
  return `<div class="turn">
    ${turn.heard ? `<div class="said-by"><span class="who mono">Caller</span><span class="caller-line">${esc(turn.heard)}</span></div>` : ""}
    <div class="said-by"><span class="who mono">Agent</span><span class="agent-line">${esc(turn.said)}</span></div>
    <div class="because"><span class="pill ${turn.action}">${TAGS[turn.action] || turn.action}</span>
      <span>${because(turn, articles)}</span>${turn.model_ms ? `<span>· decided in ${(turn.model_ms / 1000).toFixed(1)} s</span>` : ""}</div>
  </div>`;
}

// Follow the agent's call log live. Calls onChange with every record so far,
// first for what already exists and then each time the agent writes a line.
function followLog(call, onChange) {
  const records = [], source = new EventSource("/api/events" + (call ? "?call=" + call : ""));
  let queued = false;
  source.onopen = () => { records.length = 0; };        // a reconnect replays the log from the start
  source.onmessage = event => {
    records.push(JSON.parse(event.data));
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; onChange(records); });
  };
  return source;
}

function groupCalls(records) {
  const calls = new Map();
  for (const r of records) {
    if (!("action" in r)) continue;
    if (!calls.has(r.call_id)) calls.set(r.call_id, {id: r.call_id, time: r.time, turns: []});
    calls.get(r.call_id).turns.push(r);
  }
  return calls;
}
