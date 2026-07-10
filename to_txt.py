# FILE: dump_project.py
import re
from pathlib import Path
from datetime import datetime

# Назва вихідного файлу
OUTPUT_FILE = "code_dump_clean.txt"

# Посилання на поточну директорію, де запущено скрипт
ROOT = Path(__file__).resolve().parent

# Регулярний вираз для очищення ANSI/escape символів
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# Папки та розширення файлів, які ОБОВ'ЯЗКОВО потрібно ігнорувати
IGNORE_DIRS = {
    "venv", ".venv", ".tmp_venv", "env", "bin", "lib", "lib64", "include", "share",
    ".git", "__pycache__", ".idea", ".vscode", "node_modules", "static", "media"
}

IGNORE_EXTENSIONS = {
    ".db", ".sqlite", ".sqlite3", ".pyc", ".pyo", ".pyd", ".png", ".jpg", 
    ".jpeg", ".gif", ".ico", ".tar", ".gz", ".zip", ".rar", ".exe", ".bin"
}

IGNORE_FILES = {
    OUTPUT_FILE, "dump_project.py", "poetry.lock", "Pipfile.lock", ".DS_Store"
}

def should_include(path: Path) -> bool:
    """Визначає, чи є файл частиною твого коду, а не системним сміттям."""
    # Перевірка на ігнорування папок
    for part in path.parts:
        if part in IGNORE_DIRS:
            return False
            
    # Перевірка на розширення файлу
    if path.suffix in IGNORE_EXTENSIONS:
        return False
        
    # Перевірка на конкретні назви файлів
    if path.name in IGNORE_FILES:
        return False
        
    return True

def read_file_safely(path: Path) -> str:
    """Безпечно читає текстовий вміст, ігноруючи бінарні помилки кодування."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if '\x1b' in content:
            content = ANSI_ESCAPE.sub('', content)
        return content
    except Exception as e:
        return f"[Помилка читання файлу: {e}]"

def main():
    # Збираємо всі файли у проєкті recursively
    all_files = sorted(list(ROOT.rglob("*")))
    valid_files = [p for p in all_files if p.is_file() and should_include(p)]

    if not valid_files:
        print("⚠️ Жодного файлу власного коду не знайдено. Перевір розташування скрипту.")
        return

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write(f"# Дамп структури та коду проєкту від {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        out.write(f"# Всього файлів власного коду у дампі: {len(valid_files)}\n\n")
        out.write("=" * 60 + "\n\n")

        # Спочатку запишемо список усіх знайдених файлів для контексту структури проєкту
        out.write("## 📂 СТРУКТУРА ПРОЄКТУ:\n```text\n")
        for path in valid_files:
            out.write(f"- {path.relative_to(ROOT)}\n")
        out.write("```\n\n" + "=" * 60 + "\n\n")

        # Тепер записуємо вміст кожного файлу
        for path in valid_files:
            rel_path = path.relative_to(ROOT)
            suffix = path.suffix.lstrip('.') if path.suffix else ""
            
            print(f"📦 Додаю: {rel_path}")
            
            # Використовуємо Markdown заголовки третього рівня та блоки коду із вказівкою мови
            out.write(f"### FILE: {rel_path}\n")
            out.write(f"```{suffix}\n")
            out.write(read_file_safely(path))
            out.write("\n```\n\n---\n\n")

    print(f"\n🚀 Успішно! Весь чистий код твого проєкту збережено у: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()