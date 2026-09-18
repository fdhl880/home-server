const fs = require('fs');
const c = fs.readFileSync('public/index.html', 'utf8');

function dumpSnippet(target, before = 50, after = 150) {
    const idx = c.indexOf(target);
    if (idx < 0) return console.log('NOT FOUND:', target);
    console.log('--- FOUND:', target, '---');
    console.log(JSON.stringify(c.substring(idx - before, idx + after)));
}

dumpSnippet('btnEmsxExec', 60, 160);
dumpSnippet('TRADEABLE ASSET UNIVERSE', 80, 160);
dumpSnippet('GLOBAL MULTI-ASSET', 80, 160);
dumpSnippet('raw === \'PORT\'', 100, 160);
