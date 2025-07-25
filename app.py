from flask import Flask, request, render_template, send_file, jsonify
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
    url_format = request.form['url_format'].strip()
    start = int(request.form['start'])
    end = int(request.form['end'])

    if not url_format.startswith("http"):
        url_format = "https://" + url_format

    def download_and_zip():
        folder = "downloaded_images"
        os.makedirs(folder, exist_ok=True)

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        total = end - start + 1
        count = 0

        for i in range(start, end + 1):
            url = url_format.replace("###", str(i))
            try:
                res = requests.get(url, headers=headers, timeout=5)
                res.raise_for_status()

                path = urlparse(url).path
                ext = os.path.splitext(path)[1].lower().replace(".", "")
                if ext not in ["jpg", "jpeg", "png", "gif", "webp", "bmp"]:
                    ext = "jpg"

                filename = f"{i}.{ext}"
                with open(os.path.join(folder, filename), "wb") as f:
                    f.write(res.content)

            except Exception as e:
                print(f"다운로드 실패 ({url}): {e}")
                continue

            count += 1
            progress_data["percent"] = int((count / total) * 100)

        # ZIP 만들기
        zip_buffer = BytesIO()
        with ZipFile(zip_buffer, 'w') as zipf:
            for file in os.listdir(folder):
                zipf.write(os.path.join(folder, file), arcname=file)

        # 정리
        for file in os.listdir(folder):
            os.remove(os.path.join(folder, file))
        os.rmdir(folder)

        zip_buffer.seek(0)
        with open("static/result.zip", "wb") as f:
            f.write(zip_buffer.read())

        progress_data["percent"] = 100

    # 백그라운드로 실행
    Thread(target=download_and_zip).start()

    return '', 204

@app.route('/progress')
def progress():
    return jsonify({"percent": progress_data["percent"]})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
