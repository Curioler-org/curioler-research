(function () {
  const input = document.getElementById('search-input');
  const noResults = document.getElementById('no-results');
  const sortSelect = document.getElementById('sort-select');
  const filters = {
    year: document.getElementById('year-filter'),
    studyType: document.getElementById('study-type-filter'),
    intervention: document.getElementById('intervention-filter'),
    diagnosis: document.getElementById('diagnosis-filter')
  };
  const grid = document.getElementById('article-grid');
  const cards = Array.from(document.querySelectorAll('.study-card'));

  function value(select) {
    return select ? select.value : 'all';
  }

  function matches(card) {
    const query = input ? input.value.toLowerCase().trim() : '';
    const haystack = [
      card.dataset.title || '',
      card.dataset.journal || '',
      card.dataset.studyType || '',
      card.dataset.intervention || '',
      card.dataset.diagnosis || ''
    ].join(' ').toLowerCase();
    return (query === '' || haystack.includes(query)) &&
      (value(filters.year) === 'all' || card.dataset.year === value(filters.year)) &&
      (value(filters.studyType) === 'all' || card.dataset.studyType === value(filters.studyType)) &&
      (value(filters.intervention) === 'all' || card.dataset.intervention === value(filters.intervention)) &&
      (value(filters.diagnosis) === 'all' || card.dataset.diagnosis === value(filters.diagnosis));
  }

  function apply() {
    const direction = sortSelect && sortSelect.value === 'oldest' ? 1 : -1;
    const matching = cards.filter(matches).sort(function (a, b) {
      return direction * ((parseInt(a.dataset.year || '0', 10)) - (parseInt(b.dataset.year || '0', 10)));
    });
    matching.forEach(function (card) { grid.appendChild(card); });
    cards.forEach(function (card) { card.style.display = 'none'; });
    matching.forEach(function (card) { card.style.display = ''; });
    if (noResults) noResults.style.display = matching.length === 0 ? 'block' : 'none';
  }

  if (input) input.addEventListener('input', apply);
  Object.keys(filters).forEach(function (key) {
    if (filters[key]) filters[key].addEventListener('change', apply);
  });
  if (sortSelect) sortSelect.addEventListener('change', apply);
  apply();
})();
