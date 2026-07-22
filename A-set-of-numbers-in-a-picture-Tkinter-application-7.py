
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import numpy as np
from PIL import Image, ImageTk
import os
import re
import random

# Глобальные переменные
image_data = None
canvas_img_refs = [] # ссылки на PhotoImage чтобы не удалялись
current_width = None
current_height = None

# ---------- глобальные переменные для LZW-данных ----------
lzw_data = None # строка кодов через пробел, например "0 1 0 2 5 ..."
lzw_image_shape = None # (height, width) — чтобы знать как собрать обратно


# ============================================================
# СЛОВАРИ ДЛЯ ДИАПАЗОНОВ И ОБРАТНОГО ВОССТАНОВЛЕНИЯ
# ============================================================

# Глобальные словари (сохраняются при сжатии, используются при восстановлении)
unicode_dict = {}      # {'♠': [256, 271], '♦': [512, 520], ...}
unicode_dict_rev = {}  # {'♠': [256, 257, 258, ...], ...} — развёрнутый


def get_random_unicode_symbol(exclude_set):
    """
    Возвращает случайный печатный Unicode-символ (не цифра, не буква латиницы/кириллицы),
    которого ещё нет в exclude_set.
    """
    # Пулы интересных символов
    pools = [
        range(0x2600, 0x26FF),  # Разные символы: ☀☁☂☃★☆☎☏☑☒☠☢☣☤☥☦☧☨☩☪☫☬☭☮☯
        range(0x2700, 0x27BF),  # Дингбаты: ✀✁✂✃✄✅✆✇✈✉✊✋✌✍✎✏✐✑✒✓✔✕✖✗✘✙✚✛✜✝✞✟✠✡✢✣✤✥✦✧✨✩✪✫✬✭✮✯
        range(0x1F300, 0x1F5FF), # Разные символы и пиктограммы
        range(0x1F600, 0x1F64F), # Эмодзи-лица
        range(0x1F680, 0x1F6FF), # Транспорт и символы
        range(0x25A0, 0x25FF),   # Геометрические фигуры
        range(0x2200, 0x22FF),   # Математические операторы
        range(0x2300, 0x23FF),   # Разные технические
        range(0x2100, 0x214F),   # Буквоподобные символы
    ]

    # Собираем все доступные символы из пулов
    available = []
    for pool in pools:
        for code in pool:
            try:
                ch = chr(code)
                # Пропускаем суррогаты, непечатные и управляющие
                if ch.isprintable() and ch not in exclude_set and code not in range(0xD800, 0xDFFF):
                    available.append(ch)
            except (ValueError, OverflowError):
                continue

    if not available:
        # Запасной вариант — греческие буквы
        for code in range(0x0391, 0x03C9):
            ch = chr(code)
            if ch not in exclude_set:
                available.append(ch)

    if not available:
        raise RuntimeError("Не удалось найти свободный Unicode-символ.")

    return random.choice(available)


def compress_lzw_with_ranges(codes):
    """
    Принимает список LZW-кодов.
    Находит непрерывные последовательности (от 2 чисел подряд),
    заменяет их на случайные Unicode-символы.
    Одиночные числа остаются как есть.

    Возвращает:
        compressed_str — строка (числа и символы через пробел)
        dictionary     — словарь {'♠': [start, end], ...}
    """
    if not codes:
        return "", {}

    dictionary = {}
    used_symbols = set()
    result_parts = []

    i = 0
    n = len(codes)

    while i < n:
        # Пытаемся найти последовательность начиная с i
        start = codes[i]
        j = i + 1

        # Ищем, сколько чисел идут подряд по +1
        while j < n and codes[j] == codes[j - 1] + 1:
            j += 1

        seq_len = j - i

        if seq_len >= 2:
            # Это последовательность — заменяем на Unicode-символ
            end_val = codes[j - 1] + 1  # не включительно, как range(start, end_val)
            symbol = get_random_unicode_symbol(used_symbols)
            used_symbols.add(symbol)
            dictionary[symbol] = [start, end_val]
            result_parts.append(symbol)
            i = j
        else:
            # Одиночное число — оставляем как есть
            result_parts.append(str(codes[i]))
            i += 1

    compressed_str = " ".join(result_parts)
    return compressed_str, dictionary


