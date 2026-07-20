import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import numpy as np
from PIL import Image, ImageTk
import os

# Глобальные переменные
image_data = None
canvas_img_refs = []
current_width = None
current_height = None
lzw_data = None
lzw_image_shape = None


# ============================================================
# LZW-СЖАТИЕ (СОВМЕСТИМОЕ С JS-ДЕКОДЕРОМ: CLEAR=256, EOI=257)
# ============================================================

def lzw_compress(data, alphabet_size=256):
    """
    Сжимает список байтов (0..255) алгоритмом LZW.
    Выходной поток начинается с CLEAR_CODE (256) и заканчивается EOI_CODE (257).
    Новые коды словаря начинаются с 258.
    Максимальный размер словаря: 4096 (12 бит).
    """
    if not data:
        return []

    CLEAR_CODE = alphabet_size       # 256
    EOI_CODE = alphabet_size + 1     # 257
    MAX_TABLE_SIZE = 4096

    dict_size = alphabet_size + 2    # 258
    dictionary = {tuple([i]): i for i in range(alphabet_size)}

    result = [CLEAR_CODE]
    w = tuple([data[0]])

    for i in range(1, len(data)):
        k = data[i]
        wk = w + (k,)

        if wk in dictionary:
            w = wk
        else:
            result.append(dictionary[w])
            if dict_size < MAX_TABLE_SIZE:
                dictionary[wk] = dict_size
                dict_size += 1
            else:
                # Сброс словаря при переполнении
                result.append(CLEAR_CODE)
                dict_size = alphabet_size + 2
                dictionary = {tuple([j]): j for j in range(alphabet_size)}
            w = (k,)

    if w:
        result.append(dictionary[w])

    result.append(EOI_CODE)
    return result


def lzw_decompress(codes, alphabet_size=256):
    """
    Декодирует список LZW-кодов обратно в список байтов.
    Совместим с GIF-подобным форматом: CLEAR=256, EOI=257.
    """
    if not codes:
        return []

    CLEAR_CODE = alphabet_size       # 256
    EOI_CODE = alphabet_size + 1     # 257
    MAX_TABLE_SIZE = 4096

    dict_size = alphabet_size + 2    # 258
    dictionary = {i: [i] for i in range(alphabet_size)}

    decoded = []

    # Ищем первый значащий код после возможного CLEAR
    idx = 0
    if idx < len(codes) and codes[idx] == CLEAR_CODE:
        idx += 1

    if idx >= len(codes) or codes[idx] == EOI_CODE:
        return decoded

    prev_code = codes[idx]
    if prev_code >= alphabet_size:
        raise ValueError(f"Некорректный первый код: {prev_code}")
    decoded.extend(dictionary[prev_code])
    idx += 1

    while idx < len(codes):
        code = codes[idx]
        idx += 1

        if code == EOI_CODE:
            break

        if code == CLEAR_CODE:
            # Сброс словаря
            dict_size = alphabet_size + 2
            dictionary = {i: [i] for i in range(alphabet_size)}
            if idx >= len(codes):
                break
            code = codes[idx]
            idx += 1
            if code == EOI_CODE:
                break
            prev_code = code
            if prev_code < alphabet_size:
                decoded.extend(dictionary[prev_code])
            continue

        if prev_code not in dictionary:
            raise ValueError(f"Предыдущий код {prev_code} отсутствует в словаре")

        prev_entry = dictionary[prev_code]

        if code < dict_size:
            entry = list(dictionary[code])
        elif code == dict_size:
            # Особый случай: код равен текущему размеру словаря (KwKwK)
            entry = prev_entry + [prev_entry[0]]
        else:
            raise ValueError(
                f"Код {code} вне диапазона словаря (размер={dict_size})"
            )

        decoded.extend(entry)

        if dict_size < MAX_TABLE_SIZE:
            dictionary[dict_size] = prev_entry + [entry[0]]
            dict_size += 1

        prev_code = code

    return decoded


# ============================================================
# RGB ↔ БАЙТЫ (плоский список) ↔ LZW
# ============================================================

