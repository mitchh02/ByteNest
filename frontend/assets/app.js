const $ = (id) => document.getElementById(id);
const TOKEN_KEY = 'six_degrees_token';
let user = null;
let signup = false;
let searchVersion = 0;

function message(id, text = '', error = false) {
  $(id).textContent = text;
  $(id).classList.toggle('error', error);
}

async function request(path, body) {
  const headers = { 'Content-Type': 'application/json' };
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers.Authorization = `Bearer ${token}`;
  let response;
  try {
    response = await fetch(path, { method: body === undefined ? 'GET' : 'POST', headers,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  } catch {
    throw new Error('Cannot reach the server. Please try again.');
  }
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
  $('seeker').required = !value;
  $('account-button').textContent = value ? `${value.first_name} · Sign out` : 'Sign in';
  $('inbox-section').hidden = !value;
  $('inbox').replaceChildren();
  if (value) loadInbox();
}

$('account-button').addEventListener('click', () => {
  if (user) {
    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
    message('search-message');
  } else $('account-dialog').showModal();
});
$('close-account').addEventListener('click', () => $('account-dialog').close());
$('toggle-account').addEventListener('click', () => {
  signup = !signup;
  $('name-fields').hidden = !signup;
  $('first-name').required = signup;
  $('last-name').required = signup;
  $('password').autocomplete = signup ? 'new-password' : 'current-password';
  $('account-heading').textContent = signup ? 'Build your next chapter' : 'Welcome back';
  $('account-description').textContent = signup ? 'Create your Six Degrees account.' : 'Sign in to explore your network.';
  $('account-submit').textContent = signup ? 'Create account' : 'Sign in';
  $('toggle-account').textContent = signup ? 'Already have an account? Sign in' : 'Create an account';
  message('account-message');
});
$('account-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('account-submit').disabled = true;
  $('toggle-account').disabled = true;
  message('account-message');
  try {
    const body = { email: $('email').value.trim(), password: $('password').value };
    if (signup) Object.assign(body, { first_name: $('first-name').value.trim(), last_name: $('last-name').value.trim() });
    const data = await request(signup ? '/auth/signup' : '/auth/login', body);
    localStorage.setItem(TOKEN_KEY, data.token);
    setUser(data.user);
    $('password').value = '';
    $('account-dialog').close();
    message('search-message', `Welcome, ${user.first_name}. Search for a role or hiring manager to explore your connections.`);
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
  const seekerId = user?.id ?? Number($('seeker').value);
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