def decompress_ranges_to_lzw(compressed_str, dictionary):
    """
    Восстанавливает исходный список LZW-кодов из сжатой строки и словаря.
    """
    if not compressed_str.strip():
        return []

    tokens = compressed_str.split()
    result = []

    for token in tokens:
        if token in dictionary:
            start, end = dictionary[token]
            result.extend(range(start, end))
        else:
            # Обычное число
            try:
                result.append(int(token))
            except ValueError:
                raise ValueError(f"Неизвестный токен '{token}' — нет в словаре и не число.")

    return result


def compress_lzw_and_save():
    """
    Основная функция кнопки «LZW → Сжать диапазонами»:
    1. Берёт LZW-коды из текстового поля
    2. Заменяет последовательности на Unicode-символы
    3. Сохраняет сжатый файл и словарь на рабочий стол
    4. Показывает результат в табло и в отдельном окне
    """
    global unicode_dict, unicode_dict_rev

    txt = text_widget.get("1.0", tk.END).strip()
    if not txt:
        # Если табло пусто, пробуем взять из lzw_data
        if lzw_data is not None:
            txt = lzw_data
        else:
            messagebox.showwarning("Пусто", "Нет LZW-кодов. Сначала выполните «RGB → LZW» или вставьте коды в табло.")
            return

    # Парсим числа
    try:
        codes = [int(x) for x in re.split(r'[\s,]+', txt) if x.strip()]
    except ValueError as e:
        messagebox.showerror("Ошибка", f"Не удалось распознать числа:\n{e}")
        return

    if not codes:
        messagebox.showwarning("Пусто", "Не найдено ни одного числа.")
        return

    # Сжимаем
    compressed_str, dictionary = compress_lzw_with_ranges(codes)

    unicode_dict = dictionary
    # Строим развёрнутый словарь для удобства
    unicode_dict_rev = {}
    for sym, (start, end) in dictionary.items():
        unicode_dict_rev[sym] = list(range(start, end))

    # Сохраняем на рабочий стол
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")

    # Имя файла: LZW_compressed_{timestamp}.txt (или просто фиксированное)
    compressed_path = os.path.join(desktop, "LZW_compressed.txt")
    dict_path = os.path.join(desktop, "LZW_dictionary.txt")

    counter = 1
    while os.path.exists(compressed_path) or os.path.exists(dict_path):
        compressed_path = os.path.join(desktop, f"LZW_compressed_{counter}.txt")
        dict_path = os.path.join(desktop, f"LZW_dictionary_{counter}.txt")
        counter += 1

    try:
        with open(compressed_path, "w", encoding="utf-8") as f:
            f.write(compressed_str)

        with open(dict_path, "w", encoding="utf-8") as f:
            f.write("# Словарь диапазонов: символ -> [начало, конец)\n")
            f.write("# Формат: символ [начало, конец)\n\n")
            for sym, (start, end) in dictionary.items():
                f.write(f"{sym} [{start}, {end})\n")
    except Exception as e:
        messagebox.showerror("Ошибка сохранения", f"Не удалось сохранить файлы:\n{e}")
        return

    # Показываем сжатый текст в табло
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", compressed_str)

    # Окно с результатами
    result_win = tk.Toplevel(root)
    result_win.title("Результат сжатия диапазонами")
    result_win.geometry("700x500")

    result_text = tk.Text(result_win, wrap=tk.WORD, font=("Consolas", 11))
    r_yscroll = tk.Scrollbar(result_win, orient=tk.VERTICAL, command=result_text.yview)
    result_text.configure(yscrollcommand=r_yscroll.set)
    r_yscroll.pack(side=tk.RIGHT, fill=tk.Y)
    result_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    result_text.insert(tk.END, "=== СЖАТИЕ LZW-КОДОВ ДИАПАЗОНАМИ ===\n\n")
    result_text.insert(tk.END, f"Исходное количество LZW-кодов: {len(codes)}\n")
    result_text.insert(tk.END, f"После сжатия (токенов): {len(compressed_str.split())}\n")

    seq_count = len(dictionary)
    single_count = len(compressed_str.split()) - seq_count
    result_text.insert(tk.END, f"Из них диапазонов (символов): {seq_count}\n")
    result_text.insert(tk.END, f"Одиночных чисел: {single_count}\n")

    if len(codes) > 0:
        result_text.insert(tk.END, f"Коэффициент сжатия: {len(codes) / len(compressed_str.split()):.2f}x\n\n")
    else:
        result_text.insert(tk.END, "\n")

    result_text.insert(tk.END, "--- СЛОВАРЬ ---\n")
    result_text.insert(tk.END, f"{'Символ':<10} {'Диапазон':<30} {'Кол-во чисел':<15}\n")
    result_text.insert(tk.END, "-" * 55 + "\n")
    for sym, (start, end) in sorted(dictionary.items(), key=lambda x: x[1][0]):
        count = end - start
        result_text.insert(tk.END, f"{sym:<10} [{start}, {end}){'':<20} {count:<15}\n")

    result_text.insert(tk.END, "\n--- СЖАТЫЙ ТЕКСТ ---\n")
    result_text.insert(tk.END, compressed_str)

    result_text.insert(tk.END, f"\n\n--- ФАЙЛЫ СОХРАНЕНЫ ---\n")
    result_text.insert(tk.END, f"Сжатый текст: {compressed_path}\n")
    result_text.insert(tk.END, f"Словарь:       {dict_path}\n")

    # Проверка: разжимаем обратно и сравниваем
    restored = decompress_ranges_to_lzw(compressed_str, dictionary)
    match = restored == codes
    result_text.insert(tk.END, f"\nПроверка обратного восстановления: {'OK' if match else 'ОШИБКА!'}\n")
    if not match:
        result_text.insert(tk.END, f"  Исходная длина: {len(codes)}, восстановленная: {len(restored)}\n")

    result_text.config(state="disabled")
    setup_clipboard_bindings(result_text)

    messagebox.showinfo(
        "Готово",
        f"Сжатие выполнено.\n\n"
        f"LZW-кодов: {len(codes)}\n"
        f"После сжатия токенов: {len(compressed_str.split())}\n"
        f"Сжато в {len(codes)/len(compressed_str.split()):.1f}x раз\n\n"
        f"Файлы на рабочем столе:\n"
        f"• {os.path.basename(compressed_path)}\n"
        f"• {os.path.basename(dict_path)}"
    )


