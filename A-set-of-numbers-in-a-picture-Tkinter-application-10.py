import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import numpy as np
from PIL import Image, ImageTk
import os
import heapq
from collections import Counter

# Глобальные переменные
image_data = None
canvas_img_refs = []          # ссылки на PhotoImage чтобы не удалялись
current_width = None
current_height = None

# --- LZW-данные ---
lzw_data = None            # строка кодов через пробел, например "0 1 0 2 5 ..."
lzw_image_shape = None     # (height, width) — чтобы знать как собрать обратно

# --- Хаффман-данные ---
huffman_bitstring = None   # последовательность 0/1 после сжатия Хаффмана
huffman_code_map = None    # словарь {байт: код} для декодирования
huffman_image_shape = None # (height, width)


# ============================================================
# КОМПАКТНЫЙ ФОРМАТ LZW (без пробелов) — КОНВЕРТАЦИЯ
# ============================================================

def digit_count_of_number(n):
    """Возвращает количество цифр в целом неотрицательном числе."""
    if n == 0:
        return 1
    return len(str(n))


def codes_to_compact(codes):
    """
    Преобразует список LZW-кодов в компактную строку без пробелов
    с маркерами A(1), B(2), C(3), D(4), ...
    """
    if not codes:
        return ""

    result_parts = []
    i = 0
    while i < len(codes):
        current_digits = digit_count_of_number(codes[i])

        group_codes = []
        while i < len(codes) and digit_count_of_number(codes[i]) == current_digits:
            group_codes.append(codes[i])
            i += 1

        marker_index = current_digits - 1
        if marker_index > 25:
            marker = "Z"
        else:
            marker = chr(ord("A") + marker_index)

        fmt = f"{{:0{current_digits}d}}"
        nums_str = "".join(fmt.format(n) for n in group_codes)

        result_parts.append(marker + nums_str)

    return "".join(result_parts)


def compact_to_codes(compact_str):
    """
    Преобразует компактную строку (с маркерами A/B/C/...) обратно
    в список LZW-кодов.
    """
    if not compact_str:
        return []

    s = "".join(compact_str.split())

    codes = []
    i = 0
    current_width = None

    while i < len(s):
        ch = s[i]

        ch_upper = ch.upper()
        if "A" <= ch_upper <= "Z":
            current_width = ord(ch_upper) - ord("A") + 1
            i += 1
            continue

        if current_width is None:
            raise ValueError(
                f"Компактный формат: ожидался маркер (A-Z) на позиции {i}, "
                f"получен '{ch}'"
            )

        if i + current_width > len(s):
            raise ValueError(
                f"Компактный формат: не хватает цифр для "
                f"{current_width}-значного числа (позиция {i})"
            )

        num_str = s[i:i + current_width]
        codes.append(int(num_str))
        i += current_width

    return codes


def convert_lzw_to_compact():
    txt = text_widget.get("1.0", tk.END).strip()

    if not txt:
        messagebox.showwarning("Пусто", "Текстовое поле пусто. Вставьте LZW-коды через пробел.")
        return

    try:
        codes = [int(x) for x in txt.split() if x.strip()]
    except ValueError:
        messagebox.showerror("Ошибка", "Текст содержит нечисловые данные. Ожидаются LZW-коды (целые числа через пробел).")
        return

    if not codes:
        messagebox.showwarning("Пусто", "Не найдено ни одного кода.")
        return

    compact = codes_to_compact(codes)

    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", compact)

    old_len = len(txt)
    new_len = len(compact)
    ratio = (1 - new_len / old_len) * 100 if old_len > 0 else 0

    messagebox.showinfo(
        "Конвертация завершена",
        f"Кодов: {len(codes)}\n"
        f"Старая длина (с пробелами): {old_len} символов\n"
        f"Новая длина (компактный): {new_len} символов\n"
        f"Экономия: {ratio:.1f}%\n\n"
        f"Маркеры: A=1-значные, B=2-значные, C=3-значные, ..."
    )