def rgb_to_bytes(arr):
    h, w = arr.shape[:2]
    pixels = arr.reshape(-1, 3)
    byte_list = []
    for r, g, b in pixels:
        byte_list.extend([int(r), int(g), int(b)])
    return byte_list, (h, w)


def bytes_to_rgb(byte_list, shape):
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


# ============================================================
# RGB-ЛЕНТЫ → LZW-ЛЕНТЫ (БЕЗ ЗАГРУЗКИ ИЗОБРАЖЕНИЯ)
# ============================================================

def rgb_lents_to_lzw():
    """
    Пользователь выбирает ТРИ текстовых файла (R-лента, G-лента, B-лента),
    вводит ширину ленты и размеры изображения.
    Программа сжимает каждую ленту LZW и сохраняет три файла.
    """
    lent_w_text = simpledialog.askstring("Ширина ленты", "Введите ширину ленты (px):")
    if not lent_w_text:
        return
    try:
        lent_width = int(lent_w_text)
        if lent_width <= 0:
            raise ValueError()
    except ValueError:
        messagebox.showerror("Ошибка", "Ширина ленты должна быть положительным целым числом.")
        return

    img_w_text = simpledialog.askstring("Ширина изображения", "Введите ШИРИНУ изображения (px):")
    if not img_w_text:
        return
    try:
        img_w = int(img_w_text)
        if img_w <= 0:
            raise ValueError()
    except ValueError:
        messagebox.showerror("Ошибка", "Ширина изображения должна быть положительным целым числом.")
        return

    img_h_text = simpledialog.askstring("Высота изображения", "Введите ВЫСОТУ изображения (px):")
    if not img_h_text:
        return
    try:
        img_h = int(img_h_text)
        if img_h <= 0:
            raise ValueError()
    except ValueError:
        messagebox.showerror("Ошибка", "Высота изображения должна быть положительным целым числом.")
        return

    if img_w % lent_width != 0:
        messagebox.showerror(
            "Ошибка",
            f"Ширина изображения ({img_w}) не делится на ширину ленты ({lent_width}) без остатка."
        )
        return

    blocks_per_row = img_w // lent_width
    total_blocks = img_h * blocks_per_row
    values_per_lent = total_blocks * lent_width

    messagebox.showinfo(
        "Выберите RGB-ленты",
        "Теперь последовательно выберите ТРИ файла:\n"
        " 1) Lent_1.txt — красная лента (R)\n"
        " 2) Lent_2.txt — зелёная лента (G)\n"
        " 3) Lent_3.txt — синяя лента (B)\n\n"
        f"Ожидается по {values_per_lent} чисел в каждом файле."
    )

    file_r = filedialog.askopenfilename(
        title="Выберите Lent_1.txt (R-лента)",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
    )
    if not file_r:
        return

    file_g = filedialog.askopenfilename(
        title="Выберите Lent_2.txt (G-лента)",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
    )
    if not file_g:
        return

    file_b = filedialog.askopenfilename(
        title="Выберите Lent_3.txt (B-лента)",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
    )
    if not file_b:
        return

    try:
        def read_values(path):
            with open(path, "r", encoding="utf-8") as f:
                return [int(line.strip()) for line in f if line.strip() != ""]

        r_vals = read_values(file_r)
        g_vals = read_values(file_g)
        b_vals = read_values(file_b)
    except Exception as e:
        messagebox.showerror("Ошибка чтения", f"Не удалось прочитать файлы:\n{e}")
        return

    if len(r_vals) != values_per_lent:
        messagebox.showerror(
            "Ошибка",
            f"Файл R-ленты содержит {len(r_vals)} значений, ожидалось {values_per_lent}."
        )
        return
    if len(g_vals) != values_per_lent:
        messagebox.showerror(
            "Ошибка",
            f"Файл G-ленты содержит {len(g_vals)} значений, ожидалось {values_per_lent}."
        )
        return
    if len(b_vals) != values_per_lent:
        messagebox.showerror(
            "Ошибка",
            f"Файл B-ленты содержит {len(b_vals)} значений, ожидалось {values_per_lent}."
        )
        return

    codes_r = lzw_compress(r_vals, alphabet_size=256)
    codes_g = lzw_compress(g_vals, alphabet_size=256)
    codes_b = lzw_compress(b_vals, alphabet_size=256)

    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    save_dir = os.path.join(desktop, "LZW_Lents")
    os.makedirs(save_dir, exist_ok=True)

    lzw_files = {
        "Lent_1_LZW.txt": codes_r,
        "Lent_2_LZW.txt": codes_g,
        "Lent_3_LZW.txt": codes_b,
    }

    for fname, codes in lzw_files.items():
        full_path = os.path.join(save_dir, fname)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(" ".join(str(c) for c in codes))

    orig_bits = values_per_lent * 8
    lzw_bits_r = len(codes_r) * 9
    lzw_bits_g = len(codes_g) * 9
    lzw_bits_b = len(codes_b) * 9

    messagebox.showinfo(
        "Готово — RGB-ленты → LZW-ленты",
        f"LZW-файлы сохранены в:\n{save_dir}\n\n"
        f"─────────────── СТАТИСТИКА ───────────────\n"
        f"Значений в каждой ленте: {values_per_lent}\n"
        f"Исходный размер ленты: {values_per_lent * 8} бит\n\n"
        f" R-лента: {len(codes_r)} LZW-кодов (≈{lzw_bits_r} бит, "
        f"сжатие ≈{values_per_lent * 8 / max(lzw_bits_r, 1):.2f}x)\n"
        f" G-лента: {len(codes_g)} LZW-кодов (≈{lzw_bits_g} бит, "
        f"сжатие ≈{values_per_lent * 8 / max(lzw_bits_g, 1):.2f}x)\n"
        f" B-лента: {len(codes_b)} LZW-кодов (≈{lzw_bits_b} бит, "
        f"сжатие ≈{values_per_lent * 8 / max(lzw_bits_b, 1):.2f}x)\n"
    )