def decompress_ranges_and_restore():
    """
    Кнопка «Диапазоны → LZW»:
    Читает сжатый текст (с Unicode-символами) из табло
    и восстанавливает полный список LZW-кодов,
    используя словарь unicode_dict (глобальный).
    """
    global unicode_dict

    if not unicode_dict:
        # Пробуем загрузить словарь из файла
        dict_path = filedialog.askopenfilename(
            filetypes=[("Dictionary files", "*dictionary*.txt"), ("Text files", "*.txt"), ("All files", "*.*")],
            title="Выберите файл словаря (LZW_dictionary.txt)",
        )
        if not dict_path:
            return

        try:
            unicode_dict = {}
            with open(dict_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or not line:
                        continue
                    # Формат: символ [начало, конец)
                    match = re.match(r'^(\S+)\s+\[(\d+),\s*(\d+)\)', line)
                    if match:
                        sym = match.group(1)
                        start = int(match.group(2))
                        end = int(match.group(3))
                        unicode_dict[sym] = [start, end]
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать словарь:\n{e}")
            return

        if not unicode_dict:
            messagebox.showerror("Ошибка", "Словарь пуст.")
            return

    txt = text_widget.get("1.0", tk.END).strip()
    if not txt:
        messagebox.showwarning("Пусто", "Нет сжатого текста в табло.")
        return

    try:
        codes = decompress_ranges_to_lzw(txt, unicode_dict)
    except ValueError as e:
        messagebox.showerror("Ошибка восстановления", str(e))
        return

    # Показываем восстановленные коды в табло
    restored_str = " ".join(str(c) for c in codes)
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", restored_str)

    # Сохраняем восстановленный файл на рабочий стол
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    restored_path = os.path.join(desktop, "LZW_restored.txt")
    counter = 1
    while os.path.exists(restored_path):
        restored_path = os.path.join(desktop, f"LZW_restored_{counter}.txt")
        counter += 1

    try:
        with open(restored_path, "w", encoding="utf-8") as f:
            f.write(restored_str)
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось сохранить:\n{e}")
        return

    messagebox.showinfo(
        "Готово",
        f"Восстановлено {len(codes)} LZW-кодов.\n"
        f"Файл сохранён: {restored_path}"
    )


# ============================================================
# LZW-СЖАТИЕ
# ============================================================

def lzw_compress(data, alphabet_size=256):
    """
    Сжимает список байтов (0..255) алгоритмом LZW.
    Возвращает список кодов (целых чисел).
    """
    if not data:
        return []

    dict_size = alphabet_size
    dictionary = {tuple([i]): i for i in range(alphabet_size)}

    result = []
    w = tuple([data[0]])

    for i in range(1, len(data)):
        k = data[i]
        wk = w + (k,)

        if wk in dictionary:
            w = wk
        else:
            result.append(dictionary[w])
            dictionary[wk] = dict_size
            dict_size += 1
            w = (k,)

    if w:
        result.append(dictionary[w])

    return result


def lzw_decompress(codes, alphabet_size=256):
    """
    Декодирует список LZW-кодов обратно в список байтов (0..255).
    """
    if not codes:
        return []

    dict_size = alphabet_size
    dictionary = {i: [i] for i in range(alphabet_size)}

    decoded = []

    prev_code = codes[0]
    if prev_code >= dict_size:
        raise ValueError(f"Некорректный первый код: {prev_code}")
    decoded.extend(dictionary[prev_code])

    for i in range(1, len(codes)):
        code = codes[i]
        prev_entry = dictionary[prev_code]

        if code < dict_size:
            entry = dictionary[code][:]
        elif code == dict_size:
            entry = prev_entry[:]
            entry.append(prev_entry[0])
        else:
            raise ValueError(f"Код {code} вне диапазона словаря (размер={dict_size})")

        decoded.extend(entry)

        new_entry = prev_entry[:]
        new_entry.append(entry[0])
        dictionary[dict_size] = new_entry
        dict_size += 1

        prev_code = code

    return decoded


# ============================================================
# RGB ↔ БАЙТЫ (плоский список) ↔ LZW
# ============================================================

def rgb_to_bytes(arr):
    """
    Преобразует RGB массив (H, W, 3) в плоский список байтов [R,G,B,R,G,B,...].
    """
    h, w = arr.shape[:2]
    pixels = arr.reshape(-1, 3)
    byte_list = []
    for r, g, b in pixels:
        byte_list.extend([int(r), int(g), int(b)])
    return byte_list, (h, w)


def bytes_to_rgb(byte_list, shape):
    """
    Преобразует плоский список байтов [R,G,B,R,G,B,...] в RGB массив (H, W, 3).
    """
    h, w = shape
    expected = h * w * 3
    if len(byte_list) != expected:
        raise ValueError(
            f"Ожидалось {expected} байт для изображения {h}x{w}, "
            f"получено {len(byte_list)} байт."
        )

    pixels = []
    for i in range(0, len(byte_list), 3):
        pixels.append(byte_list[i:i + 3])

    arr = np.array(pixels, dtype=np.uint8).reshape((h, w, 3))
    return arr


def image_to_lzw_and_show():
    """
    Конвертирует загруженное изображение (image_data) в LZW-коды,
    показывает их в текстовом поле и сохраняет в глобальную переменную.
    """
    global image_data, lzw_data, lzw_image_shape

    if image_data is None:
        messagebox.showerror("Ошибка", "Сначала загрузите изображение (кнопка «Загрузить изображение»).")
        return

    byte_list, shape = rgb_to_bytes(image_data)
    codes = lzw_compress(byte_list, alphabet_size=256)

    lzw_data = " ".join(str(c) for c in codes)
    lzw_image_shape = shape

    h, w = shape
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", lzw_data)

    compression_ratio = (len(byte_list) * 8) / (len(codes) * 9) if codes else 0
    messagebox.showinfo(
        "Готово",
        f"Изображение {w}x{h} сжато алгоритмом LZW.\n"
        f"Исходный размер: {len(byte_list)} байт ({len(byte_list) * 8} бит)\n"
        f"LZW-кодов: {len(codes)}\n"
        f"Примерный коэффициент сжатия: {compression_ratio:.2f}x\n"
        f"Коды показаны в табло (через пробел)."
    )


def lzw_to_image_from_text():
    """
    Читает LZW-коды из текстового поля и восстанавливает изображение.
    """
    global lzw_image_shape

    txt = text_widget.get("1.0", tk.END)

    if lzw_image_shape is None:
        messagebox.showerror(
            "Ошибка",
            "Неизвестны размеры изображения. Сначала выполните «RGB → LZW» "
            "с загруженным изображением, либо загрузите LZW из файла с указанием размеров."
        )
        return

    try:
        codes_str = txt.strip()
        codes = [int(x) for x in codes_str.split() if x.strip()]

        byte_list = lzw_decompress(codes, alphabet_size=256)
        arr = bytes_to_rgb(byte_list, lzw_image_shape)
    except (ValueError, IndexError) as e:
        messagebox.showerror("Ошибка восстановления", str(e))
        return

    img = Image.fromarray(arr)

    win = tk.Toplevel(root)
    win.title("Изображение из LZW")
    canvas = tk.Canvas(win, width=img.width, height=img.height)
    canvas.pack()
    photo = ImageTk.PhotoImage(img)
    canvas.create_image(0, 0, anchor=tk.NW, image=photo)
    canvas_img_refs.append(photo)


def save_lzw_to_file():
    """
    Сохраняет LZW-коды в .txt файл.
    """
    global lzw_data

    if lzw_data is not None:
        codes_str = lzw_data
    else:
        codes_str = text_widget.get("1.0", tk.END).strip()

    if not codes_str:
        messagebox.showwarning("Пусто", "Нет LZW-данных для сохранения.")
        return

    file_path = filedialog.asksaveasfilename(
        defaultextension=".txt",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        title="Сохранить LZW-коды как...",
    )
    if not file_path:
        return

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(codes_str)
        messagebox.showinfo("Сохранено", f"Файл сохранён:\n{file_path}")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{e}")


def lzw_to_image_from_file():
    """
    Загружает LZW-коды из .txt файла, восстанавливает изображение,
    сохраняет его на рабочий стол как PNG и показывает в окне.
    """
    global lzw_image_shape

    path = filedialog.askopenfilename(
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        title="Выберите файл с LZW-кодами",
    )
    if not path:
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            codes_str = f.read()
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{e}")
        return

    w_text = simpledialog.askstring("Ширина", "Введите ширину изображения (px):")
    if not w_text:
        return

    h_text = simpledialog.askstring("Высота", "Введите высоту изображения (px):")
    if not h_text:
        return

    try:
        w = int(w_text)
        h = int(h_text)
        if w <= 0 or h <= 0:
            raise ValueError()
    except ValueError:
        messagebox.showerror("Ошибка", "Ширина и высота должны быть положительными целыми числами.")
        return

    shape = (h, w)
    lzw_image_shape = shape

    try:
        codes = [int(x) for x in codes_str.split() if x.strip()]
        byte_list = lzw_decompress(codes, alphabet_size=256)
        arr = bytes_to_rgb(byte_list, shape)
    except (ValueError, IndexError) as e:
        messagebox.showerror("Ошибка восстановления", str(e))
        return

    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", codes_str.strip())

    img = Image.fromarray(arr)

    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    base_name = os.path.splitext(os.path.basename(path))[0]
    save_path = os.path.join(desktop, f"{base_name}_restored_lzw.png")

    counter = 1
    while os.path.exists(save_path):
        save_path = os.path.join(desktop, f"{base_name}_restored_lzw_{counter}.png")
        counter += 1

    try:
        img.save(save_path)
    except Exception as e:
        messagebox.showerror("Ошибка сохранения", f"Не удалось сохранить изображение:\n{e}")
        return

    win = tk.Toplevel(root)
    win.title(f"Изображение из LZW — {os.path.basename(save_path)}")
    canvas = tk.Canvas(win, width=img.width, height=img.height)
    canvas.pack()
    photo = ImageTk.PhotoImage(img)
    canvas.create_image(0, 0, anchor=tk.NW, image=photo)
    canvas_img_refs.append(photo)

    messagebox.showinfo(
        "Готово",
        f"Изображение {w}x{h} восстановлено из LZW-кодов.\n"
        f"Сохранено на рабочий стол:\n{save_path}"
    )


# ============================================================
# ОРИГИНАЛЬНЫЕ ФУНКЦИИ
# ============================================================

def setup_clipboard_bindings(widget):
    """Настроить привязки для копирования/вставки/вырезания и SelectAll."""

    def gen(event_name):
        return lambda e: (widget.event_generate(event_name), "break")

    widget.bind("<Control-c>", gen("<<Copy>>"))
    widget.bind("<Control-x>", gen("<<Cut>>"))
    widget.bind("<Control-v>", gen("<<Paste>>"))
    widget.bind("<Control-a>", lambda e: (widget.tag_add("sel", "1.0", "end"), "break"))

    widget.bind("<Command-c>", gen("<<Copy>>"))
    widget.bind("<Command-x>", gen("<<Cut>>"))
    widget.bind("<Command-v>", gen("<<Paste>>"))
    widget.bind("<Command-a>", lambda e: (widget.tag_add("sel", "1.0", "end"), "break"))

    widget.bind("<Button-1>", lambda e: widget.focus_set())

    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="Копировать", command=lambda: widget.event_generate("<<Copy>>"))
    menu.add_command(label="Вставить", command=lambda: widget.event_generate("<<Paste>>"))
    menu.add_command(label="Вырезать", command=lambda: widget.event_generate("<<Cut>>"))
    menu.add_separator()
    menu.add_command(label="Выделить всё", command=lambda: widget.tag_add("sel", "1.0", "end"))

    def show_menu(event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    widget.bind("<Button-3>", show_menu)
    widget.bind("<Button-2>", show_menu)


def load_image():
    global image_data, current_width, current_height
    path = filedialog.askopenfilename(
        filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.gif"), ("All files", "*.*")]
    )
    if not path:
        return
    try:
        img = Image.open(path).convert("RGB")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось открыть изображение: {e}")
        return

    image_data = np.array(img)
    current_height, current_width = image_data.shape[:2]
    width_var.set(str(current_width))
    height_var.set(str(current_height))

    win = tk.Toplevel(root)
    win.title(f"Изображение — {os.path.basename(path)}")
    canvas = tk.Canvas(win, width=img.width, height=img.height)
    canvas.pack()
    photo = ImageTk.PhotoImage(img)
    canvas.create_image(0, 0, anchor=tk.NW, image=photo)
    canvas_img_refs.append(photo)

    fill_text_from_image(image_data)


def fill_text_from_image(arr):
    h, w = arr.shape[:2]
    total = h * w
    max_cells_warn = 500000
    if total > max_cells_warn:
        if not messagebox.askyesno(
            "Большое изображение",
            f"Изображение содержит {total} пикселей. Это создаст {total} строк в табло и может сильно замедлить интерфейс. Продолжить?",
        ):
            return

    lines = []
    for row in arr:
        for px in row:
            r, g, b = int(px[0]), int(px[1]), int(px[2])
            lines.append(f"{r} {g} {b}")

    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", "\n".join(lines))


def parse_rgb_text(text):
    pixels = []
    for i, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if "," in line:
            parts = [p.strip() for p in line.split(",") if p.strip() != ""]
        else:
            parts = [p for p in line.split() if p != ""]
        if len(parts) != 3:
            raise ValueError(f"Строка {i}: ожидается 3 числа (R G B), найдено {len(parts)}: '{raw_line}'")
        try:
            r, g, b = [int(p) for p in parts]
        except ValueError:
            raise ValueError(f"Строка {i}: неверный формат чисел: '{raw_line}'")
        for v in (r, g, b):
            if v < 0 or v > 255:
                raise ValueError(f"Строка {i}: значение {v} вне диапазона 0-255")
        pixels.append([r, g, b])
    if not pixels:
        raise ValueError("Не найдено ни одного RGB-триплета.")
    return pixels


def open_image_from_text():
    txt = text_widget.get("1.0", tk.END)
    try:
        pixels = parse_rgb_text(txt)
    except ValueError as e:
        messagebox.showerror("Ошибка парсинга", str(e))
        return

    w_text = width_var.get().strip()
    if w_text:
        try:
            w = int(w_text)
            if w <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Ошибка", "Поле ширины должно содержать положительное целое число.")
            return
    else:
        n = len(pixels)
        sq = int(np.sqrt(n))
        if sq * sq == n:
            w = sq
        else:
            messagebox.showinfo(
                "Уточнение",
                "Ширина не указана и длина не является квадратом. Пожалуйста, укажите ширину.",
            )
            return

    if len(pixels) % w != 0:
        messagebox.showerror(
            "Ошибка", f"Количество пикселей ({len(pixels)}) не делится на указанную ширину ({w})."
        )
        return

    arr = np.array(pixels, dtype=np.uint8)
    h = arr.shape[0] // w
    arr = arr.reshape((h, w, 3))
    img = Image.fromarray(arr)

    win = tk.Toplevel(root)
    win.title("Изображение из RGB")
    canvas = tk.Canvas(win, width=img.width, height=img.height)
    canvas.pack()
    photo = ImageTk.PhotoImage(img)
    canvas.create_image(0, 0, anchor=tk.NW, image=photo)
    canvas_img_refs.append(photo)


def clear_text():
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)


