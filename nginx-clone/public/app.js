// fetch events from /api/events and render
async function fetchEvents() {
  const res = await fetch('/api/events');
  if (!res.ok) throw new Error('Failed to fetch events');
  return res.json();
}

function formatDate(d) {
  const dt = new Date(d);
  return dt.toLocaleString();
}

function render(events) {
  const container = document.getElementById('events');
  container.innerHTML = '';
  if (!events.length) {
    container.innerHTML = '<p style="grid-column:1/-1;color:#9aa4b2">No events found.</p>';
    return;
  }
  for (const e of events) {
    const card = document.createElement('article');
    card.className = 'card';
    card.innerHTML = `
      <h3>${e.title}</h3>
      <div class="meta">${formatDate(e.date)} • ${e.location}</div>
      <div class="desc">${e.description}</div>
      <div class="tags">${e.tags.map(t=>`<span class="tag">${t}</span>`).join('')}</div>
    `;
    container.appendChild(card);
  }
}

function populateTagFilter(events){
  const select = document.getElementById('tag-filter');
  const tags = new Set();
  events.forEach(e => e.tags.forEach(t => tags.add(t)));
  tags.forEach(t => {
    const opt = document.createElement('option');
    opt.value = t; opt.textContent = t;
    select.appendChild(opt);
  });
}

function installHandlers(events){
  const q = document.getElementById('q');
  const tag = document.getElementById('tag-filter');

  function applyFilters(){
    const qs = q.value.trim().toLowerCase();
    const tagv = tag.value;
    const filtered = events.filter(e => {
      const matchQ = !qs || (e.title + ' ' + e.description + ' ' + e.tags.join(' ')).toLowerCase().includes(qs);
      const matchTag = !tagv || e.tags.includes(tagv);
      return matchQ && matchTag;
    });
    render(filtered);
  }

  q.addEventListener('input', applyFilters);
  tag.addEventListener('change', applyFilters);
}

(async function init(){
  try {
    const events = await fetchEvents();
    populateTagFilter(events);
    render(events);
    installHandlers(events);
  } catch (err) {
    document.getElementById('events').innerHTML = `<p style="color:#ffb4b4">Error loading events: ${err.message}</p>`;
  }
})();
