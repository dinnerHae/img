from flask import Flask, request, render_template, jsonify
import os, requests
from zipfile import ZipFile
from urllib.parse import urlparse
from io import BytesIO
from threading import Thread
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)
progress_data = {"percent": 0}
expected_zips = []

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/expected-zips')
def expected():
    return jsonify({"zips": expected_zips})

@app.route('/start-download', methods=['POST'])
def start_download():
    url_formats = request.form.getlist('url_format[]')
    starts = request.form.getlist('start[]')
    ends = request.form.getlist('end[]')
    wordlists = request.form.getlist('wordlist[]')
    referers = request.form.getlist('referer[]')
    cookies = request.form.getlist('cookie[]')
    zipnames = request.form.getlist('zipname[]')
    max_workers = request.form.get('max_workers', '').strip()

    try:
        max_workers = int(max_workers)
        if max_workers < 1 or max_workers > 20:
            max_workers = 5
    except Exception:
        max_workers = 5

    tasks = []
    for i in range(len(url_formats)):
        uf = (url_formats[i] or '').strip()
        if not uf:
            continue

        zn = (zipnames[i] if i < len(zipnames) else "").strip()
        if zn and not zn.lower().endswith(".zip"):
            zn += ".zip"
        if not zn:
            zn = f"result_task{len(tasks)+1}.zip"

        wl = (wordlists[i] or '').strip().splitlines()
        wl = [w.strip() for w in wl if w.strip()]

        referer = (referers[i] if i < len(referers) else "").strip()
        cookie = (cookies[i] if i < len(cookies) else "").strip()

        if wl:
            tasks.append({
                "idx": len(tasks)+1,
                "url_format": uf,
                "words": wl,
                "zipname": zn,
                "mode": "words",
                "referer": referer,
                "cookie": cookie
            })
        else:
            try:
                s = int(starts[i]); e = int(ends[i])
            except Exception:
                continue
            if s > e: s, e = e, s
            tasks.append({
                "idx": len(tasks)+1,
                "url_format": uf,
                "start": s,
                "end": e,
                "zipname": zn,
                "mode": "numbers",
                "referer": referer,
                "cookie": cookie
            })

    os.makedirs("static", exist_ok=True)

    global expected_zips
    expected_zips = [t["zipname"] for t in tasks]

    def download_and_zip_all(tasks_local, max_workers_val):
        total_images = 0
        for t in tasks_local:
            if t["mode"] == "numbers":
                total_images += (t["end"] - t["start"] + 1)
            else:
                total_images += len(t["words"])
        done_images = [0]
        progress_data["percent"] = 0

        if total_images <= 0 or not tasks_local:
            progress_data["percent"] = 100
            return

        for t in tasks_local:
            url_format = t["url_format"]
            idx = t["idx"]
            zipname = t["zipname"]
            if not url_format.startswith("http"):
                url_format = "https://" + url_format

            folder = f"downloaded_images_task{idx}"
            os.makedirs(folder, exist_ok=True)

            if t["mode"] == "numbers":
                urls = [url_format.replace("###", str(i)) for i in range(t["start"], t["end"]+1)]
            else:
                urls = [url_format.replace("###", w) for w in t["words"]]

            def fetch(url, i):
                try:
                    headers = {"User-Agent": "Mozilla/5.0"}
                    if t["referer"]: headers["Referer"] = t["referer"]
                    if t["cookie"]: headers["Cookie"] = t["cookie"]
                    res = requests.get(url, headers=headers, timeout=10)
                    res.raise_for_status()
                    path = urlparse(url).path
                    ext = os.path.splitext(path)[1].lower().replace(".", "")
                    if ext not in ["jpg", "jpeg", "png", "gif", "webp", "bmp"]:
                        ext = "jpg"
                    filename = f"{i}.{ext}"
                    with open(os.path.join(folder, filename), "wb") as f:
                        f.write(res.content)
                except Exception as e:
                    print(f"[task{idx}] 실패 {url}: {e}")
                finally:
                    done_images[0] += 1
                    progress_data["percent"] = int((done_images[0] / total_images) * 100)

            with ThreadPoolExecutor(max_workers=max_workers_val) as executor:
                futures = {executor.submit(fetch, url, i): i for i, url in enumerate(urls, start=1)}
                for future in as_completed(futures):
                    pass

            zip_path = os.path.join("static", zipname)
            zip_buffer = BytesIO()
            with ZipFile(zip_buffer, 'w') as zipf:
                for file in sorted(os.listdir(folder)):
                    zipf.write(os.path.join(folder, file), arcname=file)
            zip_buffer.seek(0)
            with open(zip_path, "wb") as f:
                f.write(zip_buffer.read())

            for file in os.listdir(folder):
                try:
                    os.remove(os.path.join(folder, file))
                except Exception:
                    pass
            try:
                os.rmdir(folder)
            except Exception:
                pass

        progress_data["percent"] = 100

    Thread(target=download_and_zip_all, args=(tasks, max_workers)).start()
    return '', 204

@app.route('/progress')
def progress():
    return jsonify({"percent": progress_data["percent"]})

@app.route('/health')
def health():
    return jsonify({"ok": True})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
