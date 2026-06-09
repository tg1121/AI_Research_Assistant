const BASE = '/api';

export async function fetchProviders() {
  const res = await fetch(`${BASE}/providers`);
  if (!res.ok) throw new Error(await res.text());
  return res.json(); // array of {name, prefix, default_model, key_hint, notes, models}
}

export async function fetchOpenRouterModels(apiKey) {
  const qs = apiKey ? `?api_key=${encodeURIComponent(apiKey)}` : '';
  const res = await fetch(`${BASE}/providers/openrouter/models${qs}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json(); // {models: [...]}
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
  const res = await fetch(`${BASE}/upload`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getStatus(paperId) {
  const res = await fetch(`${BASE}/paper/${encodeURIComponent(paperId)}/status`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getGraph(paperId) {
  const res = await fetch(`${BASE}/paper/${encodeURIComponent(paperId)}/graph`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getSummary(paperId) {
  const res = await fetch(`${BASE}/paper/${encodeURIComponent(paperId)}/summary`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function sendChat(paperId, question, readerParams, model, apiKey) {
  const res = await fetch(`${BASE}/paper/${encodeURIComponent(paperId)}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      reader_params: readerParams,
      model,
      api_key: apiKey || null,
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function cancelPaper(paperId) {
  try {
    await fetch(`${BASE}/paper/${encodeURIComponent(paperId)}/cancel`, { method: 'POST' });
  } catch (_) {}
}

export function pdfUrl(paperId) {
  return `${BASE}/paper/${encodeURIComponent(paperId)}/pdf`;
}
