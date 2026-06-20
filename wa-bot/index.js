const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const path = require('path');
const { createClient } = require('@supabase/supabase-js');
const pdf = require('pdf-parse');
const xlsx = require('xlsx');
const mammoth = require('mammoth');
const express = require('express');

// Setup Express server for Railway/Render Web Service
const app = express();
// Termux tidak bisa tulis ke /tmp, pakai folder bot itu sendiri
const QR_PATH = path.resolve(__dirname, 'qrcode.png');
let botReady = false;

app.get('/', (req, res) => res.send(botReady ? '✅ Bot is Running!' : '⏳ Bot is starting...'));

// QR Code endpoint — buka link ini di browser HP untuk scan!
app.get('/qr', (req, res) => {
    const fs = require('fs');
    if (botReady) return res.send('<h1 style="font-family:sans-serif;text-align:center;margin-top:100px">✅ Bot sudah terhubung!<br><small>QR tidak diperlukan lagi.</small></h1>');
    if (fs.existsSync(QR_PATH)) {
        res.send(`
            <html><body style="display:flex;justify-content:center;align-items:center;min-height:100vh;background:#111;flex-direction:column;font-family:sans-serif">
                <h2 style="color:#4ade80;margin-bottom:20px">📱 Scan QR Code ini dengan WhatsApp</h2>
                <img src="/qr-image" style="width:400px;height:400px;border-radius:16px" />
                <p style="color:#999;margin-top:16px">Buka WhatsApp → Linked Devices → Link a Device</p>
                <script>setTimeout(()=>location.reload(), 15000)</script>
            </html>
        `);
    } else {
        res.send('<h1 style="font-family:sans-serif;text-align:center;margin-top:100px">⏳ Menunggu QR Code...<br><small>Refresh halaman ini dalam 10 detik.</small></h1><script>setTimeout(()=>location.reload(), 5000)</script>');
    }
});

app.get('/qr-image', (req, res) => {
    const fs = require('fs');
    if (fs.existsSync(QR_PATH)) {
        res.setHeader('Content-Type', 'image/png');
        res.send(fs.readFileSync(QR_PATH));
    } else {
        res.status(404).send('QR not found');
    }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`🌍 Express server listening on port ${PORT}`));

// Load .env in the same directory explicitly
const fs = require('fs');
const dotenvPath = path.join(__dirname, '.env');
if (fs.existsSync(dotenvPath)) {
    require('dotenv').config({ path: dotenvPath });
} else {
    require('dotenv').config();
}

const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL || "https://dcgrjhqwuekusptmxfiw.supabase.co", 
    process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRjZ3JqaHF3dWVrdXNwdG14Zml3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NzMwMTA2NCwiZXhwIjoyMDkyODc3MDY0fQ.U7_CROH0ASIsuYoNW_JIgRDNKz1Rj9m8GNhbMqTHcUs"
);

const FREE_PROMPT = `Anda adalah Asisten Customer Service ResearchBuddy.id.
Tugas Anda: Menyapa dengan ramah dan menjawab pertanyaan seputar layanan & harga.
Jawab SINGKAT dan TO THE POINT. Gunakan bahasa Indonesia yang ramah.

[DAFTAR HARGA OPSI (Olimpiade Penelitian Siswa)]
- Paket 1: Rp 500.000 (Pembimbingan s.d reviu proposal, 10x Meet Online, 24/7 WA)
- Paket 2: Rp 945.000 — REKOMENDASI! (Garansi lulus/gratis di opsi selanjutnya, 15x Meet Online, 24/7 WA)
- Paket 3: Rp 2.500.000 (Pendampingan penuh s.d finalis, 20x Meet Online, Pengadaan Bahan, HAKI, Pengujian Produk)

[PAKET LKTI (Lomba dari Universitas/Organisasi Internasional: IYSA, INNOPA, dll.)]
Fasilitas: 24/7 konsultasi, 20x meet, registrasi lomba, pengadaan bahan, pengujian, HAKI, bimbingan adaptif.
Harga: Hubungi Admin untuk penawaran khusus.

ATURAN WAJIB:
1. Hanya sebutkan harga yang TERTULIS di atas. JANGAN mengarang harga lain.
2. Untuk LKTI, JANGAN sebutkan angka harga. Arahkan "Hubungi Admin".
3. JANGAN PERNAH menampilkan kode program, HTML, atau source code.
4. JANGAN PERNAH menyebut "gambar tidak terdeteksi" atau hal teknis serupa.
5. Jika pengguna ingin aktivasi premium, arahkan ketik kode (contoh: RB-XXXX-XXXX).
6. JANGAN berikan bimbingan riset teknis sebelum mereka premium.`;