# ============================================================
# LZW-ЛЕНТЫ → RGB-ЛЕНТЫ (ОБРАТНОЕ ПРЕОБРАЗОВАНИЕ)
# ============================================================

def lzw_lents_to_rgb():
    """
    Пользователь выбирает ТРИ LZW-файла,
    программа декодирует их и сохраняет три RGB-файла.
    """
    messagebox.showinfo(
        "Выберите LZW-ленты",
        "Последовательно выберите ТРИ файла:\n"
        " 1) Lent_1_LZW.txt (R)\n"
        " 2) Lent_2_LZW.txt (G)\n"
        " 3) Lent_3_LZW.txt (B)"
    )

    file_r = filedialog.askopenfilename(
        title="Выберите Lent_1_LZW.txt (R-лента)",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
    )
    if not file_r:
        return

    file_g = filedialog.askopenfilename(
        title="Выберите Lent_2_LZW.txt (G-лента)",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
    )
    if not file_g:
        return

    file_b = filedialog.askopenfilename(
        title="Выберите Lent_3_LZW.txt (B-лента)",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
    )
    if not file_b:
        return

    try:
        def read_codes(path):
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            return [int(x) for x in text.split() if x.strip()]

        codes_r = read_codes(file_r)
        codes_g = read_codes(file_g)
        codes_b = read_codes(file_b)
    except Exception as e:
        messagebox.showerror("Ошибка чтения", f"Не удалось прочитать файлы:\n{e}")
        return

    try:
        r_vals = lzw_decompress(codes_r, alphabet_size=256)
        g_vals = lzw_decompress(codes_g, alphabet_size=256)
        b_vals = lzw_decompress(codes_b, alphabet_size=256)
    except ValueError as e:
        messagebox.showerror("Ошибка LZW-декодирования", str(e))
        return

    if not (len(r_vals) == len(g_vals) == len(b_vals)):
        messagebox.showerror(
            "Ошибка",
            f"Длины декодированных лент не совпадают: R={len(r_vals)}, G={len(g_vals)}, B={len(b_vals)}"
        )
        return

    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    save_dir = os.path.join(desktop, "RGB_Lents_Restored")
    os.makedirs(save_dir, exist_ok=True)

    for fname, vals in [("Lent_1.txt", r_vals), ("Lent_2.txt", g_vals), ("Lent_3.txt", b_vals)]:
        full_path = os.path.join(save_dir, fname)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write("\n".join(str(v) for v in vals))

    messagebox.showinfo(
        "Готово — LZW-ленты → RGB-ленты",
        f"RGB-файлы сохранены в:\n{save_dir}\n\n"
        f"Значений в каждой ленте: {len(r_vals)}"
    )


