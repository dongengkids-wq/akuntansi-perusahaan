from flask import Flask, render_template, request, redirect, url_for, flash
from supabase import create_client
from config import Config
from datetime import date
import calendar
import uuid

app = Flask(__name__)
app.config.from_object(Config)

supabase = create_client(app.config["SUPABASE_URL"], app.config["SUPABASE_KEY"])

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
def dashboard():
    # Hitung total masuk, keluar, dan saldo
    transaksi = supabase.table("transaksi").select("*").order("tanggal", desc=True).limit(10).execute().data
    total_masuk = supabase.table("transaksi").select("jumlah").eq("jenis", "masuk").execute().data
    total_keluar = supabase.table("transaksi").select("jumlah").eq("jenis", "keluar").execute().data

    sum_masuk = sum(t["jumlah"] for t in total_masuk)
    sum_keluar = sum(t["jumlah"] for t in total_keluar)
    saldo = sum_masuk - sum_keluar

    # Data untuk chart tren 6 bulan terakhir
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

@app.route("/transaksi")
def list_transaksi():
    data = supabase.table("transaksi").select("*, kategori(nama)").order("tanggal", desc=True).execute().data
    return render_template("transaksi/list.html", transaksi=data)

def upload_bukti(file):
    """Upload file bukti ke Supabase Storage, return URL publik atau None."""
    if not file or file.filename == "":
        return None

    ext = file.filename.rsplit(".", 1)[-1].lower()
    nama_file = f"{uuid.uuid4()}.{ext}"

    file_bytes = file.read()
    supabase.storage.from_("bukti-transaksi").upload(
        nama_file, file_bytes, {"content-type": file.content_type}
    )
    url = supabase.storage.from_("bukti-transaksi").get_public_url(nama_file)
    return url

@app.route("/transaksi/tambah", methods=["GET", "POST"])
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
def hapus_transaksi(id):
    supabase.table("transaksi").delete().eq("id", id).execute()
    flash("Transaksi berhasil dihapus.", "success")
    return redirect(url_for("list_transaksi"))

import calendar

@app.route("/laporan")
def laporan():
    bulan = request.args.get("bulan")  # format: YYYY-MM
    query = supabase.table("transaksi").select("*, kategori(nama)")
    if bulan:
        tahun, bln = map(int, bulan.split("-"))
        hari_terakhir = calendar.monthrange(tahun, bln)[1]  # jumlah hari yg benar di bulan itu
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

@app.route("/kategori", methods=["GET", "POST"])
def kategori():
    if request.method == "POST":
        supabase.table("kategori").insert({
            "nama": request.form["nama"],
            "jenis": request.form["jenis"],
        }).execute()
        return redirect(url_for("kategori"))

    data = supabase.table("kategori").select("*").execute().data
    return render_template("kategori/list.html", kategori=data)

if __name__ == "__main__":
    app.run(debug=True)