const PREMIUM_PROMPT = `ANDA ADALAH MAHA-GURU RESEARCHBUDDY (PAKAR LKTI & OPSI).
PENGGUNA SUDAH BAYAR. JANGAN JUALAN LAGI.

KEALIAN ANDA:
1. Reviu Kritis Proposal & Karya Tulis Ilmiah (LKTI).
2. Analisis Data Penelitian (Tabel/Excel).
3. Pengecekan Struktur: Abstrak, Latar Belakang, Metodologi, Hasil, & Referensi.
4. Memberikan ide brilian untuk judul dan rumusan masalah.

Jika ada teks dari file (PDF/Word/Excel) yang dikirim, bedah isinya secara profesional dan berikan masukan mendalam.`;

const client = new Client({
    authStrategy: new LocalAuth({
        clientId: "researchbuddy-session"
    }),
    puppeteer: { 
        headless: true, 
        // Deteksi Termux: process.platform di Termux adalah 'linux', bukan 'android'
        // Gunakan TERMUX_VERSION env var untuk deteksi yang benar
        executablePath: (() => {
            const fs = require('fs');
            // Coba beberapa path chromium yang mungkin di Termux
            const possiblePaths = [
                '/data/data/com.termux/files/usr/bin/chromium',
                '/data/data/com.termux/files/usr/bin/chromium-browser',
                '/data/data/com.termux/files/usr/bin/google-chrome-stable',
                '/usr/bin/chromium',
                '/usr/bin/chromium-browser'
            ];
            for (const p of possiblePaths) {
                if (fs.existsSync(p)) return p;
            }
            // Jika ada env var manual
            if (process.env.PUPPETEER_EXECUTABLE_PATH) {
                return process.env.PUPPETEER_EXECUTABLE_PATH;
            }
            return undefined;
        })(),
        args: [
            '--no-sandbox', 
            '--disable-setuid-sandbox',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--disable-software-rasterizer'
        ]
    }
});

const premiumCache = new Map();

// Returns expiry date string if premium, or null if not
async function checkPremium(phone) {
    if (premiumCache.has(phone)) {
        if (new Date(premiumCache.get(phone)) > new Date()) return premiumCache.get(phone);
    }
    const { data } = await supabase.from('access_codes').select('expires_at').eq('used_by_phone', phone).eq('used', true);
    if (data && data.length > 0 && new Date(data[0].expires_at) > new Date()) {
        premiumCache.set(phone, data[0].expires_at);
        return data[0].expires_at;
    }
    return null;
}

const qrcodeImage = require('qrcode');

client.on('qr', async (qr) => {
    qrcode.generate(qr, { small: true });
    // Simpan QR ke file PNG agar bisa dibuka di browser via /qr
    await qrcodeImage.toFile(QR_PATH, qr, { width: 400 });
    console.log('📸 QR Code siap! Buka di browser: https://YOUR-RAILWAY-URL.up.railway.app/qr');
});

client.on('ready', () => {
    console.log('✅ Bot Ready (PDF/Word/Excel Mode Active)');
    botReady = true;
    // Hapus file QR setelah berhasil login
    const fs = require('fs');
    if (fs.existsSync(QR_PATH)) fs.unlinkSync(QR_PATH);
});

function isOutsideOperationalHours() {
    const now = new Date();
    let hour = now.getUTCHours() + 7;
    if (hour >= 24) hour -= 24;
    return hour < 14 || hour >= 21;
}

