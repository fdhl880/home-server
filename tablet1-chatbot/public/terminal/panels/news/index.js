// Registry: command code -> mount(container, ctx)
import { mount as TOP } from './top.js';
import { mount as N } from './news.js';
import { mount as ECO } from './eco.js';
import { mount as FNG } from './fng.js';
export const panels = { TOP, N, ECO, FNG };
export { TOP, N, ECO, FNG };
export default panels;
