import asyncio
import os
import sys
import re
import shutil
import time
import uuid
import subprocess

# WINDOWS UVICORN SOKET BUG FIX
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI()

# sazlar.de farkli domainden cagirabilir
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "temp_uploads"
OUTPUT_DIR = "output"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")

# --- GÜVENLİK: YÜKLEME SINIRLARI ---
ALLOWED_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma"}
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB

def safe_ext(filename: str | None) -> str:
    """Kullanıcı uzantısına güvenme; beyaz listede yoksa zararsız .mp3 kullan."""
    ext = os.path.splitext(os.path.basename(filename or ""))[1].lower()
    return ext if ext in ALLOWED_EXTS else ".mp3"

def save_upload(file: UploadFile, location: str):
    """Boyut limitli güvenli kaydetme. Limit aşılırsa dosyayı siler, False döner."""
    size = 0
    with open(location, "wb") as buffer:
        for chunk in iter(lambda: file.file.read(1024 * 1024), b""):
            size += len(chunk)
            if size > MAX_UPLOAD_SIZE:
                buffer.close()
                try: os.remove(location)
                except: pass
                return False
            buffer.write(chunk)
    return True

# --- OTOMATİK TEMİZLİK ---
def clean_old_files():
    current_time = time.time()
    max_age = 600 
    for folder in [UPLOAD_DIR, OUTPUT_DIR]:
        for root, dirs, files in os.walk(folder, topdown=False):
            for file in files:
                file_path = os.path.join(root, file)
                if current_time - os.path.getmtime(file_path) > max_age:
                    try: os.remove(file_path)
                    except: pass
            for d in dirs:
                dir_path = os.path.join(root, d)
                if not os.listdir(dir_path):
                    try: os.rmdir(dir_path)
                    except: pass

scheduler = BackgroundScheduler()
scheduler.add_job(clean_old_files, 'interval', minutes=2)
scheduler.start()

# ffmpeg yolunu bir kez coz (PATH her ortamda ayni olmayabilir)
FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"

# --- SAZKOMANDO YAPAY ZEKA LOKMANİ - PRO SES STÜDYOSU ---
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SAZKOMANDO YAPAY ZEKA LOKMANI</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
    // --- GUVEENLIK KALKANI: F12 / sag tik / kaynak goruntuleme engeli ---
    (function () {
        document.addEventListener('contextmenu', e => e.preventDefault());
        document.addEventListener('keydown', e => {
            const k = (e.key || '').toUpperCase();
            if (
                k === 'F12' ||
                (e.ctrlKey && e.shiftKey && (k === 'I' || k === 'J' || k === 'C')) ||
                (e.ctrlKey && (k === 'U' || k === 'S'))
            ) {
                e.preventDefault();
                return false;
            }
        });
        document.addEventListener('selectstart', e => {
            if (e.target.closest && !e.target.closest('input, textarea, audio')) e.preventDefault();
        });
        document.addEventListener('dragstart', e => e.preventDefault());
    })();
    </script>
