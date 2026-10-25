// Confirmação em formulários marcados com data-confirm (sem JS inline, por causa da CSP)
document.addEventListener("submit", (e) => {
  const msg = e.target.dataset && e.target.dataset.confirm;
  if (msg && !window.confirm(msg)) e.preventDefault();
});
