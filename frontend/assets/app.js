const $ = (id) => document.getElementById(id);
const TOKEN_KEY = 'six_degrees_token';
let user = null;
let signup = false;
let searchVersion = 0;
const CLOSENESS_LABELS = { 5: 'Close', 4: 'Worked together', 3: 'Know well', 2: 'Acquaintance', 1: 'Met once' };

function message(id, text = '', error = false) {
  $(id).textContent = text;
  $(id).classList.toggle('error', error);
}

async function request(path, body, method = body === undefined ? 'GET' : 'POST') {
  const headers = { 'Content-Type': 'application/json' };
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers.Authorization = `Bearer ${token}`;
  let response;
  try {
    response = await fetch(path, { method, headers,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  } catch {
    throw new Error('Cannot reach the server. Please try again.');
  }
  if (response.status === 204) return null;   // success with no body (e.g. a delete)
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && path !== '/auth/login') {
      localStorage.removeItem(TOKEN_KEY);
      setUser(null);
    }
    throw new Error(typeof data?.detail === 'string' ? data.detail :
      Array.isArray(data?.detail) ? data.detail[0]?.msg : 'Something went wrong. Please try again.');
  }
  return data;
}

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function clearResults() {
  searchVersion++;
  $('results').replaceChildren();
  $('results-section').hidden = true;
}

function setUser(value) {
  user = value;
  clearResults();
  $('seeker').value = value ? value.id : '';
  $('seeker-field').hidden = Boolean(value);
  resetSeekerLookup();
  updateSeekerMode();
  $('account-button').textContent = value ? `${value.first_name} · Sign out` : 'Sign in';
  $('inbox-section').hidden = !value;
  $('inbox').replaceChildren();
  $('connections-section').hidden = !value;
  $('connections').replaceChildren();
  connectedCloseness = new Map();
  message('connection-message');
  resetConnectionForm();
  if (value) { loadInbox(); loadConnections(); }
}

// ---------------------------------------------------------------------------
// Name boxes that suggest people as you type (used for "Start from" and
// "Find a person" in Your connections)
// ---------------------------------------------------------------------------

/**
 * Turn a text input into a people picker.
 *   exclude(): ids to leave out of the suggestions
 *   status(person): a short label shown beside a person (e.g. "Connected"), or ''
 *   onPick(person): called when someone is chosen
 *   onClear(): called when the text changes after a pick (the pick no longer applies)
 */
function personAutocomplete({ input, list, exclude = () => new Set(), status = () => '', onPick, onClear = () => {} }) {
  let version = 0;
  let timer = null;
  let items = [];
  let active = -1;
  let picked = false;

  const fullName = (person) => `${person.first_name} ${person.last_name}`;

  function close() {
    version++;
    list.hidden = true;
    list.replaceChildren();
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    items = [];
    active = -1;
  }

  function setActive(index) {
    items.forEach((item, i) => item.node.setAttribute('aria-selected', String(i === index)));
    active = index;
    if (index >= 0) {
      input.setAttribute('aria-activedescendant', items[index].node.id);
      items[index].node.scrollIntoView({ block: 'nearest' });
    } else input.removeAttribute('aria-activedescendant');
  }

  // Best matches first: name starts with the text, then a word starts with it, then anywhere
  function rank(person, query) {
    const name = fullName(person).toLowerCase();
    const q = query.toLowerCase();
    return name.startsWith(q) ? 0 : ` ${name}`.includes(` ${q}`) ? 1 : 2;
  }

  function note(text) {
    const li = element('li', text, 'suggestion-empty');
    li.setAttribute('role', 'presentation');
    return li;
  }

  function render(people, query, more) {
    items = [];
    const nodes = people.map((person, i) => {
      const option = element('li', undefined, 'suggestion');
      option.id = `${list.id}-${i}`;
      option.setAttribute('role', 'option');
      option.setAttribute('aria-selected', 'false');
      const who = element('span', undefined, 'suggestion-person');
      who.append(highlighted(fullName(person), query),
        element('small', [person.job_title, person.company, person.location].filter(Boolean).join(' · ')));
      option.append(who);
      const label = status(person);
      if (label) option.append(element('span', label, 'status'));
      // mousedown (not click) so the input keeps focus and the list doesn't close first
      option.addEventListener('mousedown', (event) => { event.preventDefault(); pick(person); });
      items.push({ person, node: option });
      return option;
    });
    if (!people.length) nodes.push(note('No one by that name. Try a first or last name.'));
    else if (more) nodes.push(note('Keep typing to narrow the list.'));
    list.replaceChildren(...nodes);
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    setActive(-1);
  }

  async function load() {
    const query = input.value.trim().replace(/\s+/g, ' ');
    if (!query || picked) { close(); return; }
    const mine = ++version;
    let data;
    try { data = await request(`/users/lookup?${new URLSearchParams({ q: query })}`); } catch { return; }
    if (mine !== version || document.activeElement !== input) return;   // a newer search or focus moved
    const skip = exclude();
    const people = data.users
      .filter((person) => !skip.has(person.id))
      .map((person, i) => ({ person, i, r: rank(person, query) }))
      .sort((a, b) => a.r - b.r || a.i - b.i)
      .map((x) => x.person)
      .slice(0, 8);
    render(people, query, data.users.length === 25);
  }

  function pick(person) {
    picked = true;
    input.value = fullName(person);
    close();
    onPick(person);
  }

  input.addEventListener('input', () => {
    picked = false;
    onClear();
    clearTimeout(timer);
    timer = setTimeout(load, 150);
  });
  input.addEventListener('keydown', (event) => {
    const open = !list.hidden && items.length;
    if (event.key === 'ArrowDown' && open) { event.preventDefault(); setActive((active + 1) % items.length); }
    else if (event.key === 'ArrowUp' && open) { event.preventDefault(); setActive(active <= 0 ? items.length - 1 : active - 1); }
    else if (event.key === 'Enter' && open) { event.preventDefault(); pick(items[Math.max(active, 0)].person); }
    else if (event.key === 'Escape' && !list.hidden) { event.preventDefault(); close(); }
  });
  input.addEventListener('focus', () => { if (input.value.trim() && !picked) load(); });
  input.addEventListener('blur', close);

  return {
    clear() { picked = false; input.value = ''; close(); },
  };
}