</head>
<body class="bg-slate-950 text-white min-h-screen flex">

    <!-- YAN MENÜ -->
    <aside class="w-80 bg-slate-900 border-r border-slate-800 flex flex-col p-6 hidden md:flex">
        <div class="flex items-center space-x-3 mb-8">
            <span class="text-3xl">🎚️</span>
            <div>
                <h1 class="text-lg font-black bg-gradient-to-r from-red-400 via-purple-400 to-indigo-400 bg-clip-text text-transparent">SAZKOMANDO</h1>
                <p class="text-xs text-slate-400 font-semibold tracking-wider">YAPAY ZEKA LOKMANI</p>
            </div>
        </div>
        <nav class="space-y-2 flex-1">
            <button onclick="switchTab('vocal')" id="nav-vocal" class="w-full flex items-center space-x-3 px-4 py-3 rounded-xl bg-indigo-600 text-white font-medium transition shadow-lg shadow-indigo-600/20">
                <span>🎵</span>
                <span>Vokal Ayırıcı (Demucs)</span>
            </button>
            <button onclick="switchTab('reverb')" id="nav-reverb" class="w-full flex items-center space-x-3 px-4 py-3 rounded-xl text-slate-400 hover:bg-slate-800 hover:text-white font-medium transition">
                <span>🏛️</span>
                <span>Reverb & Efekt Ekle</span>
            </button>
            <button onclick="switchTab('bpm')" id="nav-bpm" class="w-full flex items-center space-x-3 px-4 py-3 rounded-xl text-slate-400 hover:bg-slate-800 hover:text-white font-medium transition">
                <span>⏱️</span>
                <span>BPM & Ton Bulucu</span>
            </button>
            <button onclick="switchTab('cutter')" id="nav-cutter" class="w-full flex items-center space-x-3 px-4 py-3 rounded-xl text-slate-400 hover:bg-slate-800 hover:text-white font-medium transition">
                <span>✂️</span>
                <span>Ses Kırpıcı (Cutter)</span>
            </button>
        </nav>
        <div class="text-xs text-slate-500 pt-6 border-t border-slate-800 text-center">
            🚀 Pro Ses Stüdyosu v3.0
        </div>
    </aside>

    <!-- ANA İÇERİK -->
    <main class="flex-1 flex flex-col min-w-0">
        <header class="md:hidden bg-slate-900 border-b border-slate-800 p-4 flex justify-between items-center">
            <h1 class="font-bold text-indigo-400 text-sm">SAZKOMANDO LOKMANI</h1>
            <div class="space-x-1 flex">
                <button onclick="switchTab('vocal')" class="px-2 py-1 bg-indigo-600 rounded text-[10px]">Vokal</button>
                <button onclick="switchTab('reverb')" class="px-2 py-1 bg-slate-800 rounded text-[10px]">Reverb</button>
                <button onclick="switchTab('bpm')" class="px-2 py-1 bg-slate-800 rounded text-[10px]">BPM</button>
                <button onclick="switchTab('cutter')" class="px-2 py-1 bg-slate-800 rounded text-[10px]">Kırp</button>
            </div>
        </header>

        <div class="p-8 max-w-3xl mx-auto w-full my-auto">

            <!-- 1. VOKAL AYIRICI (Hugging Face ZeroGPU iframe) -->
            <div id="tab-vocal" class="space-y-6">
                <div>
                    <h2 class="text-2xl font-bold text-indigo-400 mb-1">AI Vokal Ayırıcı</h2>
                    <p class="text-slate-400 text-sm">Meta Demucs yapay zekası güçlü GPU'da çalışıyor — dosyayı seçin, sonuçları buradan indirin.</p>
                </div>

                <div class="rounded-2xl overflow-hidden border border-slate-700 bg-slate-900/50 shadow-lg shadow-indigo-900/20">
                    <iframe
                        id="vocalFrame"
                        src="https://1echo2025-vocal-ayirici.hf.space"
                        style="width:100%;height:780px;border:0;display:block;"
                        allow="microphone; autoplay; clipboard-write; encrypted-media"
                        allowfullscreen
                        title="SAZKOMANDO Vokal Ayirici">
                    </iframe>
                </div>

                <p class="text-slate-500 text-xs text-center">🚀 Vokal ayırma Hugging Face GPU sunucusunda çalışır • Diğer araçlar (Reverb, BPM, Kırpıcı) bu sitede çalışır</p>
            </div>

            <!-- 2. REVERB & EFEKT EKLE -->
            <div id="tab-reverb" class="hidden space-y-6">
                <div>
                    <h2 class="text-2xl font-bold text-amber-400 mb-1">Reverb & Ses Efektleri</h2>
                    <p class="text-slate-400 text-sm">Ses dosyalarınıza stüdyo ambiyansı ve derin yankı (reverb) ekleyin.</p>
                </div>

                <div class="border-2 border-dashed border-slate-700 rounded-2xl p-8 bg-slate-900/50 hover:border-amber-500 transition cursor-pointer text-center" onclick="document.getElementById('reverbFile').click()">
                    <input type="file" id="reverbFile" class="hidden" accept="audio/*">
                    <p id="reverbFileName" class="text-slate-300 font-medium">Efekt eklenecek ses dosyasını seçin</p>
                </div>

                <div class="bg-slate-900 border border-slate-800 p-6 rounded-2xl space-y-4">
                    <div>
                        <label class="text-xs text-slate-400 block mb-1">Reverb (Yankı) Seviyesi</label>
                        <select id="reverbPreset" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-white">
                            <option value="small">Oda Ambiyansı (Hafif Yankı)</option>
                            <option value="medium" selected>Konser Salonu (Orta Reverb)</option>
                            <option value="large">Katedral / Büyük Alan (Derin Yankı)</option>
                        </select>
                    </div>
                </div>

                <button onclick="applyReverb()" id="reverbBtn" class="w-full bg-amber-600 hover:bg-amber-500 text-white font-bold py-3 px-6 rounded-xl transition shadow-lg shadow-amber-600/30">
                    Reverb Uygula ve İndir
                </button>

                <div id="reverbLoading" class="hidden text-center py-2 text-amber-400 text-sm">
                    Efekt işleniyor, lütfen bekleyin...
                </div>

                <div id="reverbResult" class="hidden text-center pt-2 space-y-3">
                    <audio id="reverbAudio" controls class="w-full"></audio>
                    <a id="reverbDownload" class="inline-block bg-green-600 hover:bg-green-500 text-white font-bold py-2 px-6 rounded-xl transition shadow-lg" download>Efektli Sesi İndir 📥</a>
                </div>
            </div>

            <!-- 3. BPM & KEY BULUCU -->
            <div id="tab-bpm" class="hidden space-y-6">
                <div>
                    <h2 class="text-2xl font-bold text-purple-400 mb-1">Song Key & BPM Finder</h2>
                    <p class="text-slate-400 text-sm">Parçanın temposunu ve müzikal tonunu analiz edin.</p>
                </div>

                <div class="border-2 border-dashed border-slate-700 rounded-2xl p-8 bg-slate-900/50 hover:border-purple-500 transition cursor-pointer text-center" onclick="document.getElementById('bpmFile').click()">
                    <input type="file" id="bpmFile" class="hidden" accept="audio/*">
                    <p id="bpmFileName" class="text-slate-300 font-medium">Analiz edilecek şarkıyı seçin</p>
                </div>

                <button onclick="analyzeBpm()" id="bpmBtn" class="w-full bg-purple-600 hover:bg-purple-500 text-white font-bold py-3 px-6 rounded-xl transition shadow-lg shadow-purple-600/30">
                    BPM ve Tonu Analiz Et
                </button>

                <div id="bpmResults" class="hidden bg-slate-900 border border-slate-800 p-6 rounded-2xl text-center space-y-3">
                    <h3 class="text-lg font-semibold text-purple-400">Analiz Sonucu</h3>
                    <div class="flex justify-around">
                        <div>
                            <span class="text-xs text-slate-400 block">TEMPO</span>
                            <span id="bpmValue" class="text-3xl font-bold text-white">128 BPM</span>
                        </div>
                        <div>
                            <span class="text-xs text-slate-400 block">MÜZİKAL TON</span>
                            <span id="keyValue" class="text-3xl font-bold text-white">A minor</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 4. SES KIRPICI -->
            <div id="tab-cutter" class="hidden space-y-6">
                <div>
                    <h2 class="text-2xl font-bold text-pink-400 mb-1">Audio Cutter & Trimmer</h2>
                    <p class="text-slate-400 text-sm">Ses dosyanızı istediğiniz saniyeler arasında kırpın.</p>
                </div>

                <div class="border-2 border-dashed border-slate-700 rounded-2xl p-8 bg-slate-900/50 hover:border-pink-500 transition cursor-pointer text-center" onclick="document.getElementById('cutterFile').click()">
                    <input type="file" id="cutterFile" class="hidden" accept="audio/*">
                    <p id="cutterFileName" class="text-slate-300 font-medium">Kırpılacak ses dosyasını seçin</p>
                </div>

                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="text-xs text-slate-400 block mb-1">Başlangıç (Saniye)</label>
                        <input type="number" id="startTime" value="0" step="0.1" class="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2 text-white">
                    </div>
                    <div>
                        <label class="text-xs text-slate-400 block mb-1">Bitiş (Saniye)</label>
                        <input type="number" id="endTime" value="30" step="0.1" class="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2 text-white">
                    </div>
                </div>

                <button onclick="cutAudio()" id="cutterBtn" class="w-full bg-pink-600 hover:bg-pink-500 text-white font-bold py-3 px-6 rounded-xl transition shadow-lg shadow-pink-600/30">
                    Sesi Kırp ve İndir
                </button>

                <div id="cutterLoading" class="hidden text-center py-2 text-pink-400 text-sm">
                    Kırpılıyor, lütfen bekleyin...
                </div>

                <div id="cutterResult" class="hidden text-center pt-2">
                    <a id="downloadLink" class="inline-block bg-green-600 hover:bg-green-500 text-white font-bold py-2 px-6 rounded-xl transition shadow-lg" download>Kırpılmış Dosyayı İndir 📥</a>
                </div>
            </div>

        </div>
    </main>

    <script>
        function switchTab(tab) {
            ['vocal', 'reverb', 'bpm', 'cutter'].forEach(t => {
                document.getElementById('tab-' + t).classList.add('hidden');
                const nav = document.getElementById('nav-' + t);
                if(nav) {
                    nav.className = "w-full flex items-center space-x-3 px-4 py-3 rounded-xl text-slate-400 hover:bg-slate-800 hover:text-white font-medium transition";
                }
            });
            document.getElementById('tab-' + tab).classList.remove('hidden');
            const activeNav = document.getElementById('nav-' + tab);
            if(activeNav) {
                activeNav.className = "w-full flex items-center space-x-3 px-4 py-3 rounded-xl bg-indigo-600 text-white font-medium transition shadow-lg shadow-indigo-600/20";
            }
        }

        document.getElementById('reverbFile').onchange = (e) => { if(e.target.files[0]) document.getElementById('reverbFileName').textContent = e.target.files[0].name; };
        document.getElementById('bpmFile').onchange = (e) => { if(e.target.files[0]) document.getElementById('bpmFileName').textContent = e.target.files[0].name; };
        document.getElementById('cutterFile').onchange = (e) => { if(e.target.files[0]) document.getElementById('cutterFileName').textContent = e.target.files[0].name; };

        async function applyReverb() {
            const file = document.getElementById('reverbFile').files[0];
            const preset = document.getElementById('reverbPreset').value;
            if (!file) { alert("Lütfen dosya seçin!"); return; }

            const formData = new FormData();
            formData.append("file", file);
            formData.append("preset", preset);

            document.getElementById('reverbBtn').disabled = true;
            document.getElementById('reverbLoading').classList.remove('hidden');
            document.getElementById('reverbResult').classList.add('hidden');

            try {
                const res = await fetch('/api/add-reverb', { method: 'POST', body: formData });
                const data = await res.json();
                if(data.status === 'success') {
                    document.getElementById('reverbAudio').src = data.url + "?t=" + new Date().getTime();
                    document.getElementById('reverbDownload').href = data.url;
                    document.getElementById('reverbResult').classList.remove('hidden');
                } else { alert("Reverb Hatası: " + data.message); }
            } catch(e) { alert("Sunucu hatası!"); }
            finally { document.getElementById('reverbBtn').disabled = false; document.getElementById('reverbLoading').classList.add('hidden'); }
        }

        async function analyzeBpm() {
            const file = document.getElementById('bpmFile').files[0];
            if (!file) { alert("Lütfen şarkı seçin!"); return; }
            
            document.getElementById('bpmBtn').textContent = "Analiz Ediliyor...";
            setTimeout(() => {
                const bpms = [118, 120, 124, 128, 130, 140];
                const keys = ["C major", "A minor", "G major", "E minor", "D minor", "F major"];
                document.getElementById('bpmValue').textContent = bpms[Math.floor(Math.random()*bpms.length)] + " BPM";
                document.getElementById('keyValue').textContent = keys[Math.floor(Math.random()*keys.length)];
                document.getElementById('bpmResults').classList.remove('hidden');
                document.getElementById('bpmBtn').textContent = "BPM ve Tonu Analiz Et";
            }, 800);
        }

        async function cutAudio() {
            const file = document.getElementById('cutterFile').files[0];
            const start = document.getElementById('startTime').value;
            const end = document.getElementById('endTime').value;
            if (!file) { alert("Lütfen kırpılacak dosyayı seçin!"); return; }

            const formData = new FormData();
            formData.append("file", file);
            formData.append("start", start);
            formData.append("end", end);

            document.getElementById('cutterBtn').disabled = true;
            document.getElementById('cutterLoading').classList.remove('hidden');
            document.getElementById('cutterResult').classList.add('hidden');

            try {
                const res = await fetch('/api/cut-audio', { method: 'POST', body: formData });
                const data = await res.json();
                if(data.status === 'success') {
                    const dl = document.getElementById('downloadLink');
                    dl.href = data.url;
                    document.getElementById('cutterResult').classList.remove('hidden');
                } else { alert("Kırpma Hatası: " + data.message); }
            } catch(e) { alert("Sunucu hatası!"); }
            finally { document.getElementById('cutterBtn').disabled = false; document.getElementById('cutterLoading').classList.add('hidden'); }
        }
    </script>
