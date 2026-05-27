import os, requests, json, time
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_KEY = os.environ.get("GOOGLE_API_KEY", "AIzaSyBLWLBYdWwHsUjkf2cGUazOIjtoZoF15xM")

# In-Memory Cache für PLZ-Polygone
plz_cache = {}
last_nominatim_call = 0

@app.route("/")
def index():
    with open(os.path.join(BASE_DIR, "app.html"), encoding="utf-8") as f:
        return f.read()

@app.route("/geocode")
def geocode():
    ort = request.args.get("ort", "")
    if not ort: return jsonify({"error": "ort fehlt"}), 400
    r = requests.get("https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": ort, "key": API_KEY, "language": "de"})
    d = r.json()
    if d["status"] != "OK": return jsonify({"error": "Nicht gefunden"}), 400
    loc = d["results"][0]["geometry"]["location"]
    return jsonify({"lat": loc["lat"], "lng": loc["lng"]})

@app.route("/search")
def search():
    params = {
        "location": f"{request.args.get('lat')},{request.args.get('lng')}",
        "radius": request.args.get("radius", 10000),
        "keyword": request.args.get("keyword", ""),
        "key": API_KEY, "language": "de"
    }
    if request.args.get("pagetoken"):
        params["pagetoken"] = request.args.get("pagetoken")
    r = requests.get("https://maps.googleapis.com/maps/api/place/nearbysearch/json", params=params)
    return jsonify(r.json())

@app.route("/details")
def details():
    pid = request.args.get("place_id", "")
    if not pid: return jsonify({"error": "place_id fehlt"}), 400
    # full=1 → Reviews + Öffnungszeiten (teuer, nur beim CSV-Export)
    # Sonst nur Basic Fields (günstig)
    full = request.args.get("full", "0") == "1"
    if full:
        fields = "name,formatted_address,formatted_phone_number,opening_hours,rating,website,url,reviews,user_ratings_total"
    else:
        fields = "name,formatted_address,formatted_phone_number,rating,website,url,user_ratings_total"
    r = requests.get("https://maps.googleapis.com/maps/api/place/details/json", params={
        "place_id": pid, "fields": fields, "key": API_KEY, "language": "de"
    })
    return jsonify(r.json().get("result", {}))

@app.route("/nominatim")
def nominatim():
    global last_nominatim_call
    plz = request.args.get("plz", "")
    if not plz: return jsonify({"error": "plz fehlt"}), 400

    # Cache prüfen
    if plz in plz_cache:
        return jsonify(plz_cache[plz])

    # Rate limit: min 1.2 Sekunden zwischen Requests
    now = time.time()
    wait = 1.2 - (now - last_nominatim_call)
    if wait > 0:
        time.sleep(wait)

    try:
        r = requests.get("https://nominatim.openstreetmap.org/search", params={
            "postalcode": plz, "country": "DE", "format": "json",
            "polygon_geojson": 1, "limit": 1
        }, headers={"User-Agent": "BenderSites/2.0 alex@bendersites.de"}, timeout=15)
        last_nominatim_call = time.time()
        results = r.json()
        if not results: return jsonify({"error": "PLZ nicht gefunden"}), 404
        res = results[0]
        data = {"lat": float(res["lat"]), "lng": float(res["lon"]), "geojson": res.get("geojson", {})}
        plz_cache[plz] = data
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    app.run(host='0.0.0.0', port=port)
