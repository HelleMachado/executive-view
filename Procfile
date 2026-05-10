import os
from flask import Flask, send_from_directory

app = Flask(__name__, static_folder="static")

@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/executive_view_operacional")
def executive_view_operacional():
    return send_from_directory(app.static_folder, "executive_view_operacional.html")

@app.route("/executive_view_operacional.html")
def executive_view_operacional_html():
    return send_from_directory(app.static_folder, "executive_view_operacional.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
