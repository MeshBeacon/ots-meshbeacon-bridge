from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_security import auth_required, roles_accepted


def build_blueprint(plugin) -> Blueprint:
    """
    Minimal admin API for the MeshBeacon bridge: status info and sending a
    mesh command back through the encrypted MQTT link. `plugin` is the
    live MeshBeaconPlugin instance (closed over here, not re-looked-up per
    request) so command sends go through its already-connected MQTT client.
    """
    bp = Blueprint("ots_meshbeacon_bridge", __name__, url_prefix="/api/meshbeacon")

    @bp.route("/info", methods=["GET"])
    @auth_required()
    def info():
        return jsonify(plugin.get_info())

    @bp.route("/command", methods=["POST"])
    @roles_accepted("administrator")
    def send_command():
        body = request.get_json(silent=True) or {}
        duck_id = body.get("duck_id")
        message = body.get("message")

        if not duck_id or not message:
            return jsonify({"success": False, "message": "duck_id and message are required"}), 400

        sent = plugin.send_command(str(duck_id), str(message))
        if not sent:
            return (
                jsonify({"success": False, "message": "Bridge is not connected or not configured"}),
                503,
            )

        return jsonify({"success": True})

    return bp
