/* Shared renderer for one TikTok's extraction (used by add.html and detail.html). */
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text == null ? '' : text;
  return div.innerHTML;
}

function renderExtraction(el, r, transcript, screenText) {
  let html = '';

  const s = r.video_summary || {};
  html += `<div class="card">
    <h2>${escapeHtml(s.main_topic) || 'Video summary'}</h2>
    <p class="summary-text">${escapeHtml(s.summary) || ''}</p>
    <div class="meta-row" style="margin-top:12px">
      <span class="tag">${escapeHtml(s.destination_city) || '?'}, ${escapeHtml(s.destination_country) || '?'}</span>
      <span class="tag ${escapeHtml(s.usefulness_for_itinerary) || ''}">${escapeHtml(s.usefulness_for_itinerary) || '?'} usefulness</span>
      ${(s.overall_vibe || []).map(v => `<span class="tag vibe">${escapeHtml(v)}</span>`).join('')}
    </div>
  </div>`;

  const places = r.places || [];
  html += `<div class="card"><h2>Places <span class="count">${places.length}</span></h2>`;
  if (!places.length) html += `<div class="muted">No map-pinnable places were found in this TikTok.</div>`;
  for (const p of places) {
    const parentTxt = p.parent_place ? `<span class="place-parent">inside ${escapeHtml(p.parent_place)}</span>` : '';
    const confClass = escapeHtml(p.confidence) || 'medium';
    html += `<div class="place-card">
      <div class="place-head">
        <span class="place-name">${escapeHtml(p.name) || '(unnamed)'}</span>
        <span class="place-type">${escapeHtml(p.place_type) || ''}</span>
        ${parentTxt}
        <span class="tag ${confClass}">${escapeHtml(p.confidence)}</span>
      </div>`;
    if (p.creator_notes && p.creator_notes.length) {
      html += `<div class="place-detail">${p.creator_notes.map(n => `• ${escapeHtml(n)}`).join('<br>')}</div>`;
    }
    if (p.mentioned_foods_or_items && p.mentioned_foods_or_items.length) {
      html += `<div class="place-detail"><strong>Food / items</strong> ${p.mentioned_foods_or_items.map(escapeHtml).join(', ')}</div>`;
    }
    if (p.warnings_or_requirements && p.warnings_or_requirements.length) {
      html += `<div class="place-detail warn"><strong>Heads up</strong> ${p.warnings_or_requirements.map(escapeHtml).join('; ')}</div>`;
    }
    if (p.best_for && p.best_for.length) {
      html += `<div class="meta-row" style="margin-top:10px">${p.best_for.map(b => `<span class="tag">${escapeHtml(b)}</span>`).join('')}</div>`;
    }
    const se = p.source_evidence || {};
    html += `<div class="evidence">
      <span class="ev ${se.caption ? 'on' : 'off'}">caption</span>
      <span class="ev ${se.transcript ? 'on' : 'off'}">transcript</span>
      <span class="ev ${se.ocr ? 'on' : 'off'}">on-screen text</span>
      ${p.map_search_query ? `<span class="map-query">${escapeHtml(p.map_search_query)}</span>` : ''}
    </div>`;
    html += `</div>`;
  }
  html += `</div>`;

  const notes = r.non_place_notes || [];
  if (notes.length) {
    html += `<div class="card"><h2>Notes <span class="count">${notes.length}</span></h2>`;
    for (const n of notes) {
      const related = n.related_place ? ` <em>→ ${escapeHtml(n.related_place)}</em>` : '';
      html += `<div class="note-item"><span class="note-type">${escapeHtml(n.type) || '?'}</span>${escapeHtml(n.text) || ''}${related}</div>`;
    }
    html += `</div>`;
  }

  const reviews = r.needs_user_review || [];
  if (reviews.length) {
    html += `<div class="card"><h2>Needs your review <span class="count">${reviews.length}</span></h2>`;
    for (const rv of reviews) {
      html += `<div class="review-item"><span class="review-issue">${escapeHtml(rv.issue) || '?'}</span><span class="review-reason">${escapeHtml(rv.reason) || ''}</span></div>`;
    }
    html += `</div>`;
  }

  html += `<details class="card raw">
    <summary>Raw extracted data</summary>
    <h3>Audio transcript</h3>
    ${transcript ? `<div class="raw-data-content">${escapeHtml(transcript)}</div>` : '<div class="muted">No spoken transcript detected (music-only video).</div>'}
    <h3>On-screen text</h3>
    ${screenText ? `<div class="raw-data-content">${escapeHtml(screenText)}</div>` : '<div class="muted">No on-screen text detected.</div>'}
  </details>`;

  el.innerHTML = html;
}
