from flask import Flask, request, render_template, send_file
import os
import requests
from zipfile import ZipFile
from urllib.parse import urlparse
from io import BytesIO

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        url_format = request.form['url_format'].strip()
        start = int(request.form['start'])
        end = int(request.form['end'])

        if not url_format.startswith("http"):
            url_format = "https://" + url_format

        folder = "downloaded_images"
        os.makedirs(folder, exist_ok=True)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

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

        # 메모리 위에 ZIP 파일 만들기
        zip_buffer = BytesIO()
        with ZipFile(zip_buffer, 'w') as zipf:
            for file in os.listdir(folder):
                zipf.write(os.path.join(folder, file), arcname=file)

        # cleanup
        for file in os.listdir(folder):
            os.remove(os.path.join(folder, file))
        os.rmdir(folder)

        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='images.zip'
        )

    return render_template("index.html")
    
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
