# -*- coding: utf-8 -*-
"""
本地可视化编辑服务(纯标准库)。启动后浏览器打开 http://localhost:8765/编辑器
- GET 任意文件:直接 served(editor.html / 几何 svg / json / 出图 png)
- POST /save          :保存 furniture-<户型>.json 并自动重出图(家具模式)
- POST /derive        :内存跑 geometry.derive(不落盘),返回 {walls,doors,windows,dims,conflicts,warns}(几何实时预览)
- POST /save-geometry :校验 geometry → 无 ERROR 则写盘 + 重出图;有 ERROR 返回 400+清单(几何模式)
用法:python3 serve.py   然后浏览器访问提示地址。Ctrl+C 退出。
"""
import http.server, socketserver, json, subprocess, sys, os, functools, webbrowser
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)              # 项目根(服务根目录,这样几何图/出图PNG都可访问)
from floorplan_core import geometry       # 几何派生 / 校验 单一真源 (引擎库)

PORT = int(os.environ.get("PORT", "8765"))
HOUSE = os.environ.get("HOUSE", "D")
FURN = os.path.join(HERE, f"furniture-{HOUSE}户型.json")
GEOM = os.path.join(HERE, f"geometry-{HOUSE}户型.json")


class Handler(http.server.SimpleHTTPRequestHandler):
    # ----- 工具 -----
    def _read_body(self):
        n = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(n)

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, code, text):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ----- 路由 -----
    def do_POST(self):
        if self.path == "/save":
            self._save_furniture()
        elif self.path == "/derive":
            self._derive()
        elif self.path == "/save-geometry":
            self._save_geometry()
        else:
            self.send_error(404)

    # ----- 家具:原逻辑保留 -----
    def _save_furniture(self):
        try:
            items = json.loads(self._read_body())
            assert isinstance(items, list)
            json.dump(items, open(FURN, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            subprocess.run([sys.executable, "build.py", HOUSE, "--no-geom", "--no-open"],
                           cwd=HERE, check=True)
            self._send_text(200, "ok")
        except Exception as e:
            self._send_text(500, str(e))

    # ----- 几何:实时派生(不落盘)-----
    def _derive(self):
        try:
            G = json.loads(self._read_body())
            res = geometry.derive(G)
            # 仅返回前端需要的字段(_walls_raw 便于编辑器叠加绘制,保留)
            out = {
                "walls": res.get("walls", []),
                "doors": res.get("doors", []),
                "windows": res.get("windows", []),
                "dims": res.get("dims", {}),
                "conflicts": res.get("conflicts", []),
                "warns": res.get("warns", []),
                "_walls_raw": res.get("_walls_raw", []),
            }
            self._send_json(200, out)
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    # ----- 几何:校验 + 写盘 + 重出图 -----
    def _save_geometry(self):
        try:
            G = json.loads(self._read_body())
        except Exception as e:
            self._send_json(400, {"ok": False, "errors": ["JSON 解析失败: %s" % e], "warns": []})
            return
        try:
            issues = geometry.validate(G)
        except Exception as e:
            self._send_json(400, {"ok": False, "errors": ["校验异常: %s" % e], "warns": []})
            return
        errors = [m for (lvl, m) in issues if lvl == "ERROR"]
        warns = [m for (lvl, m) in issues if lvl == "WARN"]
        if errors:
            self._send_json(400, {"ok": False, "errors": errors, "warns": warns})
            return
        try:
            json.dump(G, open(GEOM, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            subprocess.run([sys.executable, "build.py", HOUSE, "--no-open"],
                           cwd=HERE, check=True)
        except Exception as e:
            self._send_json(500, {"ok": False, "errors": ["写盘/重出图失败: %s" % e], "warns": warns})
            return
        self._send_json(200, {"ok": True, "warns": warns})

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")   # 出图后刷新不缓存
        super().end_headers()


if __name__ == "__main__":
    os.chdir(ROOT)
    h = functools.partial(Handler, directory=ROOT)
    httpd = http.server.ThreadingHTTPServer(("", PORT), h)   # 多线程,避免单请求阻塞
    plain = f"http://localhost:{PORT}/轴测图POC/editor.html"
    encoded = f"http://localhost:{PORT}/" + quote("轴测图POC/editor.html")  # 中文路径正确编码后再打开
    print(f"编辑器已启动。若没自动打开,手动在浏览器粘贴:\n  {plain}\n(Ctrl+C 退出)")
    try:
        webbrowser.open(encoded)
    except Exception:
        pass
    httpd.serve_forever()
