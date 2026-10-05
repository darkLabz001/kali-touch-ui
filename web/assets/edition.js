// A saved device profile survives later source updates.
(() => {
  const selected = new URLSearchParams(location.search).get('edition');
  document.documentElement.dataset.edition = ['7inch', '4inch', '35inch'].includes(selected) ? selected : '4inch';
})();
