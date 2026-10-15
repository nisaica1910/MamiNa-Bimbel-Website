import os, datetime as dt
from functools import wraps
from urllib.parse import quote
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, redirect, url_for, flash, session
import config
from db import store, upload_image, DEMO

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-ganti-ini")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]


# ---------- helpers ----------
def wa_link(phone, text=""):
    p = "".join(c for c in str(phone) if c.isdigit())
    if p.startswith("0"):
        p = "62" + p[1:]
    return f"https://wa.me/{p}" + (f"?text={quote(text)}" if text else "")


@app.template_filter("rupiah")
def rupiah(n):
    return "Rp" + f"{int(n or 0):,}".replace(",", ".")


@app.template_filter("bulan")
def bulan(ym):
    y, m = ym.split("-")
    return f"{BULAN[int(m) - 1]} {y}"


@app.context_processor
def inject():
    return dict(cfg=config, wa_link=wa_link, demo=DEMO, is_admin=session.get("admin"))


def classes_with_quota():
    students = [s for s in store.all("students") if s.get("active", True)]
    out = []
    for c in sorted(store.all("classes"), key=lambda c: c.get("created", 0)):
        c["terisi"] = sum(1 for s in students if s.get("class_id") == c["id"])
        c["sisa"] = max(int(c.get("quota", 0)) - c["terisi"], 0)
        out.append(c)
    return out


def admin_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if not session.get("admin"):
            return redirect(url_for("login", next=request.path))
        return f(*a, **k)
    return wrap


def seed_demo():
    if not DEMO or store.all("classes"):
        return
    ids = {}
    for i, (n, age, dur, price, jadwal, q) in enumerate([
        ("Mewarnai Basic", "Anak-anak", "1 jam", 20000, "Hubungi WA untuk jadwal", 8),
        ("Mewarnai Lanjutan", "Anak-anak", "1 jam", 25000, "Hubungi WA untuk jadwal", 8),
        ("Menggambar", "Anak-anak", "1 jam", 25000, "Setiap Senin, 16.00", 8)]):
        ids[n] = store.add("classes", dict(name=n, age=age, duration=dur, price=price, schedule=jadwal, quota=q, color=["pink", "butter", "mint"][i]))
    for n, p, c in [("Kayla", "081200000001", "Mewarnai Basic"), ("Raka", "081200000002", "Mewarnai Lanjutan"), ("Naura", "081200000003", "Menggambar")]:
        store.add("students", dict(name=n, parent="Orang tua " + n, phone=p, class_id=ids[c], active=True))


seed_demo()


# ---------- publik ----------
@app.route("/")
def index():
    karya = sorted(store.all("artworks"), key=lambda a: -a.get("created", 0))[:6]
    return render_template("index.html", classes=classes_with_quota(), karya=karya)


@app.route("/galeri")
def galeri():
    kelas = request.args.get("kelas", "")
    classes = classes_with_quota()
    names = {c["id"]: c["name"] for c in classes}
    items = sorted(store.all("artworks"), key=lambda a: -a.get("created", 0))
    if kelas:
        items = [a for a in items if a.get("class_id") == kelas]
    return render_template("galeri.html", items=items, classes=classes, names=names, kelas=kelas)


@app.route("/daftar", methods=["GET", "POST"])
def daftar():
    classes = classes_with_quota()
    if request.method == "POST":
        f = request.form
        if not all(f.get(k, "").strip() for k in ("child", "age", "parent", "phone", "class_id")):
            flash("Semua kolom wajib diisi ya.", "error")
        else:
            c = next((c for c in classes if c["id"] == f["class_id"]), None)
            store.add("registrations", dict(child=f["child"].strip(), age=f["age"], parent=f["parent"].strip(),
                                            phone=f["phone"].strip(), class_id=f["class_id"],
                                            class_name=c["name"] if c else "-", status="baru", note=f.get("note", "")))
            msg = f"Halo kak, saya {f['parent']}. Baru daftarkan {f['child']} ({f['age']} th) untuk kelas {c['name'] if c else ''}."
            return render_template("sukses.html", child=f["child"], wa=wa_link(config.WHATSAPP, msg))
    return render_template("daftar.html", classes=classes, pre=request.args.get("kelas", ""))


