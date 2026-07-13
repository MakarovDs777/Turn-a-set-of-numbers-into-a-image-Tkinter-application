import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import numpy as np
from PIL import Image, ImageTk
import os

# Глобальные переменные
image_data = None
canvas_img_refs = []  # ссылки на PhotoImage чтобы не удалялись
current_width = None
current_height = None

# ---------- НОВОЕ: глобальная переменная для хранения битовых данных ----------
binary_data = None  # список/строка из '0' и '1'
binary_image_shape = None  # (height, width) — чтобы знать как собрать обратно

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

# ---------- НОВЫЕ ФУНКЦИИ: RGB ↔ БИТЫ ----------

def rgb_to_bits(arr):
    """
    Преобразует RGB массив (H, W, 3) в строку из '0' и '1'.
    Каждый пиксель: R(8 бит) + G(8 бит) + B(8 бит) = 24 бита.
    Порядок: row-major.
    Возвращает (bit_string, shape) где shape = (H, W).
    """
    h, w = arr.shape[:2]
    pixels = arr.reshape(-1, 3)  # (N, 3)

    bits_list = []
    for r, g, b in pixels:
        # Каждый канал — 8 бит, формат: старший бит первым (MSB first)
        for channel in (r, g, b):
            bits_list.append(format(channel, '08b'))  # 'RRRRRRRR'

    bit_string = ''.join(bits_list)
    return bit_string, (h, w)

def bits_to_rgb(bit_string, shape):
    """
    Преобразует строку из '0' и '1' обратно в RGB массив (H, W, 3).
    Каждые 8 бит = 1 байт (значение 0-255).
    Каждые 3 байта = 1 пиксель (R, G, B).
    """
    h, w = shape
    total_pixels = h * w
    expected_bits = total_pixels * 3 * 8  # H*W*3*8

    # Убираем пробелы и переносы, если есть
    bit_string = bit_string.strip()
    bit_string = ''.join(c for c in bit_string if c in '01')

    if len(bit_string) != expected_bits:
        raise ValueError(
            f"Ожидалось {expected_bits} бит для изображения {h}x{w}, "
            f"получено {len(bit_string)} бит."
        )

    pixels = []
    for i in range(0, len(bit_string), 8):
        byte_str = bit_string[i:i + 8]
        pixels.append(int(byte_str, 2))  # 0-255

    # Группируем по 3 (R, G, B)
    rgb_pixels = []
    for i in range(0, len(pixels), 3):
        rgb_pixels.append(pixels[i:i + 3])

    arr = np.array(rgb_pixels, dtype=np.uint8).reshape((h, w, 3))
    return arr

def image_to_binary_and_show():
    """
    Конвертирует загруженное изображение (image_data) в биты,
    показывает их в текстовом поле и сохраняет в глобальную переменную.
    """
    global image_data, binary_data, binary_image_shape

    if image_data is None:
        messagebox.showerror("Ошибка", "Сначала загрузите изображение (кнопка «Загрузить изображение»).")
        return

    bit_string, shape = rgb_to_bits(image_data)

    # Сохраняем в глобальные переменные для обратного преобразования
    binary_data = bit_string
    binary_image_shape = shape

    # Показываем в текстовом поле (группируем по 8 бит для читаемости)
    h, w = shape
    lines = []
    for i in range(0, len(bit_string), 8):
        lines.append(bit_string[i:i + 8])

    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", "\n".join(lines))

    messagebox.showinfo(
        "Готово",
        f"Изображение {w}x{h} преобразовано в биты.\n"
        f"Всего бит: {len(bit_string)}\n"
        f"Бит на пиксель: 24\n"
        f"Байтовые группы показаны в табло."
    )

def binary_to_image_from_text():
    """
    Читает биты из текстового поля и восстанавливает изображение.
    """
    global binary_image_shape

    txt = text_widget.get("1.0", tk.END)

    if binary_image_shape is None:
        # Пытаемся угадать: если пользователь не делал RGB→биты,
        # запрашиваем размеры
        messagebox.showerror(
            "Ошибка",
            "Неизвестны размеры изображения. Сначала выполните «RGB → Биты (0/1)» "
            "с загруженным изображением, либо укажите ширину и проверьте, "
            "что количество бит складывается в целое число пикселей."
        )
        return

    try:
        arr = bits_to_rgb(txt, binary_image_shape)
    except ValueError as e:
        messagebox.showerror("Ошибка восстановления", str(e))
        return

    img = Image.fromarray(arr)

    win = tk.Toplevel(root)
    win.title("Изображение из битов")
    canvas = tk.Canvas(win, width=img.width, height=img.height)
    canvas.pack()
    photo = ImageTk.PhotoImage(img)
    canvas.create_image(0, 0, anchor=tk.NW, image=photo)
    canvas_img_refs.append(photo)

