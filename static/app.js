/* CardVault AI — Shared utilities */

function showToast(msg, type) {
  var t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast toast-' + (type || 'success');
  t.style.display = 'block';
  setTimeout(function () { t.style.display = 'none'; }, 3000);
}