def save_text_to_file():
    txt = text_widget.get("1.0", tk.END).strip()
    if not txt:
        messagebox.showwarning("Пусто", "Нечего сохранять — текстовое поле пусто.")
        return

    file_path = filedialog.asksaveasfilename(
        defaultextension=".txt",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        title="Сохранить RGB-данные как...",
    )
    if not file_path:
        return

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(txt)
        messagebox.showinfo("Сохранено", f"Файл сохранён:\n{file_path}")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{e}")


def split_image_to_rgb_lents():
    path = filedialog.askopenfilename(
        filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.gif"), ("All files", "*.*")],
        title="Выберите изображение для разделения на RGB-ленты",
    )
    if not path:
        return

    try:
        img = Image.open(path).convert("RGB")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось открыть изображение: {e}")
        return

    arr = np.array(img)
    img_h, img_w = arr.shape[:2]

    width_str = width_var.get().strip()
    if not width_str:
        messagebox.showerror("Ошибка", "Укажите ширину ленты в поле «Ширина (px)».")
        return

    try:
        lent_width = int(width_str)
        if lent_width <= 0:
            raise ValueError()
    except ValueError:
        messagebox.showerror("Ошибка", "Поле ширины должно содержать положительное целое число.")
        return

    if img_w % lent_width != 0:
        messagebox.showerror(
            "Ошибка",
            f"Ширина изображения ({img_w}) не делится на ширину ленты ({lent_width}) без остатка.\n"
            "Выберите другую ширину ленты.",
        )
        return

    r_values = []
    g_values = []
    b_values = []

    blocks_per_row = img_w // lent_width

    for row_idx in range(img_h):
        for block_idx in range(blocks_per_row):
            start_col = block_idx * lent_width
            end_col = start_col + lent_width
            block = arr[row_idx, start_col:end_col, :]

            for px in block:
                r_values.append(int(px[0]))
                g_values.append(int(px[1]))
                b_values.append(int(px[2]))

    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    save_dir = os.path.join(desktop, "RGB_Lents")
    os.makedirs(save_dir, exist_ok=True)

    filenames = {
        "Lent_1.txt": r_values,
        "Lent_2.txt": g_values,
        "Lent_3.txt": b_values,
    }

    for fname, values in filenames.items():
        full_path = os.path.join(save_dir, fname)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write("\n".join(str(v) for v in values))

    messagebox.showinfo(
        "Готово",
        f"Три текстовых файла сохранены в папку:\n{save_dir}\n\n"
        f"Файлы:\n"
        f" Lent_1.txt — каждый 1-й индекс (R)\n"
        f" Lent_2.txt — каждый 2-й индекс (G)\n"
        f" Lent_3.txt — каждый 3-й индекс (B)\n\n"
        f"Всего значений в каждом файле: {len(r_values)}\n"
        f"Ширина ленты: {lent_width} px",
    )


