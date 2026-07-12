import os
from datetime import datetime

def make_gym_dump(source_folder="Gym_Bot", output_filename="gym_bot_dump.txt"):
    if not os.path.exists(source_folder):
        print(f"❌ Помилка: Папку '{source_folder}' не знайдено в поточній директорії!")
        return

    with open(output_filename, "w", encoding="utf-8") as dump:
        # Заголовок дампу
        dump.write(f"# Дамп структури та коду проєкту Gym_Bot від {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        dump.write("=" * 60 + "\n\n")

        # 1. Генеруємо дерево структури папки
        dump.write("## 📂 СТРУКТУРА ПРОЄКТУ GYM_BOT:\n```text\n")
        for root, dirs, files in os.walk(source_folder):
            if "__pycache__" in root:
                continue
            level = root.replace(source_folder, '').count(os.sep)
            indent = ' ' * 4 * level
            folder_name = os.path.basename(root)
            if folder_name == source_folder:
                dump.write(f"- {folder_name}/\n")
            else:
                dump.write(f"{indent}- {folder_name}/\n")
                
            sub_indent = ' ' * 4 * (level + 1)
            for f in sorted(files):
                if f.endswith(('.pyc', '.db', '.sqlite3')):
                    continue
                dump.write(f"{sub_indent}- {f}\n")
        dump.write("```\n\n" + "=" * 60 + "\n\n")

        # 2. Зчитуємо вміст кожного корисного файлу
        for root, dirs, files in os.walk(source_folder):
            if "__pycache__" in root:
                continue
            
            for file in sorted(files):
                # Пропускаємо бінарники, кеш та файли бази даних
                if file.endswith(('.pyc', '.db', '.sqlite3', '.png', '.jpg', '.tar.gz')):
                    continue
                
                file_path = os.path.join(root, file)
                
                dump.write(f"### FILE: {file_path}\n")
                if file.endswith('.py'):
                    dump.write("```py\n")
                elif file == ".env":
                    dump.write("```env\n")
                else:
                    dump.write("```\n")

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        dump.write(f.read())
                except Exception as e:
                    dump.write(f"# Помилка зчитування файлу: {e}\n")

                dump.write("\n```\n\n" + "---" + "\n\n")

    print(f"✅ Успішно! Фул-код джим-бота зібрано у файл: {output_filename}")

if __name__ == "__main__":
    make_gym_dump()