# ============================================================
# ОРИГИНАЛЬНЫЕ ФУНКЦИИ (ИЗОБРАЖЕНИЕ ↔ LZW — ОДНИМ ПОТОКОМ)
# ============================================================

def image_to_lzw_and_show():
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
    global lzw_image_shape
    txt = text_widget.get("1.0", tk.END)
    if lzw_image_shape is None:
        messagebox.showerror("Ошибка", "Неизвестны размеры изображения. Сначала выполните «RGB → LZW» "
                              "с загруженным изображением, либо загрузите LZW из файла с указанием размеров.")
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
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ИНТЕРФЕЙСА
# ============================================================

def setup_clipboard_bindings(widget):
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
            messagebox.showinfo("Уточнение", "Ширина не указана и длина не является квадратом. Пожалуйста, укажите ширину.")
            return
    if len(pixels) % w != 0:
        messagebox.showerror("Ошибка", f"Количество пикселей ({len(pixels)}) не делится на указанную ширину ({w}).")
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
        messagebox.showerror("Ошибка", f"Ширина изображения ({img_w}) не делится на ширину ленты ({lent_width}) без остатка.\nВыберите другую ширину ленты.")
        return
    r_values, g_values, b_values = [], [], []
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
    filenames = {"Lent_1.txt": r_values, "Lent_2.txt": g_values, "Lent_3.txt": b_values}
    for fname, values in filenames.items():
        full_path = os.path.join(save_dir, fname)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write("\n".join(str(v) for v in values))
    messagebox.showinfo(
        "Готово",
        f"Три текстовых файла сохранены в папку:\n{save_dir}\n\n"
        f"Файлы:\n Lent_1.txt — каждый 1-й индекс (R)\n Lent_2.txt — каждый 2-й индекс (G)\n"
        f" Lent_3.txt — каждый 3-й индекс (B)\n\n"
        f"Всего значений в каждом файле: {len(r_values)}\nШирина ленты: {lent_width} px",
    )


# ============================================================
# GUI
# ============================================================

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

# Третья строка — Ленточный режим
row3 = tk.Frame(top_frame)
row3.pack(fill=tk.X, pady=(8, 0))

lents_label = tk.Label(row3, text="Ленточный режим (без загрузки изображения):",
                       font=("Consolas", 10, "bold"))
lents_label.pack(side=tk.LEFT, padx=(0, 10))

rgb_to_lzw_btn = tk.Button(row3, text="RGB-ленты → LZW-ленты",
                           command=rgb_lents_to_lzw, bg="#c8e6ff")
rgb_to_lzw_btn.pack(side=tk.LEFT, padx=(0, 6))

lzw_to_rgb_btn = tk.Button(row3, text="LZW-ленты → RGB-ленты",
                           command=lzw_lents_to_rgb, bg="#ffccbc")
lzw_to_rgb_btn.pack(side=tk.LEFT)

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
    "LZW-режим: коды сжатия через пробел. Алгоритм LZW с алфавитом 256 (байты 0–255), CLEAR=256, EOI=257. "
    "Ленточный режим: RGB-ленты → LZW-ленты без загрузки изображения.",
    anchor="w",
)
hint.pack(fill=tk.X, padx=8, pady=(0, 8))

root.mainloop()
