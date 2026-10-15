"""Lapisan data tipis. Pakai Firestore bila kredensial ada, kalau tidak pakai memori (mode demo)."""
import os, time, uuid

_fs = None
_bucket = None
cred_path = os.getenv("FIREBASE_CREDENTIALS", "")
if cred_path and os.path.exists(cred_path):
    import firebase_admin
    from firebase_admin import credentials, firestore, storage
    opts = {"storageBucket": os.getenv("FIREBASE_BUCKET")} if os.getenv("FIREBASE_BUCKET") else {}
    firebase_admin.initialize_app(credentials.Certificate(cred_path), opts)
    _fs = firestore.client()
    if opts:
        _bucket = storage.bucket()

DEMO = _fs is None


class Store:
    def __init__(self):
        self.mem = {}

    def all(self, col):
        if _fs:
            return [{**d.to_dict(), "id": d.id} for d in _fs.collection(col).stream()]
        return [{**v, "id": k} for k, v in self.mem.get(col, {}).items()]

    def get(self, col, id):
        if _fs:
            d = _fs.collection(col).document(id).get()
            return {**d.to_dict(), "id": d.id} if d.exists else None
        v = self.mem.get(col, {}).get(id)
        return {**v, "id": id} if v else None

    def add(self, col, data, id=None):
        id = id or uuid.uuid4().hex[:12]
        data = {**data, "created": time.time()}
        if _fs:
            _fs.collection(col).document(id).set(data)
        else:
            self.mem.setdefault(col, {})[id] = data
        return id

    def update(self, col, id, data):
        if _fs:
            _fs.collection(col).document(id).set(data, merge=True)
        else:
            self.mem.setdefault(col, {}).setdefault(id, {}).update(data)

    def delete(self, col, id):
        if _fs:
            _fs.collection(col).document(id).delete()
        else:
            self.mem.get(col, {}).pop(id, None)


store = Store()


def upload_image(file, folder="karya"):
    """Simpan gambar ke Firebase Storage (atau static/uploads saat mode demo). Return URL."""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise ValueError("Format gambar harus JPG, PNG, atau WEBP.")
    name = f"{uuid.uuid4().hex}{ext}"
    if _bucket:
        blob = _bucket.blob(f"{folder}/{name}")
        blob.upload_from_file(file, content_type=file.mimetype)
        blob.make_public()
        return blob.public_url
    path = os.path.join(os.path.dirname(__file__), "static", "uploads", name)
    file.save(path)
    return f"/static/uploads/{name}"
