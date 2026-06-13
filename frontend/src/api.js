const BASE = '/api';

// ── Auth helpers ──────────────────────────────────────────────────────
export function getToken() {
  return localStorage.getItem('rpa:token');
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function handleUnauthorized(res) {
  if (res.status === 401) {
    localStorage.removeItem('rpa:token');
    localStorage.removeItem('rpa:user');
    window.location.reload();
  }
}

async function apiFetch(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  handleUnauthorized(res);
  return res;
}

export async function login(email, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error('Invalid email or password');
  return res.json(); // { access_token, user_id, email }
}

export async function signup(email, password) {
  const res = await fetch(`${BASE}/auth/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || 'Sign up failed');
  }
  return res.json(); // { access_token?, user_id?, email, confirm_email }
}

export async function getInfo() {
  const res = await apiFetch(`${BASE}/info`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getMyPapers() {
  const res = await apiFetch(`${BASE}/papers`);
  if (!res.ok) throw new Error(await res.text());
  return res.json(); // [{paper_id, title, uploaded_at, detected_domain}]
}

export async function openPaper(paperId) {
  const res = await apiFetch(`${BASE}/paper/${encodeURIComponent(paperId)}/open`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json(); // {status, restored, detected_domain?}
}

export async function submitMarkerDecision(paperId, useMarker, datalabKey = null) {
  const res = await apiFetch(`${BASE}/paper/${encodeURIComponent(paperId)}/marker_decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ use_marker: useMarker, datalab_key: datalabKey || null }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchProviders() {
  const res = await apiFetch(`${BASE}/providers`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchProviderModels(prefix, apiKey) {
  const qs = apiKey ? `?api_key=${encodeURIComponent(apiKey)}` : '';
  const res = await apiFetch(`${BASE}/providers/${encodeURIComponent(prefix)}/models${qs}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function uploadPaper(file, params) {
  const form = new FormData();
  form.append('file', file);
  form.append('model', params.model);
  form.append('api_key', params.apiKey || '');
  form.append('reader_expertise', params.readerExpertise);
  form.append('scientific_knowledge', params.scientificKnowledge);
  form.append('language_complexity', params.languageComplexity);
  form.append('datalab_api_key', params.datalabKey || '');
  form.append('domain', params.domain || 'auto');
  const res = await apiFetch(`${BASE}/upload`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getStatus(paperId) {
  const res = await apiFetch(`${BASE}/paper/${encodeURIComponent(paperId)}/status`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getGraph(paperId) {
  const res = await apiFetch(`${BASE}/paper/${encodeURIComponent(paperId)}/graph`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getSummary(paperId) {
  const res = await apiFetch(`${BASE}/paper/${encodeURIComponent(paperId)}/summary`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function sendChat(paperId, question, readerParams, model, apiKey, allPaperIds = [], priorMessages = []) {
  const res = await apiFetch(`${BASE}/paper/${encodeURIComponent(paperId)}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      reader_params: readerParams,
      model,
      api_key: apiKey || null,
      paper_ids: allPaperIds,
      prior_messages: priorMessages,
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function retryPaper(paperId) {
  const res = await apiFetch(`${BASE}/paper/${encodeURIComponent(paperId)}/retry`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deletePaper(paperId) {
  const res = await apiFetch(`${BASE}/paper/${encodeURIComponent(paperId)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function cancelPaper(paperId) {
  try {
    await apiFetch(`${BASE}/paper/${encodeURIComponent(paperId)}/cancel`, { method: 'POST' });
  } catch (_) {}
}

export function pdfUrl(paperId) {
  // PDF is served via GET — append token as query param since we can't set headers on <iframe> src
  const token = getToken();
  const base = `${BASE}/paper/${encodeURIComponent(paperId)}/pdf`;
  return token ? `${base}?token=${encodeURIComponent(token)}` : base;
}