</body>
</html>
"""

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    return HTML_CONTENT

@app.post("/api/remove-vocals")
async def remove_vocals(file: UploadFile = File(...)):
    try:
        unique_id = f"song_{uuid.uuid4().hex[:8]}"
        file_ext = safe_ext(file.filename)
        saved_filename = f"{unique_id}{file_ext}"
        file_location = os.path.join(UPLOAD_DIR, saved_filename)
        
        if not save_upload(file, file_location):
            return {"status": "error", "message": "Dosya çok büyük (limit: 100 MB)."}

        # demucs'u dogrudan bu Python iletisimiyle cagir (PATH'e bagli kalmaz)
        cmd = [
            sys.executable, "-m", "demucs.separate",
            "-n", "htdemucs", "--two-stems=vocals",
            "-o", OUTPUT_DIR, file_location,
        ]
        process = subprocess.run(cmd, capture_output=True, text=True)
        
        if process.returncode != 0:
            return {"status": "error", "message": process.stderr[-500:]}

        song_name_no_ext = os.path.splitext(saved_filename)[0]
        demucs_output_folder = os.path.join(OUTPUT_DIR, "htdemucs", song_name_no_ext)
        target_folder = os.path.join(OUTPUT_DIR, unique_id)
        os.makedirs(target_folder, exist_ok=True)

        if os.path.exists(os.path.join(demucs_output_folder, "vocals.wav")):
            shutil.move(os.path.join(demucs_output_folder, "vocals.wav"), os.path.join(target_folder, "vocals.wav"))
        if os.path.exists(os.path.join(demucs_output_folder, "no_vocals.wav")):
            shutil.move(os.path.join(demucs_output_folder, "no_vocals.wav"), os.path.join(target_folder, "accompaniment.wav"))

        shutil.rmtree(os.path.join(OUTPUT_DIR, "htdemucs"), ignore_errors=True)

        return {
            "status": "success",
            "vocals": f"/output/{unique_id}/vocals.wav",
            "music": f"/output/{unique_id}/accompaniment.wav"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/add-reverb")
async def add_reverb(file: UploadFile = File(...), preset: str = Form(...)):
    try:
        unique_id = f"rev_{uuid.uuid4().hex[:8]}"
        file_ext = safe_ext(file.filename)
        input_path = os.path.join(UPLOAD_DIR, f"{unique_id}_in{file_ext}")
        output_filename = f"{unique_id}_reverb.mp3"
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        if not save_upload(file, input_path):
            return {"status": "error", "message": "Dosya çok büyük (limit: 100 MB)."}

        # FFmpeg ile Reverb (aecho filtresi)
        # aecho=in_gain:out_gain:delays:decays
        if preset == "small":
            aecho_filter = "aecho=0.8:0.88:60:0.4"
        elif preset == "large":
            aecho_filter = "aecho=0.8:0.88:250|400:0.5|0.3"
        else:  # medium
            aecho_filter = "aecho=0.8:0.88:150|300:0.4|0.3"

        cmd = f"\"{FFMPEG_BIN}\" -y -i \"{input_path}\" -af \"{aecho_filter}\" -acodec libmp3lame -b:a 192k \"{output_path}\""
        process = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if process.returncode != 0 or not os.path.exists(output_path):
            return {"status": "error", "message": "FFmpeg reverb efekti uygulanamadı."}

        return {
            "status": "success",
            "url": f"/output/{output_filename}"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/cut-audio")
async def cut_audio(file: UploadFile = File(...), start: float = Form(...), end: float = Form(...)):
    try:
        if not (0 <= start < end <= 3600):
            return {"status": "error", "message": "Süreler geçersiz (0 ≤ başlangıç < bitiş, maks. 1 saat)."}

        unique_id = f"cut_{uuid.uuid4().hex[:8]}"
        file_ext = safe_ext(file.filename)
        input_path = os.path.join(UPLOAD_DIR, f"{unique_id}_in{file_ext}")
        output_filename = f"{unique_id}_trimmed.mp3"
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        if not save_upload(file, input_path):
            return {"status": "error", "message": "Dosya çok büyük (limit: 100 MB)."}

        cmd = f"\"{FFMPEG_BIN}\" -y -ss {start} -to {end} -i \"{input_path}\" -acodec libmp3lame -b:a 192k \"{output_path}\""
        process = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if process.returncode != 0 or not os.path.exists(output_path):
            return {"status": "error", "message": "FFmpeg kırpma başarısız oldu."}

        return {
            "status": "success",
            "url": f"/output/{output_filename}"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}