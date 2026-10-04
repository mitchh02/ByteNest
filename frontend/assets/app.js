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
$('seeker-matches').addEventListener('change', clearResults);

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
  $('account-description').textContent = signup ? 'Create your Six Degrees account.' : 'Sign in to explore your network.';
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

function renderResult(result, seekerId, searchType) {
  const card = element('article', undefined, 'result');
  const manager = result.people[result.people.length - 1];
  const managerName = `${manager.first_name} ${manager.last_name}`;
  if (searchType === 'manager') {
    card.append(element('h3', managerName),
      element('p', [manager.job_title, manager.company].filter(Boolean).join(' · ') || 'Hiring manager', 'company'));
    if (result.job) card.append(element('p', `Open role: ${result.job.title}`, 'company'));
  } else {
    card.append(element('h3', result.job.title), element('p', `${result.job.company} · ${managerName}`, 'company'));
  }
  card.append(element('span', `${result.hops} ${result.hops === 1 ? 'hop' : 'hops'} · ${Math.round(result.score * 100)}% path strength`, 'badge'));
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

$('search-type').addEventListener('change', () => {
  const byName = $('search-type').value === 'manager';
  $('query-label').textContent = byName ? 'Who would you like to connect with?' : 'What role are you looking for?';
  $('query').placeholder = byName ? 'First name, last name, or full name…' : 'Backend engineer, designer…';
  $('query').value = '';
  clearResults();
  message('search-message');
  $('query').focus();
});

$('search-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const seekerId = user?.id ?? Number($('seeker-mode').value === 'name'
    ? $('seeker-matches').value : $('seeker').value);
  if (!Number.isInteger(seekerId) || seekerId < 1) {
    message('seeker-message', 'Find and choose a user before searching.', true);
    return;
  }
  const query = $('query').value.trim();
  const searchType = $('search-type').value;
  if (!query) { message('search-message', 'Enter a role or hiring manager name to search for.', true); return; }
  clearResults();
  const version = searchVersion;
  $('search-button').disabled = true;
  message('search-message', 'Finding the strongest paths through your network…');
  try {
    const params = new URLSearchParams({ seeker_id: String(seekerId), q: query, limit: '3', search_type: searchType });
    const data = await request(`/search?${params}`);
    if (version !== searchVersion) return;
    message('search-message', data.results.length ? '' : searchType === 'manager'
      ? 'No hiring managers with that name are reachable within six hops. Try a first or last name.'
      : 'No connected hiring managers found for that role. Try another role or user.');
    $('results-section').hidden = !data.results.length;
    $('results-count').textContent = `${data.results.length} ${data.results.length === 1 ? 'path' : 'paths'} found`;
    $('results').replaceChildren(...data.results.map((result) => renderResult(result, seekerId, searchType)));
  } catch (error) {
    if (version === searchVersion) message('search-message', error.message, true);
  } finally { $('search-button').disabled = false; }
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
