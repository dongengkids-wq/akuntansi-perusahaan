from supabase import create_client
from config import Config
from werkzeug.security import generate_password_hash
import getpass

supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)

username = input("Username: ").strip()
nama = input("Nama lengkap: ").strip()
password = getpass.getpass("Password: ").strip()

if not username or not password:
    print("Username dan password tidak boleh kosong. Dibatalkan.")
    exit(1)

supabase.table("users").insert({
    "username": username,
    "nama": nama,
    "password_hash": generate_password_hash(password),
}).execute()

print(f"User '{username}' berhasil dibuat.")