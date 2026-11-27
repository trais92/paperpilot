"""Eine kleine Nachbildung der Google-Drive-Schnittstelle v3 im Speicher, als `Transport` für Tests.

Sie versteht genau die Aufrufe, die `DriveApi` macht, und prüft dabei Methode, Pfad und Token.
So läuft der Vertragstest für Ablageziele auch für `DriveStore`, ohne Netz.
"""

import itertools
import json
import re
import urllib.parse

from paperpilot_ops.ai.http import HttpResponse

FOLDER = "application/vnd.google-apps.folder"
SHEET = "application/vnd.google-apps.spreadsheet"


class FakeTokens:
    def __init__(self, token="tok-1"):
        self.token = token
        self.invalidated = 0

    def access_token(self):
        return self.token

    def invalidate(self):
        self.invalidated += 1


class FakeDrive:
    def __init__(self, token="tok-1"):
        self.token = token
        self.files = {}  # id -> {name, parents, mimeType, content}
        self.calls = []
        self.fail_next = []  # Statuscodes, die die nächsten Aufrufe liefern
        self._ids = (f"id{n}" for n in itertools.count(1))

    # -- Hilfen für Tests ---------------------------------------------------------------
    def path_of(self, file_id):
        f = self.files[file_id]
        parent = f["parents"][0]
        return f["name"] if parent == "root" else f"{self.path_of(parent)}/{f['name']}"

    def by_path(self):
        return {self.path_of(i): f for i, f in self.files.items()}

    # -- Transport --------------------------------------------------------------------------
    def __call__(self, request):
        self.calls.append((request.method, request.url))
        if self.fail_next:
            return HttpResponse(self.fail_next.pop(0), b"{}")
        if request.headers.get("Authorization") != f"Bearer {self.token}":
            return HttpResponse(401, b'{"error": "invalid_token"}')
        url = urllib.parse.urlsplit(request.url)
        query = dict(urllib.parse.parse_qsl(url.query))
        path = url.path
        if request.method == "GET" and path == "/drive/v3/files":
            return self._list(query["q"])
        if request.method == "POST" and path == "/drive/v3/files":
            meta = json.loads(request.body)
            return self._create(meta, b"")
        if request.method == "POST" and path == "/upload/drive/v3/files":
            assert query["uploadType"] == "multipart"
            meta, content = self._multipart(request)
            return self._create(meta, content)
        m = re.fullmatch(r"/upload/drive/v3/files/(\w+)", path)
        if request.method == "PATCH" and m:
            self.files[m[1]]["content"] = request.body
            return self._json({"id": m[1]})
        m = re.fullmatch(r"/drive/v3/files/(\w+)", path)
        if request.method == "GET" and m and query.get("alt") == "media":
            f = self.files[m[1]]
            assert f["mimeType"] != SHEET, "Google-Tabellen lassen sich nicht direkt herunterladen"
            return HttpResponse(200, f["content"])
        m = re.fullmatch(r"/drive/v3/files/(\w+)/export", path)
        if request.method == "GET" and m:
            assert query["mimeType"] == "text/csv" and self.files[m[1]]["mimeType"] == SHEET
            return HttpResponse(200, b"\xef\xbb\xbf" + self.files[m[1]]["content"])
        raise AssertionError(f"unerwarteter Aufruf {request.method} {request.url}")

    def _list(self, q):
        m = re.fullmatch(r"name = '((?:[^'\\]|\\.)*)' and '(\w+)' in parents and trashed = false", q)
        assert m, q
        name = re.sub(r"\\(.)", r"\1", m[1])
        hits = [
            {"id": i, "name": f["name"], "mimeType": f["mimeType"]}
            for i, f in self.files.items()
            if f["name"] == name and m[2] in f["parents"]
        ]
        return self._json({"files": hits})

    def _create(self, meta, content):
        file_id = next(self._ids)
        self.files[file_id] = {
            "name": meta["name"],
            "parents": meta["parents"],
            "mimeType": meta.get("mimeType", "application/octet-stream"),
            "content": content,
        }
        return self._json({"id": file_id})

    @staticmethod
    def _multipart(request):
        boundary = request.headers["Content-Type"].split("boundary=")[1]
        parts = request.body.split(f"--{boundary}".encode())
        meta_part, media_part = parts[1], parts[2]
        meta = json.loads(meta_part.split(b"\r\n\r\n", 1)[1].rstrip(b"\r\n"))
        content = media_part.split(b"\r\n\r\n", 1)[1][: -len(b"\r\n")]
        return meta, content

    @staticmethod
    def _json(data):
        return HttpResponse(200, json.dumps(data).encode())
