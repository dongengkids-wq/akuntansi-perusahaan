from flask import Flask, render_template, request, redirect, url_for, flash
from supabase import create_client
from config import Config
from datetime import date
import calendar
import uuid
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.config.from_object(Config)

supabase = create_client(app.config["SUPABASE_URL"], app.config["SUPABASE_KEY"])

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


class User(UserMixin):
    def __init__(self, id, username, nama):
        self.id = id
        self.username = username
        self.nama = nama


@login_manager.user_loader
def load_user(user_id):
    data = supabase.table("users").select("*").eq("id", user_id).single().execute().data
    if data:
        return User(data["id"], data["username"], data.get("nama"))
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        data = supabase.table("users").select("*").eq("username", username).execute().data
        if data and check_password_hash(data[0]["password_hash"], password):
            user = User(data[0]["id"], data[0]["username"], data[0].get("nama"))
            login_user(user)
            flash("Berhasil login.", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))
        flash("Username atau password salah.", "error")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Berhasil logout.", "success")
    return redirect(url_for("login"))


def get_bulan_terakhir(n=6):
    bulan_list = []
    today = date.today()
    y, m = today.year, today.month
    for i in range(n):
        bulan_list.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    bulan_list.reverse()
    return bulan_list


@app.route("/")
@login_required
def dashboard():
    transaksi = supabase.table("transaksi").select("*").order("tanggal", desc=True).limit(10).execute().data
    total_masuk = supabase.table("transaksi").select("jumlah").eq("jenis", "masuk").execute().data
    total_keluar = supabase.table("transaksi").select("jumlah").eq("jenis", "keluar").execute().data

    sum_masuk = sum(t["jumlah"] for t in total_masuk)
    sum_keluar = sum(t["jumlah"] for t in total_keluar)
    saldo = sum_masuk - sum_keluar

    bulan_list = get_bulan_terakhir(6)
    awal = date(bulan_list[0][0], bulan_list[0][1], 1)
    akhir_tahun, akhir_bulan = bulan_list[-1]
    akhir_hari = calendar.monthrange(akhir_tahun, akhir_bulan)[1]
    akhir = date(akhir_tahun, akhir_bulan, akhir_hari)

    data_chart = supabase.table("transaksi").select("tanggal, jenis, jumlah") \
        .gte("tanggal", str(awal)).lte("tanggal", str(akhir)).execute().data

    chart_labels = []
    chart_masuk = []
    chart_keluar = []
    nama_bulan = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Ags", "Sep", "Okt", "Nov", "Des"]

    for (y, m) in bulan_list:
        chart_labels.append(f"{nama_bulan[m]} {y}")
        key = f"{y}-{m:02d}"
        total_m = sum(t["jumlah"] for t in data_chart if t["jenis"] == "masuk" and t["tanggal"][:7] == key)
        total_k = sum(t["jumlah"] for t in data_chart if t["jenis"] == "keluar" and t["tanggal"][:7] == key)
        chart_masuk.append(total_m)
        chart_keluar.append(total_k)

    return render_template("dashboard.html",
                           transaksi=transaksi,
                           sum_masuk=sum_masuk,
                           sum_keluar=sum_keluar,
                           saldo=saldo,
                           chart_labels=chart_labels,
                           chart_masuk=chart_masuk,
                           chart_keluar=chart_keluar)


def upload_bukti(file):
    if not file or file.filename == "":
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower()
    nama_file = f"{uuid.uuid4()}.{ext}"
    file_bytes = file.read()
    supabase.storage.from_("bukti-transaksi").upload(
        nama_file, file_bytes, {"content-type": file.content_type}
    )
    url = supabase.storage.from_("bukti-transaksi").get_public_url(nama_file)
    url = url.rstrip("?")
    return url


@app.route("/transaksi")
@login_required
def list_transaksi():
    data = supabase.table("transaksi").select("*, kategori(nama)").order("tanggal", desc=True).execute().data
    return render_template("transaksi/list.html", transaksi=data)


@app.route("/transaksi/tambah", methods=["GET", "POST"])
@login_required
def tambah_transaksi():
    kategori_list = supabase.table("kategori").select("*").execute().data

    if request.method == "POST":
        bukti_url = upload_bukti(request.files.get("bukti"))

        supabase.table("transaksi").insert({
            "tanggal": request.form.get("tanggal") or str(date.today()),
            "jenis": request.form["jenis"],
            "kategori_id": request.form["kategori_id"],
            "jumlah": float(request.form["jumlah"]),
            "keterangan": request.form.get("keterangan"),
            "metode": request.form.get("metode", "cash"),
            "bukti_url": bukti_url,
        }).execute()
        flash("Transaksi berhasil disimpan.", "success")
        return redirect(url_for("list_transaksi"))

    return render_template("transaksi/form.html", kategori_list=kategori_list)


@app.route("/transaksi/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_transaksi(id):
    kategori_list = supabase.table("kategori").select("*").execute().data

    if request.method == "POST":
        data_update = {
            "tanggal": request.form["tanggal"],
            "jenis": request.form["jenis"],
            "kategori_id": request.form["kategori_id"],
            "jumlah": float(request.form["jumlah"]),
            "keterangan": request.form.get("keterangan"),
            "metode": request.form.get("metode", "cash"),
        }
        bukti_url_baru = upload_bukti(request.files.get("bukti"))
        if bukti_url_baru:
            data_update["bukti_url"] = bukti_url_baru

        supabase.table("transaksi").update(data_update).eq("id", id).execute()
        flash("Transaksi berhasil diperbarui.", "success")
        return redirect(url_for("list_transaksi"))

    data = supabase.table("transaksi").select("*").eq("id", id).single().execute().data
    return render_template("transaksi/form.html", kategori_list=kategori_list, transaksi=data)


@app.route("/transaksi/hapus/<int:id>", methods=["POST"])
@login_required
def hapus_transaksi(id):
    supabase.table("transaksi").delete().eq("id", id).execute()
    flash("Transaksi berhasil dihapus.", "success")
    return redirect(url_for("list_transaksi"))


@app.route("/kategori", methods=["GET", "POST"])
@login_required
def kategori():
    if request.method == "POST":
        supabase.table("kategori").insert({
            "nama": request.form["nama"],
            "jenis": request.form["jenis"],
        }).execute()
        return redirect(url_for("kategori"))

    data = supabase.table("kategori").select("*").execute().data
    return render_template("kategori/list.html", kategori=data)


@app.route("/laporan")
@login_required
def laporan():
    bulan = request.args.get("bulan")
    query = supabase.table("transaksi").select("*, kategori(nama)")
    if bulan:
        tahun, bln = map(int, bulan.split("-"))
        hari_terakhir = calendar.monthrange(tahun, bln)[1]
        query = query.gte("tanggal", f"{bulan}-01").lte("tanggal", f"{bulan}-{hari_terakhir:02d}")
    transaksi = query.order("tanggal").execute().data

    rekap = {}
    for t in transaksi:
        nama_kat = t["kategori"]["nama"] if t.get("kategori") else "Tanpa Kategori"
        key = (nama_kat, t["jenis"])
        rekap[key] = rekap.get(key, 0) + t["jumlah"]

    total_masuk = sum(t["jumlah"] for t in transaksi if t["jenis"] == "masuk")
    total_keluar = sum(t["jumlah"] for t in transaksi if t["jenis"] == "keluar")

    return render_template("laporan.html",
                           rekap=rekap,
                           total_masuk=total_masuk,
                           total_keluar=total_keluar,
                           bulan=bulan)


if __name__ == "__main__":
    app.run(debug=True)