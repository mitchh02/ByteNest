const $ = (id) => document.getElementById(id);
const TOKEN_KEY = 'six_degrees_token';
let user = null;
let signup = false;
let searchVersion = 0;
let lookupVersion = 0;
let connectionLookupVersion = 0;
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
  message('connection-message');
  resetConnectionForm();
  if (value) { loadInbox(); loadConnections(); }
}

function resetSeekerLookup() {
  lookupVersion++;
  $('seeker-matches').replaceChildren();
  $('seeker-matches').required = false;
  $('seeker-matches-field').hidden = true;
  message('seeker-message');
}

function updateSeekerMode() {
  const byName = $('seeker-mode').value === 'name';
  $('seeker-name-fields').hidden = !byName;
  $('seeker-id-field').hidden = byName;
  $('seeker-name').required = !user && byName;
  $('seeker').required = !user && !byName;
}

$('seeker-mode').addEventListener('change', () => {
  resetSeekerLookup();
  updateSeekerMode();
  clearResults();
});
$('seeker-name').addEventListener('input', () => {
  resetSeekerLookup();
  clearResults();
});
$('seeker').addEventListener('input', clearResults);
$('seeker-matches').addEventListener('change', () => {
  clearResults();
  if ($('query').value.trim()) runSearch({ live: true });
});

async function lookupSeeker() {
  const name = $('seeker-name').value.trim();
  if (!name) { message('seeker-message', 'Enter a user name first.', true); return; }
  resetSeekerLookup();
  clearResults();
  const version = lookupVersion;
  $('lookup-seeker').disabled = true;
  message('seeker-message', 'Looking up users…');
  try {
    const data = await request(`/users/lookup?${new URLSearchParams({ q: name })}`);
    if (version !== lookupVersion) return;
    if (!data.users.length) {
      message('seeker-message', 'No users found. Try a first or last name.', true);
      return;
    }
    const options = [new Option('Select a user…', '')];
    for (const person of data.users) {
      const details = [person.job_title, person.company, person.location].filter(Boolean).join(' · ');
      options.push(new Option(`${person.first_name} ${person.last_name}${details ? ' — ' + details : ''} (ID ${person.id})`, person.id));
    }
    $('seeker-matches').replaceChildren(...options);
    $('seeker-matches').required = true;
    $('seeker-matches-field').hidden = false;
    if (data.users.length === 1) $('seeker-matches').value = data.users[0].id;
    message('seeker-message', data.users.length === 25
      ? 'Showing the first 25 matches. Enter a fuller name to narrow the results.'
      : `${data.users.length} ${data.users.length === 1 ? 'user found.' : 'users found. Choose your starting profile.'}`);
  } catch (error) {
    if (version === lookupVersion) message('seeker-message', error.message, true);
  } finally { $('lookup-seeker').disabled = false; }
}
$('lookup-seeker').addEventListener('click', lookupSeeker);
$('seeker-name').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') { event.preventDefault(); lookupSeeker(); }
});

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

function resetConnectionForm() {
  connectionLookupVersion++;
  $('connection-matches').replaceChildren();
  $('connection-matches-field').hidden = true;
  $('connection-details').hidden = true;
}

async function loadConnections() {
  if (!user) return;
  const owner = user.id;
  try {
    const people = await request('/me/connections');
    if (user?.id !== owner) return;
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

async function lookupConnection() {
  const name = $('connection-name').value.trim();
  if (!name) { message('connection-message', 'Enter a name first.', true); return; }
  resetConnectionForm();
  const version = connectionLookupVersion;
  $('lookup-connection').disabled = true;
  message('connection-message', 'Looking up people…');
  try {
    const data = await request(`/users/lookup?${new URLSearchParams({ q: name })}`);
    if (version !== connectionLookupVersion) return;
    const people = data.users.filter((person) => person.id !== user?.id);   // not yourself
    if (!people.length) { message('connection-message', 'No one found. Try a first or last name.', true); return; }
    const options = [new Option('Select a person…', '')];
    for (const person of people) {
      const details = [person.job_title, person.company, person.location].filter(Boolean).join(' · ');
      options.push(new Option(`${person.first_name} ${person.last_name}${details ? ' — ' + details : ''}`, person.id));
    }
    $('connection-matches').replaceChildren(...options);
    $('connection-matches-field').hidden = false;
    if (people.length === 1) {
      $('connection-matches').value = people[0].id;
      $('connection-details').hidden = false;
    }
    message('connection-message', people.length === 1 ? '1 person found.' : `${people.length} people found. Choose the one you know.`);
  } catch (error) {
    if (version === connectionLookupVersion) message('connection-message', error.message, true);
  } finally { $('lookup-connection').disabled = false; }
}
$('lookup-connection').addEventListener('click', lookupConnection);
$('connection-name').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') { event.preventDefault(); lookupConnection(); }
});
$('connection-name').addEventListener('input', resetConnectionForm);
$('connection-matches').addEventListener('change', () => {
  $('connection-details').hidden = !$('connection-matches').value;
});

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
    message('connection-message', `Added ${added.first_name} ${added.last_name}. Search above to see your paths.`);
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
