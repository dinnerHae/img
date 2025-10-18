from flask import Flask, request, render_template, jsonify
import os
import requests
from zipfile import ZipFile
from urllib.parse import urlparse
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
    global expected_zips

    max_workers = request.form.get('max_workers', '').strip()
    try:
        max_workers = int(max_workers)
        if max_workers < 1 or max_workers > 20:
            max_workers = 5
    except Exception:
        max_workers = 5

    # 다중 주소 다운로드
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

            static_dir = os.path.join(os.path.dirname(__file__), "static")
            os.makedirs(static_dir, exist_ok=True)
            zip_path = os.path.join(static_dir, zipname)

            expanded = []
            for site in urls:
                if not site.startswith('http'):
                    site = 'https://' + site
                if '###' in site and start <= end:
                    for i in range(start, end + 1):
                        expanded.append((site, i))
                else:
                    expanded.append((site, None))

            total = len(expanded)
            done = 0
            progress_data["percent"] = 0

            def fetch_pack(item):
                nonlocal done
                site, i = item
                parsed = urlparse(site)
                netloc = parsed.netloc or parsed.path.split('/')[0]
                folder = netloc.replace(':', '_')
                url = site.replace('###', str(i)) if i is not None else site
                try:
                    res = requests.get(url, headers=headers, timeout=15)
                    res.raise_for_status()
                    path = urlparse(url).path
                    base = os.path.basename(path) or (f"file_{i}.jpg" if i is not None else "file.jpg")
                    temp_file = os.path.join(static_dir, f"_temp_{os.getpid()}_{base}")
                    with open(temp_file, "wb") as tf:
                        tf.write(res.content)
                    return (folder, base, temp_file)
                except Exception:
                    return None
                finally:
                    done += 1
                    progress_data["percent"] = int(done / max(1, total) * 100)

            with ThreadPoolExecutor(max_workers=workers) as executor:
                results = list(executor.map(fetch_pack, expanded))

            # ZIP을 디스크에 직접 생성 (메모리 절약)
            with ZipFile(zip_path, 'w') as zipf:
                for r in results:
                    if not r:
                        continue
                    folder, base, temp_file = r
                    arcname = os.path.join(folder, base)
                    zipf.write(temp_file, arcname=arcname)
                    try:
                        os.remove(temp_file)
                    except Exception:
                        pass

            progress_data["percent"] = 100

        Thread(target=multi_download, args=(urls_list, s, e, max_workers)).start()
        return '', 204

    # 기존 다중 작업 카드
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
            url_formats = [uf]; starts = [st]; ends = [en]; zipnames = [zn]

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

    os.makedirs("static", exist_ok=True)
    expected_zips = [t["zipname"] for t in tasks]

    def download_and_zip_all(tasks_local, max_workers_val):
        headers = {"User-Agent": "Mozilla/5.0"}
        total_images = sum((t["end"] - t["start"] + 1) for t in tasks_local)
        done_images = [0]
        progress_data["percent"] = 0

        for t in tasks_local:
            folder = f"task_{t['idx']}"
            os.makedirs(folder, exist_ok=True)
            urls = [t["url_format"].replace("###", str(i)) for i in range(t["start"], t["end"]+1)]
            zip_path = os.path.join("static", t["zipname"])

            with ZipFile(zip_path, 'w') as zipf:
                def fetch(url, i):
                    try:
                        res = requests.get(url, headers=headers, timeout=10)
                        res.raise_for_status()
                        path = urlparse(url).path
                        ext = os.path.splitext(path)[1] or ".jpg"
                        filename = f"{i}{ext}"
                        temp = os.path.join(folder, filename)
                        with open(temp, "wb") as f:
                            f.write(res.content)
                        zipf.write(temp, arcname=filename)
                        os.remove(temp)
                    except Exception as e:
                        print(f"[task{t['idx']}] 실패 {url}: {e}")
                    finally:
                        done_images[0] += 1
                        progress_data["percent"] = int((done_images[0] / total_images) * 100)

                with ThreadPoolExecutor(max_workers=max_workers_val) as executor:
                    list(executor.map(fetch, urls, range(t["start"], t["end"]+1)))

            os.rmdir(folder)
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
