import os
from pathlib import Path


PROJECT_DIR = Path("GYM_BOT")
OUTPUT_FILE = "gym_bot_dump.txt"

# Що не додавати
IGNORE_DIRS = {
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
    "venv",
    ".venv",
    "node_modules",
}

IGNORE_FILES = {
    ".pyc",
    ".db",
    ".sqlite",
    ".sqlite3",
}


def should_ignore(path: Path):

    # Папки
    for part in path.parts:
        if part in IGNORE_DIRS:
            return True

    # Файли
    if path.suffix in IGNORE_FILES:
        return True

    return False


def export_project():

    if not PROJECT_DIR.exists():
        print("❌ Папка GYM_BOT не знайдена")
        return


    files = []

    for root, dirs, filenames in os.walk(PROJECT_DIR):

        # видаляємо ігноровані папки
        dirs[:] = [
            d for d in dirs
            if d not in IGNORE_DIRS
        ]

        for filename in filenames:

            path = Path(root) / filename

            if should_ignore(path):
                continue

            files.append(path)


    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as dump:

        dump.write(
            "=" * 80 +
            "\nGYM_BOT PROJECT DUMP\n" +
            "=" * 80 +
            "\n\n"
        )


        for file in sorted(files):

            relative = file.relative_to(PROJECT_DIR)

            dump.write(
                "\n\n" +
                "=" * 80 +
                "\nFILE: " +
                str(relative) +
                "\n" +
                "=" * 80 +
                "\n\n"
            )


            try:
                content = file.read_text(
                    encoding="utf-8"
                )

                dump.write(content)

            except Exception as e:

                dump.write(
                    f"\n[ERROR READING FILE: {e}]"
                )


    print(
        f"✅ Готово! Створено {OUTPUT_FILE}"
    )

    print(
        f"📦 Файлів експортовано: {len(files)}"
    )


if __name__ == "__main__":
    export_project()