// --- "Start from": who the search starts from, when not signed in ---

function resetSeekerLookup() {
  $('seeker-matches').replaceChildren();   // holds the picked person, if any
  message('seeker-message');
}

function updateSeekerMode() {
  const byName = $('seeker-mode').value === 'name';
  $('seeker-name-fields').hidden = !byName;
  $('seeker-id-field').hidden = byName;
  $('seeker-name').required = !user && byName;
  $('seeker').required = !user && !byName;
}

const seekerPicker = personAutocomplete({
  input: $('seeker-name'),
  list: $('seeker-suggestions'),
  onPick(person) {
    const name = `${person.first_name} ${person.last_name}`;
    $('seeker-matches').replaceChildren(new Option(name, person.id, true, true));
    const details = [person.job_title, person.company].filter(Boolean).join(' · ');
    message('seeker-message', `Starting from ${name}${details ? ` (${details})` : ''}.`);
    clearResults();
    if ($('query').value.trim()) runSearch({ live: true });
  },
  onClear() { resetSeekerLookup(); clearResults(); },
});

$('seeker-mode').addEventListener('change', () => {
  seekerPicker.clear();
  resetSeekerLookup();
  updateSeekerMode();
  clearResults();
});
$('seeker').addEventListener('input', clearResults);

$('account-button').addEventListener('click', () => {
  if (user) {
    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
    message('search-message');
  } else $('account-dialog').showModal();
});
$('close-account').addEventListener('click', () => $('account-dialog').close());
$('toggle-account').addEventListener('click', () => setSignupMode(!signup));
function setSignupMode(value) {
  signup = value;
  $('name-fields').hidden = !signup;
  $('profile-fields').hidden = !signup;
  $('first-name').required = signup;
  $('last-name').required = signup;
  $('password').autocomplete = signup ? 'new-password' : 'current-password';
  $('account-heading').textContent = signup ? 'Build your next chapter' : 'Welcome back';
  $('account-description').textContent = signup ? 'Create your GitConnectd account.' : 'Sign in to explore your network.';
  $('account-submit').textContent = signup ? 'Create account' : 'Sign in';
  $('toggle-account').textContent = signup ? 'Already have an account? Sign in' : 'Create an account';
  message('account-message');
}
$('is-hiring').addEventListener('change', () => {
  $('open-role-field').hidden = !$('is-hiring').checked;
});
$('account-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('account-submit').disabled = true;
  $('toggle-account').disabled = true;
  message('account-message');
  try {
    const body = { email: $('email').value.trim(), password: $('password').value };
    const creating = signup;
    if (creating) {
      const hiring = $('is-hiring').checked;
      Object.assign(body, {
        first_name: $('first-name').value.trim(), last_name: $('last-name').value.trim(),
        job_title: $('job-title').value.trim() || null, company: $('company').value.trim() || null,
        location: $('location').value.trim() || null, bio: $('bio').value.trim() || null,
        phone: $('phone').value.trim() || null, github: $('github').value.trim() || null,
        is_hiring: hiring, open_role: hiring ? $('open-role').value.trim() || null : null,
      });
      if (body.open_role && !body.company) throw new Error('Enter your company to post an open role.');
    }
    const data = await request(creating ? '/auth/signup' : '/auth/login', body);
    localStorage.setItem(TOKEN_KEY, data.token);
    setUser(data.user);
    $('account-form').reset();
    $('open-role-field').hidden = true;
    if (creating) setSignupMode(false);   // next time the dialog opens, it's on sign in
    $('account-dialog').close();
    if (creating) {
      message('connection-message', `Welcome, ${user.first_name}! Add a few people you know so we can find paths for you.`);
      $('connections-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
      $('connection-name').focus({ preventScroll: true });
    } else {
      message('search-message', `Welcome, ${user.first_name}. Search for a role or hiring manager to explore your connections.`);
    }
  } catch (error) { message('account-message', error.message, true); }
  finally { $('account-submit').disabled = false; $('toggle-account').disabled = false; }
});

