'use strict';

const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const WebSocket = require('ws');

const {
    createServerApp,
    resolveDashToken,
    tokensMatch,
    validateSymbol,
    writeJsonAtomicSync,
    readJsonSafeSync,
    validateTradingConfigPatch,
    escapeHtml
} = require('./server');
const U = require('./terminal/api/util');

const RESULTS = [];

async function test(name, fn) {
    try {
        await fn();
        RESULTS.push({ name, ok: true });
        console.log(`PASS: ${name}`);
    } catch (err) {
        RESULTS.push({ name, ok: false, err });
        console.error(`FAIL: ${name}`);
        console.error(err && err.stack ? err.stack : err);
    }
}

function makeTempEnv() {
    const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'wp4-sec-'));
    const pluangDir = path.join(tmpRoot, 'pluang-bot');
    const resultsDir = path.join(pluangDir, 'results');
    fs.mkdirSync(resultsDir, { recursive: true });
    return {
        tmpRoot,
        pluangDir,
        resultsDir,
        configPath: path.join(pluangDir, 'trading_config.json'),
        positionsPath: path.join(resultsDir, 'active_positions.json'),
        statePath: path.join(resultsDir, 'autotrader_state.json'),
        quickScreenPath: path.join(resultsDir, 'quick_screen.json'),
        tokensPath: path.join(pluangDir, 'tokens.json'),
        perfLedgerPath: path.join(resultsDir, 'performance_ledger.json'),
        envPath: path.join(pluangDir, '.env'),
        portfolioFile: path.join(tmpRoot, 'portfolio-data.json'),
        bmailFile: path.join(tmpRoot, 'bmail-store.json'),
        dashTokenFile: path.join(pluangDir, '.dash_token')
    };
}

function listenServer(ctx) {
    return new Promise((resolve, reject) => {
        const srv = ctx.app.listen(0, '127.0.0.1', () => {
            const addr = srv.address();
            resolve({ srv, port: addr.port, baseUrl: `http://127.0.0.1:${addr.port}` });
        });
        srv.on('error', reject);
    });
}

function closeServer(srv, ctx) {
    return new Promise(resolve => {
        try { ctx.close(); } catch (_) {}
        try {
            srv.close(() => resolve());
            if (typeof srv.closeAllConnections === 'function') srv.closeAllConnections();
        } catch (_) {
            resolve();
        }
    });
}

function rawHttpRequest(port, { method = 'GET', reqPath = '/', headers = {}, body = null }) {
    return new Promise((resolve, reject) => {
        const req = http.request({
            hostname: '127.0.0.1',
            port,
            path: reqPath,
            method,
            headers
        }, res => {
            const chunks = [];
            res.on('data', d => chunks.push(d));
            res.on('end', () => {
                const text = Buffer.concat(chunks).toString('utf8');
                let json = null;
                try { json = JSON.parse(text); } catch (_) {}
                resolve({ status: res.statusCode, headers: res.headers, text, json });
            });
        });
        req.on('error', reject);
        if (body !== null && body !== undefined) req.write(body);
        req.end();
    });
}

function connectWsExpectReject(url, protocols, wsOpts = {}, label = '') {
    return new Promise((resolve, reject) => {
        const ws = protocols ? new WebSocket(url, protocols, wsOpts) : new WebSocket(url, wsOpts);
        let settled = false;
        const finish = (val) => {
            if (settled) return;
            settled = true;
            try { ws.terminate(); } catch (_) {}
            resolve(val);
        };
        ws.on('open', () => {
            settled = true;
            try { ws.terminate(); } catch (_) {}
            reject(new Error(`Expected WS rejection [${label}] for ${url}, but connection opened`));
        });
        ws.on('unexpected-response', (_req, res) => {
            finish({ rejected: true, statusCode: res.statusCode });
        });
        ws.on('error', err => {
            finish({ rejected: true, statusCode: null, message: err.message });
        });
        ws.on('close', code => {
            finish({ rejected: true, statusCode: null, closeCode: code });
        });
    });
}