def convert_compact_to_lzw():
    txt = text_widget.get("1.0", tk.END).strip()

    if not txt:
        messagebox.showwarning("Пусто", "Текстовое поле пусто. Вставьте компактную LZW-строку.")
        return

    try:
        codes = compact_to_codes(txt)
    except ValueError as e:
        messagebox.showerror("Ошибка формата", str(e))
        return

    lzw_str = " ".join(str(c) for c in codes)

    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", lzw_str)

    messagebox.showinfo(
        "Конвертация завершена",
        f"Кодов: {len(codes)}\n"
        f"Формат: LZW-коды через пробел (стандартный)"
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

    txt = text_widget.get("1.0", tk.END).strip()

    if lzw_image_shape is None:
        messagebox.showerror(
            "Ошибка",
            "Неизвестны размеры изображения. Сначала выполните «RGB → LZW» "
            "с загруженным изображением, либо загрузите LZW из файла с указанием размеров."
        )
        return

    try:
        codes_str = txt

        if " " not in codes_str and any(ch.upper() >= "A" and ch.upper() <= "Z" for ch in codes_str):
            codes = compact_to_codes(codes_str)
        else:
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
        codes_str_clean = codes_str.strip()

        if " " not in codes_str_clean and any(
            ch.upper() >= "A" and ch.upper() <= "Z" for ch in codes_str_clean
        ):
            codes = compact_to_codes(codes_str_clean)
        else:
            codes = [int(x) for x in codes_str_clean.split() if x.strip()]

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
# ХАФФМАН-СЖАТИЕ (портировано с C++/Java алгоритма)
# ============================================================

class HuffmanNode:
    """Узел дерева Хаффмана."""
    __slots__ = ("byte", "freq", "left", "right")

    def __init__(self, byte, freq, left=None, right=None):
        self.byte = byte        # байт (символ) - None для внутренних узлов
        self.freq = freq        # частота
        self.left = left
        self.right = right

    def __lt__(self, other):
        return self.freq < other.freq


def huffman_encode(root, prefix, code_map):
    """
    Обход дерева Хаффмана и построение карты кодов {байт: код}.
    Аналог функции encode() из C++/Java.
    """
    if root is None:
        return

    # листовой узел
    if root.left is None and root.right is None:
        code_map[root.byte] = prefix
        return

    huffman_encode(root.left, prefix + "0", code_map)
    huffman_encode(root.right, prefix + "1", code_map)


def build_huffman_tree(byte_list):
    """
    Строит дерево Хаффмана по списку байтов.
    Возвращает (root, code_map) — корень дерева и карту кодов.
    Аналог buildHuffmanTree() из C++/Java.
    """
    if not byte_list:
        return None, {}

    # подсчёт частоты каждого байта
    freq = Counter(byte_list)

    # приоритетная очередь (куча) — наименьшая частота имеет высший приоритет
    heap = []
    for b, f in freq.items():
        heapq.heappush(heap, HuffmanNode(b, f))

    # случай единственного уникального символа
    if len(heap) == 1:
        node = heap[0]
        root = HuffmanNode(None, node.freq, node, None)
        heap = [root]

    # объединяем узлы, пока не останется один (корень)
    while len(heap) > 1:
        left = heapq.heappop(heap)
        right = heapq.heappop(heap)
        merged = HuffmanNode(None, left.freq + right.freq, left, right)
        heapq.heappush(heap, merged)

    root = heap[0]

    # строим карту кодов
    code_map = {}
    huffman_encode(root, "", code_map)

    return root, code_map


def huffman_compress_bytes(byte_list):
    """
    Сжимает список байтов алгоритмом Хаффмана.
    Возвращает (bitstring, code_map): строку из 0/1 и карту кодов.
    """
    if not byte_list:
        return "", {}

    root, code_map = build_huffman_tree(byte_list)

    parts = []
    for b in byte_list:
        parts.append(code_map[b])

    return "".join(parts), code_map


def huffman_decompress_bytes(bitstring, code_map):
    """
    Декодирует битовую строку обратно в список байтов.
    code_map — карта {байт: код}.
    """
    if not bitstring or not code_map:
        return []

    # обратная карта: код -> байт
    reverse_map = {code: b for b, code in code_map.items()}

    result = []
    current = ""

    for bit in bitstring:
        current += bit
        if current in reverse_map:
            result.append(reverse_map[current])
            current = ""

    if current:
        raise ValueError("Битовая строка некорректна: остались несогласованные биты.")

    return result


def image_to_huffman_and_show():
    """
    Конвертирует загруженное изображение в битовую строку Хаффмана,
    показывает её в текстовом поле и сохраняет в глобальные переменные.
    """
    global image_data, huffman_bitstring, huffman_code_map, huffman_image_shape

    if image_data is None:
        messagebox.showerror("Ошибка", "Сначала загрузите изображение (кнопка «Загрузить изображение»).")
        return

    byte_list, shape = rgb_to_bytes(image_data)
    bitstring, code_map = huffman_compress_bytes(byte_list)

    huffman_bitstring = bitstring
    huffman_code_map = code_map
    huffman_image_shape = shape

    h, w = shape
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", bitstring)

    original_bits = len(byte_list) * 8
    compressed_bits = len(bitstring)
    ratio = original_bits / compressed_bits if compressed_bits > 0 else 0

    messagebox.showinfo(
        "Готово",
        f"Изображение {w}x{h} сжато алгоритмом Хаффмана.\n"
        f"Исходный размер: {original_bits} бит ({len(byte_list)} байт)\n"
        f"Сжатый размер: {compressed_bits} бит\n"
        f"Коэффициент сжатия: {ratio:.2f}x\n"
        f"Уникальных байт (символов): {len(code_map)}\n"
        f"Битовая строка показана в табло."
    )


def huffman_to_image_from_text():
    """
    Читает битовую строку Хаффмана из текстового поля
    и восстанавливает изображение.
    """
    global huffman_code_map, huffman_image_shape

    bitstring = text_widget.get("1.0", tk.END).strip()

    if huffman_code_map is None or huffman_image_shape is None:
        messagebox.showerror(
            "Ошибка",
            "Нет данных о кодах Хаффмана и размерах изображения.\n"
            "Сначала выполните «RGB → Хаффман» с загруженным изображением."
        )
        return

    try:
        byte_list = huffman_decompress_bytes(bitstring, huffman_code_map)
        arr = bytes_to_rgb(byte_list, huffman_image_shape)
    except (ValueError, IndexError) as e:
        messagebox.showerror("Ошибка восстановления", str(e))
        return

    img = Image.fromarray(arr)

    win = tk.Toplevel(root)
    win.title("Изображение из Хаффмана")
    canvas = tk.Canvas(win, width=img.width, height=img.height)
    canvas.pack()
    photo = ImageTk.PhotoImage(img)
    canvas.create_image(0, 0, anchor=tk.NW, image=photo)
    canvas_img_refs.append(photo)


def save_huffman_to_file():
    """
    Сохраняет битовую строку Хаффмана вместе с картой кодов
    и размерами изображения в файл.
    """
    global huffman_bitstring, huffman_code_map, huffman_image_shape

    if huffman_bitstring is not None:
        bitstring = huffman_bitstring
    else:
        bitstring = text_widget.get("1.0", tk.END).strip()

    if not bitstring:
        messagebox.showwarning("Пусто", "Нет данных Хаффмана для сохранения.")
        return

    file_path = filedialog.asksaveasfilename(
        defaultextension=".txt",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        title="Сохранить данные Хаффмана как...",
    )
    if not file_path:
        return

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            # Заголовок
            if huffman_image_shape is not None:
                h, w = huffman_image_shape
                f.write(f"#shape {w} {h}\n")
            if huffman_code_map is not None:
                for b, code in huffman_code_map.items():
                    f.write(f"#code {b} {code}\n")
            f.write(bitstring)
        messagebox.showinfo("Сохранено", f"Файл сохранён:\n{file_path}")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{e}")


def huffman_to_image_from_file():
    """
    Загружает файл с данными Хаффмана (битовая строка + карта кодов + размеры),
    восстанавливает изображение и показывает его.
    """
    global huffman_code_map, huffman_image_shape

    path = filedialog.askopenfilename(
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        title="Выберите файл с данными Хаффмана",
    )
    if not path:
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{e}")
        return

    # Разбор заголовка
    code_map = {}
    shape = None
    bitstring = ""

    lines = content.split("\n")
    for line in lines:
        if line.startswith("#code"):
            parts = line.split()
            b = int(parts[1])
            code = parts[2]
            code_map[b] = code
        elif line.startswith("#shape"):
            parts = line.split()
            w = int(parts[1])
            h = int(parts[2])
            shape = (h, w)
        elif not line.startswith("#"):
            bitstring += line.strip()

    if not code_map or shape is None:
        messagebox.showerror(
            "Ошибка",
            "Файл не содержит полных данных Хаффмана (карту кодов и размеры)."
        )
        return

    huffman_code_map = code_map
    huffman_image_shape = shape

    try:
        byte_list = huffman_decompress_bytes(bitstring, code_map)
        arr = bytes_to_rgb(byte_list, shape)
    except (ValueError, IndexError) as e:
        messagebox.showerror("Ошибка восстановления", str(e))
        return

    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", bitstring)

    img = Image.fromarray(arr)

    win = tk.Toplevel(root)
    win.title(f"Изображение из Хаффмана — {os.path.basename(path)}")
    canvas = tk.Canvas(win, width=img.width, height=img.height)
    canvas.pack()
    photo = ImageTk.PhotoImage(img)
    canvas.create_image(0, 0, anchor=tk.NW, image=photo)
    canvas_img_refs.append(photo)

    h, w = shape
    messagebox.showinfo(
        "Готово",
        f"Изображение {w}x{h} восстановлено из данных Хаффмана."
    )


def show_huffman_codes():
    """
    Показывает таблицу кодов Хаффмана в отдельном окне.
    """
    global huffman_code_map

    if huffman_code_map is None:
        messagebox.showerror("Ошибка", "Сначала выполните «RGB → Хаффман».")
        return

    win = tk.Toplevel(root)
    win.title("Коды Хаффмана")

    text = tk.Text(win, wrap=tk.NONE, font=("Consolas", 11))
    yscroll = tk.Scrollbar(win, orient=tk.VERTICAL, command=text.yview)
    text.configure(yscrollcommand=yscroll.set)
    yscroll.pack(side=tk.RIGHT, fill=tk.Y)
    text.pack(fill=tk.BOTH, expand=True)

    text.insert("1.0", "Байт   Код\n")
    text.insert("end", "-" * 30 + "\n")
    for b in sorted(huffman_code_map.keys()):
        code = huffman_code_map[b]
        text.insert("end", f"{b:3d}    {code}\n")

    text.config(state="disabled")


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
root.title("RGB редактор с LZW и Хаффман сжатием")
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

lzw_label = tk.Label(row2, text="LZW:", font=("Consolas", 10, "bold"))
lzw_label.pack(side=tk.LEFT, padx=(0, 10))

to_lzw_btn = tk.Button(row2, text="RGB → LZW", command=image_to_lzw_and_show, bg="#d0e8ff")
to_lzw_btn.pack(side=tk.LEFT, padx=(0, 6))

from_lzw_btn = tk.Button(row2, text="LZW → RGB (из табло)", command=lzw_to_image_from_text, bg="#ffd0d0")
from_lzw_btn.pack(side=tk.LEFT, padx=(0, 6))

save_lzw_btn = tk.Button(row2, text="Сохранить LZW как .txt", command=save_lzw_to_file, bg="#d0ffd0")
save_lzw_btn.pack(side=tk.LEFT, padx=(0, 6))

load_lzw_btn = tk.Button(row2, text="LZW из файла → Изображение", command=lzw_to_image_from_file, bg="#ffe0b0")
load_lzw_btn.pack(side=tk.LEFT)

# Третья строка — КОМПАКТНЫЙ ФОРМАТ
row3 = tk.Frame(top_frame)
row3.pack(fill=tk.X, pady=(6, 0))

compact_label = tk.Label(row3, text="Компактный:", font=("Consolas", 10, "bold"))
compact_label.pack(side=tk.LEFT, padx=(0, 10))

to_compact_btn = tk.Button(
    row3,
    text="LZW + пробелы → Компакт (A/B/C/...)",
    command=convert_lzw_to_compact,
    bg="#e8d0ff",
)
to_compact_btn.pack(side=tk.LEFT, padx=(0, 6))

from_compact_btn = tk.Button(
    row3,
    text="Компакт (A/B/C/...) → LZW + пробелы",
    command=convert_compact_to_lzw,
    bg="#ffe8d0",
)
from_compact_btn.pack(side=tk.LEFT)

# Четвёртая строка — ХАФФМАН
row4 = tk.Frame(top_frame)
row4.pack(fill=tk.X, pady=(6, 0))

huffman_label = tk.Label(row4, text="Хаффман:", font=("Consolas", 10, "bold"))
huffman_label.pack(side=tk.LEFT, padx=(0, 10))

to_huffman_btn = tk.Button(row4, text="RGB → Хаффман", command=image_to_huffman_and_show, bg="#c8f7c5")
to_huffman_btn.pack(side=tk.LEFT, padx=(0, 6))

from_huffman_btn = tk.Button(row4, text="Хаффман → RGB (из табло)", command=huffman_to_image_from_text, bg="#ffd0d0")
from_huffman_btn.pack(side=tk.LEFT, padx=(0, 6))

save_huffman_btn = tk.Button(row4, text="Сохранить Хаффман как .txt", command=save_huffman_to_file, bg="#d0ffd0")
save_huffman_btn.pack(side=tk.LEFT, padx=(0, 6))

load_huffman_btn = tk.Button(row4, text="Хаффман из файла → Изображение", command=huffman_to_image_from_file, bg="#ffe0b0")
load_huffman_btn.pack(side=tk.LEFT, padx=(0, 6))

show_codes_btn = tk.Button(row4, text="Показать коды", command=show_huffman_codes, bg="#f0f0f0")
show_codes_btn.pack(side=tk.LEFT)

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
    "LZW-режим: коды сжатия через пробел; компактный: A=1-знач., B=2-знач., C=3-знач. "
    "Хаффман: битовая строка 0/1. При восстановлении формат определяется автоматически.",
    anchor="w",
)
hint.pack(fill=tk.X, padx=8, pady=(0, 8))

root.mainloop()
