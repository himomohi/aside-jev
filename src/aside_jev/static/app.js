import { createI18n, messages } from "./i18n.mjs";
import { demo, migrateDemo, displayDescription } from "./demo.mjs";
const i18n = createI18n("aside-jev.dashboard.language");
const t = (key, values) => i18n.t(key, values);
const $ = (id) => document.getElementById(id);
const apiMessages = {
  configuration: "Set TYPESAFE_API_KEY on the server, then restart the workspace.",
  timeout: "Jev exceeded an HTTP timeout. Check the connection and timeout setting.",
  authentication: "Jev authentication failed. Check the server API key and model access.",
  rate_limit: "Jev rate limit reached. Wait before retrying.",
  busy: "Other decisions are running. Wait before retrying.",
  invalid_response: "Could not validate the Jev response. Check the candidates.",
  invalid_request: "Jev rejected the request. Check the model and input schema.",
  unavailable: "Could not reach Jev. Check the server connection.",
  input: "Check the goal, candidates, observation and settings.",
  origin: "Use the workspace on this computer to make the request.",
  session: "Reload the page, then try again.",
  not_found: "The requested resource was not found.",
};
function uiError(key, values = {}) {
  return Object.assign(new Error(key), { uiKey: key, values });
}
function apiError(code, detail) {
  if (Object.hasOwn(apiMessages, code)) return uiError(apiMessages[code]);
  return detail ? uiError("Backend detail (original): {detail}", { detail }) : uiError("Could not process the decision request.");
}
function errorText(error) {
  return error?.uiKey ? t(error.uiKey, error.values) : t("Enter a valid value.");
}
let example = demo(t);
let input = {
  ...structuredClone(example),
  model: "jev-latest",
  min_confidence: 0.7,
  timeout_s: 15,
};
let config = null;
let busy = false;
let current = null;
let history = [];
let runNumber = 0;
let revision = 0;
let toastTimer;
let resultError = null;
let settingsError = null;
let connectionFailed = false;