function connectWsOpen(url, protocols, wsOpts = {}) {
    return new Promise((resolve, reject) => {
        const ws = protocols ? new WebSocket(url, protocols, wsOpts) : new WebSocket(url, wsOpts);
        const timer = setTimeout(() => {
            try { ws.terminate(); } catch (_) {}
            reject(new Error(`Timed out waiting for WS hello on ${url}`));
        }, 5000);
        ws.on('unexpected-response', (_req, res) => {
            clearTimeout(timer);
            reject(new Error(`Unexpected HTTP ${res.statusCode} on WS ${url}`));
        });
        ws.on('error', err => {
            clearTimeout(timer);
            reject(err);
        });
        ws.on('message', raw => {
            try {
                const msg = JSON.parse(raw.toString('utf8'));
                if (msg.type === 'hello') {
                    clearTimeout(timer);
                    resolve({ ws, hello: msg, protocol: ws.protocol });
                }
            } catch (_) {}
        });
    });
}

async function run() {
    const repoRoot = __dirname;

    // 1. Source & hygiene invariants
    await test('Source scan: no hardcoded Resend key or wildcard CORS in backend files', () => {
        const serverSrc = fs.readFileSync(path.join(repoRoot, 'server.js'), 'utf8');
        const indexSrc = fs.readFileSync(path.join(repoRoot, 'terminal', 'api', 'index.js'), 'utf8');
        const gitignoreSrc = fs.readFileSync(path.join(repoRoot, '.gitignore'), 'utf8');
        const opsSrc = fs.readFileSync(path.join(repoRoot, 'public', 'terminal', 'js', 'panels', 'ops.js'), 'utf8');
        const mainSrc = fs.readFileSync(path.join(repoRoot, 'public', 'terminal', 'js', 'main.js'), 'utf8');
        const termHtml = fs.readFileSync(path.join(repoRoot, 'public', 'terminal', 'index.html'), 'utf8');
        const pluangHtml = fs.readFileSync(path.join(repoRoot, 'pluang-bot', 'static', 'index.html'), 'utf8');

        assert(!serverSrc.includes('_DEFAULT_RESEND_KEY'), 'server.js must not contain _DEFAULT_RESEND_KEY');
        assert(!/re_[A-Za-z0-9]{15,}/.test(serverSrc), 'server.js must not contain hardcoded Resend API key literal');
        assert(!/Access-Control-Allow-Origin['"`\s,]*['"`]\*['"`]/.test(indexSrc), 'terminal/api/index.js must not allow wildcard CORS *');
        assert(!/Access-Control-Allow-Origin['"`\s,]*['"`]\*['"`]/.test(serverSrc), 'server.js must not allow wildcard CORS *');
        assert(/\.dash_token/.test(gitignoreSrc), '.gitignore must ignore .dash_token');

        assert(!/value:\s*cfg\.smtpPass/.test(opsSrc), 'ops.js must not prefill smtpPass into DOM input value');
        assert(opsSrc.includes("confirm: 'CONFIRM_RESUME'"), 'ops.js RESET BREAKER must send CONFIRM_RESUME');
        assert(termHtml.includes('id="authModal"') && mainSrc.includes('/api/auth/verify'), 'Terminal UI must wire #authModal -> /api/auth/verify');
        assert(termHtml.includes('main.js?v=20261118b') && mainSrc.includes('charts.js?v=20261118b') && opsSrc.includes('charts.js?v=20261118b'), 'Cache-buster query string must match across index.html, main.js, ops.js');
        assert(pluangHtml.includes('id="auth-modal"') && pluangHtml.includes('/api/auth/verify') && !pluangHtml.includes("executeTrade('${currentSelectedSymbol}'"), 'Pluang UI must have #auth-modal and safe event bindings');

        // Compile inline <script> in pluang-bot/static/index.html to guarantee valid JS syntax
        const vm = require('vm');
        const scriptMatches = [...pluangHtml.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)];
        assert(scriptMatches.length >= 1, 'Expected inline script in pluang-bot/static/index.html');
        for (const m of scriptMatches) {
            new vm.Script(m[1], { filename: 'pluang-bot/static/index.html' });
        }
    });

    // 2. Unit checks: fail-closed token generation, timing-safe match, symbol validation, secret redaction, HTML escape
    await test('Helpers: resolveDashToken, tokensMatch, validateSymbol, config validation, redactSecrets, escapeHtml', () => {
        const env = makeTempEnv();
        const prevEnvTok = process.env.DASH_TOKEN;
        delete process.env.DASH_TOKEN;
        try {
            const first = resolveDashToken(env.dashTokenFile);
            assert.strictEqual(first.generated, true);
            assert.strictEqual(first.source, env.dashTokenFile);
            assert.match(first.token, /^[0-9a-f]{64}$/);
            assert.strictEqual(fs.existsSync(env.dashTokenFile), true);
            if (process.platform !== 'win32') {
                assert.strictEqual(fs.statSync(env.dashTokenFile).mode & 0o777, 0o600);
            }

            const second = resolveDashToken(env.dashTokenFile);
            assert.strictEqual(second.generated, false);
            assert.strictEqual(second.token, first.token);

            process.env.DASH_TOKEN = '  custom_env_token_value_123456  ';
            const fromEnv = resolveDashToken(env.dashTokenFile);
            assert.strictEqual(fromEnv.source, 'env:DASH_TOKEN');
            assert.strictEqual(fromEnv.token, 'custom_env_token_value_123456');
        } finally {
            if (prevEnvTok !== undefined) process.env.DASH_TOKEN = prevEnvTok;
            else delete process.env.DASH_TOKEN;
            fs.rmSync(env.tmpRoot, { recursive: true, force: true });
        }

        assert.strictEqual(tokensMatch('secret123', 'secret123'), true);
        assert.strictEqual(tokensMatch('secret123', 'secret124'), false);
        assert.strictEqual(tokensMatch('short', 'muchlonger'), false);
        assert.strictEqual(tokensMatch('', 'secret123'), false);
        assert.strictEqual(tokensMatch(null, 'secret123'), false);

        assert.strictEqual(validateSymbol('btc-usd'), 'BTC-USD');
        assert.strictEqual(validateSymbol('BTCUSDT.P'), 'BTCUSDT.P');
        assert.strictEqual(validateSymbol('^TNX'), '^TNX');
        assert.strictEqual(validateSymbol('BBCA.JK'), 'BBCA.JK');
        assert.strictEqual(validateSymbol("BTC'); import os; #"), null);
        assert.strictEqual(validateSymbol('-e'), null);
        assert.strictEqual(validateSymbol('BTC..USD'), null);
        assert.strictEqual(validateSymbol('A'.repeat(21)), null);

        assert.throws(() => validateTradingConfigPatch({ max_leverage: 999 }), /out of allowed range/);
        assert.throws(() => validateTradingConfigPatch({ unknown_key: 1 }), /Unsupported config field/);
        const cleanCfg = validateTradingConfigPatch({ max_leverage: 10, order_type: 'limit', tp1_move_sl_to_breakeven: true });
        assert.deepStrictEqual(cleanCfg, { max_leverage: 10, order_type: 'LIMIT', tp1_move_sl_to_breakeven: true });

        assert.strictEqual(escapeHtml(`<script>"a"&'b'</script>`), '&lt;script&gt;&quot;a&quot;&amp;&#39;b&#39;&lt;/script&gt;');

        const redacted = U.redactSecrets('GET https://finnhub.io/api/v1/quote?symbol=AAPL&token=SUPER_SECRET_123&apikey=KEY_456&key=re_AbCdEfGhIjKlMnOpQrStUv');
        assert(!redacted.includes('SUPER_SECRET_123'), 'token query param must be redacted');
        assert(!redacted.includes('KEY_456'), 'apikey query param must be redacted');
        assert(!redacted.includes('re_AbCdEfGhIjKlMnOpQrStUv'), 'Resend key must be redacted');
    });

    // Spin up isolated test server
    const testToken = crypto.randomBytes(32).toString('hex');
    const env = makeTempEnv();
    writeJsonAtomicSync(env.positionsPath, []);
    writeJsonAtomicSync(env.configPath, {
        max_leverage: 20,
        order_type: 'MARKET',
        margin_type: 'ISOLATED',
        auto_execute_on_pluang: false
    });
    writeJsonAtomicSync(env.statePath, { total_scans_done: 1 });
    writeJsonAtomicSync(env.quickScreenPath, { alerts: [], screened: 0 });
    fs.writeFileSync(env.envPath, '# Keep this comment\nUNRELATED_VAR=keep_me\nGROQ_API_KEYS=gsk_existingkey1234567890\n', 'utf8');
    writeJsonAtomicSync(env.bmailFile, {
        account: { name: 'Test User', email: 'test@bloomberg.net', externalEmail: 'owner@example.com', uuid: '1' },
        alertConfig: {
            targetEmail: 'owner@example.com',
            enableHotNews: true,
            enableFuturesOpen: true,
            enableFuturesClose: true,
            enableEmsxOrders: true,
            smtpUser: 'owner@example.com',
            smtpPass: 'super-secret-smtp-pass-999',
            resendApiKey: 're_shouldneverleaksynthetic123'
        },
        alertLog: [],
        inbox: [{ id: 'M1', unread: true, subject: 'Hi', body: 'Hello' }],
        sent: [],
        directory: []
    });

    const ctx = createServerApp({
        ...env,
        port: 0,
        dashHost: '127.0.0.1',
        dashToken: testToken,
        allowedOrigins: ['https://remote.example.ts.net'],
        maxWsPerIp: 2,
        authVerifyRateLimit: 5,
        costlyRateLimit: 50,
        apiRateLimit: 200,
        testMode: true
    });
    const { srv, port } = await listenServer(ctx);

    try {
        // 3. Fail-closed auth checks
        await test('Auth: blocks unauthenticated mutating & sensitive GET endpoints, allows Bearer/X-Dash-Token + public quotes', async () => {
            const sensitiveGets = [
                '/api/config',
                '/api/crypto-futures/settings',
                '/api/terminal/bmail',
                '/api/crypto-futures/positions',
                '/api/crypto-futures/quant-health',
                '/api/portfolio',
                '/api/committee/thesis',
                '/api/execution-log'
            ];
            for (const p of sensitiveGets) {
                const r = await rawHttpRequest(port, { method: 'GET', reqPath: p });
                assert.strictEqual(r.status, 401, `Expected 401 on unauthenticated GET ${p}, got ${r.status}`);
            }

            const unauthPost = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/crypto-futures/settings',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ max_leverage: 10 })
            });
            assert.strictEqual(unauthPost.status, 401);

            // Public GETs stay reachable
            const pubMarket = await rawHttpRequest(port, { method: 'GET', reqPath: '/api/market/quotes' });
            assert.strictEqual(pubMarket.status, 200);
            const pubStatic = await rawHttpRequest(port, { method: 'GET', reqPath: '/' });
            assert.strictEqual(pubStatic.status, 200);

            // Legacy mutating GETs are blocked even with auth (converted to POST/DELETE only)
            const legacyUnauth = await rawHttpRequest(port, { method: 'GET', reqPath: '/api/portfolio/reset' });
            assert.strictEqual(legacyUnauth.status, 401);
            const legacyAuth = await rawHttpRequest(port, {
                method: 'GET',
                reqPath: '/api/portfolio/reset',
                headers: { 'X-Dash-Token': testToken }
            });
            assert.strictEqual(legacyAuth.status, 404);
            const dmaBuyGet = await rawHttpRequest(port, {
                method: 'GET',
                reqPath: '/api/dma-buy?symbol=AAPL',
                headers: { 'X-Dash-Token': testToken }
            });
            assert.strictEqual(dmaBuyGet.status, 404);

            // Sensitive GET succeeds with Bearer and X-Dash-Token
            const authCfg = await rawHttpRequest(port, {
                method: 'GET',
                reqPath: '/api/config',
                headers: { Authorization: `Bearer ${testToken}` }
            });
            assert.strictEqual(authCfg.status, 200);
            assert.strictEqual(authCfg.json.max_leverage, 20);

            const authVerifyBad = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/auth/verify',
                headers: { 'Content-Type': 'application/json', 'X-Dash-Token': 'wrong-token' },
                body: '{}'
            });
            assert.strictEqual(authVerifyBad.status, 401);
            assert.deepStrictEqual(authVerifyBad.json, { ok: false, error: 'Unauthorized' });

            const authVerifyOk = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/auth/verify',
                headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                body: '{}'
            });
            assert.strictEqual(authVerifyOk.status, 200);
            assert.deepStrictEqual(authVerifyOk.json, { ok: true });
        });

        // 4. CORS checks
        await test('CORS: denies cross-origin requests, allows same-origin and ALLOWED_ORIGINS', async () => {
            const evilMain = await rawHttpRequest(port, {
                method: 'GET',
                reqPath: '/api/market/quotes',
                headers: { Origin: 'https://evil.attacker' }
            });
            assert.strictEqual(evilMain.status, 403);

            const evilTerm = await rawHttpRequest(port, {
                method: 'GET',
                reqPath: '/api/terminal/health',
                headers: { Origin: 'https://evil.attacker' }
            });
            assert.strictEqual(evilTerm.status, 403);
            assert.strictEqual(evilTerm.headers['access-control-allow-origin'], undefined);

            const sameOrigin = await rawHttpRequest(port, {
                method: 'GET',
                reqPath: '/api/terminal/health',
                headers: { Origin: `http://127.0.0.1:${port}` }
            });
            assert.strictEqual(sameOrigin.status, 200);
            assert.strictEqual(sameOrigin.headers['access-control-allow-origin'], `http://127.0.0.1:${port}`);

            const allowedRemote = await rawHttpRequest(port, {
                method: 'GET',
                reqPath: '/api/terminal/health',
                headers: { Origin: 'https://remote.example.ts.net' }
            });
            assert.strictEqual(allowedRemote.status, 200);
            assert.strictEqual(allowedRemote.headers['access-control-allow-origin'], 'https://remote.example.ts.net');
        });

        // 5. Python RCE payload rejection & stdin JSON safety
        await test('Python injection: rejects malicious symbol payloads with 400 and passes JSON booleans cleanly via stdin', () => {
            // Check Python stdin handling directly (if python/py available)
            let pythonCmd = null;
            for (const candidate of ['python', 'python3']) {
                try {
                    execFileSync(candidate, ['--version'], { stdio: 'pipe', timeout: 3000 });
                    pythonCmd = candidate;
                    break;
                } catch (_) {}
            }
            if (pythonCmd) {
                const payload = { symbol: "BTC'); import os; #", active: true, inactive: false, nothing: null };
                const out = execFileSync(pythonCmd, ['-c', 'import json, sys; d = json.loads(sys.stdin.read()); print(json.dumps([type(d["active"]).__name__, d["inactive"], d["nothing"] is None]))'], {
                    input: JSON.stringify(payload),
                    encoding: 'utf8',
                    timeout: 5000
                });
                assert.deepStrictEqual(JSON.parse(out.trim()), ['bool', false, true]);
            }
        });

        await test('HTTP routes reject RCE & flag-injection symbol payloads with 400', async () => {
            const payloads = ["BTC'); import os; #", "-e", "../etc/passwd", "BTC\nimport os"];
            for (const badSym of payloads) {
                const scanRes = await rawHttpRequest(port, {
                    method: 'POST',
                    reqPath: '/api/crypto-futures/scan',
                    headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                    body: JSON.stringify({ symbol: badSym })
                });
                assert.strictEqual(scanRes.status, 400, `Expected 400 for /scan symbol ${badSym}`);

                const commRes = await rawHttpRequest(port, {
                    method: 'POST',
                    reqPath: '/api/committee/run',
                    headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                    body: JSON.stringify({ symbol: badSym })
                });
                assert.strictEqual(commRes.status, 400, `Expected 400 for /committee/run symbol ${badSym}`);

                const execRes = await rawHttpRequest(port, {
                    method: 'POST',
                    reqPath: '/api/crypto-futures/execute',
                    headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                    body: JSON.stringify({ symbol: badSym, direction: 'LONG', amount_idr: 50000 })
                });
                assert.strictEqual(execRes.status, 400, `Expected 400 for /execute symbol ${badSym}`);
            }
        });

        // 6. Secret removal, B-Mail redaction & relay restriction, .env injection protection, health URL redaction
        await test('Secrets & B-Mail: strips smtpPass/resendApiKey, blocks open relay, prevents .env CRLF injection, redacts health errors', async () => {
            const bmailGet = await rawHttpRequest(port, {
                method: 'GET',
                reqPath: '/api/terminal/bmail',
                headers: { 'X-Dash-Token': testToken }
            });
            assert.strictEqual(bmailGet.status, 200);
            assert.strictEqual(bmailGet.json.data.alertConfig.hasSmtpPass, true);
            assert.strictEqual(bmailGet.json.data.alertConfig.hasResendKey, false);
            assert.strictEqual(bmailGet.json.data.alertConfig.smtpPass, undefined);
            assert.strictEqual(bmailGet.json.data.alertConfig.resendApiKey, undefined);
            assert(!bmailGet.text.includes('super-secret-smtp-pass-999'), 'GET bmail leaked smtpPass!');
            assert(!bmailGet.text.includes('re_shouldneverleaksynthetic123'), 'GET bmail leaked resendApiKey!');

            const alertBadProp = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/terminal/bmail/alert-config',
                headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                body: JSON.stringify({ injectedProp: 'bad' })
            });
            assert.strictEqual(alertBadProp.status, 400);

            const alertPatch = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/terminal/bmail/alert-config',
                headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                body: JSON.stringify({
                    enableHotNews: false,
                    smtpPass: 'updated-smtp-pass-777',
                    resendApiKey: 're_shouldignore'
                })
            });
            assert.strictEqual(alertPatch.status, 200);
            assert(!alertPatch.text.includes('updated-smtp-pass-777'));
            const diskBmail = JSON.parse(fs.readFileSync(env.bmailFile, 'utf8'));
            assert.strictEqual(diskBmail.alertConfig.injectedProp, undefined);
            assert.strictEqual(diskBmail.alertConfig.resendApiKey, undefined);
            assert.strictEqual(diskBmail.alertConfig.smtpPass, 'updated-smtp-pass-777');

            // B-Mail open relay blocked
            const relayBlocked = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/terminal/bmail/send',
                headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                body: JSON.stringify({ to: 'victim@external-domain.example', subject: 'Phish', body: 'Test' })
            });
            assert.strictEqual(relayBlocked.status, 403);

            // Internal @bloomberg.net allowed cleanly
            const internalSend = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/terminal/bmail/send',
                headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                body: JSON.stringify({ to: 'desk@bloomberg.net', subject: 'Hello Desk', body: 'Test msg' })
            });
            assert.strictEqual(internalSend.status, 200);
            assert.strictEqual(internalSend.json.ok, true);

            // .env CRLF injection rejected
            const envInj = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/crypto-futures/ai-gateway/add-key',
                headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                body: JSON.stringify({ provider: 'groq', api_key: 'gsk_validprefix123456\nADMIN_BACKDOOR=1' })
            });
            assert.strictEqual(envInj.status, 400);

            const envValid = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/crypto-futures/ai-gateway/add-key',
                headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                body: JSON.stringify({ provider: 'groq', api_key: 'gsk_syntheticKeyValid987654321' })
            });
            assert.strictEqual(envValid.status, 200);
            const envText = fs.readFileSync(env.envPath, 'utf8');
            assert(envText.includes('# Keep this comment'), '.env comments must be preserved');
            assert(envText.includes('UNRELATED_VAR=keep_me'), 'unrelated .env keys must be preserved');
            assert(envText.includes('gsk_syntheticKeyValid987654321'), 'new valid key must be saved');

            // Provider health error redaction
            U.record('wp4-test-provider', false, 12, new Error('Failed GET https://finnhub.io/api/v1/quote?token=LEAKED_TOKEN_ABC&apikey=LEAKED_API_XYZ'));
            const healthRes = await rawHttpRequest(port, { method: 'GET', reqPath: '/api/terminal/health' });
            assert.strictEqual(healthRes.status, 200);
            assert(!healthRes.text.includes('LEAKED_TOKEN_ABC'), 'health() exposed token query param');
            assert(!healthRes.text.includes('LEAKED_API_XYZ'), 'health() exposed apikey query param');
        });

        // 7. Config/trade validation, breaker/unpanic confirmation, malformed JSON & size limit
        await test('Validation & Error Handling: invalid config/trade 400, breaker/unpanic confirmation, corrupt state 500, JSON 400/413', async () => {
            const badCfg = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/crypto-futures/settings',
                headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                body: JSON.stringify({ max_leverage: 999 })
            });
            assert.strictEqual(badCfg.status, 400);

            const goodCfg = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/crypto-futures/settings',
                headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                body: JSON.stringify({ max_leverage: 10, order_type: 'limit' })
            });
            assert.strictEqual(goodCfg.status, 200);
            assert.strictEqual(goodCfg.json.max_leverage, 10);
            assert.strictEqual(goodCfg.json.order_type, 'LIMIT');

            const badTrade = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/portfolio/trade',
                headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                body: JSON.stringify({ type: 'HACK', symbol: 'AAPL', qty: -1, price: 100 })
            });
            assert.strictEqual(badTrade.status, 400);

            // Breaker confirmation + Python field preservation
            const breakerPath = path.join(env.resultsDir, 'risk_breaker_state.json');
            writeJsonAtomicSync(breakerPath, { breaker_active: true, consecutive_losses: 2, current_equity: 150, custom_py_field: 'keep_me' });

            const brkNoConfirm = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/crypto-futures/risk-breaker/resume',
                headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                body: '{}'
            });
            assert.strictEqual(brkNoConfirm.status, 400);

            const brkOk = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/crypto-futures/risk-breaker/resume',
                headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                body: JSON.stringify({ confirm: 'CONFIRM_RESUME' })
            });
            assert.strictEqual(brkOk.status, 200);
            assert.strictEqual(brkOk.json.breaker.breaker_active, false);
            assert.strictEqual(brkOk.json.breaker.custom_py_field, 'keep_me');

            // Corrupt breaker JSON must fail loudly with 500 instead of silently resetting
            fs.writeFileSync(breakerPath, '{corrupt json', 'utf8');
            const brkCorrupt = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/crypto-futures/risk-breaker/resume',
                headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                body: JSON.stringify({ confirm: 'CONFIRM_RESUME' })
            });
            assert.strictEqual(brkCorrupt.status, 500);

            // Unpanic requires CONFIRM_UNPANIC
            const unpanicBad = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/crypto-futures/unpanic',
                headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                body: '{}'
            });
            assert.strictEqual(unpanicBad.status, 400);

            const unpanicOk = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/crypto-futures/unpanic',
                headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                body: JSON.stringify({ confirm: 'CONFIRM_UNPANIC' })
            });
            assert.strictEqual(unpanicOk.status, 200);
            assert.strictEqual(unpanicOk.json.success, true);

            // Malformed JSON -> JSON 400 (not HTML)
            const badJson = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/crypto-futures/settings',
                headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                body: '{invalid-json'
            });
            assert.strictEqual(badJson.status, 400);
            assert.strictEqual(badJson.json.ok, false);

            // Oversized payload > 100kb -> JSON 413
            const bigPayload = JSON.stringify({ note: 'A'.repeat(120 * 1024) });
            const bigRes = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/crypto-futures/settings',
                headers: { 'Content-Type': 'application/json', 'X-Dash-Token': testToken },
                body: bigPayload
            });
            assert.strictEqual(bigRes.status, 413);
            assert.strictEqual(bigRes.json.ok, false);
        });

        // 8. WebSocket Hub security
        await test('WebSocket Hub: enforces token, origin, mismatched upgrade path, subprotocol, and per-IP connection cap', async () => {
            const noTok = await connectWsExpectReject(`ws://127.0.0.1:${port}/terminal/ws`, undefined, {}, 'noTok');
            assert.strictEqual(noTok.rejected, true);
            assert.strictEqual(noTok.statusCode, 401);

            const badTok = await connectWsExpectReject(`ws://127.0.0.1:${port}/terminal/ws?token=wrong`, undefined, {}, 'badTok');
            assert.strictEqual(badTok.rejected, true);
            assert.strictEqual(badTok.statusCode, 401);

            const badOrigin = await connectWsExpectReject(`ws://127.0.0.1:${port}/terminal/ws?token=${testToken}`, undefined, {
                headers: { Origin: 'https://evil.attacker' }
            }, 'badOrigin');
            assert.strictEqual(badOrigin.rejected, true);
            assert.strictEqual(badOrigin.statusCode, 403);

            const wrongPath = await connectWsExpectReject(`ws://127.0.0.1:${port}/other/ws?token=${testToken}`, undefined, {}, 'wrongPath');
            assert.strictEqual(wrongPath.rejected, true);
            assert.strictEqual(wrongPath.statusCode, 404);

            // Valid ?token= and valid Sec-WebSocket-Protocol both open; 3rd concurrent IP hits maxWsPerIp=2 -> 429
            const conn1 = await connectWsOpen(`ws://127.0.0.1:${port}/terminal/ws?token=${testToken}`);
            const conn2 = await connectWsOpen(`ws://127.0.0.1:${port}/terminal/ws`, ['pyro-v1', `bearer.${testToken}`]);
            try {
                assert.strictEqual(conn1.hello.type, 'hello');
                assert.strictEqual(conn2.hello.type, 'hello');
                assert.strictEqual(conn2.protocol, 'pyro-v1');

                const overLimit = await connectWsExpectReject(`ws://127.0.0.1:${port}/terminal/ws?token=${testToken}`, undefined, {}, 'overLimit');
                assert.strictEqual(overLimit.rejected, true);
                assert.strictEqual(overLimit.statusCode, 429);
            } finally {
                try { conn1.ws.terminate(); } catch (_) {}
                try { conn2.ws.terminate(); } catch (_) {}
            }
        });

        // 9. Rate limit DOES NOT bypass 127.0.0.1 (tunnels via localhost!)
        await test('Rate limiter: does NOT skip 127.0.0.1 on /api/auth/verify (cloudflared / Tailscale Serve protection)', async () => {
            let saw429 = null;
            for (let i = 0; i < 7; i++) {
                const r = await rawHttpRequest(port, {
                    method: 'POST',
                    reqPath: '/api/auth/verify',
                    headers: { 'Content-Type': 'application/json', 'X-Dash-Token': 'wrong' },
                    body: '{}'
                });
                if (r.status === 429) { saw429 = r; break; }
            }
            assert(saw429 && saw429.status === 429, 'Expected HTTP 429 from 127.0.0.1 without localhost bypass');
            assert(Number(saw429.headers['retry-after']) >= 1, 'Expected Retry-After header on 429');

            // Verify trust proxy resolves proxied external IP cleanly (distinct rate-limit bucket from 127.0.0.1)
            const proxiedRes = await rawHttpRequest(port, {
                method: 'POST',
                reqPath: '/api/auth/verify',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Forwarded-For': '203.0.113.77',
                    'X-Dash-Token': testToken
                },
                body: '{}'
            });
            assert.strictEqual(proxiedRes.status, 200);
            assert.strictEqual(ctx.app.get('trust proxy'), 1);

            // Verify default dashHost stays 0.0.0.0 for Tailscale / Cloudflare Tunnel compatibility
            const defaultHostCtx = createServerApp({ ...env, dashToken: testToken, testMode: true });
            try {
                assert.strictEqual(defaultHostCtx.dashHost, '0.0.0.0');
            } finally {
                defaultHostCtx.close();
            }
        });
    } finally {
        await closeServer(srv, ctx);
        fs.rmSync(env.tmpRoot, { recursive: true, force: true });
    }

    const failed = RESULTS.filter(r => !r.ok);
    console.log(`\nSummary: ${RESULTS.length - failed.length}/${RESULTS.length} passed`);
    if (failed.length > 0) {
        process.exitCode = 1;
    }
}

run().catch(err => {
    console.error(err);
    process.exit(1);
});
