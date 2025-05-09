import os
from pathlib import Path
import io # Untuk menulis ke string

# Tentukan nama folder root aplikasi Anda
APP_FOLDER_NAME = "app"

# Definisikan struktur folder
STRUCTURE = (
    APP_FOLDER_NAME, [
        ("__init__.py"), # Tambah __init__.py untuk app
        ( "api", [
            ( "v1", [
                "api.py",
                ( "endpoints", [
                    "auth.py",
                    "borrowings.py",
                    "categories.py",
                    "items.py",
                    "reports.py",
                    "users.py",
                ]),
            ]),
        ]),
        ( "core", [
            "availability.py",
            "config.py",
            "rate_limiter.py",
            "security.py",
            "utils.py",
        ]),
        ( "db", [
            "database.py",
        ]),
        ( "dto", [
            "token.py",
            # "refs.py", # Opsional
        ]),
        ( "middleware", [
            "authentication.py",
            "logging.py",
        ]),
        ( "models", [
            "borrowing.py",
            "category.py",
            "counter.py",
            "item.py",
            "user.py",
            # Pindahkan skema Pydantic ke sini atau biarkan nested (tergantung pilihan akhir)
            # "category_schemas.py",
            # "item_schemas.py", ...
        ]),
        ( "scheduler", [ # Jika pakai scheduler
             "jobs.py",
        ]),
        ( "variables", [
             "enums.py",
        ]),
        "main.py",
    ]
)

# File-file root proyek
ROOT_FILES = [
    ".env",
    ".gitignore",
    "requirements.txt",
    "README.md",
]

# --- Fungsi Pembuat Struktur Folder/File ---
def create_structure(base_path: Path, structure_data):
    """Membuat folder dan file __init__.py secara rekursif."""
    # Logika sama seperti sebelumnya untuk membuat folder dan file
    name = structure_data[0] if isinstance(structure_data, tuple) else structure_data
    current_path = base_path / name

    if isinstance(structure_data, tuple) and len(structure_data) > 1: # Ini folder
        content = structure_data[1]
        current_path.mkdir(parents=True, exist_ok=True)
        init_file = current_path / "__init__.py"
        if not init_file.exists():
             init_file.touch(exist_ok=True)
             print(f"Created File   : {init_file}")
        else:
             print(f"Skipped Init : {init_file} (exists)")
        print(f"Verified Folder: {current_path}{os.sep}")
        for item in content:
            create_structure(current_path, item)
    elif isinstance(structure_data, str): # Ini file
         file_path = current_path # Nama file sudah digabung di atas
         if not file_path.exists():
              file_path.touch(exist_ok=True)
              print(f"Created File   : {file_path}")
         else:
              print(f"Skipped File   : {file_path} (exists)")
    else: # Handle kasus nama folder tanpa isi
         current_path.mkdir(parents=True, exist_ok=True)
         init_file = current_path / "__init__.py"
         if not init_file.exists():
              init_file.touch(exist_ok=True)
              print(f"Created File   : {init_file}")
         else:
             print(f"Skipped Init : {init_file} (exists)")
         print(f"Verified Folder: {current_path}{os.sep}")


# --- Fungsi Pembuat Teks Struktur Pohon ---
def generate_tree_string(structure_data, indent="", is_last=True, output_buffer=None):
    """Membuat representasi teks pohon struktur folder."""
    if output_buffer is None:
        output_buffer = io.StringIO()

    name = structure_data[0] if isinstance(structure_data, tuple) else structure_data
    connector = "└── " if is_last else "├── "

    output_buffer.write(f"{indent}{connector}{name}\n")

    if isinstance(structure_data, tuple) and len(structure_data) > 1: # Jika folder
        content = structure_data[1]
        new_indent = indent + ("    " if is_last else "│   ")
        # Tambahkan __init__.py secara manual ke representasi pohon
        has_init = any(item == "__init__.py" for item in content if isinstance(item, str))
        if not has_init and name != APP_FOLDER_NAME: # Jangan tambah di root app jika sdh ada
             content_with_init = ["__init__.py"] + content # Taruh di awal
        else:
             content_with_init = content

        for i, item in enumerate(content_with_init):
            is_item_last = i == (len(content_with_init) - 1)
            generate_tree_string(item, new_indent, is_item_last, output_buffer)

    return output_buffer # Kembalikan buffer saat selesai

# --- Fungsi Utama ---
if __name__ == "__main__":
    project_root = Path(".")
    print(f"Generating project structure in: {project_root.resolve()}")

    # --- Buat Struktur Folder & File ---
    print("\nCreating folders and files...")
    # Buat folder app utama dan __init__.py nya dulu
    app_path = project_root / APP_FOLDER_NAME
    app_path.mkdir(parents=True, exist_ok=True)
    init_file_app = app_path / "__init__.py"
    if not init_file_app.exists(): init_file_app.touch(exist_ok=True); print(f"Created File   : {init_file_app}")
    else: print(f"Skipped Init : {init_file_app} (exists)")
    print(f"Verified Folder: {app_path}{os.sep}")

    # Proses isi folder app
    app_content = STRUCTURE[1]
    for item in app_content:
         create_structure(app_path, item)

    # Buat file-file di root
    print("\nCreating root files...")
    for file_name in ROOT_FILES:
        file_path = project_root / file_name
        if not file_path.exists():
            file_path.touch(exist_ok=True)
            print(f"Created File   : {file_path}")
        else:
            print(f"Skipped File   : {file_path} (exists)")

    # --- Generate Struktur Pohon untuk README.md ---
    print("\nGenerating structure tree for README.md...")
    tree_buffer = io.StringIO()
    # Tulis header pohon
    tree_buffer.write(f"{project_root.name}/ (Project Root)\n") # Tampilkan nama folder proyek
    # Generate pohon untuk struktur 'app'
    app_tree_buffer = generate_tree_string(STRUCTURE)
    # Tambahkan indentasi untuk isi 'app'
    for line in app_tree_buffer.getvalue().splitlines():
         tree_buffer.write(f"{line}\n") # Langsung tulis, generate_tree_string sudah handle indent
    # Tambahkan file root
    for i, file_name in enumerate(sorted(ROOT_FILES)): # Urutkan agar rapi
        connector = "└── " if i == (len(ROOT_FILES) - 1) else "├── "
        tree_buffer.write(f"{connector}{file_name}\n")

    tree_string = tree_buffer.getvalue()
    print("\n--- Generated Structure Tree ---")
    print(tree_string)
    print("--------------------------------")

    # --- Tulis ke README.md ---
    readme_path = project_root / "README.md"
    try:
        # Mode 'w' akan menimpa file jika sudah ada
        # Gunakan mode 'a' (append) jika ingin menambahkan di akhir file yang ada
        with open(readme_path, "w", encoding="utf-8") as f: # Ganti ke 'a' jika perlu append
             # Tambahkan header atau konten lain sebelum pohon struktur
             f.write("# Aplikasi Inventaris Backend dengan FastAPI\n\n")
             f.write("(Konten README lainnya bisa ditambahkan di sini...)\n\n")
             f.write("## Struktur Proyek\n\n")
             f.write("```\n") # Blok kode markdown
             f.write(tree_string)
             f.write("```\n\n")
             f.write("(Penjelasan lebih lanjut tentang setup, API, dll...)\n")
        print(f"Successfully wrote structure tree to {readme_path}")
    except IOError as e:
        print(f"Error writing to {readme_path}: {e}")


    print("\nStructure generation complete.")