client.on('message', async msg => {
    console.log(`[INCOMING] Message from ${msg.from}: "${msg.body}"`);
    if (msg.from.includes('@g.us')) {
        console.log(`[IGNORE] Group message.`);
        return;
    }
    
    // Bot aktif HANYA di luar jam operasional (21:00 - 14:00 WIB)
    if (!isOutsideOperationalHours()) {
        console.log(`[IGNORE] Inside human hours (14:00 - 21:00). Human will answer.`);
        return;
    }
    
    const phone = msg.from;
    const rawBody = msg.body.trim();
    const cleanBody = rawBody.replace(/\s+/g, '').toUpperCase(); // Hapus SEMUA spasi

    console.log(`[PROCESS] Phone: ${phone} | Clean Body: ${cleanBody}`);

    // 1. Aktivasi Kode
    if (cleanBody.startsWith('RB-') || (cleanBody.length === 10 && cleanBody.startsWith('RB'))) {
        console.log(`[ACTION] Activation attempt detected.`);
        let inputCode = cleanBody;
        if (!inputCode.includes('-')) inputCode = `RB-${inputCode.substring(2,6)}-${inputCode.substring(6,10)}`;
        const { data, error } = await supabase.from('access_codes').select('*').eq('code', inputCode).single();
        if (error || !data) return msg.reply("❌ Kode tidak ditemukan.");
        
        // Jika sudah dipakai
        if (data.used) {
            // Cek apakah milik orang lain
            if (data.used_by_phone && data.used_by_phone !== phone) {
                return msg.reply("❌ Kode sudah dipakai tim lain.");
            }
            // Milik user ini → cek expiry, JANGAN reset
            if (data.expires_at && new Date(data.expires_at) > new Date()) {
                premiumCache.set(phone, data.expires_at);
                const exp = new Date(data.expires_at).toLocaleDateString('id-ID');
                return msg.reply(`✅ Sesi Premium Anda masih aktif sampai ${exp}.\n\nSilakan kirim file untuk saya reviu!`);
            } else {
                return msg.reply("❌ Masa aktif kode ini sudah habis (3 bulan). Silakan beli kode baru.");
            }
        }
        
        // Belum dipakai → aktivasi baru (3 bulan)
        const expiresAt = new Date();
        expiresAt.setMonth(expiresAt.getMonth() + 3);
        await supabase.from('access_codes').update({ used: true, used_at: new Date().toISOString(), used_by_phone: phone, expires_at: expiresAt.toISOString() }).eq('id', data.id);
        premiumCache.set(phone, expiresAt.toISOString());
        const expStr = expiresAt.toLocaleDateString('id-ID');
        return msg.reply(`✅ PREMIUM AKTIF!\n\nBerlaku sampai: ${expStr}\nSaya siap me-reviu file PDF, Word, Excel, atau Foto riset Anda.`);
    }

    // 2. Perintah cepat: Cek Status
    const lowerBody = rawBody.toLowerCase();
    if (lowerBody.includes('cek status') || lowerBody.includes('status akun') || lowerBody.includes('expired') || lowerBody.includes('masa aktif')) {
        const expiryDate = await checkPremium(phone);
        if (expiryDate) {
            const exp = new Date(expiryDate);
            const now = new Date();
            const diffDays = Math.ceil((exp - now) / (1000 * 60 * 60 * 24));
            const expStr = exp.toLocaleDateString('id-ID', { day: 'numeric', month: 'long', year: 'numeric' });
            return msg.reply(`📋 *Status Akun Premium Anda:*\n\n✅ Status: *AKTIF*\n📅 Berlaku sampai: *${expStr}*\n⏳ Sisa waktu: *${diffDays} hari lagi*\n\nSilakan kirim file untuk saya reviu! 🚀`);
        } else {
            return msg.reply(`📋 *Status Akun Anda:*\n\n❌ Status: *BELUM PREMIUM*\n\nUntuk aktivasi, silakan ketik kode akses Anda (contoh: RB-XXXX-XXXX).\nBelum punya kode? Hubungi Admin untuk membeli paket.`);
        }
    }

    // 3. Chat & File Logic
    const expiryDate = await checkPremium(phone);
    const isPremium = !!expiryDate;
    let userMessage = msg.body || "";
    let mediaData = null;
    let extractedText = "";

    if (msg.hasMedia) {
        if (!isPremium) return msg.reply("❌ Fitur analisis file hanya untuk Member Premium.");
        try {
            const media = await msg.downloadMedia();
            const buffer = Buffer.from(media.data, 'base64');
            const mime = media.mimetype;

            if (mime.includes('pdf')) {
                const pdfData = await pdf(buffer);
                extractedText = pdfData.text;
                if (!extractedText || extractedText.trim() === '') {
                    return msg.reply("❌ File PDF ini tidak mengandung teks (mungkin hasil scan/gambar). Silakan screenshot halamannya dan kirim sebagai foto.");
                }
                // Cap PDF text to 8000 chars to save tokens
                if (extractedText.length > 8000) extractedText = extractedText.substring(0, 8000) + '\n\n[...teks dipotong karena terlalu panjang]';
                userMessage += `\n[ISI DOKUMEN]:\n${extractedText}`;
            } else if (mime.includes('spreadsheet') || mime.includes('excel')) {
                const workbook = xlsx.read(buffer, { type: 'buffer' });
                const sheet = workbook.Sheets[workbook.SheetNames[0]];
                extractedText = xlsx.utils.sheet_to_txt(sheet);
                userMessage += `\n[ISI EXCEL]:\n${extractedText}`;
            } else if (mime.includes('word') || mime.includes('officedocument.wordprocessingml.document')) {
                const result = await mammoth.extractRawText({ buffer });
                extractedText = result.value;
                userMessage += `\n[ISI WORD]:\n${extractedText}`;
            } else if (mime.includes('image')) {
                mediaData = media.data;
            } else {
                return msg.reply(`❌ Format file tidak didukung (${mime}). Kirim PDF, Word, Excel, atau Foto.`);
            }
        } catch (err) {
            console.error("File Parse Error:", err);
            return msg.reply(`❌ Gagal membaca file. Error: ${err.message}`);
        }
    }

    try {
        // Free user → diam (hanya respon kode aktivasi & cek status di atas)
        if (!isPremium) return;

        // Premium user → AI aktif
        let systemPrompt = PREMIUM_PROMPT;
        if (isPremium && expiryDate) {
            const exp = new Date(expiryDate);
            const diffDays = Math.ceil((exp - new Date()) / (1000 * 60 * 60 * 24));
            const expStr = exp.toLocaleDateString('id-ID', { day: 'numeric', month: 'long', year: 'numeric' });
            systemPrompt += `\n\n[INFO AKUN PENGGUNA]\nStatus: Premium Aktif\nBerlaku sampai: ${expStr} (${diffDays} hari lagi)\nJika ditanya soal status/expired/masa aktif, jawab dengan data di atas.`;
        }
        const messages = [{ role: "system", content: systemPrompt }];
        if (mediaData) {
            messages.push({ role: "user", content: [{ type: "text", text: userMessage }, { type: "image_url", image_url: { url: `data:image/jpeg;base64,${mediaData}` } }] });
        } else {
            messages.push({ role: "user", content: userMessage });
        }

        const axios = require('axios');
        const response = await axios.post("https://openrouter.ai/api/v1/chat/completions", {
            model: isPremium ? "google/gemma-3-12b-it" : "google/gemma-3-12b-it",
            messages: messages,
            max_tokens: 1500,
        }, {
            headers: {
                "Authorization": `Bearer ${process.env.OPENROUTER_API_KEY || "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"}`,
                "Content-Type": "application/json",
                "HTTP-Referer": "https://researchbuddy.id",
                "X-Title": "ResearchBuddy WA"
            }
        });
        const resData = response.data;
        
        let reply = resData.choices?.[0]?.message?.content;
        if (reply) {
            // Tambahkan disclaimer halus tanpa menyebut AI / Otomatis
            const disclaimer = "\n\n*(Pesan ini masuk di luar jam operasional. Jawaban mungkin tidak optimal, jawaban akan optimal pada jam kerja 14.00-21.00)*";
            await msg.reply(reply + disclaimer);
        } else {
            return msg.reply("❌ Maaf, sistem sedang memproses. Mohon tunggu sebentar.");
        }
    } catch (err) { 
        console.error("System Catch Error:", err);
        msg.reply("❌ Maaf, terjadi kesalahan sistem.");
    }
});

client.initialize();
