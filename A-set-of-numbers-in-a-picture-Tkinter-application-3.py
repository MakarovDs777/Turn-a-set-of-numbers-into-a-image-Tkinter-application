import tkinter as tk
from tkinter import filedialog, messagebox

# Глобальная переменная для хранения исходных чисел
raw_numbers = []


def setup_clipboard_bindings(widget):
    """Настроить привязки для копирования/вставки/вырезания и SelectAll."""

    def gen(event_name):
        return lambda e: (widget.event_generate(event_name), "break")

    # Windows/Linux: Ctrl
    widget.bind("<Control-c>", gen("<<Copy>>"))
    widget.bind("<Control-v>", gen("<<Paste>>"))
    widget.bind("<Control-x>", gen("<<Cut>>"))
    widget.bind("<Control-a>", lambda e: (widget.tag_add("sel", "1.0", "end"), "break"))

    # macOS: Command
    widget.bind("<Command-c>", gen("<<Copy>>"))
    widget.bind("<Command-v>", gen("<<Paste>>"))
    widget.bind("<Command-x>", gen("<<Cut>>"))
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

    widget.bind("<Button-3>", show_menu)
    widget.bind("<Control-Button-1>", show_menu)  # для macOS


def parse_numbers_from_file(filepath):
    """
    Читает файл, извлекает все числа, разделённые пробелами/переводами строк.
    Возвращает список целых чисел.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    parts = text.split()
    numbers = []
    for i, p in enumerate(parts, start=1):
        try:
            numbers.append(int(p))
        except ValueError:
            raise ValueError(f"Токен #{i} не является числом: '{p}'")
    return numbers


def find_repeating_sequences(numbers, min_seq_len=2):
    """
    Ищет повторяющиеся подряд последовательности чисел.

    Алгоритм:
    Для каждой возможной длины последовательности (от 1 до len//2)
    пробуем найти повторения, начинающиеся с текущей позиции.

    Возвращает список кортежей: (is_encoded, data)
    - is_encoded=True: ('E', count, sequence_list)
    - is_encoded=False: одиночное число
    """
    result = []
    n = len(numbers)
    i = 0

    while i < n:
        best_len = 0
        best_count = 0

        # Ищем самую длинную повторяющуюся последовательность от позиции i
        # Максимальная длина последовательности: остаток / 2 (нужно минимум 2 повтора)
        max_possible_len = (n - i) // 2
        for seq_len in range(min_seq_len, max_possible_len + 1):
            seq = numbers[i:i + seq_len]
            count = 1
            j = i + seq_len
            while j + seq_len <= n:
                if numbers[j:j + seq_len] == seq:
                    count += 1
                    j += seq_len
                else:
                    break

            if count >= 2:
                # Выбираем лучший вариант: максимизируем общее покрытие (seq_len * count)
                coverage = seq_len * count
                best_coverage = best_len * best_count
                if coverage > best_coverage:
                    best_len = seq_len
                    best_count = count

        if best_len >= min_seq_len and best_count >= 2:
            seq = numbers[i:i + best_len]
            result.append(('E', best_count, seq))
            i += best_len * best_count
        else:
            result.append(('N', numbers[i]))
            i += 1

    return result


def seq_rle_encode(numbers):
    """
    Кодирует список чисел с помощью RLE последовательностей.
    Возвращает список строк в формате:
    - 'E:КОЛИЧЕСТВО:число число ...' для повторяющихся последовательностей
    - 'число' для одиночных чисел
    """
    if not numbers:
        return []

    encoded = find_repeating_sequences(numbers)
    lines = []

    for item in encoded:
        if item[0] == 'E':
            _, count, seq = item
            seq_str = " ".join(str(x) for x in seq)
            lines.append(f"E:{count}:{seq_str}")
        else:
            _, num = item
            lines.append(str(num))

    return lines


def load_and_encode():
    """Открывает файл, парсит числа, выполняет RLE-кодирование и заполняет табло."""
    global raw_numbers

    path = filedialog.askopenfilename(
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
    )
    if not path:
        return

    try:
        numbers = parse_numbers_from_file(path)
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось прочитать файл: {e}")
        return

    if not numbers:
        messagebox.showwarning("Пусто", "Файл не содержит чисел.")
        return

    raw_numbers = numbers

    # RLE-кодирование последовательностей
    encoded_lines = seq_rle_encode(numbers)

    # Вывод в табло
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", "\n".join(encoded_lines))

    # Статистика
    original_chars = len(" ".join(str(n) for n in numbers))
    encoded_chars = len("\n".join(encoded_lines))
    compression_ratio = (1 - encoded_chars / original_chars) * 100 if original_chars > 0 else 0

    status_var.set(
        f"Загружено чисел: {len(numbers)} | Строк вывода: {len(encoded_lines)} | "
        f"Сжатие: {compression_ratio:.1f}%"
    )


def save_text_to_file():
    """Сохраняет содержимое текстового поля в выбранный файл (.txt)."""
    txt = text_widget.get("1.0", tk.END).strip()
    if not txt:
        messagebox.showwarning("Пусто", "Нечего сохранять — текстовое поле пусто.")
        return

    file_path = filedialog.asksaveasfilename(
        defaultextension=".txt",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        title="Сохранить RLE-данные как...",
    )
    if not file_path:
        return

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(txt)
        messagebox.showinfo("Сохранено", f"Файл сохранён:\n{file_path}")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{e}")


def clear_text():
    """Очищает табло."""
    global raw_numbers
    raw_numbers = []
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    status_var.set("Готов")


def decode_rle_to_numbers():
    """
    Декодирует RLE из текстового поля обратно в исходный список чисел
    и показывает в отдельном окне.
    Формат строк:
    - 'E:КОЛИЧЕСТВО:число число ...' — повторяющаяся последовательность
    - 'число' — одиночное число
    """
    txt = text_widget.get("1.0", tk.END).strip()
    if not txt:
        messagebox.showwarning("Пусто", "Табло пусто — нечего декодировать.")
        return

    numbers = []
    for i, raw_line in enumerate(txt.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("E:"):
            # Формат: E:КОЛИЧЕСТВО:последовательность
            rest = line[2:]  # убираем "E:"
            parts = rest.split(":", 1)
            if len(parts) != 2:
                messagebox.showerror(
                    "Ошибка формата",
                    f"Строка {i}: ожидается формат 'E:КОЛИЧЕСТВО:ПОСЛЕДОВАТЕЛЬНОСТЬ', получено: '{raw_line}'",
                )
                return
            try:
                count = int(parts[0])
            except ValueError:
                messagebox.showerror(
                    "Ошибка формата",
                    f"Строка {i}: неверное количество: '{parts[0]}'",
                )
                return

            seq_parts = parts[1].split()
            try:
                seq = [int(x) for x in seq_parts]
            except ValueError:
                messagebox.showerror(
                    "Ошибка формата",
                    f"Строка {i}: неверные числа в последовательности: '{parts[1]}'",
                )
                return

            numbers.extend(seq * count)
        else:
            # Одиночное число
            try:
                numbers.append(int(line))
            except ValueError:
                messagebox.showerror(
                    "Ошибка формата",
                    f"Строка {i}: неверное число: '{line}'",
                )
                return

    # Показываем результат в новом окне
    win = tk.Toplevel(root)
    win.title(f"Декодированные числа ({len(numbers)} шт.)")
    win.geometry("700x500")

    text_frame = tk.Frame(win)
    text_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    out_text = tk.Text(text_frame, wrap=tk.WORD, font=("Consolas", 11))
    yscroll = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=out_text.yview)
    out_text.configure(yscrollcommand=yscroll.set)
    yscroll.pack(side=tk.RIGHT, fill=tk.Y)
    out_text.pack(fill=tk.BOTH, expand=True)

    # Выводим числа через пробел, с переносами для читаемости
    chunk_size = 50
    lines = []
    for i in range(0, len(numbers), chunk_size):
        chunk = numbers[i : i + chunk_size]
        lines.append(" ".join(str(n) for n in chunk))
    out_text.insert("1.0", "\n".join(lines))
    out_text.config(state="disabled")


# --- GUI ---
root = tk.Tk()
root.title("RLE-кодировщик: сжатие повторяющихся последовательностей чисел")
root.geometry("900x650")

# --- Верхняя панель ---
top_frame = tk.Frame(root)
top_frame.pack(fill=tk.X, padx=8, pady=6)

load_btn = tk.Button(
    top_frame, text="Загрузить файл с числами", command=load_and_encode
)
load_btn.pack(side=tk.LEFT, padx=(0, 6))

decode_btn = tk.Button(
    top_frame, text="Декодировать обратно", command=decode_rle_to_numbers
)
decode_btn.pack(side=tk.LEFT, padx=(0, 6))

clear_btn = tk.Button(top_frame, text="Очистить табло", command=clear_text)
clear_btn.pack(side=tk.LEFT, padx=(0, 6))

save_btn = tk.Button(top_frame, text="Сохранить как .txt", command=save_text_to_file)
save_btn.pack(side=tk.LEFT)

# --- Текстовая область для RLE-результата ---
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

# --- Статус-бар ---
status_var = tk.StringVar(value="Готов")
status_bar = tk.Label(
    root,
    textvariable=status_var,
    anchor="w",
    relief=tk.SUNKEN,
    font=("Segoe UI", 10),
)
status_bar.pack(fill=tk.X, padx=0, pady=0)

# --- Подсказка ---
hint = tk.Label(
    root,
    text=(
        "Формат вывода: E:КОЛИЧЕСТВО:ПОСЛЕДОВАТЕЛЬНОСТЬ — для повторяющихся блоков; "
        "одиночные числа — как есть. "
        "Кнопка «Декодировать обратно» восстанавливает исходную последовательность."
    ),
    anchor="w",
    font=("Segoe UI", 9),
)
hint.pack(fill=tk.X, padx=8, pady=(0, 8))

root.mainloop()
