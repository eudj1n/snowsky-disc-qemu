const {test} = require('node:test');
const assert = require('node:assert/strict');
const core = import('../frontend/core.mjs');

test('catalog metadata is escaped before HTML insertion', async () => {
  const {escapeHTML} = await core;
  assert.equal(escapeHTML('<img src=x onerror="alert(1)"> &'), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp;');
});
test('missing timing stays unknown and elapsed time uses whole seconds', async () => {
  const {timeLabel} = await core;
  assert.equal(timeLabel(null), '—:—');
  assert.equal(timeLabel(NaN), '—:—');
  assert.equal(timeLabel(-1), '—:—');
  assert.equal(timeLabel(125.9), '2:05');
});
test('search combines case-insensitive title and artist without changing identities', async () => {
  const {filterItems} = await core;
  const items = [{id:'1',title:'Тихий океан',artist:'Берег'}, {id:'2',title:'Океан',artist:'Другой'}];
  assert.deepEqual(filterItems(items, '  ОКЕАН берег '), [items[0]]);
  assert.deepEqual(filterItems(items, ''), items);
  assert.deepEqual(filterItems(items, '<script>'), []);
});
test('navigation preserves literal names and artist scope through deep links', async () => {
  const {routeHash,parseRoute} = await core;
  const route = {view:'album',name:'A & B / Тихий океан',artist:'Artist + Guest'};
  assert.deepEqual(parseRoute(routeHash(route)), route);
  assert.equal(parseRoute('#view=raw-command').view, 'home');
});
test('seek uses observed duration and invalidates a draft on track/source/reconnect changes', async () => {
  const {trackDuration,seekAllowed,playbackIdentity} = await core;
  const state={connection:'ready',generation:2,playback:{state:'paused',source:3,track:{title:'Track',duration_ms:120000}}};
  assert.equal(trackDuration(state.playback.track),120);
  assert.equal(seekAllowed(state),true);
  for(const altered of [
    {...state,connection:'reconnecting'},
    {...state,playback:{...state.playback,state:'loading'}},
    {...state,playback:{...state.playback,track:{title:'Unknown duration'}}}
  ]) assert.equal(seekAllowed(altered),false);
  for(const altered of [
    {...state,generation:3},
    {...state,playback:{...state.playback,source:0}},
    {...state,playback:{...state.playback,track:{...state.playback.track,title:'Other'}}}
  ]) assert.notEqual(playbackIdentity(altered),playbackIdentity(state));
  assert.equal(playbackIdentity({...state,playback:{...state.playback,position_ms:20000}}),playbackIdentity(state));
});