function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function announce(text) {
  $("announcement").textContent = text;
}
function toast(text) {
  clearTimeout(toastTimer);
  $("toast").textContent = text;
  $("toast").hidden = false;
  toastTimer = setTimeout(() => {
    $("toast").hidden = true;
  }, 2800);
}
function formatMs(ms) {
  return ms < 1
    ? "< 1"
    : ms < 100
      ? ms.toFixed(1)
      : Math.round(ms).toLocaleString(i18n.locale);
}
function metric(id, value, unit) {
  $(id).replaceChildren(node("span", value), node("small", unit));
}
function provider() {
  return document.querySelector('input[name="provider"]:checked').value;
}
function updateMode() {
  revision++;
  $("mode-note").textContent =
    provider() === "mock"
      ? t("The local demo selects the first candidate. No API calls or browser actions.")
      : t("Jev decides using inputs sent to TypeSafe. Account usage applies; no browser action is executed.");
  resetResult();
}
function renderInputs() {
  const obs = input.observation;
  $("observation-title").textContent =
    typeof obs === "object"
      ? typeof obs.title === "string"
        ? obs.title
        : t("Current observation")
      : t("Text observation");
  const chars = JSON.stringify(obs).length;
  $("observation-meta").textContent =
    t("{chars} characters · min confidence {confidence}% · HTTP timeout {timeout}s", { chars: chars.toLocaleString(i18n.locale), confidence: Math.round(input.min_confidence * 100), timeout: input.timeout_s });
  $("candidate-count").textContent = input.candidates.length;
  $("candidate-list").replaceChildren(
    ...input.candidates.map((candidate, index) => {
      const row = node("li", undefined, "candidate-row");
      row.dataset.id = candidate.id;
      const copy = node("div", undefined, "candidate-copy");
      copy.append(
        node("strong", candidate.id),
        node("p", candidate.description),
      );
      row.append(
        node("span", String(index + 1).padStart(2, "0"), "candidate-number"),
        copy,
        node(
          "span",
          candidate.id === "abstain"
            ? t("Abstain")
            : candidate.tool
              ? t("Action")
              : t("Review"),
          "candidate-type",
        ),
      );
      return row;
    }),
  );
}
function setView(view) {
  for (const [name, id] of Object.entries({
    empty: "empty-result",
    pending: "pending-result",
    result: "result-content",
    error: "result-error",
  }))
    $(id).hidden = name !== view;
}
function resetResult() {
  if (busy) return;
  resultError = null;
  current = null;
  setView("empty");
  $("result-status").textContent = t("Ready");
  $("result-status").className = "status-badge";
  document
    .querySelectorAll(".candidate-row")
    .forEach((el) => el.classList.remove("selected"));
}
function setBusy(value) {
  busy = value;
  for (const id of [
    "run-button",
    "settings-button",
    "nav-settings",
    "edit-input",
    "goal",
    "retry-button",
    "language-select",
  ])
    $(id).disabled = value;
  document.querySelectorAll('input[name="provider"]').forEach((el) => {
    el.disabled = value || (el.value === "live" && !config?.live_available);
  });
  document.querySelectorAll(".history-view").forEach((el) => {
    el.disabled = value;
  });
  $("clear-history").disabled = value || !history.length;
  $("result-panel").setAttribute("aria-busy", String(value));
  $("run-label").textContent = value ? t("Deciding") : t("Run decision");
  $("run-arrow").textContent = value ? "…" : "↗";
}
function renderResult(entry) {
  current = entry;
  const result = entry.result;
  const abstained = result.choice_id === "abstain";
  setView("result");
  $("result-status").textContent = abstained ? t("Action stopped") : t("Decision complete");
  $("result-status").className = "status-badge complete";
  $("outcome-label").textContent = abstained
    ? result.downgraded_to_abstain
      ? t("Below confidence threshold")
      : t("Abstain selected")
    : t("Selected action");
  $("choice-name").textContent = result.choice_id;
  $("choice-description").textContent = displayDescription(result.candidate, i18n.language, messages);
  $("result-mode").textContent =
    t("{mode} · Run #{id}", { mode: result.provider === "mock" ? t("Local demo · no model inference") : `Jev Live · ${result.model}`, id: String(entry.id).padStart(2, "0") });
  metric("confidence", (result.confidence * 100).toFixed(1), "%");
  metric("decision-time", formatMs(result.timing_ms?.decision ?? 0), "ms");
  metric("roundtrip-time", formatMs(entry.roundtrip), "ms");
  const probs = Object.entries(result.probabilities).sort(
    (a, b) => b[1] - a[1],
  );
  $("probability-list").replaceChildren(
    ...probs.map(([id, probability]) => {
      const row = node("div", undefined, "probability-row");
      const label = node("div", undefined, "probability-label");
      label.append(
        node("span", id),
        node("span", `${(probability * 100).toFixed(1)}%`),
      );
      const bar = node("progress");
      bar.max = 1;
      bar.value = probability;
      bar.setAttribute("aria-label", t("Probability for {id}", { id }));
      row.append(label, bar);
      return row;
    }),
  );
  const timing = result.timing_ms || {};
  const details = [
    [t("Input preparation"), `${formatMs(timing.preparation ?? 0)} ms`],
    [t("Decision call"), `${formatMs(timing.decision ?? 0)} ms`],
    [t("Server total"), `${formatMs(timing.total ?? 0)} ms`],
    [t("Page round trip"), `${formatMs(entry.roundtrip)} ms`],
  ];
  if (result.context?.history_dropped)
    details.push([t("Omitted history"), t("{count} entries", { count: result.context.history_dropped })]);
  $("timing-details").replaceChildren(
    ...details.flatMap(([key, value]) => [node("dt", key), node("dd", value)]),
  );
  $("payload").textContent = JSON.stringify(result.execute, null, 2);
  $("result-footnote").textContent = abstained
    ? t("No action to execute. Refine the observation and candidates, then decide again.")
    : t("Decision only. No browser action was executed.");
  document
    .querySelectorAll(".candidate-row")
    .forEach((el) =>
      el.classList.toggle(
        "selected",
        el.dataset.id === result.choice_id && entry.revision === revision,
      ),
    );
}
function renderHistory() {
  $("history-count").textContent = history.length;
  $("nav-count").textContent = history.length;
  $("history-empty").hidden = history.length > 0;
  $("history-table-wrap").hidden = !history.length;
  $("clear-history").disabled = busy || !history.length;
  $("history-body").replaceChildren(
    ...history.map((entry) => {
      const result = entry.result;
      const row = node("tr");
      row.append(
        node("td", `#${String(entry.id).padStart(2, "0")} · ${new Date(entry.time).toLocaleTimeString(i18n.locale, { hour12: false })}`),
      );
      const choiceCell = node("td");
      const button = node("button", result.choice_id, "history-view");
      button.setAttribute(
        "aria-label",
        t("View run {id}: {choice}", { id: entry.id, choice: result.choice_id }),
      );
      button.disabled = busy;
      button.addEventListener("click", () => {
        if (!busy) {
          renderResult(entry);
          $("result-panel").scrollIntoView({
            behavior: "smooth",
            block: "nearest",
          });
          announce(t("Showing result for run {id}.", { id: entry.id }));
        }
      });
      choiceCell.append(button);
      row.append(choiceCell);
      const modeCell = node("td");
      modeCell.append(
        node(
          "span",
          result.provider === "mock" ? t("Demo") : "Live",
          `history-tag ${result.provider === "live" ? "live" : ""}`,
        ),
      );
      row.append(
        modeCell,
        node("td", `${(result.confidence * 100).toFixed(1)}%`),
        node("td", `${formatMs(result.timing_ms?.decision ?? 0)} ms`),
        node("td", result.choice_id === "abstain" ? t("Abstain") : t("Selected")),
      );
      return row;
    }),
  );
}
async function run(event) {
  event?.preventDefault();
  if (busy || !config) return;
  if (!i18n.validate($("decision-form"))) return;
  if (!$("goal").value.trim()) {
    $("goal").setCustomValidity(t("Enter a decision goal."));
    $("goal").reportValidity();
    return;
  }
  const requested = {
    ...structuredClone(input),
    goal: $("goal").value.trim(),
    provider: provider(),
  };
  setBusy(true);
  current = null;
  setView("pending");
  $("result-status").textContent = t("Evaluating");
  $("result-status").className = "status-badge";
  document
    .querySelectorAll(".candidate-row")
    .forEach((el) => el.classList.remove("selected"));
  const start = performance.now();
  $("elapsed").textContent = "0.0 s";
  announce(t("Decision started."));
  const timer = setInterval(() => {
    $("elapsed").textContent =
      `${((performance.now() - start) / 1000).toFixed(1)} s`;
  }, 100);
  const controller = new AbortController();
  const deadline = setTimeout(
    () => controller.abort(),
    (input.timeout_s + 10) * 1000,
  );
  try {
    const response = await fetch("/api/decide", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Jev-Session": config.session_token,
      },
      body: JSON.stringify(requested),
      signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok)
      throw apiError(result.code, result.error);
    const entry = {
      id: ++runNumber,
      revision,
      result,
      roundtrip: performance.now() - start,
      time: Date.now(),
    };
    history = [entry, ...history].slice(0, 20);
    renderResult(entry);
    renderHistory();
    announce(
      t("Selected {choice}. Confidence {confidence} percent. No browser action was executed.", { choice: result.choice_id, confidence: (result.confidence * 100).toFixed(1) }),
    );
  } catch (error) {
    setView("error");
    $("result-status").textContent = t("Needs attention");
    $("result-status").className = "status-badge failed";
    resultError = error.name === "AbortError"
      ? uiError("The page stopped waiting. The server may still be processing; check its status before retrying.")
      : error instanceof TypeError
        ? uiError("Cannot reach the workspace. Check the running terminal, then try again.")
        : error.uiKey ? error : uiError("The server returned an unexpected response. Check its status before retrying.");
    $("error-message").textContent = errorText(resultError);
  } finally {
    clearInterval(timer);
    clearTimeout(deadline);
    setBusy(false);
  }
}
function openSettings() {
  if (busy) return;
  $("observation-input").value = JSON.stringify(input.observation, null, 2);
  $("candidates-input").value = JSON.stringify(input.candidates, null, 2);
  $("model-input").value = input.model;
  $("threshold-input").value = input.min_confidence;
  $("timeout-input").value = input.timeout_s;
  settingsError = null;
  $("settings-error").hidden = true;
  $("settings-dialog").showModal();
}
function applySettings(event) {
  event.preventDefault();
  if (!i18n.validate($("settings-form"))) return;
  try {
    let observation, candidates;
    try {
      observation = JSON.parse($("observation-input").value);
    } catch {
      throw uiError("Check the observation JSON syntax.");
    }
    if (
      observation === null ||
      (typeof observation !== "string" &&
        (typeof observation !== "object" || Array.isArray(observation)))
    )
      throw uiError("Observation must be a JSON object or string.");
    try {
      candidates = JSON.parse($("candidates-input").value);
    } catch {
      throw uiError("Check the candidate JSON syntax.");
    }
    if (
      !Array.isArray(candidates) ||
      !candidates.length ||
      candidates.length > 64
    )
      throw uiError("Candidates must be a JSON array with 1–64 entries.");
    const ids = new Set();
    for (const candidate of candidates) {
      if (
        !candidate ||
        typeof candidate !== "object" ||
        typeof candidate.id !== "string" ||
        !candidate.id.trim()
      )
        throw uiError("Each candidate needs a non-empty id.");
      if (ids.has(candidate.id))
        throw uiError("Candidate ids must be unique.");
      ids.add(candidate.id);
      if (
        candidate.tool != null &&
        (typeof candidate.tool !== "string" || !candidate.tool.trim())
      )
        throw uiError("tool must be a tool name or null.");
      if (
        candidate.arguments != null &&
        (typeof candidate.arguments !== "object" ||
          Array.isArray(candidate.arguments))
      )
        throw uiError("arguments must be a JSON object.");
      if (
        candidate.id === "abstain" &&
        (candidate.tool || Object.keys(candidate.arguments || {}).length)
      )
        throw uiError("The abstain candidate cannot contain a tool or arguments.");
      if (
        candidate.description != null &&
        typeof candidate.description !== "string"
      )
        throw uiError("description must be a string.");
      candidate.description ||= candidate.id;
      candidate.tool ??= null;
      candidate.arguments ??= {};
    }
    if (!ids.has("abstain")) {
      if (candidates.length === 64)
        throw uiError("Reserve one of the 64 candidate slots for abstain.");
      candidates.push(structuredClone(example.candidates[2]));
    }
    const model = $("model-input").value.trim();
    if (!model) throw uiError("Enter a Jev model name.");
    const next = {
      observation,
      candidates,
      model,
      min_confidence: Number($("threshold-input").value),
      timeout_s: Number($("timeout-input").value),
    };
    if (
      !Number.isFinite(next.min_confidence) ||
      next.min_confidence < 0 ||
      next.min_confidence > 1 ||
      !Number.isFinite(next.timeout_s) ||
      next.timeout_s < 1 ||
      next.timeout_s > 60
    )
      throw uiError("Minimum confidence must be 0–1 and the HTTP timeout must be 1–60 seconds.");
    if (new TextEncoder().encode(JSON.stringify(next)).length > 120000)
      throw uiError("The input is too large. Keep only the necessary observation and candidates.");
    input = next;
    revision++;
    renderInputs();
    resetResult();
    $("settings-dialog").close();
    toast(t("Inputs and settings applied."));
  } catch (error) {
    settingsError = error;
    $("settings-error").textContent = errorText(error);
    $("settings-error").hidden = false;
    $("settings-error").scrollIntoView({ block: "nearest" });
  }
}

