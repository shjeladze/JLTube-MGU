#!/usr/bin/env python3
"""Small laptop client for the fixed read-only Inspector operations."""
import json
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from inspector_connect import OPERATIONS, request, ssh_argv


def main():
    root = tk.Tk()
    root.title('MGU Inspector — მხოლოდ წაკითხვა')
    root.geometry('820x650')
    root.minsize(680, 520)
    body = ttk.Frame(root, padding=20)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text='MGU Inspector', font=('Segoe UI', 22, 'bold')).pack(anchor='w')
    ttk.Label(body, text='ID7 / ID8 • არსებული SSH კავშირი • ავტომატური ატვირთვის გარეშე').pack(anchor='w', pady=(2, 18))
    fields = ttk.Frame(body)
    fields.pack(fill='x')
    host, identity, operation = tk.StringVar(), tk.StringVar(), tk.StringVar(value='report')
    ttk.Label(fields, text='MGU-ს IP ან SSH alias').grid(row=0, column=0, sticky='w', pady=5)
    ttk.Entry(fields, textvariable=host).grid(row=0, column=1, columnspan=2, sticky='ew', padx=(12, 0))
    ttk.Label(fields, text='SSH გასაღების ფაილი (სურვილისამებრ)').grid(row=1, column=0, sticky='w', pady=5)
    ttk.Entry(fields, textvariable=identity).grid(row=1, column=1, sticky='ew', padx=(12, 5))
    def choose():
        path = filedialog.askopenfilename(title='არსებული SSH identity ფაილი')
        if path:
            identity.set(path)
    ttk.Button(fields, text='არჩევა', command=choose).grid(row=1, column=2)
    ttk.Label(fields, text='მონაცემები').grid(row=2, column=0, sticky='w', pady=5)
    ttk.Combobox(fields, textvariable=operation, values=OPERATIONS, state='readonly').grid(row=2, column=1, sticky='ew', padx=(12, 5))
    fields.columnconfigure(1, weight=1)
    status = tk.StringVar(value='მანქანაზე უნდა იყოს დაყენებული Inspector და მოქმედებდეს დადასტურებული SSH კავშირი.')
    ttk.Label(body, textvariable=status, wraplength=750).pack(fill='x', pady=14)
    controls = ttk.Frame(body)
    controls.pack(fill='x')
    text = tk.Text(body, wrap='word', font=('Consolas', 10))
    text.pack(fill='both', expand=True, pady=12)
    events = queue.Queue()
    current = [None]
    def worker(argv, op):
        try:
            report = request(argv)
            if report.get('operation') != op:
                raise ValueError('Operation mismatch')
            events.put(('ok', report))
        except Exception:
            events.put(('error', None))
    def collect():
        try:
            op = operation.get()
            argv = ssh_argv(host.get().strip(), op, identity=identity.get().strip() or None)
        except ValueError:
            messagebox.showerror('მისამართი', 'ჩაწერე სწორი IPv4 მისამართი, hostname ან არსებული SSH alias.')
            return
        current[0] = None
        save.configure(state='disabled')
        collect_button.configure(state='disabled')
        text.delete('1.0', 'end')
        status.set('მონაცემების კითხვა… მანქანის პარამეტრები არ იცვლება.')
        threading.Thread(target=worker, args=(argv, op), daemon=True).start()
    def export():
        if current[0] is None:
            return
        path = filedialog.asksaveasfilename(defaultextension='.json', initialfile='mgu-inspector-report.json', filetypes=[('JSON', '*.json')])
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as stream:
                    json.dump(current[0], stream, indent=2, sort_keys=True)
                    stream.write('\n')
                status.set('ანგარიში შენახულია ლეპტოპზე. ავტომატურად არსად გაგზავნილა.')
            except OSError:
                messagebox.showerror('შენახვა', 'ფაილის შენახვა ვერ მოხერხდა.')
    collect_button = ttk.Button(controls, text='მონაცემების წაკითხვა', command=collect)
    collect_button.pack(side='left')
    save = ttk.Button(controls, text='JSON ანგარიშის შენახვა', state='disabled', command=export)
    save.pack(side='left', padx=10)
    def poll():
        try:
            kind, report = events.get_nowait()
            collect_button.configure(state='normal')
            if kind == 'ok':
                current[0] = report
                text.insert('1.0', json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
                save.configure(state='normal')
                status.set('ანგარიში მიღებულია. ეს შესაძლებლობების სიაა და არა თავსებადობის გარანტია.')
            else:
                status.set('კავშირი ვერ შედგა. შეამოწმე არსებული SSH, host key და მანქანაზე Inspector-ის დაყენება.')
        except queue.Empty:
            pass
        root.after(150, poll)
    root.after(150, poll)
    root.mainloop()


if __name__ == '__main__':
    main()