# --- GUI ---
root = tk.Tk()
root.title("RGB редактор с LZW-сжатием")
root.geometry("1200x750")

top_frame = tk.Frame(root)
top_frame.pack(fill=tk.X, padx=8, pady=6)

# Первая строка кнопок
row1 = tk.Frame(top_frame)
row1.pack(fill=tk.X, pady=(0, 4))

load_btn = tk.Button(row1, text="Загрузить изображение", command=load_image)
load_btn.pack(side=tk.LEFT, padx=(0, 6))

width_label = tk.Label(row1, text="Ширина (px):")
width_label.pack(side=tk.LEFT)
width_var = tk.StringVar()
width_entry = tk.Entry(row1, textvariable=width_var, width=8)
width_entry.pack(side=tk.LEFT, padx=(4, 8))

height_label = tk.Label(row1, text="Высота (px):")
height_label.pack(side=tk.LEFT)
height_var = tk.StringVar()
height_entry = tk.Entry(row1, textvariable=height_var, width=8)
height_entry.pack(side=tk.LEFT, padx=(4, 12))

open_from_text_btn = tk.Button(row1, text="Открыть изображение из RGB", command=open_image_from_text)
open_from_text_btn.pack(side=tk.LEFT, padx=(0, 6))

clear_btn = tk.Button(row1, text="Очистить табло", command=clear_text)
clear_btn.pack(side=tk.LEFT, padx=(0, 6))