$("decision-form").addEventListener("submit", run);
$("retry-button").addEventListener("click", () =>
  $("decision-form").requestSubmit(),
);
$("goal").addEventListener("input", () => {
  revision++;
  $("goal").setCustomValidity("");
  resetResult();
});
document
  .querySelectorAll('input[name="provider"]')
  .forEach((el) => el.addEventListener("change", updateMode));
for (const id of ["settings-button", "nav-settings", "edit-input"])
  $(id).addEventListener("click", openSettings);
for (const id of ["close-settings", "cancel-settings"])
  $(id).addEventListener("click", () => $("settings-dialog").close());
$("settings-form").addEventListener("submit", applySettings);
$("load-example").addEventListener("click", () => {
  $("observation-input").value = JSON.stringify(example.observation, null, 2);
  $("candidates-input").value = JSON.stringify(example.candidates, null, 2);
  settingsError = null;
  $("settings-error").hidden = true;
});
$("copy-payload").addEventListener("click", async () => {
  if (!current) return;
  try {
    await navigator.clipboard.writeText(
      JSON.stringify(current.result.execute, null, 2),
    );
    toast(t("Action payload copied."));
  } catch {
    toast(t("Check clipboard permission or select the payload manually."));
  }
});
$("clear-history").addEventListener("click", () => {
  history = [];
  renderHistory();
  resetResult();
  toast(t("This session’s history was cleared."));
});
document.addEventListener("keydown", (event) => {
  if (
    (event.metaKey || event.ctrlKey) &&
    event.key === "Enter" &&
    !$("settings-dialog").open
  ) {
    event.preventDefault();
    $("decision-form").requestSubmit();
  }
});
async function init() {
  renderInputs();
  setBusy(true);
  try {
    const response = await fetch("/api/config", {
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) throw new Error("config");
    config = await response.json();
    $("version").textContent = `ASIDE JEV / v${config.version}`;
    $("connection-label").textContent = t("Local workspace connected");
    $("key-status").textContent = config.live_available
      ? t("API key configured · authentication checked on a Live run")
      : t("No API key · local demo available");
    if (!config.live_available)
      $("mode-note").textContent =
        t("Try the local demo without a key. See Inputs & settings for Live setup.");
    setBusy(false);
  } catch {
    connectionFailed = true;
    setBusy(false);
    $("run-button").disabled = true;
    $("connection-label").textContent = t("Connection needs attention");
    $("app-error").textContent =
      t("Cannot reach the local workspace. Run aside-jev dashboard in a terminal, then reload this page.");
    $("app-error").hidden = false;
    $("key-status").textContent = t("Available after connecting to the server.");
  }
}
function renderConnection() {
  if (connectionFailed) {
    $("connection-label").textContent = t("Connection needs attention");
    $("app-error").textContent = t("Cannot reach the local workspace. Run aside-jev dashboard in a terminal, then reload this page.");
    $("key-status").textContent = t("Available after connecting to the server.");
  } else if (config) {
    $("connection-label").textContent = t("Local workspace connected");
    $("key-status").textContent = config.live_available ? t("API key configured · authentication checked on a Live run") : t("No API key · local demo available");
  }
}
function changeLanguage() {
  const previous = example;
  const oldGoal = t("Choose the next action to fill the empty verification field.");
  const draftObservation = $("observation-input").value;
  const draftCandidates = $("candidates-input").value;
  i18n.setLanguage($("language-select").value);
  example = demo(t);
  input = migrateDemo(input, previous, example);
  if ($("goal").value === oldGoal) $("goal").value = t("Choose the next action to fill the empty verification field.");
  if (draftObservation === JSON.stringify(previous.observation, null, 2)) $("observation-input").value = JSON.stringify(example.observation, null, 2);
  if (draftCandidates === JSON.stringify(previous.candidates, null, 2)) $("candidates-input").value = JSON.stringify(example.candidates, null, 2);
  i18n.apply();
  renderInputs();
  renderHistory();
  renderConnection();
  $("mode-note").textContent = provider() === "mock" ? t("The local demo selects the first candidate. No API calls or browser actions.") : t("Jev decides using inputs sent to TypeSafe. Account usage applies; no browser action is executed.");
  if (current) renderResult(current);
  else if (resultError) {
    $("result-status").textContent = t("Needs attention");
    $("error-message").textContent = errorText(resultError);
  }
  if (settingsError) $("settings-error").textContent = errorText(settingsError);
  document.querySelectorAll("input, textarea").forEach((field) => field.setCustomValidity(""));
  $("toast").hidden = true;
  announce(t("Language updated."));
}
$("language-select").value = i18n.language;
$("language-select").addEventListener("change", changeLanguage);
i18n.apply();
$("goal").value = t("Choose the next action to fill the empty verification field.");
init();
