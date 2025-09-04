from flask import Flask, request, render_template, jsonify
import os
import requests
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

    if not url_formats:
        uf = request.form.get('url_format', '').strip()
        st = request.form.get('start', '').strip()
        en = request.form.get('end', '').strip()
        if uf and st and en:
            url_formats = [uf]
            starts = [st]
            ends = [en]

    tasks = []
    for i in range(len(url_formats)):
        uf = (url_formats[i] or '').strip()
        if not uf:
            continue
        try:
            s = int(starts[i])
            e = int(ends[i])
        except Exception:
            continue
        if s > e:
            s, e = e, s
        tasks.append({"idx": len(tasks)+1, "url_format": uf, "start": s, "end": e})

    os.makedirs("static", exist_ok=True)

    global expected_zips
    expected_zips = [f"result_task{t['idx']}.zip" for t in tasks] if tasks else []

    def download_and_zip_all(tasks_local):
        headers = {"User-Agent": "Mozilla/5.0"}
        total_images = sum((t["end"] - t["start"] + 1) for t in tasks_local)
        done_images = [0]
        progress_data["percent"] = 0

        if total_images <= 0 or not tasks_local:
            progress_data["percent"] = 100
            return

        for t in tasks_local:
            url_format = t["url_format"]
            start = t["start"]
            end = t["end"]
            idx = t["idx"]
            if not url_format.startswith("http"):
                url_format = "https://" + url_format

            folder = f"downloaded_images_task{idx}"
            os.makedirs(folder, exist_ok=True)

            urls = [url_format.replace("###", str(i)) for i in range(start, end+1)]

            def fetch(url, i):
                try:
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

            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(fetch, url, i): i for i, url in enumerate(urls, start=start)}
                for future in as_completed(futures):
                    pass

            zip_path = os.path.join("static", f"result_task{idx}.zip")
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

    Thread(target=download_and_zip_all, args=(tasks,)).start()
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
