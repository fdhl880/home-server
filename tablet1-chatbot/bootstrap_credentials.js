/**
 * BOOTSTRAP CREDENTIALS MODULE (ZERO-SETUP SERVER INITIALIZER)
 * Automatically unpacks preconfigured environment configurations and Pluang OAuth tokens
 * on first startup if .env or tokens.json are missing.
 */
const fs = require('fs');
const path = require('path');

function bootstrapCredentials() {
    const rootDir = __dirname;
    const pluangDir = path.join(rootDir, 'pluang-bot');

    const ENV1_B64 = "IyA9PT0gQkxPT01CRVJHIFRFUk1JTkFMIChOb2RlLmpzIC0gUG9ydCA0MDAwKSA9PT0KUE9SVD00MDAwCkdFTUlOSV9BUElfS0VZPUFRLkFiOFJONkplc09laUViNVZxOThFWVF3TW9jTWg3TTZ5bl9LcmVoUkRHTVFnVUdWaWh3CkdST1FfQVBJX0tFWT1nc2tfbGF1UzMwREdYYU94ZTdLSEZ4S1pXR2R5YjNGWXRrYzcwWDhGYVVHMXlXektoQlo1WjRKagpPUEVOUk9VVEVSX0FQSV9LRVk9c2stb3ItdjEtMGQzMmI2MWZjOTM4ODRjNzdhMjYxMWM0MzZiN2FmZjlhYmQ3ZjdiZWZkNzQ4Mzg4MzdiZDhiMGQ2ZjE0NGVhNgoKIyA9PT0gUExVQU5HIEJPVCAoUHl0aG9uIC0gUG9ydCA1MDAwKSA9PT0KUExVQU5HX1BPUlQ9NTAwMApURUxFR1JBTV9CT1RfVE9LRU49ODgyOTUzNTQyOTpBQUhGSE01NlJETkFkNy1heDZEZC0zVjNnOU9aRWxlWWk1TQpBSV9QUk9WSURFUj1ncm9xCkdST1FfTU9ERUw9b3BlbmFpL2dwdC1vc3MtMTIwYgpPUEVOUk9VVEVSX01PREVMPW1pbmltYXgvbWluaW1heC1tMy4xLWZsYXNoOmZyZWUK";
    const ENV2_B64 = "T1BFTlJPVVRFUl9BUElfS0VZPXNrLW9yLXYxLWM0OWIzNmI2MDlkYjVlOWFiMDM4MTRmM2Y5ZjgyNTIzNzc2NTZhMWFmMDA0ZDZmOTJjOTFmNzZmZWQxMDVhMmYKT1BFTlJPVVRFUl9NT0RFTD1taW5pbWF4L21pbmltYXgtbTMuMS1mbGFzaDpmcmVlCkdST1FfQVBJX0tFWT1nc2tfbGF1UzMwREdYYU94ZTdLSEZ4S1pXR2R5YjNGWXRrYzcwWDhGYVVHMXlXektoQlo1WjRKagpHUk9RX01PREVMPW9wZW5haS9ncHQtb3NzLTEyMGIKVEVMRUdSQU1fQk9UX1RPS0VOPTg4Mjk1MzU0Mjk6QUFIRkhNNTZSRE5BZDctYXg2RGQtM1YzZzlPWkVsZVlpNU0KQUlfUFJPVklERVI9Z3JvcQo=";
    const TOK_B64 = "ew0KICAiYWNjZXNzX3Rva2VuIjogImQzNnpvOGZ1QVJBbkVybV9uaWRXV000YTN6ajVaMzlzYUN5SEJiRzZDQzgiLA0KICAidG9rZW5fdHlwZSI6ICJCZWFyZXIiLA0KICAiZXhwaXJlc19pbiI6IDM2MDAsDQogICJzY29wZSI6ICJtYXJrZXQ6cmVhZCBwb3J0Zm9saW86cmVhZCB0cmFkZTp3cml0ZSIsDQogICJyZWZyZXNoX3Rva2VuIjogIk9rMnhodjlDd1B1WXc1UHZFbjFzNlNQR3EzT0FJSkU1eV9meURpN2I3NXciLA0KICAiYWNxdWlyZWRfYXQiOiAxNzkyNDIzODM4LjI4Mjg1OTYNCn0=";

    const env1Path = path.join(rootDir, '.env');
    if (!fs.existsSync(env1Path)) {
        try {
            fs.writeFileSync(env1Path, Buffer.from(ENV1_B64, 'base64').toString('utf8'), 'utf8');
            console.log('[BOOTSTRAP] Created root .env successfully.');
        } catch (e) {}
    }

    if (fs.existsSync(pluangDir)) {
        const env2Path = path.join(pluangDir, '.env');
        if (!fs.existsSync(env2Path)) {
            try {
                fs.writeFileSync(env2Path, Buffer.from(ENV2_B64, 'base64').toString('utf8'), 'utf8');
                console.log('[BOOTSTRAP] Created pluang-bot/.env successfully.');
            } catch (e) {}
        }

        const tokPath = path.join(pluangDir, 'tokens.json');
        if (!fs.existsSync(tokPath)) {
            try {
                fs.writeFileSync(tokPath, Buffer.from(TOK_B64, 'base64').toString('utf8'), 'utf8');
                console.log('[BOOTSTRAP] Created pluang-bot/tokens.json successfully.');
            } catch (e) {}
        }
    }
}

module.exports = bootstrapCredentials;
