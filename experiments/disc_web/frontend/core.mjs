export function escapeHTML(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
export function timeLabel(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '—:—';
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
}
export function trackColumns(items) {
  return {album:items.some(item=>Boolean(item.album)),
    duration:items.some(item=>Number.isFinite(item.duration)&&item.duration>=0)};
}
export function filterItems(items, query) {
  const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return items.filter(item => {
    const fields = ['artist','playlist'].includes(item.type) ? [item.title]
      : item.type==='album' ? [item.title,item.artist,...(item.artists||[])]
      : [item.title,item.artist,item.album];
    const text=fields.filter(Boolean).join(' ').toLocaleLowerCase();
    return words.every(word=>text.includes(word));
  });
}
export function searchKind(view) {
  return ({home:'albums',albums:'albums',artist:'albums',artists:'artists',playlists:'playlists'})[view] || 'tracks';
}
export function routeHash(route) {
  return '#' + new URLSearchParams({view:route.view, ...(route.name ? {name:route.name} : {}), ...(route.artist ? {artist:route.artist} : {})});
}
export function parseRoute(hash) {
  const params = new URLSearchParams(hash.replace(/^#/, ''));
  const view = params.get('view') || 'home';
  return {view:['home','albums','artists','tracks','favorites','playlists','album','artist','playlist'].includes(view) ? view : 'home', name:params.get('name') || '', artist:params.get('artist') || ''};
}

export function trackDuration(track) {
  return Number.isFinite(track?.duration_ms) ? track.duration_ms / 1000
    : Number.isFinite(track?.duration) ? track.duration : null;
}
export function playbackIdentity(state) {
  return JSON.stringify([state?.generation, state?.playback?.source, state?.playback?.track]);
}
export function coverIdentity(state) {
  const track=state?.playback?.track;
  return JSON.stringify([track?.title,track?.artist,track?.album,track?.path,
    track?.queue_position,track?.duration_ms,state?.generation]);
}
export function artworkSource(value) {
  return typeof value==='string' && (/^\/art\/cover-[0-7]\.svg$/.test(value)
    || /^\/api\/artwork\/[0-9a-f]{64}$/.test(value)) ? value : null;
}
export function seekAllowed(state) {
  const duration = trackDuration(state?.playback?.track);
  return state?.connection === 'ready' && ['playing','paused'].includes(state.playback.state)
    && Number.isFinite(duration) && duration >= 1;
}

export function mediaFormat(track) {
  const extension = track?.path?.split('.').pop()?.toLowerCase();
  return ['flac','wav','aiff','aif','alac','mp3','aac','m4a','ogg','opus','dsf','dff','iso','ape','wma'].includes(extension)
    ? extension.toUpperCase() : null;
}
export function queueTrackMatches(item, track) {
  return Number.isInteger(track?.queue_position) && item.position === track.queue_position
    && item.title === track.title && (item.artist || '') === (track.artist || '');
}
