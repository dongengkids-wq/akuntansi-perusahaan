from flask import Flask, render_template, request, redirect, url_for, flash
from supabase import create_client
from config import Config
from datetime import date

app = Flask(__name__)
app.config.from_object(Config)

supabase = create_client(app.config["SUPABASE_URL"], app.config["SUPABASE_KEY"])

@app.route("/")
def dashboard():
    # Hitung total masuk, keluar, dan saldo
    transaksi = supabase.table("transaksi").select("*").order("tanggal", desc=True).limit(10).execute().data
    total_masuk = supabase.table("transaksi").select("jumlah").eq("jenis", "masuk").execute().data
    total_keluar = supabase.table("transaksi").select("jumlah").eq("jenis", "keluar").execute().data

    sum_masuk = sum(t["jumlah"] for t in total_masuk)
    sum_keluar = sum(t["jumlah"] for t in total_keluar)
    saldo = sum_masuk - sum_keluar

    return render_template("dashboard.html",
                           transaksi=transaksi,
                           sum_masuk=sum_masuk,
                           sum_keluar=sum_keluar,
                           saldo=saldo)

@app.route("/transaksi")
def list_transaksi():
    data = supabase.table("transaksi").select("*, kategori(nama)").order("tanggal", desc=True).execute().data
    return render_template("transaksi/list.html", transaksi=data)

@app.route("/transaksi/tambah", methods=["GET", "POST"])
def tambah_transaksi():
    kategori_list = supabase.table("kategori").select("*").execute().data

    if request.method == "POST":
        supabase.table("transaksi").insert({
            "tanggal": request.form.get("tanggal") or str(date.today()),
            "jenis": request.form["jenis"],
            "kategori_id": request.form["kategori_id"],
            "jumlah": float(request.form["jumlah"]),
            "keterangan": request.form.get("keterangan"),
            "metode": request.form.get("metode", "cash"),
        }).execute()
        flash("Transaksi berhasil disimpan.", "success")
        return redirect(url_for("list_transaksi"))

    return render_template("transaksi/form.html", kategori_list=kategori_list)

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