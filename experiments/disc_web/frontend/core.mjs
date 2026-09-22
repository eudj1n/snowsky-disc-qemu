export function escapeHTML(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
export function timeLabel(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '—:—';
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
}
export function filterItems(items, query) {
  const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return items.filter(item => words.every(word => `${item.title ?? ''} ${item.artist ?? ''} ${item.album ?? ''}`.toLocaleLowerCase().includes(word)));
}
export function routeHash(route) {
  return '#' + new URLSearchParams({view:route.view, ...(route.name ? {name:route.name} : {}), ...(route.artist ? {artist:route.artist} : {})});
}
export function parseRoute(hash) {
  const params = new URLSearchParams(hash.replace(/^#/, ''));
  const view = params.get('view') || 'home';
  return {view:['home','albums','artists','tracks','favorites','playlists','album','artist','playlist'].includes(view) ? view : 'home', name:params.get('name') || '', artist:params.get('artist') || ''};
}