save_btn = tk.Button(row1, text="Сохранить RGB как .txt", command=save_text_to_file)
save_btn.pack(side=tk.LEFT, padx=(0, 6))

split_btn = tk.Button(row1, text="Разделить на RGB-ленты", command=split_image_to_rgb_lents)
split_btn.pack(side=tk.LEFT)

# Вторая строка — кнопки LZW
row2 = tk.Frame(top_frame)
row2.pack(fill=tk.X, pady=(4, 0))

lzw_label = tk.Label(row2, text="LZW-операции:", font=("Consolas", 10, "bold"))
lzw_label.pack(side=tk.LEFT, padx=(0, 10))

to_lzw_btn = tk.Button(row2, text="RGB → LZW", command=image_to_lzw_and_show, bg="#d0e8ff")
to_lzw_btn.pack(side=tk.LEFT, padx=(0, 6))

from_lzw_btn = tk.Button(row2, text="LZW → RGB (из табло)", command=lzw_to_image_from_text, bg="#ffd0d0")
from_lzw_btn.pack(side=tk.LEFT, padx=(0, 6))

save_lzw_btn = tk.Button(row2, text="Сохранить LZW как .txt", command=save_lzw_to_file, bg="#d0ffd0")
save_lzw_btn.pack(side=tk.LEFT, padx=(0, 6))