// ---------------------------------------------------------------------------
// Search: suggestions as you type, live results, and the result cards
// ---------------------------------------------------------------------------

let suggestVersion = 0;
let suggestTimer = null;
let liveTimer = null;
let pickedManager = null;     // { id, name } after choosing a person from the suggestions
let activeOption = -1;        // keyboard-highlighted suggestion
let suggestionItems = [];     // [{ kind: 'role' | 'manager', value, node }]
const MIN_LIVE_CHARS = 2;

function searchType() { return $('search-type').value; }

function currentSeekerId() {
  const id = user?.id ?? Number($('seeker-mode').value === 'name' ? $('seeker-matches').value : $('seeker').value);
  return Number.isInteger(id) && id > 0 ? id : null;
}

/** Text with the part matching `query` wrapped in <mark>, built without innerHTML. */
function highlighted(text, query) {
  const span = element('span');
  const at = text.toLowerCase().indexOf(query.toLowerCase());
  if (!query || at < 0) { span.textContent = text; return span; }
  span.append(text.slice(0, at), element('mark', text.slice(at, at + query.length)), text.slice(at + query.length));
  return span;
}

function closeSuggestions() {
  suggestVersion++;
  $('suggestions').hidden = true;
  $('suggestions').replaceChildren();
  $('query').setAttribute('aria-expanded', 'false');
  $('query').removeAttribute('aria-activedescendant');
  suggestionItems = [];
  activeOption = -1;
}

function setActiveOption(index) {
  suggestionItems.forEach((item, i) => item.node.setAttribute('aria-selected', String(i === index)));
  activeOption = index;
  if (index >= 0) {
    $('query').setAttribute('aria-activedescendant', suggestionItems[index].node.id);
    suggestionItems[index].node.scrollIntoView({ block: 'nearest' });
  } else $('query').removeAttribute('aria-activedescendant');
}

function renderSuggestions(data, query) {
  const list = $('suggestions');
  const type = searchType();
  const groups = [];
  if (type !== 'manager' && data.roles.length) groups.push(['Roles', 'role', data.roles]);
  if (type !== 'role' && data.managers.length) groups.push(['People hiring', 'manager', data.managers]);
  suggestionItems = [];
  const nodes = [];
  for (const [label, kind, items] of groups) {
    nodes.push(element('li', label, 'suggestion-group'));
    nodes.at(-1).setAttribute('role', 'presentation');
    for (const item of items) {
      const option = element('li', undefined, 'suggestion');
      option.id = `suggestion-${suggestionItems.length}`;
      option.setAttribute('role', 'option');
      option.setAttribute('aria-selected', 'false');
      if (kind === 'role') {
        option.append(highlighted(item.title, query),
          element('small', `${item.openings} open ${item.openings === 1 ? 'role' : 'roles'}`));
      } else {
        const name = `${item.first_name} ${item.last_name}`;
        const details = [item.job_title, item.company].filter(Boolean).join(' · ');
        option.append(highlighted(name, query),
          element('small', [details, item.open_roles ? `${item.open_roles} open ${item.open_roles === 1 ? 'role' : 'roles'}` : 'Hiring'].filter(Boolean).join(' · ')));
      }
      const entry = { kind, value: item, node: option };
      // mousedown (not click) so the input doesn't lose focus and close the list first
      option.addEventListener('mousedown', (event) => { event.preventDefault(); chooseSuggestion(entry); });
      suggestionItems.push(entry);
      nodes.push(option);
    }
  }
  if (!suggestionItems.length) { closeSuggestions(); return; }
  list.replaceChildren(...nodes);
  list.hidden = false;
  $('query').setAttribute('aria-expanded', 'true');
  setActiveOption(-1);
}

