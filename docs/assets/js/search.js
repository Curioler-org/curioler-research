(function () {
  const input = document.getElementById('search-input');
  const grid = document.getElementById('article-grid');
  const noResults = document.getElementById('no-results');
  const filterBtns = document.querySelectorAll('.filter-btn');
  const cards = Array.from(document.querySelectorAll('.card'));

  let activeFilter = 'all';
  let searchQuery = '';

  function applyFilters() {
    let visible = 0;
    cards.forEach(function (card) {
      const domain = card.dataset.domain || '';
      const title = card.dataset.title || '';
      const topic = card.dataset.topic || '';

      const matchesDomain = activeFilter === 'all' || domain === activeFilter;
      const matchesSearch = searchQuery === '' ||
        title.includes(searchQuery) ||
        topic.includes(searchQuery) ||
        domain.toLowerCase().includes(searchQuery);

      if (matchesDomain && matchesSearch) {
        card.style.display = '';
        visible++;
      } else {
        card.style.display = 'none';
      }
    });

    noResults.style.display = visible === 0 ? 'block' : 'none';
  }

  if (input) {
    input.addEventListener('input', function () {
      searchQuery = input.value.toLowerCase().trim();
      applyFilters();
    });
  }

  filterBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      filterBtns.forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      activeFilter = btn.dataset.domain;
      applyFilters();
    });
  });
})();