load_lzw_btn = tk.Button(row2, text="LZW из файла → Изображение", command=lzw_to_image_from_file, bg="#ffe0b0")
load_lzw_btn.pack(side=tk.LEFT)

# Третья строка — сжатие диапазонами
row3 = tk.Frame(top_frame)
row3.pack(fill=tk.X, pady=(8, 0))

range_label = tk.Label(row3, text="Сжатие диапазонами:", font=("Consolas", 10, "bold"))
range_label.pack(side=tk.LEFT, padx=(0, 10))

compress_ranges_btn = tk.Button(row3, text="LZW → Сжать диапазонами", command=compress_lzw_and_save, bg="#d0ffe8")
compress_ranges_btn.pack(side=tk.LEFT, padx=(0, 6))

decompress_ranges_btn = tk.Button(row3, text="Диапазоны → LZW", command=decompress_ranges_and_restore, bg="#ffe8d0")
decompress_ranges_btn.pack(side=tk.LEFT)

# Текстовая область
text_frame = tk.Frame(root)
text_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

text_widget = tk.Text(text_frame, wrap=tk.NONE, font=("Consolas", 11))
yscroll = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
xscroll = tk.Scrollbar(text_frame, orient=tk.HORIZONTAL, command=text_widget.xview)
text_widget.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
yscroll.pack(side=tk.RIGHT, fill=tk.Y)
xscroll.pack(side=tk.BOTTOM, fill=tk.X)
text_widget.pack(fill=tk.BOTH, expand=True)

setup_clipboard_bindings(text_widget)

hint = tk.Label(
    root,
    text="Формат RGB: по одному триплету на строку: R G B (или R,G,B). "
    "LZW-режим: коды сжатия через пробел. "
    "Сжатие диапазонами: последовательности (≥2 чисел подряд) заменяются на Unicode-символы. "
    "Словарь сохраняется на рабочий стол.",
    anchor="w",
)
hint.pack(fill=tk.X, padx=8, pady=(0, 8))

root.mainloop()
