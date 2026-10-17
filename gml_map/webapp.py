"""Prefix-safe Tornado server for interactive WebAgg viewing.

Replaces matplotlib's stock WebAgg application, which references assets with
root-absolute paths (`/_static/...`) and builds the WebSocket URI from the
server side. Both break when the app is reached through a reverse proxy that
adds a path prefix (e.g. code-server's /proxy/<port>/ URLs): the browser
requests https://proxy.example/_static/css/page.css and gets a 404.

This server instead:

- mounts every route behind a wildcard prefix, so it works under any URL
  prefix (`/`, `/gml/`, `/proxy/8988/`, ...),
- emits an index page with *relative* asset URLs,
- lets the browser derive the WebSocket URI from window.location, so
  wss:// and the proxy prefix are handled automatically,
- allows cross-origin WebSocket connections (proxies often rewrite Host).
"""

from __future__ import annotations

import base64
import json
import mimetypes
from io import BytesIO
from pathlib import Path

import matplotlib as mpl
import tornado.ioloop
import tornado.template
import tornado.web
import tornado.websocket
from matplotlib._pylab_helpers import Gcf
from matplotlib.backends import backend_webagg_core as core

_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <link rel="stylesheet" href="_static/css/page.css" type="text/css">
    <link rel="stylesheet" href="_static/css/boilerplate.css" type="text/css">
    <link rel="stylesheet" href="_static/css/fbm.css" type="text/css">
    <link rel="stylesheet" href="_static/css/mpl.css" type="text/css">
    <script src="_static/js/mpl_tornado.js"></script>
    <script src="js/mpl.js"></script>
    <script>
      function ready(fn) {
        if (document.readyState != "loading") {
          fn();
        } else {
          document.addEventListener("DOMContentLoaded", fn);
        }
      }

      function figure_ready(fig_id) {
        return function () {
          var main_div = document.querySelector("div#figures");
          var figure_div = document.createElement("div");
          figure_div.id = "figure-div";
          main_div.appendChild(figure_div);
          var websocket_type = mpl.get_websocket_type();
          var path = location.pathname;
          if (!path.endsWith("/")) path += "/";
          var proto = location.protocol === "https:" ? "wss://" : "ws://";
          var uri = proto + location.host + path + fig_id + "/ws";
          var websocket = new websocket_type(uri);
          var fig = new mpl.figure(fig_id, websocket, mpl_ondownload, figure_div);

          fig.focus_on_mouseover = true;
          fig.canvas.setAttribute("tabindex", fig_id);
        };
      }

      {% for (fig_id, fig_manager) in figures %}
        ready(figure_ready({{ str(fig_id) }}));
      {% end %}
    </script>
    <title>{{ title }}</title>
  </head>
  <body>
    <div id="mpl-warnings" class="mpl-warnings"></div>
    <div id="figures" style="margin: 10px 10px;"></div>
  </body>
</html>
"""


class _Static(tornado.web.StaticFileHandler):
    """StaticFileHandler that ignores the wildcard prefix capture group."""

    def get(self, _prefix, path, include_body=True):
        return super().get(path, include_body)


class _FavIcon(tornado.web.RequestHandler):
    def get(self, _prefix):
        self.set_header("Content-Type", "image/png")
        self.write(Path(mpl.get_data_path(), "images", "matplotlib.png").read_bytes())


class _MplJs(tornado.web.RequestHandler):
    def get(self, _prefix):
        self.set_header("Content-Type", "application/javascript")
        self.write(core.FigureManagerWebAgg.get_javascript())


class _Download(tornado.web.RequestHandler):
    def get(self, _prefix, fignum, fmt):
        fignum = int(fignum)
        manager = Gcf.get_fig_manager(fignum)
        self.set_header("Content-Type", mimetypes.types_map.get(fmt, "binary"))
        buff = BytesIO()
        manager.canvas.figure.savefig(buff, format=fmt)
        self.write(buff.getvalue())


class _WebSocket(tornado.websocket.WebSocketHandler):
    supports_binary = True

    def check_origin(self, origin):
        return True  # proxied deployments may rewrite the Host header

    def open(self, _prefix, fignum):
        self.fignum = int(fignum)
        self.manager = Gcf.get_fig_manager(self.fignum)
        self.manager.add_web_socket(self)
        if hasattr(self, "set_nodelay"):
            self.set_nodelay(True)

    def on_close(self):
        self.manager.remove_web_socket(self)

    def on_message(self, message):
        message = json.loads(message)
        if message["type"] == "supports_binary":
            self.supports_binary = message["value"]
        else:
            manager = Gcf.get_fig_manager(self.fignum)
            if manager is not None:
                manager.handle_json(message)

    def send_json(self, content):
        self.write_message(json.dumps(content))

    def send_binary(self, blob):
        if self.supports_binary:
            self.write_message(blob, binary=True)
        else:
            data_uri = "data:image/png;base64," + base64.b64encode(blob).decode()
            self.write_message(data_uri)


class _Index(tornado.web.RequestHandler):
    def initialize(self, title):
        self.title = title

    def get(self, _prefix=""):
        if not self.request.path.endswith("/"):
            # Ensure relative asset URLs resolve under the proxy prefix.
            self.redirect(self.request.path + "/", permanent=False)
            return
        figures = sorted(Gcf.figs.items())
        html = tornado.template.Template(_INDEX_HTML).generate(
            figures=figures, title=self.title)
        self.write(html)


def serve(fig, *, port=8988, address="0.0.0.0", title="GML Map Viewer"):
    """Serve `fig` interactively; blocks until Ctrl-C.

    Works both directly and behind reverse proxies with or without a URL
    prefix - the browser computes all URLs relative to the page.
    """
    app = tornado.web.Application([
        (r"(.*)/_static/(.*)", _Static,
         {"path": core.FigureManagerWebAgg.get_static_file_path()}),
        (r"(.*)/_images/(.*)", _Static,
         {"path": str(Path(mpl.get_data_path(), "images"))}),
        (r"(.*)/favicon\.ico", _FavIcon),
        (r"(.*)/js/mpl\.js", _MplJs),
        (r"(.*)/([0-9]+)/ws", _WebSocket),
        (r"(.*)/([0-9]+)/download\.([a-z0-9.]+)", _Download),
        (r"(.*)", _Index, {"title": title}),
    ])
    app.listen(port, address)
    print(f"Interactive map ready on port {port} (any URL prefix works).")
    print("If you are behind a reverse proxy, open this port through it,")
    print("e.g. https://proxy.example/proxy/{}/".format(port))
    print("Press Ctrl-C in this terminal to stop.")
    ioloop = tornado.ioloop.IOLoop.current()
    try:
        ioloop.start()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            ioloop.stop()
        except Exception:
            pass
