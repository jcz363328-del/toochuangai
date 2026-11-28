import os

from waitress import serve

from app import app
from innovation.home_snapshots import start_home_snapshot_worker
from lunch_push import lunch_push

app.config["SESSION_COOKIE_NAME"] = os.environ.get("TC_SESSION_COOKIE_NAME", "tc_docker_session")

def application(environ, start_response):
    if environ.get("PATH_INFO") == "/_container/health":
        start_response("200 OK", [("Content-Type", "text/plain"), ("Content-Length", "2")])
        return [b"ok"]
    return app(environ, start_response)


if __name__ == "__main__":
    if not os.environ.get("FLASK_SECRET_KEY") or not os.environ.get("INNOVATION_SECRET_KEY"):
        raise RuntimeError("Set FLASK_SECRET_KEY and INNOVATION_SECRET_KEY in .env.docker")
    start_home_snapshot_worker(app)
    if os.environ.get('TC_BACKGROUND_JOBS', '1') == '1':
        lunch_push.start()
    serve(application, host=os.environ.get("TC_WEB_HOST", "0.0.0.0"), port=int(os.environ.get("TC_WEB_PORT", "8000")), threads=16, max_request_body_size=536870912)
