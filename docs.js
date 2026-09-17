const menuButton = document.querySelector('#menuButton');
const sidebar = document.querySelector('#sidebar');
const search = document.querySelector('#search');
const results = document.querySelector('#searchResults');

menuButton?.addEventListener('click', () => sidebar.classList.toggle('open'));

search?.addEventListener('input', () => {
  const q = search.value.trim().toLowerCase();
  results.innerHTML = '';
  if (!q) {
    results.hidden = true;
    return;
  }
  const hits = (window.SEARCH_INDEX || [])
    .filter(item => (item.title + ' ' + item.text).toLowerCase().includes(q))
    .slice(0, 8);
  if (!hits.length) {
    results.innerHTML = '<p>No results</p>';
  } else {
    for (const hit of hits) {
      const a = document.createElement('a');
      a.href = hit.url;
      a.textContent = hit.title;
      results.appendChild(a);
    }
  }
  results.hidden = false;
});
