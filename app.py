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

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/expected-zips')
def expected():
    global expected_zips
    return jsonify({"zips": expected_zips})

@app.route('/start-download', methods=['POST'])
def start_download():
    global expected_zips
    expected_zips = []

    max_workers = request.form.get('max_workers', '').strip()
    try:
        max_workers = int(max_workers)
        if max_workers < 1 or max_workers > 20:
            max_workers = 5
    except Exception:
        max_workers = 5

    # === 다중 주소 처리 ===
    multi_urls_raw = (request.form.get('multi_urls') or '').strip()
    if multi_urls_raw:
        urls_list = [u.strip() for u in multi_urls_raw.split(',') if u.strip()]
        try:
            s = int(request.form.get('multi_start', '0') or 0)
            e = int(request.form.get('multi_end', '0') or 0)
        except Exception:
            s, e = 0, -1
        if s > e:
            s, e = e, s

        referer = (request.form.get('multi_referer') or '').strip()
        cookie = (request.form.get('multi_cookie') or '').strip()
        zipname = (request.form.get('multi_zipname') or '').strip() or 'multi_sites.zip'
        if not zipname.lower().endswith('.zip'):
            zipname += '.zip'

        expected_zips = [zipname]

        def multi_download(urls, start, end, workers):
            headers = {"User-Agent": "Mozilla/5.0"}
            if referer: headers["Referer"] = referer
            if cookie: headers["Cookie"] = cookie

            expanded = []
            for site in urls:
                if not site.startswith('http'):
                    site = 'https://' + site
                if '###' in site and start <= end:
                    for i in range(start, end+1):
                        expanded.append((site, i))
                else:
                    expanded.append((site, None))

            total = len(expanded)
            done = 0
            progress_data["percent"] = 0
            os.makedirs("static", exist_ok=True)
            zip_path = os.path.join("static", zipname)

            zip_buffer = BytesIO()
            with ZipFile(zip_buffer, 'w') as zipf:
                def fetch_and_write(item):
                    nonlocal done
                    site, i = item
                    parsed = urlparse(site)
                    netloc = parsed.netloc or parsed.path.split('/')[0]
                    folder = netloc.replace(':', '_').replace('/', '_')
                    url = site.replace('###', str(i)) if i is not None else site
                    try:
                        res = requests.get(url, headers=headers, timeout=15)
                        res.raise_for_status()
                        path = urlparse(url).path
                        # 안전한 파일명 (중복방지 + 폴더명 prefix)
                        base = f"{folder}_{os.path.basename(path) or (f'file_{i}.jpg' if i is not None else 'file.jpg')}"
                        arcname = os.path.join(folder, base)
                        zipf.writestr(arcname, res.content)
                    except Exception as ex:
                        print(f"[multi] 실패 {url}: {ex}")
                    finally:
                        done += 1
                        progress_data["percent"] = int(done / max(1, total) * 100)

                with ThreadPoolExecutor(max_workers=workers) as executor:
                    executor.map(fetch_and_write, expanded)

            with open(zip_path, "wb") as f:
                f.write(zip_buffer.getvalue())
            progress_data["percent"] = 100

        Thread(target=multi_download, args=(urls_list, s, e, max_workers)).start()
        return '', 204

    # === 기존 기능 (단일 or 여러 작업 카드) ===
    url_formats = request.form.getlist('url_format[]')
    starts = request.form.getlist('start[]')
    ends = request.form.getlist('end[]')
    zipnames = request.form.getlist('zipname[]')

    if not url_formats:
        uf = request.form.get('url_format', '').strip()
        st = request.form.get('start', '').strip()
        en = request.form.get('end', '').strip()
        zn = request.form.get('zipname', '').strip()
        if uf and st and en:
            url_formats = [uf]
            starts = [st]
            ends = [en]
            zipnames = [zn]

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

        zn = (zipnames[i] if i < len(zipnames) else "").strip()
        if zn and not zn.lower().endswith(".zip"):
            zn += ".zip"
        if not zn:
            zn = f"result_task{len(tasks)+1}.zip"

        tasks.append({
            "idx": len(tasks)+1,
            "url_format": uf,
            "start": s,
            "end": e,
            "zipname": zn
        })

    expected_zips = [t["zipname"] for t in tasks]
    os.makedirs("static", exist_ok=True)

    def download_and_zip_all(tasks_local, max_workers_val):
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
            zipname = t["zipname"]
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

            with ThreadPoolExecutor(max_workers=max_workers_val) as executor:
                futures = {executor.submit(fetch, url, i): i for i, url in enumerate(urls, start=start)}
                for _ in as_completed(futures):
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
