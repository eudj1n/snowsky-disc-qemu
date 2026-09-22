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