def save_binary_to_file():
    """
    Сохраняет битовые данные (0 и 1) в .txt файл.
    Использует данные из глобальной переменной binary_data,
    либо читает из текстового поля.
    """
    global binary_data

    # Приоритет: глобальная переменная, иначе — текст из поля
    if binary_data is not None:
        bits = binary_data
    else:
        bits = text_widget.get("1.0", tk.END).strip()
        bits = ''.join(c for c in bits if c in '01')

    if not bits:
        messagebox.showwarning("Пусто", "Нет битовых данных для сохранения.")
        return

    file_path = filedialog.asksaveasfilename(
        defaultextension=".txt",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        title="Сохранить биты (0/1) как...",
    )
    if not file_path:
        return

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(bits)
        messagebox.showinfo("Сохранено", f"Файл сохранён:\n{file_path}")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{e}")

def binary_to_image_from_file():
    """
    Загружает биты из .txt файла, восстанавливает изображение,
    сохраняет его на рабочий стол как PNG и показывает в окне.
    """
    global binary_image_shape

    path = filedialog.askopenfilename(
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        title="Выберите файл с битами (0/1)",
    )
    if not path:
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            bit_string = f.read()
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{e}")
        return

    # Спрашиваем размеры через диалоговые окна
    w_text = tk.simpledialog.askstring("Ширина", "Введите ширину изображения (px):")
    if not w_text:
        return

    h_text = tk.simpledialog.askstring("Высота", "Введите высоту изображения (px):")
    if not h_text:
        return

    try:
        w = int(w_text)
        h = int(h_text)
        if w <= 0 or h <= 0:
            raise ValueError()
    except:
        messagebox.showerror("Ошибка", "Ширина и высота должны быть положительными целыми числами.")
        return

    shape = (h, w)
    binary_image_shape = shape

    try:
        arr = bits_to_rgb(bit_string, shape)
    except ValueError as e:
        messagebox.showerror("Ошибка восстановления", str(e))
        return

    # Показываем биты в текстовом поле
    clean_bits = ''.join(c for c in bit_string if c in '01')
    lines = []
    for i in range(0, len(clean_bits), 8):
        lines.append(clean_bits[i:i + 8])
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", "\n".join(lines))

    # Восстанавливаем изображение
    img = Image.fromarray(arr)

    # Сохраняем на рабочий стол
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    base_name = os.path.splitext(os.path.basename(path))[0]  # имя файла без расширения
    save_path = os.path.join(desktop, f"{base_name}_restored.png")

    # Если файл уже существует — добавляем номер
    counter = 1
    while os.path.exists(save_path):
        save_path = os.path.join(desktop, f"{base_name}_restored_{counter}.png")
        counter += 1

    try:
        img.save(save_path)
    except Exception as e:
        messagebox.showerror("Ошибка сохранения", f"Не удалось сохранить изображение:\n{e}")
        return

    # Показываем в окне
    win = tk.Toplevel(root)
    win.title(f"Изображение из битов — {os.path.basename(save_path)}")
    canvas = tk.Canvas(win, width=img.width, height=img.height)
    canvas.pack()
    photo = ImageTk.PhotoImage(img)
    canvas.create_image(0, 0, anchor=tk.NW, image=photo)
    canvas_img_refs.append(photo)

    messagebox.showinfo(
        "Готово",
        f"Изображение {w}x{h} восстановлено из битов.\n"
        f"Сохранено на рабочий стол:\n{save_path}"
    )

# ---------- СУЩЕСТВУЮЩИЕ ФУНКЦИИ (БЕЗ ИЗМЕНЕНИЙ) ----------

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
    win.title(f"Изображение — {path.split('/')[-1]}")
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
        except:
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
        except:
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
    except:
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
root.title("RGB редактор Tkinter")
root.geometry("900x750")

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

# Вторая строка — новые кнопки для битового преобразования
row2 = tk.Frame(top_frame)
row2.pack(fill=tk.X, pady=(4, 0))

bit_label = tk.Label(row2, text="Битовые операции:", font=("Consolas", 10, "bold"))
bit_label.pack(side=tk.LEFT, padx=(0, 10))

to_bits_btn = tk.Button(row2, text="RGB → Биты (0/1)", command=image_to_binary_and_show, bg="#d0e8ff")
to_bits_btn.pack(side=tk.LEFT, padx=(0, 6))

from_bits_btn = tk.Button(row2, text="Биты → RGB (из табло)", command=binary_to_image_from_text, bg="#ffd0d0")
from_bits_btn.pack(side=tk.LEFT, padx=(0, 6))

save_bits_btn = tk.Button(row2, text="Сохранить биты как .txt", command=save_binary_to_file, bg="#d0ffd0")
save_bits_btn.pack(side=tk.LEFT, padx=(0, 6))

load_bits_btn = tk.Button(row2, text="Биты из файла → Изображение", command=binary_to_image_from_file, bg="#ffe0b0")
load_bits_btn.pack(side=tk.LEFT)

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
         "Битовый режим: группы по 8 бит = 1 байт, каждые 3 байта = 1 пиксель.",
    anchor="w",
)
hint.pack(fill=tk.X, padx=8, pady=(0, 8))

root.mainloop()