# ---------- admin ----------
@app.route("/admin/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Password salah.", "error")
    return render_template("admin/login.html")


@app.route("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def dashboard():
    ym = dt.date.today().strftime("%Y-%m")
    students = [s for s in store.all("students") if s.get("active", True)]
    pay = [p for p in store.all("payments") if p.get("month") == ym and p.get("status") == "lunas"]
    stats = dict(
        baru=sum(1 for r in store.all("registrations") if r.get("status") == "baru"),
        murid=len(students),
        belum=len(students) - len(pay),
        masuk=sum(int(p.get("amount", 0)) for p in pay),
    )
    return render_template("admin/dashboard.html", stats=stats, ym=ym, classes=classes_with_quota())


@app.route("/admin/pendaftar")
@admin_required
def pendaftar():
    rows = sorted(store.all("registrations"), key=lambda r: -r.get("created", 0))
    return render_template("admin/pendaftar.html", rows=rows)


@app.route("/admin/pendaftar/<id>/<aksi>", methods=["POST"])
@admin_required
def pendaftar_aksi(id, aksi):
    r = store.get("registrations", id)
    if not r:
        return redirect(url_for("pendaftar"))
    if aksi == "terima":
        c = next((c for c in classes_with_quota() if c["id"] == r["class_id"]), None)
        if not c or c["sisa"] <= 0:
            flash("Kuota kelas penuh. Tambah kuota di menu Kelas dulu.", "error")
        else:
            store.add("students", dict(name=r["child"], age=r["age"], parent=r["parent"], phone=r["phone"], class_id=r["class_id"], active=True))
            store.update("registrations", id, {"status": "diterima"})
            flash(f"{r['child']} sudah jadi murid.", "ok")
    elif aksi == "tolak":
        store.update("registrations", id, {"status": "ditolak"})
    elif aksi == "hapus":
        store.delete("registrations", id)
    return redirect(url_for("pendaftar"))


@app.route("/admin/kelas", methods=["GET", "POST"])
@admin_required
def kelas():
    if request.method == "POST":
        f = request.form
        data = dict(name=f["name"], age=f["age"], duration=f["duration"], price=int(f["price"] or 0),
                    schedule=f["schedule"], quota=int(f["quota"] or 0), color=f["color"])
        if f.get("id"):
            store.update("classes", f["id"], data)
        else:
            store.add("classes", data)
        flash("Kelas disimpan.", "ok")
        return redirect(url_for("kelas"))
    edit = store.get("classes", request.args["edit"]) if request.args.get("edit") else None
    return render_template("admin/kelas.html", classes=classes_with_quota(), edit=edit)


@app.route("/admin/kelas/<id>/hapus", methods=["POST"])
@admin_required
def kelas_hapus(id):
    store.delete("classes", id)
    return redirect(url_for("kelas"))


@app.route("/admin/murid", methods=["GET", "POST"])
@admin_required
def murid():
    classes = classes_with_quota()
    if request.method == "POST":
        f = request.form
        store.add("students", dict(name=f["name"], age=f.get("age", ""), parent=f["parent"], phone=f["phone"], class_id=f["class_id"], active=True))
        flash("Murid ditambahkan.", "ok")
        return redirect(url_for("murid"))
    names = {c["id"]: c["name"] for c in classes}
    rows = sorted(store.all("students"), key=lambda s: s.get("name", "").lower())
    return render_template("admin/murid.html", rows=rows, classes=classes, names=names)


@app.route("/admin/murid/<id>/<aksi>", methods=["POST"])
@admin_required
def murid_aksi(id, aksi):
    s = store.get("students", id)
    if s and aksi == "toggle":
        store.update("students", id, {"active": not s.get("active", True)})
    elif aksi == "hapus":
        store.delete("students", id)
    return redirect(url_for("murid"))


@app.route("/admin/absensi", methods=["GET", "POST"])
@admin_required
def absensi():
    classes = classes_with_quota()
    kid = request.values.get("kelas") or (classes[0]["id"] if classes else "")
    tgl = request.values.get("tanggal") or dt.date.today().isoformat()
    students = sorted([s for s in store.all("students") if s.get("class_id") == kid and s.get("active", True)], key=lambda s: s["name"].lower())
    doc_id = f"{kid}_{tgl}"
    if request.method == "POST" and request.form.get("simpan"):
        rec = {s["id"]: request.form.get(f"s_{s['id']}", "hadir") for s in students}
        store.add("attendance", dict(class_id=kid, date=tgl, records=rec), id=doc_id)
        flash("Absensi tersimpan.", "ok")
    saved = (store.get("attendance", doc_id) or {}).get("records", {})
    return render_template("admin/absensi.html", classes=classes, kid=kid, tgl=tgl, students=students, saved=saved)


@app.route("/admin/spp", methods=["GET", "POST"])
@admin_required
def spp():
    ym = request.values.get("bulan") or dt.date.today().strftime("%Y-%m")
    classes = {c["id"]: c for c in classes_with_quota()}
    # jumlah jam = berapa kali murid berstatus "hadir" di bulan ini
    hadir = {}
    for a in store.all("attendance"):
        if str(a.get("date", "")).startswith(ym):
            for sid, st in a.get("records", {}).items():
                if st == "hadir":
                    hadir[sid] = hadir.get(sid, 0) + 1
    if request.method == "POST":
        sid = request.form["sid"]
        s = store.get("students", sid)
        doc_id = f"{sid}_{ym}"
        cur = store.get("payments", doc_id)
        if cur and cur.get("status") == "lunas":
            store.update("payments", doc_id, {"status": "belum", "amount": 0})
        elif s:
            tarif = classes.get(s.get("class_id"), {}).get("price", 0)
            store.add("payments", dict(student_id=sid, month=ym, status="lunas", amount=tarif * hadir.get(sid, 0),
                                       paid_on=dt.date.today().isoformat()), id=doc_id)
        return redirect(url_for("spp", bulan=ym))
    paid = {p["student_id"]: p for p in store.all("payments") if p.get("month") == ym and p.get("status") == "lunas"}
    rows = []
    for s in sorted([s for s in store.all("students") if s.get("active", True)], key=lambda s: s["name"].lower()):
        c = classes.get(s.get("class_id"), {})
        tarif, jam = c.get("price", 0), hadir.get(s["id"], 0)
        msg = (f"Halo {s['parent']}, rincian biaya kelas {c.get('name', '')} bulan {bulan(ym)} untuk {s['name']}: "
               f"{jam} jam x {rupiah(tarif)} = {rupiah(tarif * jam)}. Pembayaran bisa {config.PEMBAYARAN}. Terima kasih 🙏")
        rows.append(dict(s=s, kelas=c.get("name", "-"), tarif=tarif, jam=jam, tagihan=tarif * jam,
                         lunas=s["id"] in paid, wa=wa_link(s["phone"], msg)))
    total = sum(int(p.get("amount", 0)) for p in paid.values())
    return render_template("admin/spp.html", rows=rows, ym=ym, total=total)


@app.route("/admin/karya", methods=["GET", "POST"])
@admin_required
def karya():
    classes = classes_with_quota()
    if request.method == "POST":
        files = [f for f in request.files.getlist("foto") if f.filename]
        try:
            for f in files:
                store.add("artworks", dict(title=request.form.get("title") or "Tanpa judul", child=request.form.get("child", ""),
                                           class_id=request.form.get("class_id", ""), url=upload_image(f)))
            flash(f"{len(files)} karya diunggah.", "ok")
        except Exception as e:
            flash(str(e), "error")
        return redirect(url_for("karya"))
    items = sorted(store.all("artworks"), key=lambda a: -a.get("created", 0))
    return render_template("admin/karya.html", items=items, classes=classes)


@app.route("/admin/karya/<id>/hapus", methods=["POST"])
@admin_required
def karya_hapus(id):
    store.delete("artworks", id)
    return redirect(url_for("karya"))


if __name__ == "__main__":
    app.run(debug=True, port=int(os.getenv("PORT", 5001)))
