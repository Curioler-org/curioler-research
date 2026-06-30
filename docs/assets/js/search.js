(function () {
  const input = document.getElementById('search-input');
  const noResults = document.getElementById('no-results');
  const filterBtns = document.querySelectorAll('.filter-btn');
  const loadMoreWrap = document.getElementById('load-more-wrap');
  const loadMoreBtn = document.getElementById('load-more-btn');
  const cards = Array.from(document.querySelectorAll('.card'));

  const PAGE_SIZE = 6;
  let activeFilter = 'all';
  let searchQuery = '';
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

  function applyFilters() {
    const matching = getMatchingCards();

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

  if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', function () {
      visibleCount += PAGE_SIZE;
      applyFilters();
    });
  }

  applyFilters();
})();
