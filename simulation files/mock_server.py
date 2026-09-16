#!/usr/bin/env python3
"""
mock_server.py — a tiny stand-in for Person 2's real ingest endpoint.

Run this in one terminal, then run simulator.py (without --mock) in another
terminal pointing at http://localhost:5000/readings. This lets you test the
full HTTP flow before Person 2's real AWS endpoint exists.

Requires Flask:  pip install flask
Run:             python3 mock_server.py
"""

from flask import Flask, request, jsonify

app = Flask(__name__)
received = []


@app.route("/readings", methods=["POST"])
def ingest():
    data = request.get_json()
    received.append(data)
    if len(received) % 50 == 0:
        print(f"[mock_server] received {len(received)} readings so far... "
              f"latest: {data}")
    return jsonify({"status": "ok"}), 201


@app.route("/readings", methods=["GET"])
def query():
    sensor_id = request.args.get("sensor_id")
    if sensor_id:
        return jsonify([r for r in received if r["sensor_id"] == sensor_id])
    return jsonify(received)


if __name__ == "__main__":
    print("Mock ingest server running on http://localhost:5000/readings")
    app.run(port=5000, debug=False)