async function loadSuggestions() {
  const query = $('query').value.trim();
  if (!query) { closeSuggestions(); return; }
  const version = ++suggestVersion;
  try {
    const data = await request(`/search/suggest?${new URLSearchParams({ q: query, limit: '6' })}`);
    if (version !== suggestVersion || document.activeElement !== $('query')) return;
    renderSuggestions(data, query);
  } catch { /* suggestions are optional; the search itself still works */ }
}

function chooseSuggestion(entry) {
  closeSuggestions();
  clearTimeout(liveTimer);
  if (entry.kind === 'role') {
    pickedManager = null;
    $('query').value = entry.value.title;
    runSearch({ type: 'role' });
  } else {
    const name = `${entry.value.first_name} ${entry.value.last_name}`;
    pickedManager = { id: entry.value.id, name };
    $('query').value = name;
    runSearch({ managerId: entry.value.id });
  }
}

$('query').addEventListener('input', () => {
  pickedManager = null;
  clearTimeout(suggestTimer);
  clearTimeout(liveTimer);
  suggestTimer = setTimeout(loadSuggestions, 120);
  const query = $('query').value.trim();
  if (query.length >= MIN_LIVE_CHARS && currentSeekerId()) {
    liveTimer = setTimeout(() => runSearch({ live: true }), 450);   // results follow your typing
  } else if (!query) { clearResults(); message('search-message'); }
});

$('query').addEventListener('keydown', (event) => {
  const open = !$('suggestions').hidden && suggestionItems.length;
  if (event.key === 'ArrowDown' && open) {
    event.preventDefault();
    setActiveOption((activeOption + 1) % suggestionItems.length);
  } else if (event.key === 'ArrowUp' && open) {
    event.preventDefault();
    setActiveOption(activeOption <= 0 ? suggestionItems.length - 1 : activeOption - 1);
  } else if (event.key === 'Enter' && open && activeOption >= 0) {
    event.preventDefault();
    chooseSuggestion(suggestionItems[activeOption]);
  } else if (event.key === 'Escape' && open) {
    event.preventDefault();
    closeSuggestions();
  }
});
$('query').addEventListener('focus', () => { if ($('query').value.trim()) loadSuggestions(); });
$('query').addEventListener('blur', closeSuggestions);

// Filter chips: All / Roles / People
for (const chip of document.querySelectorAll('.chip')) {
  chip.addEventListener('click', () => {
    for (const other of document.querySelectorAll('.chip')) other.setAttribute('aria-checked', String(other === chip));
    $('search-type').value = chip.dataset.type;
    pickedManager = null;
    if ($('query').value.trim() && currentSeekerId()) runSearch({});
    else clearResults();
  });
}

