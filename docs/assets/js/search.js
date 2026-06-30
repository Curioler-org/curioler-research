(function () {
  const input = document.getElementById('search-input');
  const noResults = document.getElementById('no-results');
  const filterBtns = document.querySelectorAll('.filter-btn');
  const sortSelect = document.getElementById('sort-select');
  const loadMoreWrap = document.getElementById('load-more-wrap');
  const loadMoreBtn = document.getElementById('load-more-btn');
  const grid = document.getElementById('article-grid');
  const cards = Array.from(document.querySelectorAll('.card'));

  const PAGE_SIZE = 6;
  let activeFilter = 'all';
  let searchQuery = '';
  let sortKey = 'date-desc';
  let visibleCount = PAGE_SIZE;

  function getMatchingCards() {
    return cards.filter(function (card) {
      const domain = card.dataset.domain || '';
      const title = card.dataset.title || '';
      const topic = card.dataset.topic || '';
      const matchesDomain = activeFilter === 'all' || domain === activeFilter;
      const matchesSearch = searchQuery === '' ||
        title.includes(searchQuery) ||
        topic.includes(searchQuery) ||
        domain.toLowerCase().includes(searchQuery);
      return matchesDomain && matchesSearch;
    });
  }

  function sortCards(list) {
    return list.slice().sort(function (a, b) {
      switch (sortKey) {
        case 'date-desc': return (b.dataset.date || '').localeCompare(a.dataset.date || '');
        case 'date-asc':  return (a.dataset.date || '').localeCompare(b.dataset.date || '');
        case 'tier-asc':  return parseInt(a.dataset.tier || 9) - parseInt(b.dataset.tier || 9);
        case 'tier-desc': return parseInt(b.dataset.tier || 0) - parseInt(a.dataset.tier || 0);
        case 'domain-asc': return (a.dataset.domain || '').localeCompare(b.dataset.domain || '');
        default: return 0;
      }
    });
  }

  function applyFilters() {
    const matching = sortCards(getMatchingCards());

    // Re-order DOM nodes to match sort
    matching.forEach(function (card) { grid.appendChild(card); });

    // Hide all, show up to visibleCount
    cards.forEach(function (card) { card.style.display = 'none'; });
    matching.slice(0, visibleCount).forEach(function (card) { card.style.display = ''; });

    noResults.style.display = matching.length === 0 ? 'block' : 'none';

    if (matching.length > visibleCount) {
      loadMoreWrap.style.display = 'flex';
      loadMoreBtn.textContent = 'Load more (' + (matching.length - visibleCount) + ' remaining)';
    } else {
      loadMoreWrap.style.display = 'none';
    }
  }

  if (input) {
    input.addEventListener('input', function () {
      searchQuery = input.value.toLowerCase().trim();
      visibleCount = PAGE_SIZE;
      applyFilters();
    });
  }

  filterBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      filterBtns.forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      activeFilter = btn.dataset.domain;
      visibleCount = PAGE_SIZE;
      applyFilters();
    });
  });

  if (sortSelect) {
    sortSelect.addEventListener('change', function () {
      sortKey = sortSelect.value;
      visibleCount = PAGE_SIZE;
      applyFilters();
    });
  }

  if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', function () {
      visibleCount += PAGE_SIZE;
      applyFilters();
    });
  }

  applyFilters();
})();
