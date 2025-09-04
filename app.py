from flask import Flask, request, render_template, jsonify
import os
import requests
from zipfile import ZipFile
from urllib.parse import urlparse
from io import BytesIO
from threading import Thread

app = Flask(__name__)
progress_data = {"percent": 0}

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/start-download', methods=['POST'])
def start_download():
    # Receive arrays for multiple tasks
    url_formats = request.form.getlist('url_format[]')
    starts = request.form.getlist('start[]')
    ends = request.form.getlist('end[]')

    # Build task list
    tasks = []
    for i in range(len(url_formats)):
        if not url_formats[i].strip():
            continue
        tasks.append({
            "idx": i + 1,  # 1-based for filenames
            "url_format": url_formats[i].strip(),
            "start": int(starts[i]),
            "end": int(ends[i])
        })

    # Ensure static dir
    os.makedirs("static", exist_ok=True)

    def download_and_zip_all():
        headers = {"User-Agent": "Mozilla/5.0"}

        total_images = 0
        for t in tasks:
            total_images += (t["end"] - t["start"] + 1)
        done_images = 0
        progress_data["percent"] = 0

        for t in tasks:
            url_format = t["url_format"]
            start = t["start"]
            end = t["end"]
            idx = t["idx"]

            if not url_format.startswith("http"):
                url_format = "https://" + url_format

            # Working folder per task
            folder = f"downloaded_images_task{idx}"
            os.makedirs(folder, exist_ok=True)

            for i in range(start, end + 1):
                url = url_format.replace("###", str(i))
                try:
                    res = requests.get(url, headers=headers, timeout=7)
                    res.raise_for_status()

                    path = urlparse(url).path
                    ext = os.path.splitext(path)[1].lower().replace(".", "")
                    if ext not in ["jpg", "jpeg", "png", "gif", "webp", "bmp"]:
                        ext = "jpg"

                    filename = f"{i}.{ext}"
                    with open(os.path.join(folder, filename), "wb") as f:
                        f.write(res.content)
                except Exception as e:
                    print(f"[task{idx}] 다운로드 실패 ({url}): {e}")
                finally:
                    done_images += 1
                    if total_images > 0:
                        progress_data["percent"] = int((done_images / total_images) * 100)

            # Make ZIP for this task
            zip_path = os.path.join("static", f"result_task{idx}.zip")
            zip_buffer = BytesIO()
            with ZipFile(zip_buffer, 'w') as zipf:
                for file in sorted(os.listdir(folder)):
                    zipf.write(os.path.join(folder, file), arcname=file)
            zip_buffer.seek(0)
            with open(zip_path, "wb") as f:
                f.write(zip_buffer.read())

            # Cleanup
            for file in os.listdir(folder):
                os.remove(os.path.join(folder, file))
            os.rmdir(folder)

        progress_data["percent"] = 100

    Thread(target=download_and_zip_all).start()
    return '', 204

@app.route('/progress')
def progress():
    return jsonify({"percent": progress_data["percent"]})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
