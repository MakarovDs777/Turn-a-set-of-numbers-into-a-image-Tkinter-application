import tkinter as tk
from tkinter import filedialog, messagebox
import numpy as np
from PIL import Image, ImageTk
import os

# Глобальные переменные
image_data = None
canvas_img_refs = []  # ссылки на PhotoImage чтобы не удалялись
current_width = None
current_height = None


def setup_clipboard_bindings(widget):
    """Настроить привязки для копирования/вставки/вырезания и SelectAll."""

    def gen(event_name):
        return lambda e: (widget.event_generate(event_name), "break")

    # Windows/Linux: Ctrl
    widget.bind("<Control-c>", gen("<<Copy>>"))
    widget.bind("<Control-x>", gen("<<Cut>>"))
    widget.bind("<Control-v>", gen("<<Paste>>"))
    widget.bind("<Control-a>", lambda e: (widget.tag_add("sel", "1.0", "end"), "break"))

    # macOS: Command
    widget.bind("<Command-c>", gen("<<Copy>>"))
    widget.bind("<Command-x>", gen("<<Cut>>"))
    widget.bind("<Command-v>", gen("<<Paste>>"))
    widget.bind("<Command-a>", lambda e: (widget.tag_add("sel", "1.0", "end"), "break"))

    # При клике — ставим фокус в виджет
    widget.bind("<Button-1>", lambda e: widget.focus_set())

    # Контекстное меню (правый клик)
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

    widget.bind("<Button-3>", show_menu)   # Windows/Linux
    widget.bind("<Button-2>", show_menu)   # для macOS


def load_image():
    """Открывает файл изображения, показывает его и заполняет табло RGB."""
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

    # Показать изображение в новом окне
    win = tk.Toplevel(root)
    win.title(f"Изображение — {path.split('/')[-1]}")
    canvas = tk.Canvas(win, width=img.width, height=img.height)
    canvas.pack()
    photo = ImageTk.PhotoImage(img)
    canvas.create_image(0, 0, anchor=tk.NW, image=photo)
    canvas_img_refs.append(photo)

    # Заполнить текстовое поле RGB-числами (по одному триплету на строку: R G B)
    fill_text_from_image(image_data)


def fill_text_from_image(arr):
    """Заполняет text_widget пикселями из массива arr (h,w,3) — по одному триплету на строку."""
    h, w = arr.shape[:2]

    # Предупреждение для очень больших изображений
    max_cells_warn = 500000  # если больше строк — показываем предупреждение
    total = h * w
    if total > max_cells_warn:
        if not messagebox.askyesno(
            "Большое изображение",
            f"Изображение содержит {total} пикселей. Это создаст {total} строк в табло и может сильно замедлить интерфейс. Продолжить?",
        ):
            return

    # Формируем строки в памяти и вставляем одной операцией (быстрее)
    lines = []

    # Идём в порядке строк (row-major)
    for row in arr:
        for px in row:
            r, g, b = int(px[0]), int(px[1]), int(px[2])
            lines.append(f"{r} {g} {b}")

    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", "\n".join(lines))
    # Оставляем текст доступным для редактирования (state="normal")


def parse_rgb_text(text):
    """Парсит текст с RGB триплетами. Возвращает список [R,G,B] или бросает ValueError."""
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
    """Парсит текст в табло и открывает окно с изображением на его основании."""
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
    """Сохраняет содержимое текстового поля в выбранный файл (.txt)."""
    txt = text_widget.get("1.0", tk.END).strip()
    if not txt:
        messagebox.showwarning("Пусто", "Нечего сохранять — текстовое поле пусто.")
        return

    file_path = filedialog.asksaveasfilename(
        defaultextension=".txt",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        title="Сохранить RGB-данные как...",
    )
    if not file_path:  # пользователь отменил сохранение
        return

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(txt)
        messagebox.showinfo("Сохранено", f"Файл сохранён:\n{file_path}")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{e}")


