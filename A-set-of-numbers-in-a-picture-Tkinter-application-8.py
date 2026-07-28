import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import numpy as np
from PIL import Image, ImageTk
import os

# Глобальные переменные
image_data = None
canvas_img_refs = [] # ссылки на PhotoImage чтобы не удалялись
current_width = None
current_height = None

# ---------- НОВОЕ: глобальные переменные для LZW-данных ----------
lzw_data = None # строка кодов через пробел, например "0 1 0 2 5 ..."
lzw_image_shape = None # (height, width) — чтобы знать как собрать обратно


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

    # Инициализация словаря всеми односимвольными строками (0..alphabet_size-1)
    # Ключ — кортеж байтов, значение — код
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
            # Выводим код для w
            result.append(dictionary[w])
            # Добавляем wk в словарь
            dictionary[wk] = dict_size
            dict_size += 1
            # Начинаем новую фразу с k
            w = (k,)

    # Выводим код для последней фразы
    if w:
        result.append(dictionary[w])

    return result


def lzw_decompress(codes, alphabet_size=256):
    """
    Декодирует список LZW-кодов обратно в список байтов (0..255).
    """
    if not codes:
        return []

    # Инициализация словаря всеми односимвольными строками
    dict_size = alphabet_size
    dictionary = {i: [i] for i in range(alphabet_size)}

    decoded = []

    # Первый код
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
            # Особый случай: код равен текущему размеру словаря
            entry = prev_entry[:]
            entry.append(prev_entry[0])
        else:
            raise ValueError(f"Код {code} вне диапазона словаря (размер={dict_size})")

        decoded.extend(entry)

        # Добавляем в словарь: prev_entry + первый байт entry
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
    pixels = arr.reshape(-1, 3) # (N, 3)
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

    # Группируем по 3 (R, G, B)
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

    # Сохраняем в глобальные переменные для обратного преобразования
    lzw_data = " ".join(str(c) for c in codes)
    lzw_image_shape = shape

    # Показываем в текстовом поле
    h, w = shape
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", lzw_data)

    compression_ratio = (len(byte_list) * 8) / (len(codes) * 9) if codes else 0 # ~9 бит на код в среднем
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
        # Парсим коды из текста (через пробел / перенос строки)
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

    # Спрашиваем размеры через диалоговые окна
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

    # Показываем коды в текстовом поле
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", codes_str.strip())

    # Восстанавливаем изображение
    img = Image.fromarray(arr)

    # Сохраняем на рабочий стол
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

    # Показываем в окне
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
# НОВАЯ ФУНКЦИЯ: Разделение LZW-текста на два файла
# ============================================================

def split_lzw_to_two_files():
    """
    Берёт LZW-коды из текстового поля (или глобальной переменной lzw_data),
    разделяет их на два текстовых файла:
      - LZW_part1.txt — все коды с индексами 0, 2, 4, ... (первые числа)
      - LZW_part2.txt — все коды с индексами 1, 3, 5, ... (вторые числа)
    """
    global lzw_data

    # Получаем строку с кодами
    codes_str = text_widget.get("1.0", tk.END).strip()
    if not codes_str and lzw_data:
        codes_str = lzw_data

    if not codes_str:
        messagebox.showwarning("Пусто", "Нет LZW-данных для разделения. "
                                        "Сначала выполните «RGB → LZW» или вставьте коды в табло.")
        return

    # Парсим коды
    try:
        codes = codes_str.split()
        # Проверим, что всё парсится как числа
        [int(x) for x in codes]
    except ValueError:
        messagebox.showerror("Ошибка", "Текст содержит нечисловые значения. "
                                       "Убедитесь, что в табло только LZW-коды (целые числа через пробел).")
        return

    n = len(codes)
    # Разделяем: чётные индексы (0, 2, 4...) и нечётные (1, 3, 5...)
    part1_codes = codes[0::2]  # первые числа
    part2_codes = codes[1::2]  # вторые числа

    # Сохраняем на рабочий стол
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    save_dir = os.path.join(desktop, "LZW_Split")
    os.makedirs(save_dir, exist_ok=True)

    part1_path = os.path.join(save_dir, "LZW_part1.txt")
    part2_path = os.path.join(save_dir, "LZW_part2.txt")

    try:
        with open(part1_path, "w", encoding="utf-8") as f:
            f.write(" ".join(part1_codes))
        with open(part2_path, "w", encoding="utf-8") as f:
            f.write(" ".join(part2_codes))
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось сохранить файлы:\n{e}")
        return

    messagebox.showinfo(
        "Готово — LZW разделён",
        f"Исходный LZW-текст содержит {n} кодов.\n\n"
        f"Файл 1 («первые числа», индексы 0,2,4...):\n"
        f"  {part1_path}\n"
        f"  Кодов: {len(part1_codes)}\n\n"
        f"Файл 2 («вторые числа», индексы 1,3,5...):\n"
        f"  {part2_path}\n"
        f"  Кодов: {len(part2_codes)}\n\n"
        f"Папка: {save_dir}"
    )


# ============================================================
# ОРИГИНАЛЬНЫЕ ФУНКЦИИ (БЕЗ ИЗМЕНЕНИЙ)
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
load_lzw_btn.pack(side=tk.LEFT, padx=(0, 6))

# ---------- НОВАЯ КНОПКА: Разделить LZW на два файла ----------
split_lzw_btn = tk.Button(row2, text="Разделить LZW на 2 файла", command=split_lzw_to_two_files, bg="#e8d0ff")
split_lzw_btn.pack(side=tk.LEFT)

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
    text="Формат: по одному триплету на строку: R G B (или R,G,B). "
    "Если поле 'Ширина' пустое — пытаемся подобрать квадрат. "
    "LZW-режим: коды сжатия через пробел. Алгоритм LZW с алфавитом 256 (байты 0–255).",
    anchor="w",
)
hint.pack(fill=tk.X, padx=8, pady=(0, 8))

root.mainloop()
