#!/usr/bin/env python3
"""
push_to_github.py — швидко залити всі файли проєкту на GitHub.
Запускати з кореня проєкту (де лежить .git або де його треба ініціалізувати).
"""

import subprocess
import sys
import os

REPO_URL = "https://github.com/hdxy16/servbot.git"
BRANCH = "main"

# Файли/папки, які НІКОЛИ не повинні потрапити в git (секрети, сміття)
GITIGNORE_CONTENT = """\
.env
__pycache__/
*.pyc
venv/
.venv/
*.db
*.sqlite3
code_dump*.txt
"""


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        if check:
            sys.exit(f"❌ Команда провалилась: {' '.join(cmd)}")
    return result


def ensure_gitignore():
    if not os.path.exists(".gitignore"):
        with open(".gitignore", "w", encoding="utf-8") as f:
            f.write(GITIGNORE_CONTENT)
        print("✅ Створено .gitignore")
    else:
        with open(".gitignore", "r+", encoding="utf-8") as f:
            existing = f.read()
            missing = [line for line in GITIGNORE_CONTENT.splitlines() if line and line not in existing]
            if missing:
                f.write("\n" + "\n".join(missing) + "\n")
                print(f"✅ Додано в .gitignore: {missing}")


def main():
    if not os.path.exists(".git"):
        run(["git", "init"])
        run(["git", "branch", "-M", BRANCH])

    ensure_gitignore()

    # Перевірка, чи .env випадково вже в git-історії (важливо!)
    result = run(["git", "ls-files", ".env"], check=False)
    if result.stdout.strip():
        print("⚠️  УВАГА: .env вже відстежується git! Прибираю з індексу (файл на диску лишиться).")
        run(["git", "rm", "--cached", ".env"], check=False)

    run(["git", "add", "-A"])

    result = run(["git", "status", "--porcelain"], check=False)
    if not result.stdout.strip():
        print("ℹ️  Немає змін для коміту.")
    else:
        commit_msg = input("Опис коміту (Enter — 'update'): ").strip() or "update"
        run(["git", "commit", "-m", commit_msg])

    # Перевіряємо, чи вже є remote 'origin'
    remotes = run(["git", "remote"], check=False).stdout.split()
    if "origin" not in remotes:
        run(["git", "remote", "add", "origin", REPO_URL])
    else:
        run(["git", "remote", "set-url", "origin", REPO_URL])

    run(["git", "push", "-u", "origin", BRANCH])
    print("🚀 Готово! Код залито на GitHub.")


if __name__ == "__main__":
    main()