function renderResult(result, seekerId) {
  const card = element('article', undefined, 'result');
  const manager = result.people[result.people.length - 1];
  const managerName = `${manager.first_name} ${manager.last_name}`;
  const match = result.match || [];
  // Lead with the person when their name is what matched (or they have no open job)
  if (!result.job || (match.includes('name') && !match.includes('role'))) {
    card.append(element('h3', managerName),
      element('p', [manager.job_title, manager.company].filter(Boolean).join(' · ') || 'Hiring manager', 'company'));
    if (result.job) card.append(element('p', `Open role: ${result.job.title}`, 'company'));
  } else {
    card.append(element('h3', result.job.title), element('p', `${result.job.company} · ${managerName}`, 'company'));
  }
  const tags = element('div', undefined, 'result-tags');
  tags.append(element('span', `${result.hops} ${result.hops === 1 ? 'hop' : 'hops'} · ${Math.round(result.score * 100)}% path strength`, 'badge'));
  if (match.includes('role')) tags.append(element('span', 'Role match', 'tag'));
  if (match.includes('name')) tags.append(element('span', 'Name match', 'tag'));
  card.append(tags);
  const path = element('div', undefined, 'path');
  result.people.forEach((person, index) => {
    if (index) path.append(element('span', '→', 'path-arrow'));
    const name = element('div', `${person.first_name} ${person.last_name}`, 'person');
    name.append(element('small', person.job_title || 'Your connection'));
    if (index) name.title = result.reasons[index - 1] || '';
    path.append(name);
  });
  card.append(path);
  const actions = element('div', undefined, 'result-actions');
  const button = element('button', user ? 'Request introduction ↗' : 'Sign in to request an introduction');
  const status = element('p', undefined, 'message');
  status.setAttribute('role', 'status');
  button.addEventListener('click', async () => {
    if (!user) { $('account-dialog').showModal(); return; }
    if (user.id !== seekerId) return;
    button.disabled = true;
    try {
      const intro = await request('/intros', { seeker_id: seekerId, path: result.path, job_id: result.job?.id ?? null });
      status.textContent = `Introduction #${intro.id} requested. The first person in your path can respond from their inbox.`;
      button.textContent = 'Introduction requested';
    } catch (error) {
      status.textContent = error.message;
      status.classList.add('error');
      button.disabled = false;
    }
  });
  actions.append(button);
  card.append(actions, status);
  return card;
}

/**
 * Run a path search for what's in the box.
 *   live:      triggered by typing (quieter: no error when no start person is chosen)
 *   type:      force 'role' / 'manager' / 'all' (defaults to the selected chip)
 *   managerId: one specific person, after picking them from the suggestions
 */
async function runSearch({ live = false, type = searchType(), managerId = pickedManager?.id } = {}) {
  const seekerId = currentSeekerId();
  const query = $('query').value.trim();
  if (!seekerId) {
    if (!live) message('seeker-message', 'Find and choose a user before searching.', true);
    return;
  }
  if (!query) { if (!live) message('search-message', 'Type a role or a person\'s name to search for.', true); return; }
  if (live && query.length < MIN_LIVE_CHARS) return;

  searchVersion++;                         // any older search's results are now out of date
  const version = searchVersion;
  $('results-section').setAttribute('aria-busy', 'true');
  if (!live) $('search-button').disabled = true;
  message('search-message', 'Finding the strongest paths through your network…');
  try {
    const params = new URLSearchParams({ seeker_id: String(seekerId), q: query, limit: '3', search_type: type });
    if (managerId) params.set('manager_id', String(managerId));
    const data = await request(`/search?${params}`);
    if (version !== searchVersion) return;
    const what = managerId ? `${pickedManager?.name ?? 'that person'} isn't` :
      type === 'role' ? 'No connected hiring managers for that role are' :
      type === 'manager' ? 'No hiring managers with that name are' : 'No matching roles or hiring managers are';
    message('search-message', data.results.length ? '' : `${what} reachable within six introductions. Try another search, or add more connections.`);
    $('results-section').hidden = !data.results.length;
    $('results-count').textContent = `${data.results.length} ${data.results.length === 1 ? 'path' : 'paths'} found`;
    $('results').replaceChildren(...data.results.map((result) => renderResult(result, seekerId)));
  } catch (error) {
    if (version === searchVersion) message('search-message', error.message, true);
  } finally {
    if (version === searchVersion) $('results-section').removeAttribute('aria-busy');
    $('search-button').disabled = false;
  }
}

$('search-form').addEventListener('submit', (event) => {
  event.preventDefault();
  clearTimeout(liveTimer);
  closeSuggestions();
  runSearch();
});

// ---------------------------------------------------------------------------
// Your connections: find people you know and add them
// ---------------------------------------------------------------------------

let connectedCloseness = new Map();   // id -> closeness for the signed-in user's connections

function resetConnectionForm() {
  $('connection-matches').value = '';
  $('connection-details').hidden = true;
  $('connection-chosen').replaceChildren();
  $('add-connection').textContent = 'Add connection';
}

