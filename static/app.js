/* CardVault AI — Shared utilities */

function showToast(msg, type) {
  var t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast toast-' + (type || 'success');
  t.style.display = 'block';
  setTimeout(function () { t.style.display = 'none'; }, 3000);
}

/* PWA — Register service worker */
if ('serviceWorker' in navigator) {
  window.addEventListener('load', function () {
    navigator.serviceWorker.register('/static/service-worker.js')
      .then(function(reg) { console.log('[CardVault] SW registered'); })
      .catch(function(err) { console.log('[CardVault] SW failed:', err); });
  });
}
