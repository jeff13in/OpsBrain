import { navigation, renderPage, routeFromHash, validateDraft } from './ui.js';

const main = document.querySelector('#main');
const nav = document.querySelector('#workspace-navigation');
const toggle = document.querySelector('.menu-toggle');

function render(moveFocus = false) {
  const route = routeFromHash(window.location.hash);
  const page = renderPage(route);
  nav.innerHTML = navigation(route);
  // Renderers contain trusted templates; all dynamic text is escaped in ui.js.
  main.innerHTML = page.html;
  document.querySelector('#breadcrumb').textContent = page.title;
  document.title = `${page.title} — OpsBrain`;
  toggle.setAttribute('aria-expanded', 'false');
  nav.classList.remove('is-open');
  if (moveFocus) main.focus();
  document.querySelector('#draft-form')?.addEventListener('submit', event => {
    event.preventDefault();
    document.querySelector('#draft-result').textContent = validateDraft(new FormData(event.currentTarget).get('draft'));
  });
  document.querySelector('[data-preview-action]')?.addEventListener('click', event => {
    event.currentTarget.textContent = 'Checked · no backend action';
    document.querySelector('#announcement').textContent = 'Interface interaction checked. No backend action was performed.';
  });
}

toggle.addEventListener('click', () => {
  const open = toggle.getAttribute('aria-expanded') !== 'true';
  toggle.setAttribute('aria-expanded', String(open));
  nav.classList.toggle('is-open', open);
});

document.querySelector('.skip-link').addEventListener('click', event => {
  event.preventDefault();
  main.focus();
});

document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
    toggle.setAttribute('aria-expanded', 'false');
    nav.classList.remove('is-open');
    toggle.focus();
  }
});

window.addEventListener('hashchange', () => render(true));
render();