def split_image_to_rgb_lents():
    """
    Выбирает изображение, нарезает его на ленты указанной ширины (по горизонтали,
    row-major), затем сохраняет на рабочий стол в папку 'RGB_Lents' три .txt файла:
      - Lent_1.txt: каждый 1-й индекс (R) — каждое значение с новой строки
      - Lent_2.txt: каждый 2-й индекс (G) — каждое значение с новой строки
      - Lent_3.txt: каждый 3-й индекс (B) — каждое значение с новой строки

    Порядок обхода пикселей: строка за строкой, слева направо.
    Если ширина ленты меньше ширины изображения — строки режутся на несколько лент,
    которые выкладываются последовательно одна за другой.
    """
    # 1. Выбор файла изображения
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

    arr = np.array(img)  # shape: (H, W, 3)
    img_h, img_w = arr.shape[:2]
    total_pixels = img_h * img_w

    # 2. Запрос ширины ленты
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

    # 3. Нарезаем изображение на ленты и собираем значения по каналам
    # Каждая строка изображения делится на блоки длиной lent_width.
    # Все блоки выкладываются последовательно.
    r_values = []
    g_values = []
    b_values = []

    blocks_per_row = img_w // lent_width

    for row_idx in range(img_h):
        for block_idx in range(blocks_per_row):
            start_col = block_idx * lent_width
            end_col = start_col + lent_width
            block = arr[row_idx, start_col:end_col, :]  # shape: (lent_width, 3)

            for px in block:
                r_values.append(int(px[0]))
                g_values.append(int(px[1]))
                b_values.append(int(px[2]))

    # 4. Сохраняем на рабочем столе в папку RGB_Lents
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
        f"  Lent_1.txt — каждый 1-й индекс (R)\n"
        f"  Lent_2.txt — каждый 2-й индекс (G)\n"
        f"  Lent_3.txt — каждый 3-й индекс (B)\n\n"
        f"Всего значений в каждом файле: {len(r_values)}\n"
        f"Ширина ленты: {lent_width} px",
    )


# --- GUI ---
root = tk.Tk()
root.title("RGB редактор Tkinter")
root.geometry("900x650")

top_frame = tk.Frame(root)
top_frame.pack(fill=tk.X, padx=8, pady=6)

# Кнопка загрузки изображения (показывает и заполняет табло)
load_btn = tk.Button(top_frame, text="Загрузить изображение", command=load_image)
load_btn.pack(side=tk.LEFT, padx=(0, 6))

width_label = tk.Label(top_frame, text="Ширина (px):")
width_label.pack(side=tk.LEFT)
width_var = tk.StringVar()
width_entry = tk.Entry(top_frame, textvariable=width_var, width=8)
width_entry.pack(side=tk.LEFT, padx=(4, 12))

open_from_text_btn = tk.Button(top_frame, text="Открыть изображение из RGB", command=open_image_from_text)
open_from_text_btn.pack(side=tk.LEFT, padx=(0, 6))

clear_btn = tk.Button(top_frame, text="Очистить табло", command=clear_text)
clear_btn.pack(side=tk.LEFT, padx=(0, 6))

# --- Кнопка сохранения ---
save_btn = tk.Button(top_frame, text="Сохранить RGB как .txt", command=save_text_to_file)
save_btn.pack(side=tk.LEFT, padx=(0, 6))

# --- Кнопка разделения на RGB-ленты ---
split_btn = tk.Button(top_frame, text="Разделить на RGB-ленты", command=split_image_to_rgb_lents)
split_btn.pack(side=tk.LEFT)

# Текстовая область для RGB
text_frame = tk.Frame(root)
text_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

text_widget = tk.Text(text_frame, wrap=tk.NONE, font=("Consolas", 11))
yscroll = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
xscroll = tk.Scrollbar(text_frame, orient=tk.HORIZONTAL, command=text_widget.xview)
text_widget.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
yscroll.pack(side=tk.RIGHT, fill=tk.Y)
xscroll.pack(side=tk.BOTTOM, fill=tk.X)
text_widget.pack(fill=tk.BOTH, expand=True)

# Включаем привязки буфера обмена и контекстное меню
setup_clipboard_bindings(text_widget)

# Подсказка внизу
hint = tk.Label(
    root,
    text="Формат: по одному триплету на строку: R G B (или R,G,B). Если поле 'Ширина' пустое, пытаемся подобрать квадрат.",
    anchor="w",
)
hint.pack(fill=tk.X, padx=8, pady=(0, 8))

root.mainloop()
