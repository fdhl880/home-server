// TOP: top headlines.
import { api, h, baseStyle, header, arr, srcLabel, down, poll, ENDPOINTS } from './common.js';
import { normalize, dedupe, renderList } from './news.js';

export function mount(container, ctx) {
  const t = baseStyle(container, ctx);
  const hd = header(t, 'TOP  Top Headlines');
  const body = h('div');
  container.append(hd.el, body);
  const load = async () => {
    try {
      const { data, env } = await api(ctx, ENDPOINTS.topNews);
      const items = dedupe(arr(data).map(normalize)).sort((a, b) => new Date(b.ts) - new Date(a.ts)).slice(0, 20);
      hd.right.textContent = srcLabel(env) || 'LIVE';
      renderList(t, items, body);
    } catch (_) { body.innerHTML = ''; hd.right.textContent = ''; down(body, t); }
  };
  const stop = poll(load, 60000);
  return { unmount() { stop(); container.innerHTML = ''; }, setSymbol() {} };
}