const connectionPicker = personAutocomplete({
  input: $('connection-name'),
  list: $('connection-suggestions'),
  exclude: () => new Set(user ? [user.id] : []),          // not yourself
  status: (person) => connectedCloseness.has(person.id)
    ? `Connected · ${CLOSENESS_LABELS[connectedCloseness.get(person.id)]}` : '',
  onPick(person) {
    const existing = connectedCloseness.get(person.id);
    $('connection-matches').value = person.id;
    const details = [person.job_title, person.company].filter(Boolean).join(' · ');
    $('connection-chosen').replaceChildren(
      existing ? 'Updating ' : 'Adding ', element('strong', `${person.first_name} ${person.last_name}`),
      details ? ` · ${details}` : '');
    if (existing) $('closeness').value = String(existing);
    $('add-connection').textContent = existing ? 'Update connection' : 'Add connection';
    $('connection-details').hidden = false;
    message('connection-message');
    $('closeness').focus();
  },
  onClear: resetConnectionForm,
});

async function loadConnections() {
  if (!user) return;
  const owner = user.id;
  try {
    const people = await request('/me/connections');
    if (user?.id !== owner) return;
    connectedCloseness = new Map(people.map((person) => [person.id, person.closeness]));
    $('connections-count').textContent = `${people.length} ${people.length === 1 ? 'person' : 'people'}`;
    if (!people.length && !$('connection-message').textContent) {
      message('connection-message', 'You haven\'t added anyone yet. Add a few people you know so we can find paths for you.');
    }
    $('connections').replaceChildren(...people.map((person) => {
      const item = element('li');
      const who = element('div');
      who.append(element('strong', `${person.first_name} ${person.last_name}`),
        element('small', [person.job_title, person.company, person.context].filter(Boolean).join(' · ')));
      const remove = element('button', 'Remove', 'secondary');
      remove.setAttribute('aria-label', `Remove ${person.first_name} ${person.last_name}`);
      remove.addEventListener('click', async () => {
        remove.disabled = true;
        try {
          await request(`/me/connections/${person.id}`, undefined, 'DELETE');
          message('connection-message', `Removed ${person.first_name} ${person.last_name}.`);
          clearResults();
          await loadConnections();
        } catch (error) {
          message('connection-message', error.message, true);
          remove.disabled = false;
        }
      });
      item.append(who, element('span', CLOSENESS_LABELS[person.closeness] ?? '', 'badge'), remove);
      return item;
    }));
  } catch (error) { if (user?.id === owner) message('connection-message', error.message, true); }
}

$('connection-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const otherId = Number($('connection-matches').value);
  if (!otherId) { message('connection-message', 'Choose a person first.', true); return; }
  $('add-connection').disabled = true;
  try {
    const added = await request('/me/connections', {
      user_id: otherId,
      closeness: Number($('closeness').value),
      context: $('connection-context').value.trim() || null,
    });
    message('connection-message', `${$('add-connection').textContent.startsWith('Update') ? 'Updated' : 'Added'} ${added.first_name} ${added.last_name}. Search above to see your paths.`);
    $('connection-form').reset();
    resetConnectionForm();
    clearResults();
    await loadConnections();
    $('connection-name').focus();
  } catch (error) { message('connection-message', error.message, true); }
  finally { $('add-connection').disabled = false; }
});

async function loadInbox() {
  if (!user) return;
  const owner = user.id;
  message('inbox-message', 'Loading introductions…');
  try {
    const items = await request(`/inbox/${owner}`);
    if (user?.id !== owner) return;
    message('inbox-message', items.length ? '' : 'No introductions waiting for you.');
    $('inbox').replaceChildren(...items.map((item) => {
      const card = element('article', undefined, 'inbox-item');
      card.append(element('p', item.message));
      const actions = element('div', undefined, 'inbox-actions');
      for (const [label, accept] of [['Accept introduction', true], ['Decline', false]]) {
        const button = element('button', label, accept ? '' : 'secondary');
        button.addEventListener('click', async () => {
          for (const action of actions.children) action.disabled = true;
          try {
            await request(`/intros/${item.request_id}/respond`, { user_id: owner, accept });
            await loadInbox();
          } catch (error) {
            message('inbox-message', error.message, true);
            for (const action of actions.children) action.disabled = false;
          }
        });
        actions.append(button);
      }
      card.append(actions);
      return card;
    }));
  } catch (error) { if (user?.id === owner) message('inbox-message', error.message, true); }
}
$('refresh-inbox').addEventListener('click', loadInbox);

if (localStorage.getItem(TOKEN_KEY)) {
  $('account-button').disabled = true;
  try { setUser(await request('/auth/me')); }
  catch (error) { message('search-message', error.message, true); }
  finally { $('account-button').disabled = false; }
}
if (location.pathname === '/auth' && !user) $('account-dialog').showModal();
